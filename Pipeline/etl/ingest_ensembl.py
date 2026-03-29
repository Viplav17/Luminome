"""
Pipeline/etl/ingest_ensembl.py
Fetches all protein-coding and cancer/disease-linked genes from Ensembl REST API
(GRCh38) chromosome-by-chromosome and upserts into the genes table.

Run via seed.py or directly:
    python Pipeline/etl/ingest_ensembl.py
"""

import os, time, logging
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [ensembl] %(message)s')
log = logging.getLogger(__name__)

BASE   = 'https://rest.ensembl.org'
HEADS  = {'Content-Type': 'application/json', 'Accept': 'application/json'}

# GRCh38 chromosome lengths in Mb (used to compute pos_frac 0–1)
CHR_LEN_MB = {
    '1':249,'2':242,'3':198,'4':190,'5':181,'6':171,'7':159,'8':145,
    '9':138,'10':133,'11':135,'12':133,'13':114,'14':107,'15':102,'16':90,
    '17':83,'18':80,'19':59,'20':63,'21':47,'22':51,'X':155,'Y':59,
}

CHROMS = [str(i) for i in range(1, 23)] + ['X', 'Y']

# Only pull these biotypes to keep the table focused
WANTED_BIOTYPES = {
    'protein_coding', 'lncRNA', 'miRNA', 'snRNA', 'snoRNA',
    'rRNA', 'pseudogene', 'polymorphic_pseudogene',
}


def fetch_genes_on_chr(chr_name: str) -> list[dict]:
    length_bp = CHR_LEN_MB.get(chr_name, 150) * 1_000_000
    region    = f'{chr_name}:1-{length_bp}'
    url       = f'{BASE}/overlap/region/homo_sapiens/{region}'
    params    = {'feature': 'gene', 'content-type': 'application/json'}
    retries   = 3
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADS, params=params, timeout=60)
            if r.status_code == 429:
                wait = int(r.headers.get('Retry-After', 30))
                log.warning('Rate limited — sleeping %ss', wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log.warning('Attempt %d failed for chr%s: %s', attempt + 1, chr_name, e)
            time.sleep(5 * (attempt + 1))
    return []


def ensg_to_symbol(ensg_id: str) -> str | None:
    try:
        r = requests.get(
            f'{BASE}/lookup/id/{ensg_id}',
            headers=HEADS,
            params={'content-type': 'application/json'},
            timeout=15,
        )
        if r.status_code == 200:
            d = r.json()
            return d.get('display_name') or d.get('id')
    except Exception:
        pass
    return None


def build_row(g: dict, chr_name: str) -> dict | None:
    biotype = g.get('biotype', '')
    if biotype not in WANTED_BIOTYPES:
        return None
    ensg    = g.get('id', '')
    symbol  = g.get('external_name') or ensg_to_symbol(ensg) or ensg
    if not symbol or not ensg:
        return None
    start   = g.get('start', 0)
    end     = g.get('end',   0)
    len_bp  = CHR_LEN_MB.get(chr_name, 150) * 1_000_000
    mid     = (start + end) / 2
    pos     = round(mid / len_bp, 6)
    strand  = 1 if g.get('strand', 1) > 0 else -1
    desc    = (g.get('description') or '').split(' [')[0]  # strip source suffix
    return {
        'symbol':      symbol.upper(),
        'ensg_id':     ensg,
        'chr':         chr_name,
        'pos_frac':    min(max(pos, 0.0), 1.0),
        'type':        'other',        # normalize.py assigns real categories later
        'loc':         f"{chr_name}{'q' if strand == 1 else 'p'}",
        'description': desc,
        'biotype':     biotype,
        'strand':      strand,
        'bp_start':    start,
        'bp_end':      end,
    }


def upsert_genes(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO genes
            (symbol, ensg_id, chr, pos_frac, type, loc, description, biotype,
             strand, bp_start, bp_end, updated_at)
        VALUES %s
        ON CONFLICT (symbol) DO UPDATE SET
            ensg_id     = EXCLUDED.ensg_id,
            chr         = EXCLUDED.chr,
            pos_frac    = EXCLUDED.pos_frac,
            loc         = EXCLUDED.loc,
            description = EXCLUDED.description,
            biotype     = EXCLUDED.biotype,
            strand      = EXCLUDED.strand,
            bp_start    = EXCLUDED.bp_start,
            bp_end      = EXCLUDED.bp_end,
            updated_at  = NOW()
    """
    vals = [(
        r['symbol'], r['ensg_id'], r['chr'], r['pos_frac'],
        r['type'], r['loc'], r['description'], r['biotype'],
        r['strand'], r['bp_start'], r['bp_end'], 'NOW()',
    ) for r in rows]
    with conn.cursor() as cur:
        execute_values(cur, sql, [
            (r['symbol'], r['ensg_id'], r['chr'], r['pos_frac'],
             r['type'], r['loc'], r['description'], r['biotype'],
             r['strand'], r['bp_start'], r['bp_end'])
            for r in rows
        ], template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())")
    conn.commit()
    return len(rows)


def run():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise EnvironmentError('DATABASE_URL not set in .env')
    conn  = psycopg2.connect(db_url)
    total = 0
    for chr_name in CHROMS:
        log.info('Fetching chr%s …', chr_name)
        raw  = fetch_genes_on_chr(chr_name)
        rows = [r for g in raw if (r := build_row(g, chr_name))]
        n    = upsert_genes(conn, rows)
        total += n
        log.info('  chr%s → %d genes upserted (raw %d)', chr_name, n, len(raw))
        time.sleep(0.3)   # be polite to Ensembl
    conn.close()
    log.info('Done — %d total genes upserted', total)
    return total


if __name__ == '__main__':
    run()
