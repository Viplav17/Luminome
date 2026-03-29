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

/** Curated pharmacologic classes → gene symbols (HGNC) for genome highlighting when ChEMBL is slow/unavailable */
const DRUG_CLASS_GENES = {
  kinase_inhibitor: [
    'EGFR', 'ALK', 'BRAF', 'KIT', 'FLT3', 'MET', 'ROS1', 'RET', 'NTRK1', 'NTRK2', 'NTRK3',
    'PDGFRA', 'PDGFRB', 'ABL1', 'SRC', 'JAK2', 'JAK3', 'ERBB2', 'ERBB3', 'ERBB4',
    'FGFR1', 'FGFR2', 'FGFR3', 'CDK4', 'CDK6', 'CDK2', 'MTOR', 'PIK3CA', 'PIK3CB', 'AKT1', 'MAP2K1', 'MAP2K2',
  ],
  monoclonal_antibody: [
    'EGFR', 'ERBB2', 'MS4A1', 'FCGR3A', 'VEGFA', 'PDCD1', 'CD274', 'CTLA4', 'TNFRSF17', 'TNF', 'IL6R',
    'IL17A', 'CD3E', 'CD19', 'CD52', 'INSR', 'IGF1R', 'FOLR1', 'MET',
  ],
  hormone_therapy: ['ESR1', 'ESR2', 'PGR', 'AR', 'NR3C1', 'SHBG', 'CYP19A1', 'HSD17B1', 'NR3C2'],
  checkpoint_inhibitor: ['PDCD1', 'CD274', 'PDCD1LG2', 'CTLA4', 'LAG3', 'TIGIT', 'HAVCR2', 'CD276'],
  proteasome_inhibitor: ['PSMB5', 'PSMB1', 'PSMB2', 'PSMB3', 'PSMB4', 'PSMB6', 'PSMB7', 'PSMB8', 'PSMB9', 'PSMB10'],
  alkylating_agent: ['TP53', 'MLH1', 'MSH2', 'MSH6', 'PMS2', 'BRCA1', 'BRCA2', 'ATM', 'ATR', 'PARP1', 'RAD51C'],
};

async function getGenesForDrugClass(classKey) {
  const key = String(classKey || '').toLowerCase().replace(/-/g, '_');
  const list = DRUG_CLASS_GENES[key];
  if (!list || !list.length) return [];
  return list.map(id => ({ id }));
}

module.exports = { getDrugTargets, getGenesForDrugClass, DRUG_CLASS_GENES };
