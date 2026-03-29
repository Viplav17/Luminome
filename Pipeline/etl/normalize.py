"""
Pipeline/etl/normalize.py
Post-ingestion normalization pass:
  1. Classifies each gene into disease categories (cancer, cardiovascular, …)
     using disease associations already loaded into gene_disease.
  2. Updates genes.type to the highest-scoring category.
  3. Populates gene_category table with confidence scores.
  4. Fills missing ENSG IDs by querying Ensembl for any gene that lacks one.

Run AFTER ingest_ensembl.py, ingest_omim.py, ingest_pharmgkb.py.
Run via seed.py or directly:
    python Pipeline/etl/normalize.py
"""

import os, time, logging
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [normalize] %(message)s')
log = logging.getLogger(__name__)

ENSEMBL_BASE = 'https://rest.ensembl.org'
HEADS        = {'Content-Type': 'application/json', 'Accept': 'application/json'}

# Maps disease name keywords → gene type category
CATEGORY_KEYWORDS = {
    'cancer': [
        'cancer', 'carcinoma', 'tumor', 'tumour', 'leukemia', 'leukaemia',
        'lymphoma', 'sarcoma', 'melanoma', 'glioma', 'adenoma', 'myeloma',
        'neoplasm', 'oncol', 'blastoma',
    ],
    'cardiovascular': [
        'heart', 'cardiac', 'cardiomyopathy', 'arrhythmia', 'atrial',
        'ventricular', 'aortic', 'vascular', 'coronary', 'hypertension',
        'myocardial', 'dilated cardiomyopathy', 'long qt',
    ],
    'neurological': [
        'neurolog', 'brain', 'epilepsy', 'seizure', 'parkinson', 'alzheimer',
        'dementia', 'autism', 'schizophrenia', 'ataxia', 'neuropathy',
        'cerebral', 'intellectual disability', 'psychiatric', 'bipolar',
        'huntington', 'amyotrophic',
    ],
    'metabolic': [
        'diabetes', 'obesity', 'metabolic', 'lipid', 'glycogen', 'mitochondr',
        'thyroid', 'adrenal', 'liver', 'fatty acid', 'insulin', 'glycemia',
        'glycosylation', 'phenylketonuria',
    ],
    'immunological': [
        'immune', 'immunodeficiency', 'autoimmune', 'inflammatory',
        'lupus', 'rheumatoid', 'allergy', 'asthma', 'lymphocyte',
        'neutrophil', 'macrophage', 'interferon', 'complement',
    ],
    'rare': [
        'syndrome', 'dysplasia', 'dystrophy', 'hypoplasia', 'agenesis',
        'aplasia', 'congenital', 'hereditary', 'familial',
    ],
}

CATEGORY_ORDER = [
    'cancer', 'cardiovascular', 'neurological',
    'metabolic', 'immunological', 'rare',
]


def score_disease_name(name: str) -> dict[str, float]:
    n = name.lower()
    scores: dict[str, float] = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in n)
        if hits:
            scores[cat] = round(min(hits / len(kws) * 3, 1.0), 4)
    return scores


def classify_all_genes(conn) -> dict[str, dict[str, float]]:
    """
    Aggregate disease name scores across all gene_disease rows per gene.
    Returns {symbol: {category: cumulative_score}}.
    """
    classification: dict[str, dict[str, float]] = {}
    with conn.cursor() as cur:
        cur.execute('SELECT gene_symbol, disease_name FROM gene_disease')
        for symbol, dname in cur.fetchall():
            scores = score_disease_name(dname or '')
            if symbol not in classification:
                classification[symbol] = {}
            for cat, s in scores.items():
                classification[symbol][cat] = classification[symbol].get(cat, 0) + s
    return classification


def write_gene_categories(conn, classification: dict[str, dict[str, float]]) -> int:
    n = 0
    with conn.cursor() as cur:
        for symbol, scores in classification.items():
            for cat, raw_score in scores.items():
                conf = round(min(raw_score, 1.0), 4)
                cur.execute("""
                    INSERT INTO gene_category (gene_symbol, category, confidence, source)
                    VALUES (%s, %s, %s, 'omim+pharmgkb')
                    ON CONFLICT (gene_symbol, category) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        source     = EXCLUDED.source
                """, (symbol, cat, conf))
                n += 1
    conn.commit()
    return n


def update_gene_types(conn, classification: dict[str, dict[str, float]]) -> int:
    n = 0
    with conn.cursor() as cur:
        for symbol, scores in classification.items():
            if not scores:
                continue
            best = max(scores, key=scores.__getitem__)
            cur.execute(
                "UPDATE genes SET type = %s WHERE symbol = %s AND type = 'other'",
                (best, symbol)
            )
            if cur.rowcount:
                n += 1
    conn.commit()
    return n


def resolve_missing_ensg(conn) -> int:
    """For genes that have no ensg_id, query Ensembl to fill it in."""
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM genes WHERE ensg_id IS NULL LIMIT 500")
        symbols = [r[0] for r in cur.fetchall()]
    if not symbols:
        return 0
    log.info('Resolving %d genes missing ENSG IDs …', len(symbols))
    resolved = 0
    with conn.cursor() as cur:
        for sym in symbols:
            try:
                r = requests.get(
                    f'{ENSEMBL_BASE}/lookup/symbol/homo_sapiens/{sym}',
                    headers=HEADS,
                    params={'content-type': 'application/json'},
                    timeout=10,
                )
                if r.status_code == 200:
                    ensg = r.json().get('id')
                    if ensg:
                        cur.execute(
                            'UPDATE genes SET ensg_id = %s WHERE symbol = %s AND ensg_id IS NULL',
                            (ensg, sym)
                        )
                        resolved += cur.rowcount
                elif r.status_code == 429:
                    time.sleep(int(r.headers.get('Retry-After', 30)))
            except Exception:
                pass
            time.sleep(0.1)
    conn.commit()
    return resolved


def run():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise EnvironmentError('DATABASE_URL not set')

    conn = psycopg2.connect(db_url)

    log.info('Classifying genes by disease associations …')
    classification = classify_all_genes(conn)
    log.info('  %d genes have ≥1 disease association', len(classification))

    n_cats = write_gene_categories(conn, classification)
    log.info('  wrote %d gene_category rows', n_cats)

    n_types = update_gene_types(conn, classification)
    log.info('  updated gene type for %d genes', n_types)

    n_ensg = resolve_missing_ensg(conn)
    log.info('  resolved %d missing ENSG IDs', n_ensg)

    conn.close()
    log.info('Normalization complete')
    return n_cats


if __name__ == '__main__':
    run()
