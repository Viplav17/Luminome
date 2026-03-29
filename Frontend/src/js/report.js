(function () {
  var btn = document.getElementById('report-btn');
  if (!btn) return;

  btn.addEventListener('click', function () {
    if (!S.uploadChrMap || !Object.keys(S.uploadChrMap).length) {
      alert('Upload a CSV/TSV file first.'); return;
    }
    btn.textContent = 'Generating\u2026'; btn.disabled = true;
    try { generateReport(); } catch (e) { alert('PDF error: ' + e.message); }
    btn.textContent = '\u2193 PDF Report'; btn.disabled = false;
  });

  function generateReport() {
    var jsPDF = window.jspdf.jsPDF;
    var doc = new jsPDF({ unit: 'mm', format: 'a4' });
    var W = 210, margin = 16, cw = W - margin * 2;
    var y = margin;

    function addPage() { doc.addPage(); y = margin; }
    function checkPage(need) { if (y + need > 280) addPage(); }

    function heading(text, size) {
      checkPage(12);
      doc.setFontSize(size || 14);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(90, 60, 200);
      doc.text(text, margin, y); y += (size || 14) * 0.5 + 2;
    }

    function line(text, opts) {
      opts = opts || {};
      checkPage(6);
      doc.setFontSize(opts.size || 9);
      doc.setFont('helvetica', opts.bold ? 'bold' : 'normal');
      doc.setTextColor(opts.color || '#333333');
      var lines = doc.splitTextToSize(text, cw);
      doc.text(lines, margin, y);
      y += lines.length * (opts.size || 9) * 0.4 + 1.5;
    }

    function separator() {
      checkPage(4);
      doc.setDrawColor(180, 180, 210);
      doc.setLineWidth(0.3);
      doc.line(margin, y, W - margin, y);
      y += 3;
    }

    // ── Gather data ──
    var map = S.uploadChrMap || {};
    var sex = S.uploadSex || 'Unknown';
    var chrKeys = Object.keys(map).sort(function (a, b) {
      var na = a === 'X' ? 23 : a === 'Y' ? 24 : parseInt(a);
      var nb = b === 'X' ? 23 : b === 'Y' ? 24 : parseInt(b);
      return na - nb;
    });
    var totalRows = 0, critRows = [], modRows = [], lowRows = 0;
    chrKeys.forEach(function (chr) {
      map[chr].rows.forEach(function (r) {
        totalRows++;
        if (r.sev === 'critical') critRows.push({ chr: chr, gene: r.gene, variant: r.variant, zyg: r.zyg, protein: r.protein || '' });
        else if (r.sev === 'moderate') modRows.push({ chr: chr, gene: r.gene, variant: r.variant, zyg: r.zyg, protein: r.protein || '' });
        else lowRows++;
      });
    });

    var uniqueGenes = {};
    chrKeys.forEach(function (chr) {
      map[chr].rows.forEach(function (r) {
        if (r.gene) uniqueGenes[r.gene.toUpperCase()] = true;
      });
    });

    // ── Title page ──
    doc.setFontSize(22);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(60, 40, 160);
    doc.text('Luminome', margin, y); y += 8;
    doc.setFontSize(16);
    doc.setTextColor(50, 50, 80);
    doc.text('Genomic Analysis Summary Report', margin, y); y += 10;
    separator();

    line('Generated: ' + new Date().toLocaleString(), { size: 8, color: '#888888' });
    line('Platform: Luminome \u2014 luminome.tech', { size: 8, color: '#888888' });
    line('This report is for research / informational purposes only. Not a clinical diagnosis.', { size: 7, color: '#aa4444', bold: true });
    y += 4;

    // ── Patient overview ──
    heading('Patient Overview');
    line('Biological sex: ' + sex.charAt(0).toUpperCase() + sex.slice(1), { bold: true });
    line('Total variant calls: ' + totalRows.toLocaleString());
    line('Chromosomes with data: ' + chrKeys.length + ' / 24');
    line('Unique genes analyzed: ' + Object.keys(uniqueGenes).length);
    y += 2;

    // ── Summary box ──
    heading('Variant Classification Summary');
    line('Pathogenic / Likely Pathogenic (critical): ' + critRows.length, { bold: true, color: '#cc2222' });
    line('Variants of Uncertain Significance (VUS): ' + modRows.length, { bold: true, color: '#cc8800' });
    line('Benign / Likely Benign: ' + lowRows.toLocaleString(), { color: '#228844' });
    y += 4;
    separator();

    // ── Critical findings ──
    if (critRows.length) {
      heading('Critical Findings \u2014 Pathogenic Variants', 13);
      line('These variants are classified as pathogenic or likely pathogenic and warrant clinical follow-up.', { size: 8, color: '#666666' });
      y += 2;
      critRows.forEach(function (r, i) {
        checkPage(14);
        line((i + 1) + '.  Gene: ' + r.gene + '  \u00b7  Chr ' + r.chr, { bold: true, size: 10 });
        line('    Variant: ' + r.variant + (r.protein ? '  (' + r.protein + ')' : ''), { size: 9 });
        line('    Zygosity: ' + r.zyg, { size: 8, color: '#555555' });
        y += 1;
      });
      y += 2;
      separator();
    }

    // ── VUS summary ──
    if (modRows.length) {
      heading('Variants of Uncertain Significance (VUS)', 13);
      line(modRows.length + ' moderate-impact variants detected. These may or may not be clinically relevant.', { size: 8, color: '#666666' });
      y += 2;
      var vusGenes = {};
      modRows.forEach(function (r) { vusGenes[r.gene] = (vusGenes[r.gene] || 0) + 1; });
      var vusEntries = Object.entries(vusGenes).sort(function (a, b) { return b[1] - a[1]; });
      var maxVus = Math.min(vusEntries.length, 25);
      for (var vi = 0; vi < maxVus; vi++) {
        line('\u2022  ' + vusEntries[vi][0] + ' \u2014 ' + vusEntries[vi][1] + ' variant' + (vusEntries[vi][1] > 1 ? 's' : ''), { size: 9 });
      }
      if (vusEntries.length > 25) {
        line('... and ' + (vusEntries.length - 25) + ' more genes', { size: 8, color: '#888888' });
      }
      y += 2;
      separator();
    }

    // ── Per-chromosome breakdown ──
    heading('Chromosome Breakdown', 13);
    chrKeys.forEach(function (chr) {
      var rows = map[chr].rows;
      var c = rows.filter(function (r) { return r.sev === 'critical'; }).length;
      var m = rows.filter(function (r) { return r.sev === 'moderate'; }).length;
      var b = rows.length - c - m;
      var severity = map[chr].maxSev;
      var tag = severity === 'critical' ? ' \u26a0' : '';
      checkPage(5);
      line('Chr ' + chr + ': ' + rows.length + ' variants (' + c + ' critical, ' + m + ' VUS, ' + b + ' benign)' + tag, {
        size: 9, bold: c > 0, color: c > 0 ? '#cc2222' : '#333333'
      });
    });
    y += 2;
    separator();

    // ── Clinical recommendations (boilerplate) ──
    heading('Recommendations', 12);
    if (critRows.length) {
      line('\u2022  Genetic counseling is recommended for the ' + critRows.length + ' pathogenic variant(s) identified.', { size: 9 });
      line('\u2022  Cascade testing of first-degree relatives should be considered.', { size: 9 });
      line('\u2022  Refer to NCCN guidelines for management based on specific gene findings.', { size: 9 });
    }
    if (modRows.length) {
      line('\u2022  VUS findings (' + modRows.length + ') should be periodically re-evaluated as classification databases update.', { size: 9 });
    }
    line('\u2022  This report does not replace clinical judgment. All findings should be interpreted by a qualified geneticist.', { size: 9 });
    y += 4;

    // ── Footer ──
    separator();
    line('Luminome \u2014 Interactive Genomic Atlas', { size: 8, color: '#888888' });
    line('luminome.tech  |  For research use only  |  Not a medical device', { size: 7, color: '#aaaaaa' });

    // ── Save ──
    var filename = 'luminome_report_' + sex + '_' + new Date().toISOString().slice(0, 10) + '.pdf';
    doc.save(filename);
  }
})();
