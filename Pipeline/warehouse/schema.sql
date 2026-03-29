-- MutationMap — PostgreSQL schema
-- Run once: psql $DATABASE_URL -f Pipeline/warehouse/schema.sql

BEGIN;

-- ── Core gene registry ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS genes (
    symbol          TEXT PRIMARY KEY,
    ensg_id         TEXT UNIQUE,
    chr             TEXT NOT NULL,
    pos_frac        NUMERIC(8,6) NOT NULL,   -- 0–1 position along chromosome
    type            TEXT NOT NULL DEFAULT 'other',
    loc             TEXT,                    -- cytogenetic band e.g. "17q21"
    description     TEXT,
    biotype         TEXT,                    -- protein_coding | lncRNA | etc.
    strand          SMALLINT,                -- 1 | -1
    bp_start        BIGINT,
    bp_end          BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Disease / phenotype registry (OMIM) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS diseases (
    mim_number      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT,
    inheritance     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Gene ↔ disease associations (OMIM + OpenTargets) ─────────────────────────
CREATE TABLE IF NOT EXISTS gene_disease (
    gene_symbol     TEXT NOT NULL REFERENCES genes(symbol) ON DELETE CASCADE,
    disease_key     TEXT NOT NULL,           -- mim_number or OT disease ID
    disease_name    TEXT NOT NULL,
    score           NUMERIC(6,4),
    source          TEXT,                    -- omim | opentargets
    PRIMARY KEY (gene_symbol, disease_key)
);

-- ── Pathogenic variants (ClinVar) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS variants (
    variant_id      TEXT PRIMARY KEY,        -- ClinVar accession e.g. "VCV000012345"
    gene_symbol     TEXT REFERENCES genes(symbol) ON DELETE CASCADE,
    name            TEXT,
    hgvs            TEXT,
    significance    TEXT,                    -- Pathogenic | Likely pathogenic | etc.
    condition       TEXT,
    review_status   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Drug–target pairs (ChEMBL) ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS drugs (
    chembl_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    drug_type       TEXT,
    max_phase       SMALLINT,
    gene_symbol     TEXT,
    mechanism       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── PharmGKB gene/drug/disease relationships ─────────────────────────────────
CREATE TABLE IF NOT EXISTS pharmgkb_relations (
    id              SERIAL PRIMARY KEY,
    entity1_id      TEXT,
    entity1_name    TEXT,
    entity1_type    TEXT,
    entity2_id      TEXT,
    entity2_name    TEXT,
    entity2_type    TEXT,
    evidence        TEXT[],
    pmids           TEXT[],
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Gene disease-category classification ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS gene_category (
    gene_symbol     TEXT NOT NULL REFERENCES genes(symbol) ON DELETE CASCADE,
    category        TEXT NOT NULL,           -- cancer | cardiovascular | neurological | etc.
    confidence      NUMERIC(4,3),
    source          TEXT,
    PRIMARY KEY (gene_symbol, category)
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_genes_chr      ON genes(chr);
CREATE INDEX IF NOT EXISTS idx_genes_type     ON genes(type);
CREATE INDEX IF NOT EXISTS idx_genes_ensg     ON genes(ensg_id);
CREATE INDEX IF NOT EXISTS idx_variants_gene  ON variants(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_variants_sig   ON variants(significance);
CREATE INDEX IF NOT EXISTS idx_drugs_gene     ON drugs(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_gd_gene        ON gene_disease(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_gd_disease     ON gene_disease(disease_key);
CREATE INDEX IF NOT EXISTS idx_pgkb_e1        ON pharmgkb_relations(entity1_id);
CREATE INDEX IF NOT EXISTS idx_pgkb_e2        ON pharmgkb_relations(entity2_id);
CREATE INDEX IF NOT EXISTS idx_gc_category    ON gene_category(category);

-- ── Auto-update trigger ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS genes_updated_at ON genes;
CREATE TRIGGER genes_updated_at
  BEFORE UPDATE ON genes
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

COMMIT;
