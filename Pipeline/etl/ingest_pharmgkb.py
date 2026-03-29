"""
Pipeline/etl/ingest_pharmgkb.py
Parses Data/relationships.tsv (PharmGKB gene–drug–disease relationships)
and upserts into the pharmgkb_relations table.

No API key needed — data is the local TSV file.
Run via seed.py or directly:
    python Pipeline/etl/ingest_pharmgkb.py
"""

import os, csv, logging
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [pharmgkb] %(message)s')
log = logging.getLogger(__name__)

# Path relative to project root
TSV_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'Data', 'relationships.tsv'
)


def parse_tsv(path: str) -> list[dict]:
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for line in reader:
            # PMIDs can be semicolon-separated
            pmids    = [p.strip() for p in (line.get('PMIDs') or '').split(';') if p.strip()]
            evidence = [e.strip() for e in (line.get('Evidence') or '').split(',') if e.strip()]
            rows.append({
                'entity1_id':   line.get('Entity1_id',   '').strip(),
                'entity1_name': line.get('Entity1_name', '').strip(),
                'entity1_type': line.get('Entity1_type', '').strip(),
                'entity2_id':   line.get('Entity2_id',   '').strip(),
                'entity2_name': line.get('Entity2_name', '').strip(),
                'entity2_type': line.get('Entity2_type', '').strip(),
                'evidence':     evidence,
                'pmids':        pmids,
            })
    return rows


def upsert_relations(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    # Truncate and reload — relationships.tsv is the full snapshot
    with conn.cursor() as cur:
        cur.execute('TRUNCATE pharmgkb_relations RESTART IDENTITY')
    sql = """
        INSERT INTO pharmgkb_relations
            (entity1_id, entity1_name, entity1_type,
             entity2_id, entity2_name, entity2_type,
             evidence, pmids)
        VALUES %s
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, [
            (r['entity1_id'], r['entity1_name'], r['entity1_type'],
             r['entity2_id'], r['entity2_name'], r['entity2_type'],
             r['evidence'], r['pmids'])
            for r in rows
        ])
    conn.commit()
    return len(rows)


def backfill_gene_disease(conn) -> int:
    """
    After loading pharmgkb_relations, backfill gene_disease with
    Gene ↔ Disease pairs that have a direct 'associated' evidence.
    """
    sql = """
        INSERT INTO gene_disease (gene_symbol, disease_key, disease_name, score, source)
        SELECT
            UPPER(pr.entity1_name),
            pr.entity2_id,
            pr.entity2_name,
            0.7,
            'pharmgkb'
        FROM pharmgkb_relations pr
        WHERE pr.entity1_type = 'Gene'
          AND pr.entity2_type = 'Disease'
          AND 'ClinicalAnnotation' = ANY(pr.evidence)
          AND EXISTS (SELECT 1 FROM genes g WHERE g.symbol = UPPER(pr.entity1_name))
        ON CONFLICT (gene_symbol, disease_key) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        count = cur.rowcount
    conn.commit()
    return count


def run():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise EnvironmentError('DATABASE_URL not set')

    tsv = os.path.normpath(TSV_PATH)
    if not os.path.exists(tsv):
        log.error('TSV not found at %s', tsv)
        return 0

    log.info('Parsing %s …', tsv)
    rows = parse_tsv(tsv)
    log.info('Parsed %d relationship rows', len(rows))

    conn = psycopg2.connect(db_url)
    n = upsert_relations(conn, rows)
    log.info('Inserted %d pharmgkb_relations', n)
    gd = backfill_gene_disease(conn)
    log.info('Backfilled %d gene-disease links from PharmGKB', gd)
    conn.close()
    return n


if __name__ == '__main__':
    run()
