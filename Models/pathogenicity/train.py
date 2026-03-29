"""
Models/pathogenicity/train.py
LightGBM classifier: real ClinVar variant features -> Harmful / Benign / Uncertain

Labels: 0 = Benign | 1 = Uncertain | 2 = Pathogenic

Data priority:
  1. PostgreSQL variants table (if pipeline/seed.py already populated it)
  2. Live ClinVar API + gnomAD enrichment

Run:
    python Models/pathogenicity/train.py
"""

import os
import re
import sys
import time
import logging

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_pathogenicity_features, PATHOGENICITY_FEATURE_NAMES

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    from sklearn.ensemble import GradientBoostingClassifier
    HAS_LGB = False

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [pathogenicity] %(message)s')
log = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'pathogenicity.pkl')
NCBI_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
GNOMAD_GQL = 'https://gnomad.broadinstitute.org/api'
NCBI_KEY = os.environ.get('NCBI_API_KEY', '')
PER_CLASS = 1500
BATCH = 200
SLEEP = 0.12 if NCBI_KEY else 0.35


def _kp() -> str:
    return f'&api_key={NCBI_KEY}' if NCBI_KEY else ''


def _esearch(query: str, retmax: int) -> list[str]:
    url = (
        f'{NCBI_BASE}/esearch.fcgi?db=clinvar&term={requests.utils.quote(query)}'
        f'&retmax={retmax}&retmode=json{_kp()}'
    )
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json().get('esearchresult', {}).get('idlist', [])
        except Exception as e:
            log.warning('esearch attempt %d failed: %s', attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return []


def _esummary(ids: list[str]) -> dict:
    if not ids:
        return {}
    url = (
        f'{NCBI_BASE}/esummary.fcgi?db=clinvar&id={",".join(ids)}'
        f'&retmode=json{_kp()}'
    )
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=45)
            r.raise_for_status()
            return r.json().get('result', {})
        except Exception as e:
            log.warning('esummary attempt %d failed: %s', attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return {}


_MUTATION_PATTERNS = [
    (r'p\.\w+\*', 'nonsense'),
    (r'del|dup|ins', 'frameshift'),
    (r'splice|splice-site|IVS', 'splice_site'),
    (r'p\.\w+\d+\w+', 'missense'),
    (r'=', 'synonymous'),
    (r'inframe', 'inframe_indel'),
]


def _mutation_type(text: str) -> str:
    for pattern, mtype in _MUTATION_PATTERNS:
        if re.search(pattern, text or '', re.IGNORECASE):
            return mtype
    return 'other'


def _splicing_distance(text: str) -> int:
    m = re.search(r'[cC]\.\d+[+-](\d+)', text or '')
    if m:
        return min(int(m.group(1)), 1000)
    return 500


def _review_status(raw: str) -> str:
    s = (raw or '').lower()
    if 'practice guideline' in s:
        return 'practice_guideline'
    if 'expert panel' in s:
        return 'expert_panel'
    if 'multiple submitter' in s:
        return 'multiple_submitters'
    if 'criteria provided' in s:
        return 'single_submitter'
    return 'no_criteria'


_GNOMAD_QUERY = '''
query($gene: String!) {
  gene(gene_symbol: $gene, reference_genome: GRCh38) {
    gnomad_constraint {
      pLI
      oe_mis
    }
  }
}
'''


def _gnomad_metrics(symbols: list[str]) -> dict[str, tuple[float, float]]:
    out = {}
    for symbol in symbols:
        time.sleep(SLEEP)
        try:
            r = requests.post(
                GNOMAD_GQL,
                json={'query': _GNOMAD_QUERY, 'variables': {'gene': symbol}},
                headers={'Content-Type': 'application/json'},
                timeout=20,
            )
            r.raise_for_status()
            c = (r.json().get('data', {}).get('gene') or {}).get('gnomad_constraint') or {}
            pli = float(c['pLI']) if c.get('pLI') is not None else 0.5
            oe_mis = float(c['oe_mis']) if c.get('oe_mis') is not None else 0.5
            conservation = max(0.0, min(10.0, (1.0 - oe_mis) * 10.0))
            out[symbol] = (round(pli, 4), round(conservation, 4))
        except Exception:
            out[symbol] = (0.5, 5.0)
    return out


def fetch_from_clinvar() -> pd.DataFrame:
    queries = [
        ('benign[clinsig] OR "likely benign"[clinsig]', 0),
        ('"uncertain significance"[clinsig] OR "conflicting interpretations"[clinsig]', 1),
        ('pathogenic[clinsig] OR "likely pathogenic"[clinsig]', 2),
    ]

    rows = []
    for query, label in queries:
        ids = _esearch(query, PER_CLASS)
        if not ids:
            continue
        log.info('ClinVar query label=%d returned %d IDs', label, len(ids))
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            time.sleep(SLEEP)
            result = _esummary(chunk)
            for uid in chunk:
                rec = result.get(uid)
                if not rec:
                    continue
                title = rec.get('title', '')
                hgvs = ''
                for vs in rec.get('variation_set', []):
                    cdna = vs.get('cdna_change', [])
                    if cdna:
                        hgvs = cdna[0]
                        break

                allele_frequency = 0.0
                for af in rec.get('allele_freq_set', []):
                    src = (af.get('source') or '').lower()
                    if 'gnomad' in src or 'exac' in src:
                        try:
                            allele_frequency = float(af.get('value') or 0.0)
                            break
                        except (TypeError, ValueError):
                            pass

                genes = rec.get('genes', [])
                gene_symbol = genes[0].get('symbol', '').upper() if genes else ''
                cs = rec.get('clinical_significance', {})
                scvs = rec.get('supporting_submissions', {}).get('scv', [])

                rows.append({
                    'gene_symbol': gene_symbol,
                    'mutation_type': _mutation_type(title),
                    'conservation_score': 5.0,
                    'allele_frequency': allele_frequency,
                    'submission_count': min(len(scvs) if scvs else 1, 100),
                    'review_status': _review_status(cs.get('review_status', '')),
                    'gene_pli': 0.5,
                    'splicing_distance': _splicing_distance(hgvs or title),
                    'label': label,
                })

    if not rows:
        raise RuntimeError('No ClinVar data retrieved from API.')

    df = pd.DataFrame(rows)
    genes = [s for s in df['gene_symbol'].dropna().unique().tolist() if s]
    log.info('Enriching %d unique genes with gnomAD metrics', len(genes))
    metrics = _gnomad_metrics(genes)
    for gene, (pli, conservation) in metrics.items():
        mask = df['gene_symbol'] == gene
        df.loc[mask, 'gene_pli'] = pli
        df.loc[mask, 'conservation_score'] = conservation
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
                significance,
                COALESCE(mutation_type, 'other') AS mutation_type,
                COALESCE(conservation_score, 5.0)::float AS conservation_score,
                COALESCE(allele_frequency, 0.0)::float AS allele_frequency,
                COALESCE(submission_count, 1)::int AS submission_count,
                COALESCE(review_status, 'no_criteria') AS review_status,
                COALESCE(gene_pli, 0.5)::float AS gene_pli,
                COALESCE(splicing_distance, 500)::int AS splicing_distance
            FROM variants
            WHERE significance IS NOT NULL
            LIMIT 30000
            ''',
            conn,
        )
        conn.close()
        if df.empty:
            return None

        sig_map = {
            'benign': 0,
            'likely benign': 0,
            'uncertain significance': 1,
            'conflicting interpretations': 1,
            'conflicting': 1,
            'pathogenic': 2,
            'likely pathogenic': 2,
        }
        df['label'] = df['significance'].str.lower().map(sig_map)
        df = df.dropna(subset=['label'])
        if len(df) < 100:
            return None
        df['label'] = df['label'].astype(int)
        log.info('Loaded %d rows from DB variants table', len(df))
        return df
    except Exception as e:
        log.warning('DB load failed: %s', e)
        return None


def build_X(df: pd.DataFrame) -> np.ndarray:
    rows = []
    for _, r in df.iterrows():
        rows.append(
            build_pathogenicity_features(
                {
                    'mutation_type': r['mutation_type'],
                    'conservation_score': r['conservation_score'],
                    'allele_frequency': r['allele_frequency'],
                    'submission_count': r['submission_count'],
                    'review_status': r['review_status'],
                    'gene_pli': r['gene_pli'],
                    'splicing_distance': r['splicing_distance'],
                }
            )
        )
    return np.array(rows, dtype=np.float32)


def train():
    df = load_from_db()
    if df is None:
        log.info('DB not ready for variants; fetching from live ClinVar APIs')
        df = fetch_from_clinvar()

    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    X = build_X(df)
    y = df['label'].values

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    if HAS_LGB:
        model = lgb.LGBMClassifier(
            n_estimators=400,
            learning_rate=0.05,
            num_leaves=31,
            max_depth=6,
            class_weight='balanced',
            random_state=42,
            verbose=-1,
        )
    else:
        model = GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)

    log.info('Training on %d samples', len(X_tr))
    model.fit(X_tr, y_tr)

    preds = model.predict(X_te)
    log.info(
        'Evaluation:\n%s',
        classification_report(y_te, preds, target_names=['benign', 'uncertain', 'pathogenic']),
    )

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': PATHOGENICITY_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return model


if __name__ == '__main__':
    train()
