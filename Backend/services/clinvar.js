const axios = require('axios');
const C     = require('../../Config/api.config');

async function getVariants(symbol) {
  const key = process.env.NCBI_API_KEY ? `&api_key=${process.env.NCBI_API_KEY}` : '';
  try {
    const s = await axios.get(
      `${C.CLINVAR}/esearch.fcgi?db=clinvar&term=${symbol}[gene]&retmax=10&retmode=json${key}`
    );
    const ids = s.data?.esearchresult?.idlist || [];
    if (!ids.length) return [];
    const f = await axios.get(
      `${C.CLINVAR}/esummary.fcgi?db=clinvar&id=${ids.join(',')}&retmode=json${key}`
    );
    const res = f.data?.result || {};
    return ids.map(id => {
      const v = res[id];
      return v ? { clinvarId: id, hgvs: v.title, pathogenicity: v.clinical_significance?.description || 'Unknown' } : null;
    }).filter(Boolean);
  } catch { return []; }
}

module.exports = { getVariants };
