const router  = require('express').Router();
const { pgPool } = require('../../Config/db.config');
const cache   = require('../middleware/cache');
const ensembl = require('../services/ensembl');
const ot      = require('../services/opentargets');
const clinvar = require('../services/clinvar');
const chembl  = require('../services/chembl');
const ct      = require('../services/clinicaltrials');

router.get('/', async (req, res) => {
  const { chr, type, page = 1, limit = 300 } = req.query;
  const ck = `genes:${chr||'*'}:${type||'*'}:${page}`;
  const hit = await cache.get(ck);
  if (hit) return res.json(hit);
  try {
    const params = [], conds = [];
    if (chr)  { params.push(chr);  conds.push(`chr=$${params.length}`); }
    if (type) { params.push(type); conds.push(`type=$${params.length}`); }
    const off = (parseInt(page) - 1) * parseInt(limit);
    params.push(parseInt(limit), off);
    const q = `SELECT symbol AS id, chr, pos_frac AS pos, type, loc, description AS desc FROM genes ${conds.length ? 'WHERE '+conds.join(' AND ') : ''} LIMIT $${params.length-1} OFFSET $${params.length}`;
    const { rows } = await pgPool.query(q, params);
    await cache.set(ck, rows, 3600);
    res.json(rows);
  } catch { res.json([]); }
});

router.get('/:id', async (req, res) => {
  const id = req.params.id.toUpperCase();
  const ck = `gene:${id}`;
  const hit = await cache.get(ck);
  if (hit) return res.json(hit);
  try {
    const { rows } = await pgPool.query(
      'SELECT * FROM genes WHERE symbol=$1 OR ensg_id=$1', [id]
    );
    const row = rows[0];
    const live = row ? null : await ensembl.lookupGene(id);
    const ensgId = row ? row.ensg_id : live?.ensgId;
    if (!ensgId && !row) return res.status(404).json({ error: 'Not found' });
    const [dis, drgs, muts, trs] = await Promise.allSettled([
      ot.getDiseaseAssociations(ensgId || ''),
      chembl.getDrugTargets(id),
      clinvar.getVariants(id),
      ct.getActiveTrials(id),
    ]).then(r => r.map(x => x.status === 'fulfilled' ? x.value : []));
    const gene = row
      ? { id:row.symbol, chr:row.chr, pos:parseFloat(row.pos_frac), type:row.type, loc:row.loc, desc:row.description, dis, drugs:drgs, muts, trials:trs }
      : { ...live, dis, drugs:drgs, muts, trials:trs };
    await cache.set(ck, gene, 3600);
    res.json(gene);
  } catch (err) { res.status(500).json({ error: err.message }); }
});

module.exports = router;
