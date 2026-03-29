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

function _normSex(v) {
  var s = String(v || '').trim().toLowerCase();
  if (!s) return null;
  if (/^(male|man|m|xy|46,xy|46xy)$/.test(s)) return 'male';
  if (/^(female|woman|f|xx|46,xx|46xx)$/.test(s)) return 'female';
  return null;
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
      sex:     _col(hdrs, [/^sex$/, /^gender$/, /^biological[._\s-]?sex$/, /^karyotype$/]),
      depth:   _col(hdrs, [/read[_\s-]?depth|^depth$|coverage|dp\b/i]),
      qual:    _col(hdrs, [/quality|qual|gq\b|score/i]),
      tx:      _col(hdrs, [/transcript|nm_|refseq.*rna/i]),
      protein: _col(hdrs, [/protein|(^p\.)/i, /^aa$/]),
      ref:     _col(hdrs, [/^ref[_\s-]?allele$|^ref$/i]),
      alt:     _col(hdrs, [/^alt[_\s-]?allele$|^alt$/i]),
      af:      _col(hdrs, [/gnomad|allele[_\s-]?freq|af\b|maf/i]),
    };

    if (ci.chr < 0) {
      alert('Missing required column: "chr" or "chromosome".\nDetected columns: ' + hdrs.join(', '));
      return;
    }

    var map = {}, total = 0;
    var sexVotes = {male:0, female:0};
    var hasX = false, hasY = false;
    for (var i = 1; i < lines.length; i++) {
      var cols = lines[i].split(sep).map(function(c){ return c.trim().replace(/^["']|["']$/g,''); });
      var chr  = _normChr(cols[ci.chr] || '');
      if (!CHR_DATA[chr]) continue;
      if (chr === 'X') hasX = true;
      if (chr === 'Y') hasY = true;
      if (ci.sex >= 0) {
        var sx = _normSex(cols[ci.sex]);
        if (sx) sexVotes[sx]++;
      }
      var sev = _parseSev(ci.sev >= 0 ? cols[ci.sev] : '');
      if (!map[chr]) map[chr] = {rows:[], maxSev:'low'};
      map[chr].rows.push({
        gene:    ci.gene    >= 0 ? cols[ci.gene]    : '',
        variant: ci.variant >= 0 ? cols[ci.variant] : '',
        sev:     sev,
        zyg:     ci.zyg    >= 0 ? cols[ci.zyg]     : '',
        pos:     ci.pos    >= 0 ? parseFloat(cols[ci.pos])||0 : 0,
        depth:   ci.depth  >= 0 ? cols[ci.depth]   : '',
        qual:    ci.qual   >= 0 ? cols[ci.qual]    : '',
        tx:      ci.tx     >= 0 ? cols[ci.tx]      : '',
        protein: ci.protein>= 0 ? cols[ci.protein] : '',
        ref:     ci.ref    >= 0 ? cols[ci.ref]     : '',
        alt:     ci.alt    >= 0 ? cols[ci.alt]     : '',
        af:      ci.af     >= 0 ? cols[ci.af]      : '',
      });
      if (SEV_RANK[sev] > SEV_RANK[map[chr].maxSev]) map[chr].maxSev = sev;
      total++;
    }

    var uploadSex = null;
    if (sexVotes.male || sexVotes.female) {
      uploadSex = sexVotes.male >= sexVotes.female ? 'male' : 'female';
    } else if (hasY) {
      uploadSex = 'male';
    } else if (hasX) {
      uploadSex = 'female';
    }

    // ── Inject genes from upload into S.genes so pair view shows them ────────
    var genesBySymbol = {};
    Object.keys(map).forEach(function(chr) {
      map[chr].rows.forEach(function(row) {
        var gid = (row.gene || '').toUpperCase().trim();
        if (!gid) return;
        if (!genesBySymbol[gid]) {
          var chrLen = (CHR_DATA[chr] ? CHR_DATA[chr].l : 100) * 1e6;
          var normPos = row.pos > 0 ? row.pos / chrLen : 0.5;
          normPos = Math.min(Math.max(normPos, 0.05), 0.95);
          genesBySymbol[gid] = {
            id: gid, chr: chr, pos: normPos,
            type: row.sev === 'critical' ? 'ts' : row.sev === 'low' ? 'onco' : 'other',
            muts: [], dis: [], drugs: [], trials: [],
            loc: 'Chr ' + chr, desc: 'Uploaded variant',
            _uploaded: true,
          };
        }
        if (row.variant) genesBySymbol[gid].muts.push({ hgvs: row.variant });
      });
    });
    Object.keys(genesBySymbol).forEach(function(gid) {
      var idx = S.genes.findIndex(function(g) { return g.id === gid; });
      if (idx >= 0) {
        genesBySymbol[gid].muts.forEach(function(m) {
          var already = (S.genes[idx].muts || []).some(function(x) { return (x.hgvs || x) === (m.hgvs || m); });
          if (!already) {
            if (!S.genes[idx].muts) S.genes[idx].muts = [];
            S.genes[idx].muts.push(m);
          }
        });
      } else {
        S.genes.push(genesBySymbol[gid]);
      }
    });
    // ─────────────────────────────────────────────────────────────────────────

    S.uploadChrMap = map;
    S.uploadSex = uploadSex;
    if (S.uploadSex === 'male' && S.selChr === 'X') {
      S.view = 'genome';
      S.selChr = null;
      S.selGene = null;
    }
    if (S.uploadSex === 'female' && S.selChr === 'Y') {
      S.view = 'genome';
      S.selChr = null;
      S.selGene = null;
    }
    var affected = Object.keys(map).length;
    var st = document.getElementById('upload-status');
    st.textContent = affected + ' chr \u00b7 ' + total + ' variants' + (uploadSex ? ' \u00b7 ' + uploadSex.toUpperCase() : '');
    st.style.display = 'inline';
    document.getElementById('upload-clear').style.display = 'inline-flex';
    var rb = document.getElementById('report-btn');
    if (rb) rb.classList.remove('hidden');
    if (typeof updatePairDock === 'function') updatePairDock();
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
  S.uploadSex = null;
  // Remove genes that were injected from this upload
  S.genes = S.genes.filter(function(g) { return !g._uploaded; });
  S.sortMode = 'default';
  document.getElementById('sort-select').value = 'default';
  document.getElementById('upload-status').style.display = 'none';
  this.style.display = 'none';
  var dcs = document.getElementById('drug-class-select');
  if (dcs) dcs.value = '';
  var rb = document.getElementById('report-btn');
  if (rb) rb.classList.add('hidden');
  if (typeof updatePairDock === 'function') updatePairDock();
});
