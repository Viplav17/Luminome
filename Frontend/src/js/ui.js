var cvEl = document.getElementById('genome-canvas');
var panel = document.getElementById('info-panel');
var backBtn = document.getElementById('back-btn');
var zoomWrap = document.getElementById('zoom-controls');
var zoomInBtn = document.getElementById('zoom-in-btn');
var zoomOutBtn = document.getElementById('zoom-out-btn');
var openDnaBtn = document.getElementById('panel-open-dna');
var pairDock = document.getElementById('pair-dock');
var drugClassSelect = document.getElementById('drug-class-select');

function mPos(e) {
  var r = cvEl.getBoundingClientRect();
  return {x: e.clientX - r.left, y: e.clientY - r.top};
}

function hitChr(p) {
  return chrHits.find(function(h) {
    return p.x >= h.bx && p.x <= h.bx+h.bw && p.y >= h.by && p.y <= h.by+h.bh;
  }) || null;
}

function hitGene(p) {
  if (S.view === 'pair') {
    return chrDetailHits.find(function(h) {
      return p.x >= h.bx && p.x <= h.bx + h.bw && p.y >= h.by && p.y <= h.by + h.bh;
    }) || null;
  }
  return geneHits.find(function(h) {
    return Math.hypot(p.x-h.cx, p.y-h.cy) <= h.r;
  }) || null;
}

cvEl.addEventListener('mousemove', function(e) {
  if (S.view !== 'genome' && S.view !== 'pair') return;
  var p = mPos(e), g = hitGene(p), c = hitChr(p);
  if (S.view === 'pair') {
    S.hovGene = g ? g.gene : null;
    cvEl.style.cursor = g ? 'pointer' : 'default';
    return;
  }
  S.hovGene = g ? g.gene : null;
  S.hovChr  = g ? g.gene.chr : (c ? c.id : null);
  cvEl.style.cursor = (g || c) ? 'pointer' : 'crosshair';
});

cvEl.addEventListener('click', function(e) {
  if (S.view !== 'genome' && S.view !== 'pair') return;
  var p = mPos(e), g = hitGene(p), c = hitChr(p);
  if (S.view === 'pair') {
    if (!g) return;
    S.selGene = g.gene;
    S.selMutation = (Array.isArray(g.gene.muts) && g.gene.muts.length) ? (g.gene.muts[0].hgvs || g.gene.muts[0]) : null;
    openPanel(g.gene);
    loadDetail(g.gene.id);
    return;
  }
  if (g) {
    S.selGene = g.gene; S.selChr = g.gene.chr;
    S.selMutation = (Array.isArray(g.gene.muts) && g.gene.muts.length) ? (g.gene.muts[0].hgvs || g.gene.muts[0]) : null;
    openPanel(g.gene); loadDetail(g.gene.id);
    return;
  }
  if (c) {
    S.selChr = c.id; S.view = 'pair'; S.selGene = null; S.selMutation = null;
    backBtn.classList.remove('hidden');
    zoomWrap.classList.remove('hidden');
    if (pairDock) { pairDock.classList.remove('hidden'); updatePairDock(); }
  }
});

backBtn.addEventListener('click', function() {
  if (S.view === 'dna') {
    S.view = 'pair';
    return;
  }
  if (S.view === 'pair') {
    goHome();
  }
});

function goHome() {
  S.view = 'genome'; S.selChr = null; S.selGene = null; S.selMutation = null;
  backBtn.classList.add('hidden');
  zoomWrap.classList.add('hidden');
  if (pairDock) pairDock.classList.add('hidden');
  closePanel();
}

document.getElementById('logo').addEventListener('click', goHome);

document.getElementById('panel-close').addEventListener('click', closePanel);

document.querySelectorAll('.chip').forEach(function(chip) {
  chip.addEventListener('click', function() {
    document.querySelectorAll('.chip').forEach(function(c) { c.classList.remove('active'); });
    chip.classList.add('active');
    var f = chip.dataset.filter;
    S.filter = f === 'null' ? null : f;
    if (S.filter) {
      chip.textContent = chip.textContent.replace(/\s*\(.*\)$/, '') + ' \u2026';
      getDiseaseGenes(S.filter).then(function(genes) {
        S.hlDisease = (genes||[]).map(function(g) { return g.id || g.symbol || g; });
        var matched = S.genes.filter(function(sg) { return S.hlDisease.indexOf(sg.id) >= 0; }).length;
        chip.textContent = chip.textContent.replace(/\s*\u2026$/, '') + ' (' + matched + ')';
        updatePairDock();
      }).catch(function(){
        S.hlDisease = [];
        chip.textContent = chip.textContent.replace(/\s*\u2026$/, '');
      });
    } else {
      S.hlDisease = [];
      document.querySelectorAll('.chip').forEach(function(c) {
        c.textContent = c.textContent.replace(/\s*\(.*\)$/, '');
      });
      updatePairDock();
    }
  });
});

if (drugClassSelect) {
  drugClassSelect.addEventListener('change', function() {
    var v = this.value;
    if (!v) {
      S.hlDrug = [];
      updatePairDock();
      return;
    }
    getDrugClassGenes(v).then(function(genes) {
      S.hlDrug = (genes || []).map(function(g) { return g.id || g.symbol || g; });
      updatePairDock();
    }).catch(function() { S.hlDrug = []; });
  });
}

function updatePairDock() {
  if (!pairDock) return;
  if (S.view !== 'pair' || !S.selChr) return;
  var chr = S.selChr;
  var chrLabel = chr;
  if (chr === 'X' && S.uploadSex === 'female') chrLabel = 'XX';
  else if (chr === 'X' && S.uploadSex !== 'female') chrLabel = 'XY';
  document.getElementById('pair-dock-title').textContent = 'Chr ' + chrLabel + ' — services';
  var upCount = 0;
  if (S.uploadChrMap && S.uploadChrMap[chr]) upCount += S.uploadChrMap[chr].rows.length;
  if (chr === 'X' && S.uploadSex !== 'female' && S.uploadChrMap && S.uploadChrMap['Y']) upCount += S.uploadChrMap['Y'].rows.length;
  var elU = document.getElementById('pair-dock-upload');
  elU.textContent = upCount > 0
    ? ('Your upload: ' + upCount + ' variant rows on this chromosome.')
    : 'No rows from your CSV/TSV on this chromosome yet — upload a file to compare.';
  var bits = [];
  if ((S.hlDisease || []).length) bits.push('Disease filter: ' + S.hlDisease.length + ' genes (cyan)');
  if ((S.hlDrug || []).length) bits.push('Drug class: ' + S.hlDrug.length + ' targets (magenta)');
  if ((S.aiGenes || []).length) bits.push('AI query: ' + S.aiGenes.length + ' genes (amber)');
  document.getElementById('pair-dock-filters').textContent = bits.length ? bits.join(' · ') : 'No filters highlighting — choose a disease category, drug class, or ask the AI.';
}

function uploadRowsForGene(geneId) {
  var out = [];
  var gid = String(geneId || '').toUpperCase();
  var map = S.uploadChrMap || {};
  Object.keys(map).forEach(function(chr) {
    map[chr].rows.forEach(function(r) {
      if (String(r.gene || '').toUpperCase() === gid) out.push(r);
    });
  });
  return out;
}

function doSearch() {
  var input = document.getElementById('search-input');
  var fb = document.getElementById('search-feedback');
  var q = input.value.trim().toUpperCase();
  if (!q) return;
  fb.textContent = 'Searching\u2026'; fb.className = '';

  var local = S.genes.find(function(g) { return g.id === q; });
  if (local) {
    fb.textContent = ''; fb.className = 'ok';
    S.selGene = local; S.selChr = local.chr; S.view = 'pair';
    backBtn.classList.remove('hidden');
    zoomWrap.classList.remove('hidden');
    if (pairDock) { pairDock.classList.remove('hidden'); updatePairDock(); }
    openPanel(local); loadDetail(local.id);
    return;
  }

  getGene(q).then(function(gene) {
    if (!gene || gene.error) {
      fb.textContent = 'No genetic sequence found for "' + q + '"';
      fb.className = 'error';
      return;
    }
    fb.textContent = gene.id + ' found'; fb.className = 'ok';
    S.selGene = gene; S.selChr = gene.chr;
    var idx = S.genes.findIndex(function(g) { return g.id === gene.id; });
    if (idx < 0) S.genes.push(gene); else Object.assign(S.genes[idx], gene);
    S.view = 'pair';
    backBtn.classList.remove('hidden');
    zoomWrap.classList.remove('hidden');
    if (pairDock) { pairDock.classList.remove('hidden'); updatePairDock(); }
    openPanel(gene); loadDetail(gene.id);
  }).catch(function(err) {
    fb.textContent = 'No genetic sequence found for "' + q + '"';
    fb.className = 'error';
  });
}

document.getElementById('search-input').addEventListener('keydown', function(e) {
  if (e.key !== 'Enter') return;
  doSearch();
});

document.getElementById('search-btn').addEventListener('click', doSearch);

function openPanel(gene) {
  document.getElementById('panel-gene-name').textContent = gene.id;
  var pt = document.getElementById('panel-gene-type');
  pt.textContent = gene.type === 'ts' ? 'TSG' : gene.type === 'onco' ? 'Oncogene' : 'Other';
  pt.className = gene.type === 'ts' ? 'tsg' : gene.type === 'onco' ? 'onco' : 'other';
  document.getElementById('panel-gene-loc').textContent  = gene.loc  || '';
  document.getElementById('panel-gene-desc').textContent = gene.desc || '';
  var upRows = uploadRowsForGene(gene.id);
  fillList('panel-upload-rows', upRows, formatUploadRow, 60);
  fillList('panel-mutations', gene.muts   || [], function(m) {
    var h = m.hgvs || m;
    var p = m.pathogenicity ? ' (' + m.pathogenicity + ')' : '';
    return h + p;
  }, 40);
  fillList('panel-diseases',  gene.dis    || [], function(d) {
    var n = d.name || d;
    return d.score != null ? n + ' (score ' + Number(d.score).toFixed(2) + ')' : n;
  }, 35);
  var sym = gene.symptoms || [];
  var sn = document.getElementById('panel-symptoms-note');
  if (sn) {
    sn.textContent = sym.length
      ? 'Clinical and ontology-linked text from associated disease entries (EFO).'
      : 'No ontology description snippets returned — see linked diseases.';
  }
  fillList('panel-symptoms', sym, function(s) { return s; }, 25);
  fillList('panel-drugs',     gene.drugs  || [], formatDrugLine, 35);
  fillList('panel-trials',    gene.trials || [], function(t) {
    var title = t.title || t.nctId || t;
    var ph = t.phase ? ' · ' + t.phase : '';
    var st = t.status ? ' (' + t.status + ')' : '';
    return title + ph + st;
  }, 25);
  if (openDnaBtn) openDnaBtn.classList.remove('hidden');
  panel.classList.remove('hidden');
}

function formatUploadRow(r) {
  var parts = [r.variant || '\u2014', r.sev || '', r.zyg || ''].filter(Boolean);
  if (r.tx) parts.push('tx ' + r.tx);
  if (r.protein) parts.push(r.protein);
  if (r.ref || r.alt) parts.push((r.ref || '?') + '>' + (r.alt || '?'));
  if (r.af) parts.push('AF ' + r.af);
  if (r.depth !== '' && r.depth != null) parts.push('depth ' + r.depth);
  if (r.qual !== '' && r.qual != null) parts.push('Q ' + r.qual);
  return parts.join(' \u00b7 ');
}

function formatDrugLine(d) {
  var n = d.name || d.drugId || d;
  var ph = d.phase != null && d.phase !== '' ? ' · Phase ' + d.phase : '';
  var st = d.status ? ' · ' + d.status : '';
  return n + ph + st;
}

function fillList(id, arr, fn, maxItems) {
  maxItems = maxItems == null ? 40 : maxItems;
  var ul = document.getElementById(id);
  if (!ul) return;
  ul.innerHTML = arr.length
    ? arr.slice(0, maxItems).map(function(x) {
        return '<li>' + String(fn(x)||'').replace(/</g,'&lt;') + '</li>';
      }).join('')
    : '<li class="loading">\u2014</li>';
}

function closePanel() {
  panel.classList.add('hidden');
  if (openDnaBtn) openDnaBtn.classList.add('hidden');
  // Keep selGene while in DNA view so the helix render stays visible
  if (S.view !== 'dna') S.selGene = null;
}

function loadDetail(id) {
  ['panel-upload-rows','panel-mutations','panel-diseases','panel-symptoms','panel-drugs','panel-trials'].forEach(function(lid) {
    var el = document.getElementById(lid);
    if (el) el.innerHTML = '<li class="loading">Loading\u2026</li>';
  });
  Promise.all([
    getGene(id).catch(function() { return null; }),
    getDrugs(id).catch(function() { return []; }),
    getTrials(id).catch(function() { return []; }),
  ]).then(function(res) {
    var gene = res[0], drugs = res[1], trials = res[2];
    if (gene) {
      document.getElementById('panel-gene-desc').textContent = gene.desc || '';
      var upRows = uploadRowsForGene(gene.id);
      fillList('panel-upload-rows', upRows, formatUploadRow, 60);
      fillList('panel-mutations', gene.muts||[], function(m){ return (m.hgvs||m) + (m.pathogenicity ? ' ('+m.pathogenicity+')' : ''); }, 40);
      fillList('panel-diseases',  gene.dis ||[], function(d){ return d.name||d; }, 35);
      var sym = gene.symptoms || [];
      var sn = document.getElementById('panel-symptoms-note');
      if (sn) {
        sn.textContent = sym.length
          ? 'Clinical and ontology-linked text from associated disease entries (EFO).'
          : 'No ontology description snippets returned — see linked diseases.';
      }
      fillList('panel-symptoms', sym, function(s) { return s; }, 25);
      var idx = S.genes.findIndex(function(g){return g.id===gene.id;});
      if (idx >= 0) Object.assign(S.genes[idx], gene);
    }
    fillList('panel-drugs',  drugs  || [], formatDrugLine, 35);
    fillList('panel-trials', trials || [], function(t) {
      var title = t.title || t.nctId || t;
      var ph = t.phase ? ' · ' + t.phase : '';
      var st = t.status ? ' (' + t.status + ')' : '';
      return title + ph + st;
    }, 25);
  });
}

document.getElementById('sort-select').addEventListener('change', function() {
  S.sortMode = this.value;
});

getGenes().then(function(genes) {
  S.genes = genes || [];
  document.getElementById('gene-count').textContent = S.genes.length + ' genes';
}).catch(function(err) {
  console.warn('[api]', err.message);
  document.getElementById('gene-count').textContent = 'Backend offline';
});

document.getElementById('panel-mutations').addEventListener('click', function(e) {
  var li = e.target.closest('li');
  if (!li) return;
  var t = (li.textContent || '').trim();
  if (!t || t === '—' || t === 'Loading…') return;
  S.selMutation = t;
});

if (openDnaBtn) {
  openDnaBtn.addEventListener('click', function() {
    if (!S.selGene) return;
    S.view = 'dna';
    backBtn.classList.remove('hidden');
    zoomWrap.classList.remove('hidden');
  });
}

function clampZoom(v) {
  return Math.max(0.6, Math.min(3.5, v));
}

if (zoomInBtn) {
  zoomInBtn.addEventListener('click', function() {
    if (S.view === 'dna') S.dnaZoom = clampZoom(S.dnaZoom + 0.2);
    else if (S.view === 'pair') S.detailZoom = clampZoom(S.detailZoom + 0.15);
  });
}

if (zoomOutBtn) {
  zoomOutBtn.addEventListener('click', function() {
    if (S.view === 'dna') S.dnaZoom = clampZoom(S.dnaZoom - 0.2);
    else if (S.view === 'pair') S.detailZoom = clampZoom(S.detailZoom - 0.15);
  });
}
