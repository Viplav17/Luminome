const axios = require('axios');
const C     = require('../../Config/api.config');

async function getDrugTargets(symbol) {
  try {
    const r = await axios.get(`${C.CHEMBL}/target_search.json`, {
      params: { target_synonym__icontains: symbol, limit: 5 }
    });
    const cids = (r.data?.targets || []).slice(0, 2).map(t => t.target_chembl_id);
    if (!cids.length) return [];
    const results = await Promise.allSettled(cids.map(cid =>
      axios.get(`${C.CHEMBL}/activity.json`, { params: { target_chembl_id: cid, limit: 5 } })
        .then(rr => (rr.data?.activities||[]).map(a => ({
          name: a.molecule_pref_name || a.molecule_chembl_id,
          chemblId: a.molecule_chembl_id,
          mechanism: 'inhibitor',
        })))
    ));
    return results.flatMap(r => r.status === 'fulfilled' ? r.value : []);
  } catch { return []; }
}

module.exports = { getDrugTargets };
