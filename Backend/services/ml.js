/**
 * Backend/services/ml.js
 * HTTP client that proxies calls to the Python FastAPI ML inference server
 * running on port 3002. Gracefully returns null when the ML server is offline.
 */

const axios = require('axios');

const ML_BASE = process.env.ML_BASE || 'http://localhost:3002';
const TIMEOUT = 10_000;

async function call(path, body) {
  try {
    const r = await axios.post(`${ML_BASE}${path}`, body, { timeout: TIMEOUT });
    return r.data;
  } catch (err) {
    const status = err.response?.status;
    const detail = err.response?.data?.detail || err.message;
    if (status === 503) throw new Error(`ML model not ready: ${detail}`);
    if (err.code === 'ECONNREFUSED') throw new Error('ML server offline — start with: python Models/server.py');
    throw new Error(detail || err.message);
  }
}

module.exports = {
  pathogenicity:  (f)          => call('/predict/pathogenicity', f),
  variant:        (f)          => call('/predict/variant', f),
  diseaseRisk:    (f)          => call('/predict/disease-risk', f),
  diseaseRiskBatch: (records)  => call('/predict/disease-risk/batch', { records }),
  drugResponse:   (f)          => call('/predict/drug-response', f),
  trialMatch:     (f)          => call('/predict/trial-match', f),
  rankTrials:     (patient, trials) => call('/predict/rank-trials', { patient, trials }),
  health:         ()           => axios.get(`${ML_BASE}/health`, { timeout: 3000 }).then(r => r.data),
  modelStatus:    ()           => axios.get(`${ML_BASE}/models/status`, { timeout: 3000 }).then(r => r.data),
};
