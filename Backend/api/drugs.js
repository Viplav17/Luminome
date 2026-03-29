const router = require('express').Router();
const chembl = require('../services/chembl');
const ot     = require('../services/opentargets');

router.get('/class/:classKey/genes', async (req, res) => {
  try {
    const genes = await chembl.getGenesForDrugClass(req.params.classKey);
    res.json(genes);
  } catch { res.json([]); }
});

router.get('/:gene', async (req, res) => {
  try {
    const [a, b] = await Promise.allSettled([
      chembl.getDrugTargets(req.params.gene),
      ot.getDrugAssociations(req.params.gene),
    ]).then(r => r.map(x => x.status === 'fulfilled' ? x.value : []));
    const seen = new Set();
    res.json([...a, ...b].filter(d => {
      const k = d.name || d.drugId;
      return seen.has(k) ? false : !!seen.add(k);
    }));
  } catch { res.json([]); }
});
module.exports = router;
