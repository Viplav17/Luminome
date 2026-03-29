/**
 * Backend/api/ml.js
 * Express routes that proxy the 5 ML model predictions.
 *
 * POST /api/ml/pathogenicity     — variant harmful / benign / uncertain
 * POST /api/ml/variant           — VUS pathogenicity score 0–1
 * POST /api/ml/disease-risk      — gene-disease association confidence
 * POST /api/ml/disease-risk/batch
 * POST /api/ml/drug-response     — treatment response by genotype
 * POST /api/ml/trial-match       — single trial match probability
 * POST /api/ml/rank-trials       — rank trial list for a patient
 * GET  /api/ml/status            — which models are trained
 */

const router = require('express').Router();
const ml     = require('../services/ml');

function wrap(fn) {
  return async (req, res) => {
    try {
      res.json(await fn(req));
    } catch (err) {
      const msg = err.message || String(err);
      const code = msg.includes('offline') || msg.includes('not ready') ? 503 : 500;
      res.status(code).json({ error: msg });
    }
  };
}

router.post('/pathogenicity',      wrap(req => ml.pathogenicity(req.body)));
router.post('/variant',            wrap(req => ml.variant(req.body)));
router.post('/disease-risk',       wrap(req => ml.diseaseRisk(req.body)));
router.post('/disease-risk/batch', wrap(req => ml.diseaseRiskBatch(req.body.records || [])));
router.post('/drug-response',      wrap(req => ml.drugResponse(req.body)));
router.post('/trial-match',        wrap(req => ml.trialMatch(req.body)));
router.post('/rank-trials',        wrap(req => ml.rankTrials(req.body.patient, req.body.trials)));
router.get('/status',              wrap(() => ml.modelStatus()));

module.exports = router;
