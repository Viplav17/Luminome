
// BASE comes from api.config.js which loads before this file.

const BASE = API_CONFIG.BACKEND_BASE;

// Helper — fetch JSON from the backend, throw on non-2xx
async function apiFetch(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

// Helper — POST JSON to the backend
async function apiPost(path, body) {
  const res = await fetch(BASE + path, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

// Load all genes — called once on startup, result stored in S.genes
// Optional filters: chr ('17'), type ('ts' | 'onco' | 'other')
async function getGenes({ chr, type } = {}) {
  const params = new URLSearchParams();
  if (chr)  params.set('chr', chr);
  if (type) params.set('type', type);
  const qs = params.toString() ? '?' + params.toString() : '';
  return apiFetch('/api/genes' + qs);
}

// Load a single gene with full detail — diseases, mutations, drugs, trials
async function getGene(id) {
  return apiFetch('/api/genes/' + encodeURIComponent(id));
}

// All genes linked to a disease name (used by filter chips)
async function getDiseaseGenes(name) {
  return apiFetch('/api/diseases/' + encodeURIComponent(name) + '/genes');
}

// Drugs that target a specific gene
async function getDrugs(geneId) {
  return apiFetch('/api/drugs/' + encodeURIComponent(geneId));
}

// Gene symbols targeted by a pharmacologic class (genome highlight)
async function getDrugClassGenes(classKey) {
  if (!classKey) return [];
  return apiFetch('/api/drugs/class/' + encodeURIComponent(classKey) + '/genes');
}

// Active clinical trials for a specific gene
async function getTrials(geneId) {
  return apiFetch('/api/trials/' + encodeURIComponent(geneId));
}

// Send a natural language question to the AI via the backend proxy.
// Returns { genes: ['BRCA1', 'TP53', ...], explanation: '...' }
async function queryAI(text, geneUniverse) {
  return apiPost('/api/ai/query', {
    query: text,
    geneUniverse: Array.isArray(geneUniverse) ? geneUniverse : [],
  });
}