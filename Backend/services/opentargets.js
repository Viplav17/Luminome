const axios = require('axios');
const C     = require('../../Config/api.config');

async function gql(query, vars) {
  const r = await axios.post(C.OPENTARGETS, { query, variables: vars });
  return r.data.data;
}

async function getDiseaseAssociations(ensgId) {
  const q = `query($id:String!){target(ensemblId:$id){associatedDiseases(page:{index:0,size:10}){rows{disease{id name}score}}}}`;
  try {
    const d = await gql(q, { id: ensgId });
    return (d?.target?.associatedDiseases?.rows || [])
      .map(r => ({ id: r.disease.id, name: r.disease.name, score: r.score, cat: 'other' }));
  } catch { return []; }
}

async function getDrugAssociations(ensgId) {
  const q = `query($id:String!){target(ensemblId:$id){knownDrugs(page:{index:0,size:10}){rows{drug{id name}phase status}}}}`;
  try {
    const d = await gql(q, { id: ensgId });
    return (d?.target?.knownDrugs?.rows || [])
      .map(r => ({ drugId: r.drug.id, name: r.drug.name, phase: r.phase, status: r.status }));
  } catch { return []; }
}

async function getGenesForDisease(name) {
  const q = `query($q:String!){search(queryString:$q,entityNames:["disease"],page:{index:0,size:1}){hits{object{...on Disease{associatedTargets(page:{index:0,size:20}){rows{target{id approvedSymbol}}}}}}}}`;
  try {
    const d = await gql(q, { q: name });
    const rows = d?.search?.hits?.[0]?.object?.associatedTargets?.rows || [];
    return rows.map(r => ({ id: r.target.approvedSymbol, ensgId: r.target.id }));
  } catch { return []; }
}

module.exports = { getDiseaseAssociations, getDrugAssociations, getGenesForDisease };
