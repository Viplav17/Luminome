const axios = require('axios');
const C     = require('../../Config/api.config');

async function getActiveTrials(symbol) {
  try {
    const r = await axios.get(C.CLINICALTRIALS, {
      params: {
        'query.term':           symbol,
        'filter.overallStatus': 'RECRUITING,ACTIVE_NOT_RECRUITING',
        pageSize:               20,
      }
    });
    return (r.data?.studies || []).map(s => ({
      nctId:  s.protocolSection?.identificationModule?.nctId,
      title:  s.protocolSection?.identificationModule?.briefTitle,
      phase:  s.protocolSection?.designModule?.phases?.[0],
      status: s.protocolSection?.statusModule?.overallStatus,
    })).filter(t => t.nctId);
  } catch { return []; }
}

module.exports = { getActiveTrials };
