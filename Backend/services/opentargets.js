const axios = require('axios');
const C     = require('../../Config/api.config');

/** Maps UI disease chip keys to Open Targets search strings */
const CATEGORY_SEARCH = {
  cancer:          'cancer',
  cardiovascular:  'cardiovascular disease',
  neurological:    'neurological disorder',
  metabolic:       'metabolic disease',
  immunological:   'immune system disease',
  rare:            'rare genetic disease',
};

function mapTherapeuticToCat(taName) {
  const s = String(taName || '').toLowerCase();
  if (/oncolog|neoplasm|cancer|tumor|malignan/.test(s)) return 'cancer';
  if (/cardio|vascular|heart|circulatory/.test(s)) return 'cardiovascular';
  if (/neuro|psychiatr|mental|brain/.test(s)) return 'neurological';
  if (/metabol|endocrine|diabetes|lipid|nutritional/.test(s)) return 'metabolic';
  if (/immune|inflammat|autoimmune|allerg|hematologic/.test(s)) return 'immunological';
  if (/rare|orphan|genetic|familial|congenital/.test(s)) return 'rare';
  return 'other';
}

async function gql(query, vars) {
  const r = await axios.post(C.OPENTARGETS, { query, variables: vars });
  return r.data.data;
}

async function getDiseaseAssociations(ensgId) {
  const q = `query($id:String!){target(ensemblId:$id){associatedDiseases(page:{index:0,size:25}){rows{score disease{id name therapeuticAreas{name}}}}}}`;
  try {
    const d = await gql(q, { id: ensgId });
    return (d?.target?.associatedDiseases?.rows || []).map(r => {
      const tas = r.disease.therapeuticAreas || [];
      let cat = 'other';
      for (const ta of tas) {
        const c = mapTherapeuticToCat(ta.name);
        if (c !== 'other') { cat = c; break; }
      }
      if (cat === 'other' && tas[0]) cat = mapTherapeuticToCat(tas[0].name);
      return { id: r.disease.id, name: r.disease.name, score: r.score, cat };
    });
  } catch { return []; }
}

async function getDrugAssociations(ensgId) {
  const q = `query($id:String!){target(ensemblId:$id){knownDrugs(page:{index:0,size:25}){rows{drug{id name}phase status}}}}`;
  try {
    const d = await gql(q, { id: ensgId });
    return (d?.target?.knownDrugs?.rows || [])
      .map(r => ({ drugId: r.drug.id, name: r.drug.name, phase: r.phase, status: r.status }));
  } catch { return []; }
}

/** Clinical presentation lines from EFO disease ontology descriptions (symptom-adjacent). */
async function getPresentationHintsFromEfoIds(efoIds) {
  const ids = (efoIds || []).filter(id => String(id).startsWith('EFO_')).slice(0, 5);
  const out = [];
  const seen = new Set();
  for (const efoId of ids) {
    try {
      const q = `query($id:String!){ disease(efoId:$id){ description } }`;
      const d = await gql(q, { id: efoId });
      const text = d?.disease?.description;
      if (!text || typeof text !== 'string') continue;
      text.split(/\.\s+/).filter(Boolean).slice(0, 2).forEach(function(s) {
        const t = s.trim();
        if (t.length > 12 && !seen.has(t)) {
          seen.add(t);
          out.push(t);
        }
      });
    } catch (_) { /* skip single EFO failure */ }
  }
  return out.slice(0, 18);
}

async function getGenesForDisease(nameOrKey) {
  const raw = String(nameOrKey || '').trim();
  const qStr = CATEGORY_SEARCH[raw.toLowerCase()] || raw;
  const q = `query($q:String!){search(queryString:$q,entityNames:["disease"],page:{index:0,size:1}){hits{object{...on Disease{associatedTargets(page:{index:0,size:50}){rows{target{id approvedSymbol}}}}}}}}`;
  try {
    const d = await gql(q, { q: qStr });
    const rows = d?.search?.hits?.[0]?.object?.associatedTargets?.rows || [];
    return rows.map(r => ({ id: r.target.approvedSymbol, ensgId: r.target.id }));
  } catch { return []; }
}

module.exports = {
  getDiseaseAssociations,
  getDrugAssociations,
  getGenesForDisease,
  getPresentationHintsFromEfoIds,
  CATEGORY_SEARCH,
};
