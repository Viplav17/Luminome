const router = require('express').Router();
const ct     = require('../services/clinicaltrials');
router.get('/:gene', async (req, res) => {
  try { res.json(await ct.getActiveTrials(req.params.gene)); }
  catch { res.json([]); }
});
module.exports = router;
