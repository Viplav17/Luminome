"""
Models/drug_response/train.py
Random Forest classifier: PharmGKB relationships + genotype evidence ->
predicted response class {poor, intermediate, good, adverse}.

Run:
    python Models/drug_response/train.py
"""

import csv
import os
import sys
import time
import logging

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_drug_response_features, DRUG_RESPONSE_FEATURE_NAMES, RESPONSE_CLASSES

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [drug_response] %(message)s')
log = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'drug_response.pkl')
TSV_PATH = os.path.join(ROOT, 'Data', 'relationships.tsv')
GNOMAD_GQL = 'https://gnomad.broadinstitute.org/api'
CHEMBL = 'https://www.ebi.ac.uk/chembl/api/data'


def _parse_list(cell: str, sep: str) -> list[str]:
    return [x.strip() for x in (cell or '').split(sep) if x.strip()]


def _evidence_strength(evidence: list[str]) -> int:
    # 0 strongest (1A equivalent), 5 weakest.
    rank = {
        'ClinicalAnnotation': 0,
        'MultilinkAnnotation': 2,
        'VariantAnnotation': 3,
        'Literature': 4,
        'AutomatedAnnotation': 5,
    }
    vals = [rank[e] for e in evidence if e in rank]
    return min(vals) if vals else 5


def _label_from_assoc(assoc: str, evidence: list[str], pk: str, pd: str) -> int:
    a = (assoc or '').lower()
    has_clin = 'ClinicalAnnotation' in evidence
    has_var = 'VariantAnnotation' in evidence
    if 'associated' in a and 'not associated' not in a:
        if has_clin:
            return 2
        if has_var:
            return 1
        return 1
    if 'ambiguous' in a:
        return 1
    if 'not associated' in a:
        if (pk or '').strip() or (pd or '').strip():
            return 3
        return 0
    return 3


_GNOMAD_Q = '''
query($gene: String!) {
  gene(gene_symbol: $gene, reference_genome: GRCh38) {
    gnomad_constraint { pLI }
  }
}
'''


def _gnomad_pli(symbols: list[str]) -> dict[str, float]:
    out = {}
    for symbol in symbols:
        try:
            r = requests.post(
                GNOMAD_GQL,
                json={'query': _GNOMAD_Q, 'variables': {'gene': symbol}},
                headers={'Content-Type': 'application/json'},
                timeout=20,
            )
            r.raise_for_status()
            c = (r.json().get('data', {}).get('gene') or {}).get('gnomad_constraint') or {}
            out[symbol] = float(c.get('pLI') or 0.5)
        except Exception:
            out[symbol] = 0.5
        time.sleep(0.1)
    return out


def _chembl_max_phase(drug_names: list[str], limit: int = 500) -> dict[str, int]:
    out = {}
    for idx, name in enumerate(drug_names):
        if idx >= limit:
            out[name] = 0
            continue
        try:
            r = requests.get(f'{CHEMBL}/molecule/search.json', params={'q': name, 'limit': 1}, timeout=25)
            r.raise_for_status()
            mols = r.json().get('molecules') or []
            if mols:
                out[name] = int(mols[0].get('max_phase') or 0)
            else:
                out[name] = 0
        except Exception:
            out[name] = 0
        time.sleep(0.08)
    return out


def load_from_tsv() -> pd.DataFrame:
    if not os.path.exists(TSV_PATH):
        raise FileNotFoundError(f'PharmGKB TSV not found: {TSV_PATH}')

    rows = []
    with open(TSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for r in reader:
            if (r.get('Entity1_type') or '').strip() != 'Gene':
                continue
            if (r.get('Entity2_type') or '').strip() != 'Chemical':
                continue

            evidence = _parse_list(r.get('Evidence', ''), ',')
            pmids = _parse_list(r.get('PMIDs', ''), ';')
            assoc = r.get('Association', '')
            pk = r.get('PK', '')
            pd_col = r.get('PD', '')

            pmid_count = len(set(pmids))
            clinical_ct = pmid_count if 'ClinicalAnnotation' in evidence else 0
            variant_ct = pmid_count if 'VariantAnnotation' in evidence else 0

            rows.append(
                {
                    'gene': (r.get('Entity1_name') or '').strip().upper(),
                    'drug': (r.get('Entity2_name') or '').strip(),
                    'evidence_types': evidence,
                    'clinical_annotation_count': min(clinical_ct, 50),
                    'variant_annotation_count': min(variant_ct, 50),
                    'evidence_strength': _evidence_strength(evidence),
                    'pk_evidence': int(bool((pk or '').strip())),
                    'pd_evidence': int(bool((pd_col or '').strip())),
                    'population_diversity': max(1, min(pmid_count, 10)),
                    'label': _label_from_assoc(assoc, evidence, pk, pd_col),
                }
            )

    if not rows:
        raise RuntimeError('No Gene-Chemical rows found in relationships.tsv')

    df = pd.DataFrame(rows)
    log.info('Loaded %d PharmGKB gene-drug rows from TSV', len(df))

    # Real enrichment: gnomAD pLI per gene and ChEMBL max phase per drug.
    genes = sorted([g for g in df['gene'].dropna().unique().tolist() if g])
    drugs = sorted([d for d in df['drug'].dropna().unique().tolist() if d])
    log.info('Enriching %d genes via gnomAD and %d drugs via ChEMBL', len(genes), len(drugs))
    pli_map = _gnomad_pli(genes)
    phase_map = _chembl_max_phase(drugs)
    df['gene_pli'] = df['gene'].map(lambda g: float(pli_map.get(g, 0.5)))
    df['drug_max_phase'] = df['drug'].map(lambda d: int(phase_map.get(d, 0)))
    return df


def load_from_db() -> pd.DataFrame | None:
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    try:
        import psycopg2

        conn = psycopg2.connect(db_url)
        df = pd.read_sql(
            '''
            SELECT
                entity1_name AS gene,
                entity2_name AS drug,
                evidence,
                pmids
            FROM pharmgkb_relations
            WHERE entity1_type = 'Gene'
              AND entity2_type = 'Chemical'
            LIMIT 30000
            ''',
            conn,
        )
        conn.close()
        if len(df) < 100:
            return None

        def _evid(v):
            return v if isinstance(v, list) else []

        df['evidence_types'] = df['evidence'].apply(_evid)
        df['clinical_annotation_count'] = df.apply(
            lambda r: min(len(set(r['pmids'] or [])), 50) if 'ClinicalAnnotation' in r['evidence_types'] else 0,
            axis=1,
        )
        df['variant_annotation_count'] = df.apply(
            lambda r: min(len(set(r['pmids'] or [])), 50) if 'VariantAnnotation' in r['evidence_types'] else 0,
            axis=1,
        )
        df['evidence_strength'] = df['evidence_types'].apply(_evidence_strength)
        df['pk_evidence'] = 0
        df['pd_evidence'] = 0
        df['population_diversity'] = df['pmids'].apply(lambda p: max(1, min(len(set(p or [])), 10)))
        df['label'] = df['evidence_types'].apply(
            lambda ev: 2 if 'ClinicalAnnotation' in ev else (1 if 'VariantAnnotation' in ev else 0)
        )

        genes = sorted([g for g in df['gene'].dropna().astype(str).str.upper().unique().tolist() if g])
        drugs = sorted([d for d in df['drug'].dropna().astype(str).unique().tolist() if d])
        pli_map = _gnomad_pli(genes)
        phase_map = _chembl_max_phase(drugs)
        df['gene'] = df['gene'].astype(str).str.upper()
        df['gene_pli'] = df['gene'].map(lambda g: float(pli_map.get(g, 0.5)))
        df['drug_max_phase'] = df['drug'].map(lambda d: int(phase_map.get(d, 0)))
        log.info('Loaded %d rows from DB pharmgkb_relations', len(df))
        return df
    except Exception as e:
        log.warning('DB load failed: %s', e)
        return None


def build_X(df: pd.DataFrame) -> np.ndarray:
    return np.array([build_drug_response_features(r.to_dict()) for _, r in df.iterrows()], dtype=np.float32)


def train():
    # Primary source is the uploaded real TSV; DB is fallback.
    try:
        df = load_from_tsv()
    except Exception as e:
        log.warning('TSV load failed (%s); falling back to DB', e)
        df = load_from_db()
        if df is None:
            raise RuntimeError('No real PharmGKB data available from TSV or DB')

    X = build_X(df)
    y = df['label'].values.astype(int)

    cv_scores = cross_val_score(
        RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced'),
        X,
        y,
        cv=StratifiedKFold(3),
        scoring='f1_macro',
    )
    log.info('CV F1-macro: %.3f +/- %.3f', cv_scores.mean(), cv_scores.std())

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    model = RandomForestClassifier(
        n_estimators=400,
        max_depth=12,
        min_samples_leaf=5,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1,
    )
    log.info('Training on %d samples', len(X_tr))
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)
    log.info(
        'Evaluation:\n%s',
        classification_report(y_te, pred, labels=[0, 1, 2, 3], target_names=RESPONSE_CLASSES),
    )

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump(
        {
            'model': model,
            'feature_names': DRUG_RESPONSE_FEATURE_NAMES,
            'classes': RESPONSE_CLASSES,
        },
        ARTIFACT,
    )
    log.info('Saved -> %s', ARTIFACT)
    return model


if __name__ == '__main__':
    train()
