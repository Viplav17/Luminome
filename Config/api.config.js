
if (typeof process !== 'undefined' && typeof require !== 'undefined') {
  try {
    require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
  } catch (_) { /* dotenv not available in browser — safe to ignore */ }
}

var API_CONFIG = {
  // All client → server calls go through the backend (never directly to Claude etc.)
  BACKEND_BASE: (typeof process !== 'undefined' && process.env && process.env.BACKEND_BASE)
    ? process.env.BACKEND_BASE
    : 'http://localhost:3001',

  // Ensembl REST API — gene coordinates (GRCh38, no auth required)
  ENSEMBL: 'https://rest.ensembl.org',

  // NCBI E-utilities — ClinVar variant + pathogenicity data
  // Append ?api_key=NCBI_API_KEY to raise rate limit from 3 to 10 req/sec
  CLINVAR: 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils',

  // OpenTargets — disease associations + drug targets (GraphQL, no auth)
  OPENTARGETS: 'https://api.platform.opentargets.org/api/v4/graphql',

  // ClinicalTrials.gov v2 — active trial search (no auth)
  CLINICALTRIALS: 'https://clinicaltrials.gov/api/v2/studies',

  // ChEMBL — drug-gene target mapping (no auth)
  CHEMBL: 'https://www.ebi.ac.uk/chembl/api/data',

  // OMIM — disease phenotypes (API key required — server-side only)
  OMIM: 'https://api.omim.org/api',

  // Human Phenotype Ontology — symptom-gene mapping (no auth)
  HPO: 'https://hpo.jax.org/api/hpo',

  // PharmGKB — data loaded from Data/relationships.tsv, no API call needed
  // PHARMGKB: not used

  // Google Gemini — SERVER-SIDE PROXY ONLY. Key must never reach the browser.
  GEMINI: 'https://generativelanguage.googleapis.com/v1beta',
};

// CommonJS export for Node.js — no-op in browser
if (typeof module !== 'undefined') module.exports = API_CONFIG;
