document.getElementById('ai-form').addEventListener('submit', function(e) {
  e.preventDefault();
  var q = document.getElementById('ai-input').value.trim();
  if (!q) return;
  var btn = document.getElementById('ai-submit');
  btn.disabled = true; btn.textContent = '\u2026';
  document.getElementById('ai-explanation').textContent = 'Thinking\u2026';
  var known = (S.genes || []).map(function(g) { return g.id; }).filter(Boolean);
  queryAI(q, known).then(function(res) {
    var genes = Array.isArray(res.genes) ? res.genes : [];

    genes.forEach(function(gid) {
      var exists = S.genes.some(function(g) { return g.id === gid; });
      if (!exists) {
        S.genes.push({
          id: gid, chr: '1', pos: 0.5, type: 'other',
          muts: [], dis: [], drugs: [], trials: [],
          loc: '', desc: 'AI-identified gene',
          _aiPlaceholder: true,
        });
      }
    });

    if (known.length > 0) {
      var allowed = new Set(known.concat(genes));
      S.aiGenes = genes.filter(function(g) { return allowed.has(g); });
    } else {
      S.aiGenes = genes;
    }
    document.getElementById('ai-explanation').textContent =
      (res.explanation || '') + (S.aiGenes.length ? ' (' + S.aiGenes.length + ' genes highlighted)' : '');
    if (typeof updatePairDock === 'function') updatePairDock();

    S.aiGenes.forEach(function(gid) {
      getGene(gid).then(function(gene) {
        if (!gene || gene.error) return;
        var idx = S.genes.findIndex(function(g) { return g.id === gid; });
        if (idx >= 0) Object.assign(S.genes[idx], gene);
        else S.genes.push(gene);
      }).catch(function() {});
    });
  }).catch(function(err) {
    document.getElementById('ai-explanation').textContent = 'Error: ' + err.message;
  }).finally(function() {
    btn.disabled = false; btn.textContent = 'Ask';
  });
});
