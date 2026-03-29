function _parseSev(v) {
  var s = String(v||'').toLowerCase();
  if (!s || s === '-' || s === 'na') return 'moderate';
  if (/high|critical|pathogenic$|likely_pathogenic|stop_gain|frameshift|splice_donor|splice_acceptor|loss_of_function|\blof\b/i.test(s)) return 'critical';
  if (/low|benign|likely_benign/i.test(s)) return 'low';
  return 'moderate';
}

function _normChr(v) {
  var s = String(v||'').trim().replace(/^chr/i,'').toUpperCase();
  return s === '23' ? 'X' : s === '24' ? 'Y' : s;
}

function _delim(line) {
  return (line.match(/\t/g)||[]).length >= (line.match(/,/g)||[]).length ? '\t' : ',';
}

function _col(hdrs, pats) {
  for (var i = 0; i < hdrs.length; i++)
    for (var j = 0; j < pats.length; j++)
      if (pats[j].test(hdrs[i])) return i;
  return -1;
}

function _parseUpload(file) {
  var reader = new FileReader();
  reader.onload = function(e) {
    var lines = e.target.result.split(/\r?\n/).filter(function(l){ return l.trim(); });
    if (lines.length < 2) { alert('File has no data rows.'); return; }
    var sep  = _delim(lines[0]);
    var hdrs = lines[0].split(sep).map(function(h){ return h.trim().toLowerCase().replace(/["']/g,''); });

    var ci = {
      chr:     _col(hdrs, [/^chr(om(osome)?)?$/]),
      gene:    _col(hdrs, [/^gene([._\s]?(id|symbol|name))?$/, /^symbol$/]),
      variant: _col(hdrs, [/variant|mutation|hgvs|allele|alt$|change/]),
      sev:     _col(hdrs, [/severity|impact|effect|consequence|pathogen|classif/, /^type$/, /^class$/]),
      zyg:     _col(hdrs, [/zygosity|genotype/]),
      pos:     _col(hdrs, [/^pos(ition)?$/, /^start$/, /^bp$/, /^coord/]),
    };

    if (ci.chr < 0) {
      alert('Missing required column: "chr" or "chromosome".\nDetected columns: ' + hdrs.join(', '));
      return;
    }

    var map = {}, total = 0;
    for (var i = 1; i < lines.length; i++) {
      var cols = lines[i].split(sep).map(function(c){ return c.trim().replace(/^["']|["']$/g,''); });
      var chr  = _normChr(cols[ci.chr] || '');
      if (!CHR_DATA[chr]) continue;
      var sev = _parseSev(ci.sev >= 0 ? cols[ci.sev] : '');
      if (!map[chr]) map[chr] = {rows:[], maxSev:'low'};
      map[chr].rows.push({
        gene:    ci.gene    >= 0 ? cols[ci.gene]    : '',
        variant: ci.variant >= 0 ? cols[ci.variant] : '',
        sev:     sev,
        zyg:     ci.zyg    >= 0 ? cols[ci.zyg]     : '',
        pos:     ci.pos    >= 0 ? parseFloat(cols[ci.pos])||0 : 0,
      });
      if (SEV_RANK[sev] > SEV_RANK[map[chr].maxSev]) map[chr].maxSev = sev;
      total++;
    }

    S.uploadChrMap = map;
    var affected = Object.keys(map).length;
    var st = document.getElementById('upload-status');
    st.textContent = affected + ' chr \u00b7 ' + total + ' variants';
    st.style.display = 'inline';
    document.getElementById('upload-clear').style.display = 'inline-flex';
  };
  reader.readAsText(file);
}

document.getElementById('upload-btn').addEventListener('click', function() {
  document.getElementById('upload-input').click();
});

document.getElementById('upload-input').addEventListener('change', function(e) {
  var f = e.target.files[0];
  if (f) { this.value = ''; _parseUpload(f); }
});

document.getElementById('upload-clear').addEventListener('click', function() {
  S.uploadChrMap = {};
  S.sortMode = 'default';
  document.getElementById('sort-select').value = 'default';
  document.getElementById('upload-status').style.display = 'none';
  this.style.display = 'none';
});
