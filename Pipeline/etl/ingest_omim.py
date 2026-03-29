"""
Pipeline/etl/ingest_omim.py
Fetches OMIM gene-phenotype map (genemap2) and upserts into:
  • diseases table (mim_number, name, category)
  • gene_disease table (gene ↔ disease associations)

Requires OMIM_API_KEY in .env. Apply at: https://www.omim.org/api
Run via seed.py or directly:
    python Pipeline/etl/ingest_omim.py
"""

import os, time, logging
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [omim] %(message)s')
log = logging.getLogger(__name__)

BASE = 'https://api.omim.org/api'

# OMIM phenotype.inheritanceCodes → readable
INHERITANCE_MAP = {
    'AR': 'Autosomal recessive',
    'AD': 'Autosomal dominant',
    'XL': 'X-linked',
    'XLR': 'X-linked recessive',
    'XLD': 'X-linked dominant',
    'MT': 'Mitochondrial',
    'Y':  'Y-linked',
    'SM': 'Somatic mutation',
}

# Keywords in phenotype name → disease category
CATEGORY_KEYWORDS = {
    'cancer': ['cancer', 'carcinoma', 'tumor', 'tumour', 'leukemia', 'lymphoma',
               'sarcoma', 'melanoma', 'glioma', 'adenoma', 'myeloma', 'neoplasm'],
    'cardiovascular': ['heart', 'cardiac', 'cardiomyopathy', 'arrhythmia', 'atrial',
                       'ventricular', 'aortic', 'vascular', 'coronary', 'hypertension'],
    'neurological': ['neurolog', 'brain', 'epilepsy', 'seizure', 'parkinson',
                     'alzheimer', 'dementia', 'autism', 'schizophrenia', 'ataxia',
                     'neuropathy', 'cerebral', 'intellectual disability'],
    'metabolic': ['diabetes', 'obesity', 'metabolic', 'lipid', 'glycogen',
                  'mitochondr', 'thyroid', 'adrenal', 'liver', 'fatty acid'],
    'immunological': ['immune', 'immunodeficiency', 'autoimmune', 'inflammatory',
                      'lupus', 'rheumatoid', 'allergy', 'asthma', 'lymphocyte'],
    'rare': ['syndrome', 'dysplasia', 'dystrophy', 'hypoplasia', 'agenesis'],
}


def classify_disease(name: str) -> str:
    n = name.lower()
    for category, kws in CATEGORY_KEYWORDS.items():
        if any(kw in n for kw in kws):
            return category
    return 'other'


def fetch_genemap2(api_key: str) -> list[dict]:
    """
    Download full genemap2 as JSON.  OMIM returns up to 10 000 entries per call;
    we paginate with start/limit until exhausted.
    """
    all_entries, start, limit = [], 0, 500
    while True:
        params = {
            'apiKey':  api_key,
            'format':  'json',
            'start':   start,
            'limit':   limit,
        }
        try:
            r = requests.get(f'{BASE}/geneMap', params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(60)
                continue
            r.raise_for_status()
        except requests.RequestException as e:
            log.error('OMIM fetch error at start=%d: %s', start, e)
            break
        data = r.json().get('omim', {}).get('listRsp', {})
        entries = data.get('geneMapList', [])
        if not entries:
            break
        all_entries.extend(entries)
        log.info('  fetched %d–%d', start, start + len(entries))
        if len(entries) < limit:
            break
        start += limit
        time.sleep(0.5)
    return all_entries


def parse_entries(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    diseases, gd = [], []
    seen_dis = set()
    for entry in entries:
        gm = entry.get('geneMap', {})
        symbol = (gm.get('approvedSymbol') or gm.get('geneSymbols') or '').split(',')[0].strip().upper()
        if not symbol:
            continue
        for ph_entry in gm.get('phenotypeMapList', []):
            ph = ph_entry.get('phenotypeMap', {})
            mim = str(ph.get('mimNumber', ''))
            name = ph.get('phenotype', '') or ''
            if not mim or not name:
                continue
            cat = classify_disease(name)
            inh = INHERITANCE_MAP.get(ph.get('phenotypeMappingKey', ''), '')
            if mim not in seen_dis:
                seen_dis.add(mim)
                diseases.append({'mim_number': mim, 'name': name[:255],
                                  'category': cat, 'inheritance': inh})
            gd.append({'gene_symbol': symbol, 'disease_key': mim,
                       'disease_name': name[:255], 'score': 1.0, 'source': 'omim'})
    return diseases, gd


def upsert_diseases(conn, rows: list[dict]):
    if not rows:
        return
    sql = """
        INSERT INTO diseases (mim_number, name, category, inheritance)
        VALUES %s
        ON CONFLICT (mim_number) DO UPDATE SET
            name        = EXCLUDED.name,
            category    = EXCLUDED.category,
            inheritance = EXCLUDED.inheritance
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, [
            (r['mim_number'], r['name'], r['category'], r['inheritance'])
            for r in rows
        ])
    conn.commit()


def upsert_gene_disease(conn, rows: list[dict]):
    if not rows:
        return
    # Only insert pairs where the gene already exists in the genes table
    sql = """
        INSERT INTO gene_disease (gene_symbol, disease_key, disease_name, score, source)
        SELECT %s, %s, %s, %s, %s
        WHERE EXISTS (SELECT 1 FROM genes WHERE symbol = %s)
        ON CONFLICT (gene_symbol, disease_key) DO UPDATE SET
            disease_name = EXCLUDED.disease_name,
            score        = EXCLUDED.score,
            source       = EXCLUDED.source
    """
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(sql, (
                r['gene_symbol'], r['disease_key'], r['disease_name'],
                r['score'], r['source'], r['gene_symbol'],
            ))
    conn.commit()


def run():
    api_key = os.environ.get('OMIM_API_KEY')
    db_url  = os.environ.get('DATABASE_URL')
    if not db_url:
        raise EnvironmentError('DATABASE_URL not set')
    if not api_key:
        log.warning('OMIM_API_KEY not set — skipping OMIM ingestion')
        return 0, 0

    conn = psycopg2.connect(db_url)
    log.info('Downloading OMIM genemap2 …')
    entries = fetch_genemap2(api_key)
    log.info('Parsing %d entries …', len(entries))
    diseases, gd = parse_entries(entries)
    upsert_diseases(conn, diseases)
    log.info('Upserted %d diseases', len(diseases))
    upsert_gene_disease(conn, gd)
    log.info('Upserted %d gene-disease links', len(gd))
    conn.close()
    return len(diseases), len(gd)


if __name__ == '__main__':
    run()
