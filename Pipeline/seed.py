"""
Pipeline/seed.py
Master orchestrator for the MutationMap data pipeline.

Execution order:
  1. Apply schema.sql  (create tables / indexes if not exist)
  2. ingest_ensembl   — gene coordinates from Ensembl GRCh38
  3. ingest_pharmgkb  — gene–drug–disease from Data/relationships.tsv
  4. ingest_omim      — phenotype-gene map (requires OMIM_API_KEY)
  5. normalize        — category classification + missing ENSG resolution

Usage:
    # Full pipeline (all steps)
    
    python Pipeline/seed.py

    # Skip OMIM if no API key
    python Pipeline/seed.py --skip-omim

    # Re-run only normalization
    python Pipeline/seed.py --only-normalize
"""

import argparse, logging, os, sys, time
import psycopg2
from dotenv import load_dotenv

# ── Make sure imports resolve from project root ───────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Pipeline.etl import ingest_ensembl, ingest_omim, ingest_pharmgkb, normalize

load_dotenv(os.path.join(ROOT, '.env'))
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [seed] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


def apply_schema(db_url: str):
    schema_path = os.path.join(ROOT, 'Pipeline', 'warehouse', 'schema.sql')
    log.info('Applying schema from %s …', schema_path)
    with open(schema_path, encoding='utf-8') as f:
        sql = f.read()
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    conn.close()
    log.info('Schema applied ✓')


def main():
    parser = argparse.ArgumentParser(description='MutationMap data pipeline')
    parser.add_argument('--skip-omim',      action='store_true', help='Skip OMIM ingestion')
    parser.add_argument('--skip-ensembl',   action='store_true', help='Skip Ensembl ingestion')
    parser.add_argument('--skip-pharmgkb',  action='store_true', help='Skip PharmGKB ingestion')
    parser.add_argument('--only-normalize', action='store_true', help='Run normalization only')
    args = parser.parse_args()

    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        log.error('DATABASE_URL not set in .env — aborting')
        sys.exit(1)

    t0 = time.time()
    log.info('═' * 60)
    log.info('MutationMap seed pipeline starting')
    log.info('═' * 60)

    if not args.only_normalize:
        # ── Step 1: Schema ────────────────────────────────────────────────────
        try:
            apply_schema(db_url)
        except Exception as e:
            log.error('Schema failed: %s', e)
            sys.exit(1)

        # ── Step 2: Ensembl genes ─────────────────────────────────────────────
        if not args.skip_ensembl:
            log.info('─' * 40)
            log.info('STEP 2 — Ensembl gene ingestion')
            try:
                n = ingest_ensembl.run()
                log.info('Ensembl done — %d genes upserted', n)
            except Exception as e:
                log.error('Ensembl ingestion failed: %s', e)

        # ── Step 3: PharmGKB ─────────────────────────────────────────────────
        if not args.skip_pharmgkb:
            log.info('─' * 40)
            log.info('STEP 3 — PharmGKB ingestion')
            try:
                n = ingest_pharmgkb.run()
                log.info('PharmGKB done — %d rows inserted', n)
            except Exception as e:
                log.error('PharmGKB ingestion failed: %s', e)

        # ── Step 4: OMIM ─────────────────────────────────────────────────────
        if not args.skip_omim:
            log.info('─' * 40)
            log.info('STEP 4 — OMIM ingestion')
            try:
                nd, ngd = ingest_omim.run()
                log.info('OMIM done — %d diseases, %d gene-disease links', nd, ngd)
            except Exception as e:
                log.error('OMIM ingestion failed: %s', e)
        else:
            log.info('STEP 4 — OMIM skipped (--skip-omim)')

    # ── Step 5: Normalize ─────────────────────────────────────────────────────
    log.info('─' * 40)
    log.info('STEP 5 — Normalization')
    try:
        n = normalize.run()
        log.info('Normalization done — %d category rows written', n)
    except Exception as e:
        log.error('Normalization failed: %s', e)

    elapsed = round(time.time() - t0, 1)
    log.info('═' * 60)
    log.info('Pipeline complete in %ss', elapsed)
    log.info('═' * 60)


if __name__ == '__main__':
    main()
