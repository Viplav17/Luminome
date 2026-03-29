const axios = require('axios');
const C     = require('../../Config/api.config');

const CHR_LEN = {
  '1':249,'2':242,'3':198,'4':190,'5':181,'6':171,'7':159,'8':145,
  '9':138,'10':133,'11':135,'12':133,'13':114,'14':107,'15':102,'16':90,
  '17':83,'18':80,'19':59,'20':63,'21':47,'22':51,'X':155,'Y':59,
};

async function lookupGene(symbol) {
  try {
    const r = await axios.get(
      `${C.ENSEMBL}/lookup/symbol/homo_sapiens/${symbol}`,
      { headers: { 'Content-Type': 'application/json' }, params: { expand: 1 } }
    );
    const d = r.data, chr = String(d.seq_region_name);
    const maxBp = (CHR_LEN[chr] || 150) * 1e6;
    return {
      id: symbol.toUpperCase(), ensgId: d.id, chr,
      pos:  parseFloat((d.start / maxBp).toFixed(4)),
      type: 'other',
      loc:  `${chr}${d.strand > 0 ? 'q' : 'p'}`,
      desc: d.description || '',
    };
  } catch { return null; }
}

module.exports = { lookupGene };
