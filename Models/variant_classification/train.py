"""
Models/variant_classification/train.py
Gradient Boosting regressor: ClinVar + Ensembl structural features -> score 0-1

Run:
    python Models/variant_classification/train.py
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
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_variant_features, VARIANT_FEATURE_NAMES

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [variant_class] %(message)s')
log = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'variant_classification.pkl')
NCBI_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
ENSEMBL = 'https://rest.ensembl.org'
GNOMAD_GQL = 'https://gnomad.broadinstitute.org/api'
NCBI_KEY = os.environ.get('NCBI_API_KEY', '')
PER_CLASS = 1200
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
    url = f'{NCBI_BASE}/esummary.fcgi?db=clinvar&id={",".join(ids)}&retmode=json{_kp()}'
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=45)
            r.raise_for_status()
            return r.json().get('result', {})
        except Exception as e:
            log.warning('esummary attempt %d failed: %s', attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return {}


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


_MUTATION_PATTERNS = [
    (r'p\.\w+\*', 'nonsense'),
    (r'del|dup|ins', 'frameshift'),
    (r'splice|splice-site|IVS', 'splice_site'),
    (r'p\.\w+\d+\w+', 'missense'),
    (r'=', 'synonymous'),
    (r'inframe', 'inframe_indel'),
]


def _mutation_type(text: str) -> str:
    for pat, mtype in _MUTATION_PATTERNS:
        if re.search(pat, text or '', re.IGNORECASE):
            return mtype
    return 'other'


def _splicing_distance(text: str) -> int:
    m = re.search(r'[cC]\.\d+[+-](\d+)', text or '')
    if m:
        return min(int(m.group(1)), 1000)
    return 500


def _score_from_significance(sig: str) -> float:
    s = (sig or '').lower()
    if 'pathogenic' in s and 'likely' not in s:
        return 0.95
    if 'likely pathogenic' in s:
        return 0.80
    if 'benign' in s and 'likely' not in s:
        return 0.05
    if 'likely benign' in s:
        return 0.20
    if 'conflicting' in s or 'uncertain' in s:
        return 0.50
    return 0.50


_GNOMAD_QUERY = '''
query($gene: String!) {
  gene(gene_symbol: $gene, reference_genome: GRCh38) {
    gnomad_constraint { pLI oe_mis }
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


_HIGH_CONSEQUENCE = {
    'stop_gained',
    'frameshift_variant',
    'splice_acceptor_variant',
    'splice_donor_variant',
    'start_lost',
}
_MOD_CONSEQUENCE = {'missense_variant', 'inframe_insertion', 'inframe_deletion', 'splice_region_variant'}


def _extract_vep_features(payload: dict) -> dict:
    trans = payload.get('transcript_consequences') or []
    domain_overlap = False
    cadd_score = 0.0
    af_popmax = 0.0
    known = False
    for tr in trans:
        if tr.get('domains'):
            domain_overlap = True
        cons = set(tr.get('consequence_terms') or [])
        if cons & _HIGH_CONSEQUENCE or cons & _MOD_CONSEQUENCE:
            known = True
        cadd = tr.get('cadd_phred')
        if cadd is not None:
            cadd_score = max(cadd_score, float(cadd))
    for cv in payload.get('colocated_variants') or []:
        g_af = cv.get('gnomadg_af')
        if g_af is not None:
            af_popmax = max(af_popmax, float(g_af))
    return {
        'domain_overlap': domain_overlap,
        'repeat_region': False,
        'cadd_score': round(cadd_score, 3),
        'af_popmax': af_popmax,
        'known_functional_impact': known,
    }


def _vep_batch(rsids: list[str]) -> dict[str, dict]:
    out = {}
    if not rsids:
        return out
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    params = {'canonical': 1, 'domains': 1, 'cadd': 1, 'af_gnomadg': 1}
    for i in range(0, len(rsids), 200):
        chunk = rsids[i:i + 200]
        time.sleep(0.5)
        try:
            r = requests.post(
                f'{ENSEMBL}/vep/human/id',
                json={'ids': chunk},
                headers=headers,
                params=params,
                timeout=60,
            )
            if r.status_code == 429:
                wait = int(r.headers.get('Retry-After', 20))
                time.sleep(wait)
                r = requests.post(
                    f'{ENSEMBL}/vep/human/id',
                    json={'ids': chunk},
                    headers=headers,
                    params=params,
                    timeout=60,
                )
            r.raise_for_status()
            for row in r.json():
                vid = row.get('id')
                if vid:
                    out[vid] = _extract_vep_features(row)
        except Exception as e:
            log.warning('VEP batch %d failed: %s', i // 200, e)
    return out


def fetch_from_clinvar() -> pd.DataFrame:
    queries = [
        ('"uncertain significance"[clinsig] OR "conflicting interpretations"[clinsig]', 1200),
        ('benign[clinsig] OR "likely benign"[clinsig]', 1000),
        ('pathogenic[clinsig] OR "likely pathogenic"[clinsig]', 1000),
    ]

    rows = []
    rsid_to_idx = {}
    rsid_re = re.compile(r'\b(rs\d+)\b', re.IGNORECASE)

    for query, retmax in queries:
        ids = _esearch(query, retmax)
        if not ids:
            continue
        log.info('ClinVar query "%s" returned %d IDs', query[:40], len(ids))
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            time.sleep(SLEEP)
            summary = _esummary(chunk)
            for uid in chunk:
                rec = summary.get(uid)
                if not rec:
                    continue

                title = rec.get('title', '')
                hgvs = ''
                for vs in rec.get('variation_set', []):
                    cdna = vs.get('cdna_change', [])
                    if cdna:
                        hgvs = cdna[0]
                        break

                cs = rec.get('clinical_significance', {})
                sig = cs.get('description', '')
                genes = rec.get('genes', [])
                gene_symbol = genes[0].get('symbol', '').upper() if genes else ''
                scvs = rec.get('supporting_submissions', {}).get('scv', [])

                allele_frequency = 0.0
                for af in rec.get('allele_freq_set', []):
                    src = (af.get('source') or '').lower()
                    if 'gnomad' in src or 'exac' in src:
                        try:
                            allele_frequency = float(af.get('value') or 0.0)
                            break
                        except (TypeError, ValueError):
                            pass

                row = {
                    'gene_symbol': gene_symbol,
                    'mutation_type': _mutation_type(title),
                    'conservation_score': 5.0,
                    'allele_frequency': allele_frequency,
                    'submission_count': min(len(scvs) if scvs else 1, 100),
                    'review_status': _review_status(cs.get('review_status', '')),
                    'gene_pli': 0.5,
                    'splicing_distance': _splicing_distance(hgvs or title),
                    'domain_overlap': False,
                    'af_popmax': allele_frequency,
                    'known_functional_impact': False,
                    'repeat_region': False,
                    'cadd_score': 0.0,
                    'label': _score_from_significance(sig),
                }
                rows.append(row)
                idx = len(rows) - 1

                m = rsid_re.search(f'{title} {hgvs}')
                if m:
                    rsid = m.group(1).lower()
                    rsid_to_idx.setdefault(rsid, []).append(idx)

    if not rows:
        raise RuntimeError('No ClinVar data available for variant classification training.')

    df = pd.DataFrame(rows)

    genes = [s for s in df['gene_symbol'].dropna().unique().tolist() if s]
    metrics = _gnomad_metrics(genes)
    for gene, (pli, cons) in metrics.items():
        mask = df['gene_symbol'] == gene
        df.loc[mask, 'gene_pli'] = pli
        df.loc[mask, 'conservation_score'] = cons

    rsids = list(rsid_to_idx.keys())
    log.info('Enriching %d variants with Ensembl VEP', len(rsids))
    vep = _vep_batch(rsids)
    for rsid, idxs in rsid_to_idx.items():
        feat = vep.get(rsid)
        if not feat:
            continue
        for idx in idxs:
            for k, v in feat.items():
                df.at[idx, k] = v

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
                COALESCE(splicing_distance, 500)::int AS splicing_distance,
                COALESCE(domain_overlap, false) AS domain_overlap,
                COALESCE(af_popmax, 0.0)::float AS af_popmax,
                COALESCE(known_functional_impact, false) AS known_functional_impact,
                COALESCE(repeat_region, false) AS repeat_region,
                COALESCE(cadd_score, 0.0)::float AS cadd_score
            FROM variants
            WHERE significance IS NOT NULL
            LIMIT 35000
            ''',
            conn,
        )
        conn.close()
        if len(df) < 200:
            return None
        df['label'] = df['significance'].apply(_score_from_significance).astype(np.float32)
        log.info('Loaded %d variant rows from DB', len(df))
        return df
    except Exception as e:
        log.warning('DB load failed: %s', e)
        return None


def build_X(df: pd.DataFrame) -> np.ndarray:
    return np.array([build_variant_features(r.to_dict()) for _, r in df.iterrows()], dtype=np.float32)


def train():
    df = load_from_db()
    if df is None:
        log.info('DB variant features unavailable; fetching from ClinVar + VEP APIs')
        df = fetch_from_clinvar()

    X = build_X(df)
    y = df['label'].values.astype(np.float32)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    model = GradientBoostingRegressor(
        n_estimators=500,
        learning_rate=0.04,
        max_depth=5,
        subsample=0.8,
        min_samples_leaf=10,
        random_state=42,
    )
    log.info('Training on %d samples', len(X_tr))
    model.fit(X_tr, y_tr)

    preds = np.clip(model.predict(X_te), 0.0, 1.0)
    log.info('MAE=%.4f  R2=%.4f', mean_absolute_error(y_te, preds), r2_score(y_te, preds))

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': VARIANT_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return model


if __name__ == '__main__':
    train()
