document.getElementById('ai-form').addEventListener('submit', function(e) {
  e.preventDefault();
  var q = document.getElementById('ai-input').value.trim();
  if (!q) return;
  var btn = document.getElementById('ai-submit');
  btn.disabled = true; btn.textContent = '\u2026';
  document.getElementById('ai-explanation').textContent = 'Thinking\u2026';
  queryAI(q).then(function(res) {
    S.aiGenes = Array.isArray(res.genes) ? res.genes : [];
    document.getElementById('ai-explanation').textContent = res.explanation || '';
  }).catch(function(err) {
    document.getElementById('ai-explanation').textContent = 'Error: ' + err.message;
  }).finally(function() {
    btn.disabled = false; btn.textContent = 'Ask';
  });
});
