var cvEl = document.getElementById('genome-canvas');
var panel = document.getElementById('info-panel');
var backBtn = document.getElementById('back-btn');

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
  return geneHits.find(function(h) {
    return Math.hypot(p.x-h.cx, p.y-h.cy) <= h.r;
  }) || null;
}

cvEl.addEventListener('mousemove', function(e) {
  if (S.view !== 'genome') return;
  var p = mPos(e), g = hitGene(p), c = hitChr(p);
  S.hovGene = g ? g.gene : null;
  S.hovChr  = g ? g.gene.chr : (c ? c.id : null);
  cvEl.style.cursor = (g || c) ? 'pointer' : 'crosshair';
});

cvEl.addEventListener('click', function(e) {
  if (S.view !== 'genome') return;
  var p = mPos(e), g = hitGene(p), c = hitChr(p);
  if (g) {
    S.selGene = g.gene; S.selChr = g.gene.chr;
    openPanel(g.gene); loadDetail(g.gene.id);
    return;
  }
  if (c) {
    S.selChr = c.id; S.view = 'pair';
    backBtn.classList.remove('hidden');
    if (window.Viewer) Viewer.showPair(c.id, S.selGene && S.selGene.chr === c.id ? S.selGene : null);
  }
});

backBtn.addEventListener('click', function() {
  if (S.view === 'dna') {
    S.view = 'pair';
    if (window.Viewer) Viewer.showPair(S.selChr, S.selGene);
  } else {
    S.view = 'genome'; S.selChr = null;
    if (window.Viewer) Viewer.hide();
    backBtn.classList.add('hidden');
    closePanel();
  }
});

document.getElementById('panel-close').addEventListener('click', closePanel);

document.querySelectorAll('.chip').forEach(function(chip) {
  chip.addEventListener('click', function() {
    document.querySelectorAll('.chip').forEach(function(c) { c.classList.remove('active'); });
    chip.classList.add('active');
    var f = chip.dataset.filter;
    S.filter = f === 'null' ? null : f;
    if (S.filter) {
      getDiseaseGenes(S.filter).then(function(genes) {
        S.aiGenes = (genes||[]).map(function(g) { return g.id || g.symbol || g; });
      }).catch(function(){});
    } else {
      S.aiGenes = [];
    }
  });
});

document.getElementById('search-input').addEventListener('keydown', function(e) {
  if (e.key !== 'Enter') return;
  var q = this.value.trim().toUpperCase(); if (!q) return;
  getGene(q).then(function(gene) {
    if (!gene) return;
    S.selGene = gene; S.selChr = gene.chr;
    var idx = S.genes.findIndex(function(g) { return g.id === gene.id; });
    if (idx < 0) S.genes.push(gene); else Object.assign(S.genes[idx], gene);
    openPanel(gene); loadDetail(gene.id);
  }).catch(function(){});
});

function openPanel(gene) {
  document.getElementById('panel-gene-name').textContent = gene.id;
  var pt = document.getElementById('panel-gene-type');
  pt.textContent = gene.type === 'ts' ? 'TSG' : gene.type === 'onco' ? 'Oncogene' : 'Other';
  pt.className = gene.type === 'ts' ? 'tsg' : gene.type === 'onco' ? 'onco' : 'other';
  document.getElementById('panel-gene-loc').textContent  = gene.loc  || '';
  document.getElementById('panel-gene-desc').textContent = gene.desc || '';
  fillList('panel-mutations', gene.muts   || [], function(m) { return m.hgvs  || m; });
  fillList('panel-diseases',  gene.dis    || [], function(d) { return d.name  || d; });
  fillList('panel-drugs',     gene.drugs  || [], function(d) { return d.name  || d; });
  fillList('panel-trials',    gene.trials || [], function(t) { return t.title || t.nctId || t; });
  panel.classList.remove('hidden');
}

function fillList(id, arr, fn) {
  var ul = document.getElementById(id);
  ul.innerHTML = arr.length
    ? arr.slice(0, 8).map(function(x) {
        return '<li>' + String(fn(x)||'').replace(/</g,'&lt;') + '</li>';
      }).join('')
    : '<li class="loading">\u2014</li>';
}

function closePanel() { panel.classList.add('hidden'); S.selGene = null; }

function loadDetail(id) {
  ['panel-mutations','panel-diseases','panel-drugs','panel-trials'].forEach(function(lid) {
    document.getElementById(lid).innerHTML = '<li class="loading">Loading\u2026</li>';
  });
  Promise.all([
    getGene(id).catch(function() { return null; }),
    getDrugs(id).catch(function() { return []; }),
    getTrials(id).catch(function() { return []; }),
  ]).then(function(res) {
    var gene = res[0], drugs = res[1], trials = res[2];
    if (gene) {
      document.getElementById('panel-gene-desc').textContent = gene.desc || '';
      fillList('panel-mutations', gene.muts||[], function(m){return m.hgvs||m;});
      fillList('panel-diseases',  gene.dis ||[], function(d){return d.name||d;});
      var idx = S.genes.findIndex(function(g){return g.id===gene.id;});
      if (idx >= 0) Object.assign(S.genes[idx], gene);
    }
    fillList('panel-drugs',  drugs  || [], function(d){return d.name||d;});
    fillList('panel-trials', trials || [], function(t){return t.title||t.nctId||t;});
  });
}

getGenes().then(function(genes) {
  S.genes = genes || [];
  document.getElementById('gene-count').textContent = S.genes.length + ' genes';
}).catch(function(err) {
  console.warn('[api]', err.message);
  document.getElementById('gene-count').textContent = 'Backend offline';
});
