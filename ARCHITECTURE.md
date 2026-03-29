# MutationMap — File Dependency Map

## Navigation flow
Genome grid (Canvas 2D) → Chromosome pair (Three.js 3D) → DNA strand (Three.js 3D)
S.view: 'genome' → 'pair' → 'dna'

---

## Frontend — script load order (index.html)

```
/Config/api.config.js       defines API_CONFIG (global)
         ↓
Frontend/src/js/state.js    defines S (global var)
         ↓
Frontend/src/js/api.js      reads API_CONFIG.BACKEND_BASE
                            exposes: getGenes, getGene, getDiseaseGenes, getDrugs, getTrials, queryAI
         ↓
Frontend/src/js/renderer.js reads S, CHR_DATA
                            exposes: chrHits, geneHits (globals)
                            owns: Canvas 2D animation loop
         ↓
Frontend/src/js/ui.js       reads S, chrHits, geneHits
                            calls: api.js functions, window.Viewer (set by viewer.js)
                            writes: S.view, S.selChr, S.selGene, S.hovChr, S.hovGene, S.filter
         ↓
Frontend/src/js/ai.js       calls: queryAI() from api.js
                            writes: S.aiGenes
         ↓
Frontend/src/js/viewer.js   [type=module] imports THREE, OrbitControls, STLLoader
                            reads: S, window.CHR_DATA
                            writes: window.Viewer = { showPair, showDNA, hide }
                            owns: Three.js WebGL renderer, rAF loop
```

---

## Backend — request flow (Backend/server.js)

```
HTTP request
    ↓
middleware/rateLimit.js     100 req / 15 min per IP
    ↓
api/genes.js       GET /api/genes           → pgPool (cache → DB → empty)
                   GET /api/genes/:id       → ensembl + opentargets + clinvar + chembl + clinicaltrials
api/diseases.js    GET /api/diseases/:name  → opentargets
api/drugs.js       GET /api/drugs/:gene     → chembl + opentargets
api/trials.js      GET /api/trials/:gene    → clinicaltrials
api/ai.js          POST /api/ai/query       → @google/generative-ai (GEMINI_API_KEY)
```

---

## Config — read by both browser and server

```
Config/api.config.js    all external API base URLs
                        GEMINI, ENSEMBL, CLINVAR, OPENTARGETS, CLINICALTRIALS, CHEMBL, OMIM, HPO
                        browser: loaded as <script>, sets API_CONFIG global
                        server:  required by Backend/services/*

Config/db.config.js     PostgreSQL pool + Redis client
                        server only — never loaded by browser
```

---

## Pipeline — run independently (Python)

```
Pipeline/warehouse/schema.sql       PostgreSQL table definitions
Pipeline/warehouse/seed.py          orchestrates full ETL run

Pipeline/etl/ingest_ensembl.py      REST Ensembl → genes table
Pipeline/etl/ingest_omim.py         OMIM API → genes table (OMIM_API_KEY)
Pipeline/etl/ingest_pharmgkb.py     Data/relationships.tsv → drug_targets table (no API key)
Pipeline/etl/normalize.py           resolves gene symbols → ENSG IDs across all sources
```

---

## Models — Phase 4 (Python / scikit-learn)

```
Models/pathogenicity/train.py        GradientBoostingClassifier  — variant harmful vs benign
Models/variant_classification/train.py GradientBoostingClassifier — VUS classification
Models/disease_risk/train.py         HistGradientBoostingClassifier — gene-disease confidence
Models/drug_response/train.py        RandomForestClassifier      — treatment response by genotype
Models/trial_matching/train.py       LogisticRegression          — patient vs trial eligibility
                                     (must return SHAP feature explanations for clinicians)
```

---

## 3D Assets

```
Frontend/src/assets/models/
    chromosome_pair.stl   → loaded by viewer.js in 'pair' view
    dna_strand.stl        → loaded by viewer.js in 'dna' view
    (procedural fallback rendered if files absent)
```

---

## Secrets flow

```
.env  →  Config/api.config.js (server-side only, via process.env)
      →  Config/db.config.js  (server-side only)
      
GEMINI_API_KEY  never leaves Backend/api/ai.js
OMIM_API_KEY    never leaves Backend/services/ or Pipeline/etl/
```
