const router = require('express').Router();
const ot     = require('../services/opentargets');
router.get('/:name/genes', async (req, res) => {
  try { res.json(await ot.getGenesForDisease(req.params.name)); }
  catch { res.json([]); }
});
module.exports = router;
