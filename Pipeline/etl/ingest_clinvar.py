"""
Pipeline/etl/ingest_clinvar.py
Fetches ClinVar variants (Pathogenic / Benign / Uncertain significance)
via NCBI E-utilities and enriches them with:
  - gnomAD GraphQL  → gene pLI + conservation_score (oe_mis)
  - Ensembl VEP     → domain_overlap, repeat_region, cadd_score,
                      af_popmax, known_functional_impact

Writes to the `variants` table with full ML feature columns
as defined in Pipeline/warehouse/schema.sql.

Run via seed.py or directly:
    python Pipeline/etl/ingest_clinvar.py

Environment variables used:
    DATABASE_URL     — PostgreSQL connection string
    NCBI_API_KEY     — Raises rate limit from 3 to 10 req/sec (recommended)
"""

import os, re, time, logging
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [clinvar] %(message)s')
log = logging.getLogger(__name__)

NCBI_BASE  = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
GNOMAD_GQL = 'https://gnomad.broadinstitute.org/api'
ENSEMBL    = 'https://rest.ensembl.org'
NCBI_KEY   = os.environ.get('NCBI_API_KEY', '')

# How many variants to fetch per significance class
PER_CLASS = 1800    # 1800 × 3 = 5400 total max
BATCH     = 200     # esummary batch size
SLEEP_OK  = 0.12    # ~8/sec with API key; 3/sec without
SLEEP_ERR = 5.0

# ClinVar significance search terms → model label
SIG_QUERIES = [
    ('benign[clinsig] OR "likely benign"[clinsig]',         0, 'benign'),
    ('"uncertain significance"[clinsig] OR '
     '"conflicting interpretations"[clinsig]',              1, 'uncertain'),
    ('pathogenic[clinsig] OR "likely pathogenic"[clinsig]', 2, 'pathogenic'),
]

# HGVS title → mutation_type classifier
_MUT_PATTERNS = [
    (r'p\.\w+\*',                           'nonsense'),
    (r'del|dup|ins(?!ertion)',               'frameshift'),
    (r'splice|splice-site|IVS',             'splice_site'),
    (r'p\.\w+\d+\w+',                       'missense'),
    (r'=',                                   'synonymous'),
    (r'inframe',                             'inframe_indel'),
]


def _parse_mutation_type(title: str) -> str:
    t = title or ''
    for pattern, mtype in _MUT_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return mtype
    return 'other'


def _parse_splicing_distance(hgvs: str) -> int:
    """
    Extract distance to splice site from HGVS notation.
    c.123+5A>G → 5  |  c.456-2A>C → 2  |  any exonic → 500
    """
    if not hgvs:
        return 500
    m = re.search(r'[cC]\.\d+(?:[+-])(\d+)', hgvs)
    if m:
        return min(int(m.group(1)), 1000)
    return 500


def _parse_review_status(status_str: str) -> str:
    """Normalise ClinVar review_status display text to our vocabulary."""
    s = (status_str or '').lower()
    if 'practice guideline'  in s: return 'practice_guideline'
    if 'expert panel'        in s: return 'expert_panel'
    if 'multiple submitter'  in s: return 'multiple_submitters'
    if 'criteria provided'   in s: return 'single_submitter'
    return 'no_criteria'


# ── NCBI helpers ──────────────────────────────────────────────────────────────

def _key_param() -> str:
    return f'&api_key={NCBI_KEY}' if NCBI_KEY else ''


def esearch(query: str, retmax: int = PER_CLASS) -> list[str]:
    """Return up to `retmax` ClinVar UIDs for `query`."""
    url = (f'{NCBI_BASE}/esearch.fcgi?db=clinvar&term={requests.utils.quote(query)}'
           f'&retmax={retmax}&retmode=json{_key_param()}')
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            ids = r.json().get('esearchresult', {}).get('idlist', [])
            log.info('esearch "%s" → %d IDs', query[:60], len(ids))
            return ids
        except Exception as e:
            log.warning('esearch attempt %d failed: %s', attempt + 1, e)
            time.sleep(SLEEP_ERR * (attempt + 1))
    return []


def esummary_batch(ids: list[str]) -> dict:
    """Fetch ClinVar esummary records for a batch of IDs (max 200)."""
    url = (f'{NCBI_BASE}/esummary.fcgi?db=clinvar&id={",".join(ids)}'
           f'&retmode=json{_key_param()}')
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=45)
            r.raise_for_status()
            result = r.json().get('result', {})
            return result
        except Exception as e:
            log.warning('esummary attempt %d failed: %s', attempt + 1, e)
            time.sleep(SLEEP_ERR * (attempt + 1))
    return {}


def parse_esummary(uid: str, rec: dict, label: int) -> dict | None:
    """Extract ML features from a single esummary record."""
    if not rec or uid == 'uids':
        return None

    # Variant ID / HGVS
    title        = rec.get('title', '')
    accession    = rec.get('accession', f'VCV{uid}')

    # Gene symbol
    gene_list    = rec.get('genes', [])
    gene_symbol  = gene_list[0].get('symbol', '').upper() if gene_list else None

    # Significance
    cs           = rec.get('clinical_significance', {})
    sig_text     = cs.get('description', '')
    review_raw   = cs.get('review_status', '')

    # Submission count from SCV list length
    trait_set    = rec.get('trait_set', [])
    scv_list     = rec.get('supporting_submissions', {}).get('scv', [])
    sub_count    = len(scv_list) if scv_list else 1

    # Allele frequency from allele_freq_set (gnomAD or exac)
    af_val       = 0.0
    for af_entry in rec.get('allele_freq_set', []):
        src  = (af_entry.get('source') or '').lower()
        if 'gnomad' in src or 'exac' in src:
            try:
                af_val = float(af_entry.get('value', 0))
                break
            except (TypeError, ValueError):
                pass

    # Condition
    condition = ''
    if trait_set:
        condition = trait_set[0].get('trait_name', '')

    # HGVS — try variation_set first
    hgvs = ''
    for vs in rec.get('variation_set', []):
        for vname in vs.get('cdna_change', []):
            hgvs = vname
            break
        if hgvs:
            break

    return {
        'variant_id':       accession,
        'gene_symbol':      gene_symbol,
        'name':             title,
        'hgvs':             hgvs,
        'significance':     sig_text,
        'condition':        condition,
        'review_status':    _parse_review_status(review_raw),
        'mutation_type':    _parse_mutation_type(title),
        'allele_frequency': af_val,
        'submission_count': min(sub_count, 32767),
        'splicing_distance':_parse_splicing_distance(hgvs or title),
        'label':            label,
        # enriched below
        'gene_pli':         None,
        'conservation_score': None,
        'domain_overlap':   False,
        'repeat_region':    False,
        'cadd_score':       None,
        'af_popmax':        af_val,
        'known_functional_impact': False,
    }


# ── gnomAD GraphQL ────────────────────────────────────────────────────────────

_GNOMAD_QUERY = '''
query geneMetrics($gene: String!) {
  gene(gene_symbol: $gene, reference_genome: GRCh38) {
    gnomad_constraint {
      pLI
      oe_mis
    }
  }
}
'''


def fetch_gnomad_batch(symbols: list[str]) -> dict[str, dict]:
    """Return {symbol: {'pli': float, 'conservation': float}} for each gene."""
    results = {}
    for sym in symbols:
        time.sleep(SLEEP_OK)
        try:
            r = requests.post(
                GNOMAD_GQL,
                json={'query': _GNOMAD_QUERY, 'variables': {'gene': sym}},
                timeout=20,
                headers={'Content-Type': 'application/json'},
            )
            r.raise_for_status()
            constraint = (r.json()
                          .get('data', {})
                          .get('gene', {}) or {})
            c = (constraint.get('gnomad_constraint') or {})
            pli  = c.get('pLI')
            oem  = c.get('oe_mis')
            results[sym] = {
                'pli':          float(pli) if pli is not None else 0.5,
                # conservation proxy: lower oe_mis → gene more intolerant → higher score
                'conservation': float(max(0, min(10, (1 - float(oem)) * 10))) if oem is not None else 5.0,
            }
        except Exception as e:
            log.debug('gnomAD lookup failed for %s: %s', sym, e)
            results[sym] = {'pli': 0.5, 'conservation': 5.0}
    return results


# ── Ensembl VEP ──────────────────────────────────────────────────────────────

_CONSEQUENCE_HIGH = {
    'stop_gained', 'frameshift_variant', 'splice_acceptor_variant',
    'splice_donor_variant', 'start_lost', 'transcript_ablation',
    'transcript_amplification',
}
_CONSEQUENCE_MOD = {
    'missense_variant', 'inframe_insertion', 'inframe_deletion',
    'protein_altering_variant', 'splice_region_variant',
}


def _vep_features(transcript_list: list) -> dict:
    """Extract domain_overlap, repeat_region, cadd, af_popmax, known_impact."""
    domain_overlap = False
    repeat_region  = False
    cadd_score     = 0.0
    af_popmax      = 0.0
    known_impact   = False
    for tr in (transcript_list or []):
        cons_set = set((tr.get('consequence_terms') or []))
        if cons_set & _CONSEQUENCE_HIGH:
            known_impact = True
        elif not known_impact and cons_set & _CONSEQUENCE_MOD:
            known_impact = True
        if tr.get('domains'):
            domain_overlap = True
        if tr.get('exon') and tr.get('intron') is None:
            pass  # normal exon
        for c in (tr.get('colocated_variants') or []):
            gnomad_af = c.get('gnomadg_af', 0.0)
            if gnomad_af and float(gnomad_af) > af_popmax:
                af_popmax = float(gnomad_af)
        # CADD from extras
        cadd = tr.get('cadd_phred')
        if cadd and float(cadd) > cadd_score:
            cadd_score = float(cadd)
    return {
        'domain_overlap': domain_overlap,
        'repeat_region':  repeat_region,
        'cadd_score':     round(cadd_score, 2),
        'af_popmax':      af_popmax,
        'known_functional_impact': known_impact,
    }


def vep_batch(rsids: list[str]) -> dict[str, dict]:
    """
    POST to Ensembl VEP /vep/human/id (batch up to 200).
    Returns {rsid: {domain_overlap, repeat_region, cadd_score, af_popmax, known_functional_impact}}.
    """
    url     = f'{ENSEMBL}/vep/human/id'
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    params  = {'canonical': 1, 'domains': 1, 'cadd': 1, 'af_gnomadg': 1}
    results = {}
    # Chunk into 200-ID batches
    for i in range(0, len(rsids), 200):
        chunk = rsids[i:i + 200]
        time.sleep(0.5)  # Ensembl rate limit ~15/sec
        try:
            r = requests.post(
                url,
                json={'ids': chunk},
                headers=headers,
                params=params,
                timeout=60,
            )
            if r.status_code == 429:
                wait = int(r.headers.get('Retry-After', 30))
                log.warning('VEP rate limited — waiting %ds', wait)
                time.sleep(wait)
                r = requests.post(url, json={'ids': chunk},
                                  headers=headers, params=params, timeout=60)
            r.raise_for_status()
            for variant in r.json():
                vid = variant.get('id')
                if vid:
                    results[vid] = _vep_features(
                        variant.get('transcript_consequences') or
                        variant.get('intergenic_consequences') or []
                    )
        except Exception as e:
            log.warning('VEP batch failed (chunk %d): %s', i // 200, e)
    return results


# ── Main ingestion + database write ──────────────────────────────────────────

def upsert_variants(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO variants (
            variant_id, gene_symbol, name, hgvs, significance, condition,
            review_status, allele_frequency, mutation_type, gene_pli,
            conservation_score, submission_count, splicing_distance,
            domain_overlap, repeat_region, cadd_score, af_popmax,
            known_functional_impact
        ) VALUES %s
        ON CONFLICT (variant_id) DO UPDATE SET
            gene_pli             = EXCLUDED.gene_pli,
            conservation_score   = EXCLUDED.conservation_score,
            allele_frequency     = EXCLUDED.allele_frequency,
            mutation_type        = EXCLUDED.mutation_type,
            submission_count     = EXCLUDED.submission_count,
            splicing_distance    = EXCLUDED.splicing_distance,
            domain_overlap       = EXCLUDED.domain_overlap,
            repeat_region        = EXCLUDED.repeat_region,
            cadd_score           = EXCLUDED.cadd_score,
            af_popmax            = EXCLUDED.af_popmax,
            known_functional_impact = EXCLUDED.known_functional_impact
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, [
            (
                r['variant_id'], r.get('gene_symbol'), r['name'], r['hgvs'],
                r['significance'], r['condition'], r['review_status'],
                r['allele_frequency'], r['mutation_type'], r['gene_pli'],
                r['conservation_score'], r['submission_count'], r['splicing_distance'],
                r['domain_overlap'], r['repeat_region'], r['cadd_score'],
                r['af_popmax'], r['known_functional_impact'],
            )
            for r in rows
        ])
    conn.commit()
    return len(rows)


def run(per_class: int = PER_CLASS) -> int:
    """
    Fetch ClinVar variants, enrich with gnomAD + VEP, write to DB.
    Returns total rows inserted/updated.
    """
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise EnvironmentError('DATABASE_URL not set in .env')
    conn = psycopg2.connect(db_url)

    all_records: list[dict] = []

    for query, label, label_name in SIG_QUERIES:
        log.info('── Fetching %s variants ──', label_name)
        ids = esearch(query, retmax=per_class)
        if not ids:
            log.warning('No IDs returned for %s — skipping', label_name)
            continue

        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            time.sleep(SLEEP_OK)
            result = esummary_batch(chunk)
            for uid in chunk:
                rec = result.get(uid)
                parsed = parse_esummary(uid, rec, label)
                if parsed:
                    all_records.append(parsed)
            log.info('  Progress: %d/%d %s', min(i + BATCH, len(ids)), len(ids), label_name)

    log.info('Total ClinVar records parsed: %d', len(all_records))

    # ── gnomAD enrichment (gene-level) ───────────────────────────────────────
    unique_genes = [s for s in {r['gene_symbol'] for r in all_records
                                if r.get('gene_symbol')} if s]
    log.info('Fetching gnomAD metrics for %d genes …', len(unique_genes))
    gnomad_data = fetch_gnomad_batch(unique_genes)

    for r in all_records:
        g = gnomad_data.get(r.get('gene_symbol') or '', {'pli': 0.5, 'conservation': 5.0})
        r['gene_pli']           = round(g['pli'], 4)
        r['conservation_score'] = round(g['conservation'], 4)

    # ── Ensembl VEP enrichment (variant-level) ───────────────────────────────
    # Only variants that have an rsID in their title/name can be VEP-queried by ID
    rsid_re = re.compile(r'\b(rs\d+)\b')
    rsid_map: dict[str, list[int]] = {}   # rsid → list of indices in all_records
    for idx, r in enumerate(all_records):
        m = rsid_re.search(r.get('name', '') + ' ' + r.get('hgvs', ''))
        if m:
            rsid = m.group(1)
            rsid_map.setdefault(rsid, []).append(idx)

    rsids = list(rsid_map.keys())
    log.info('Running VEP batch for %d rsIDs …', len(rsids))
    vep_data = vep_batch(rsids) if rsids else {}

    for rsid, indices in rsid_map.items():
        features = vep_data.get(rsid)
        if not features:
            continue
        for idx in indices:
            all_records[idx].update(features)

    # ── Write to DB ───────────────────────────────────────────────────────────
    log.info('Upserting %d variant records …', len(all_records))
    try:
        # Ensure gene_symbol exists in genes table (foreign key); drop orphans
        with conn.cursor() as cur:
            cur.execute('SELECT symbol FROM genes')
            valid_genes = {row[0] for row in cur.fetchall()}

        valid_records  = [r for r in all_records if r.get('gene_symbol') in valid_genes]
        orphan_records = [r for r in all_records if r.get('gene_symbol') not in valid_genes]

        if orphan_records:
            log.warning('%d variants have unknown gene symbols — inserting without gene_symbol',
                        len(orphan_records))
            for r in orphan_records:
                r['gene_symbol'] = None

        n = upsert_variants(conn, all_records)
        log.info('Upserted %d variants (%d linked to known genes)', n, len(valid_records))
    except Exception as e:
        conn.rollback()
        log.error('DB upsert failed: %s', e)
        raise
    finally:
        conn.close()

    return len(all_records)


if __name__ == '__main__':
    total = run()
    log.info('ClinVar ingestion complete — %d variants', total)
