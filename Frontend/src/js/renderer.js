var cv = document.getElementById('genome-canvas');
var ctx = cv.getContext('2d');

var COL = {
  bg:'#030711',           // near-black canvas background
  brd:'#2a5fbd',          // vivid blue chromosome border
  cen:'#c026d3',          // fuchsia centromere — clearly distinct
  ts:'#ff3560',           // bright red-pink  — tumor suppressors
  onco:'#00c8f5',         // vivid cyan       — oncogenes
  oth:'#00e898',          // vivid mint        — other genes
  ai:'#ffb700',           // vivid amber       — AI highlight
  disHl:'#22d3ee',        // cyan              — disease filter
  drugHl:'#e879f9',       // fuchsia           — drug class filter
  txt:'#dde8fa',          // blue-white text
  mut:'#7090b4',          // muted blue-gray labels
  acc:'#a78bfa',          // purple accent / hover
};

var CHR_DATA = {
  '1':{l:249,c:0.43},'2':{l:242,c:0.39},'3':{l:198,c:0.46},'4':{l:190,c:0.35},
  '5':{l:181,c:0.46},'6':{l:171,c:0.39},'7':{l:159,c:0.39},'8':{l:145,c:0.43},
  '9':{l:138,c:0.35},'10':{l:133,c:0.39},'11':{l:135,c:0.42},'12':{l:133,c:0.42},
  '13':{l:114,c:0.20},'14':{l:107,c:0.19},'15':{l:102,c:0.20},'16':{l:90,c:0.45},
  '17':{l:83,c:0.33},'18':{l:80,c:0.21},'19':{l:59,c:0.48},'20':{l:63,c:0.45},
  '21':{l:47,c:0.16},'22':{l:51,c:0.17},'X':{l:155,c:0.40},'Y':{l:59,c:0.28},
};

var CHR_ORD = ['1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','X','Y'];
var COLS = 6, ROWS = 4, MAX_L = 249;
var chrHits = [], geneHits = [], chrDetailHits = [];

function resize() {
  var dpr = window.devicePixelRatio || 1;
  cv.width = cv.offsetWidth * dpr;
  cv.height = cv.offsetHeight * dpr;
  ctx = cv.getContext('2d');
  ctx.scale(dpr, dpr);
}

function anyFilterActive() {
  return (S.aiGenes && S.aiGenes.length > 0)
      || (S.hlDrug && S.hlDrug.length > 0)
      || (S.hlDisease && S.hlDisease.length > 0);
}

function hlPriority(g) {
  if (!g || !g.id) return null;
  if (S.aiGenes.indexOf(g.id) >= 0) return 'ai';
  if ((S.hlDrug || []).indexOf(g.id) >= 0) return 'drug';
  if ((S.hlDisease || []).indexOf(g.id) >= 0) return 'dis';
  return null;
}

function gClr(g) {
  var h = hlPriority(g);
  if (h === 'ai') return COL.ai;
  if (h === 'drug') return COL.drugHl;
  if (h === 'dis') return COL.disHl;
  return g.type === 'ts' ? COL.ts : g.type === 'onco' ? COL.onco : COL.oth;
}

function rr(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x+r, y);
  ctx.lineTo(x+w-r, y); ctx.arcTo(x+w, y, x+w, y+r, r);
  ctx.lineTo(x+w, y+h-r); ctx.arcTo(x+w, y+h, x+w-r, y+h, r);
  ctx.lineTo(x+r, y+h); ctx.arcTo(x, y+h, x, y+h-r, r);
  ctx.lineTo(x, y+r); ctx.arcTo(x, y, x+r, y, r);
  ctx.closePath();
}

function drawChr(id, bx, by, bw, bh) {
  var d = CHR_DATA[id], r = bw * 0.45;
  var cy = by + d.c * bh, ph = cy - by, qh = bh - ph;
  var hov = S.hovChr === id || (id === 'X' && S.hovChr === 'XY') || (id === 'Y' && S.hovChr === 'XY');
  if (hov) {
    ctx.save();
    ctx.shadowColor = '#a78bfa'; ctx.shadowBlur = 14;
  }
  rr(bx, by, bw, ph, r);
  ctx.fillStyle = hov ? '#2050b4' : '#163a74'; ctx.fill();
  ctx.strokeStyle = hov ? COL.acc : COL.brd; ctx.lineWidth = hov ? 1.0 : 0.7; ctx.stroke();
  rr(bx, cy, bw, qh, r);
  ctx.fillStyle = hov ? '#1a449a' : '#0f2f5f'; ctx.fill();
  ctx.strokeStyle = hov ? COL.acc : COL.brd; ctx.lineWidth = hov ? 1.0 : 0.7; ctx.stroke();
  if (hov) ctx.restore();
  ctx.fillStyle = COL.cen; ctx.fillRect(bx, cy - 2, bw, 4);
}

function visGenes() {
  return S.genes;
}

function sortedOrd() {
  var m = S.uploadChrMap || {};
  var ord = [];
  for (var k = 0; k < CHR_ORD.length; k++) {
    var c = CHR_ORD[k];
    if (c === 'Y') continue;
    if (c === 'X') {
      if (S.uploadSex === 'female') { ord.push('X'); }
      else { ord.push('XY'); }
      continue;
    }
    ord.push(c);
  }
  if (S.sortMode === 'default' || !Object.keys(m).length) return ord;
  return ord.slice().sort(function(a, b) {
    var aid = a === 'XY' ? 'X' : a, bid = b === 'XY' ? 'X' : b;
    var ca = m[aid] ? m[aid].rows.length : 0, cb = m[bid] ? m[bid].rows.length : 0;
    if (a === 'XY') ca += (m['Y'] ? m['Y'].rows.length : 0);
    if (b === 'XY') cb += (m['Y'] ? m['Y'].rows.length : 0);
    if (S.sortMode === 'severity') {
      var sa = m[aid] ? SEV_RANK[m[aid].maxSev] : 0, sb = m[bid] ? SEV_RANK[m[bid].maxSev] : 0;
      if (sb !== sa) return sb - sa;
    }
    if (cb !== ca) return cb - ca;
    return CHR_ORD.indexOf(aid) - CHR_ORD.indexOf(bid);
  });
}

function drawGenome() {
  var W = cv.offsetWidth, H = cv.offsetHeight;
  ctx.fillStyle = COL.bg; ctx.fillRect(0, 0, W, H);
  var cw = W/COLS, ch = H/ROWS;
  chrHits = []; geneHits = [];
  var genes = visGenes();
  sortedOrd().forEach(function(id, i) {
    var col = i%COLS, row = Math.floor(i/COLS);
    var mx = col*cw + cw*0.5, my = row*ch + ch*0.5;
    var bw = 16, gap = 8;
    var isXY = id === 'XY';
    var isXX = id === 'X';
    var left_id  = isXY ? 'X' : (isXX ? 'X' : id);
    var right_id = isXY ? 'Y' : (isXX ? 'X' : id);
    var bh_left  = (CHR_DATA[left_id].l/MAX_L)*ch*0.78;
    var bh2      = (CHR_DATA[right_id].l/MAX_L)*ch*0.78;
    var bh_ref   = Math.max(bh_left, bh2);
    var bx1 = mx - bw - gap*0.5, bx2 = mx + gap*0.5;
    var by1 = my - bh_left*0.5, by2 = my - bh2*0.5;
    var cx1 = bx1 + bw*0.5, cx2 = bx2 + bw*0.5;
    var displayLabel = isXY ? 'XY' : (isXX ? 'XX' : id);
    var hitId = isXY ? 'X' : id;
    chrHits.push({id:hitId, bx:bx1, by:my-bh_ref*0.5, bw:bw*2+gap, bh:bh_ref, mx:mx});
    var uploadSlotRows = 0;
    var uploadMaxSev = 'low';
    if (S.uploadChrMap) {
      if (S.uploadChrMap[left_id]) {
        uploadSlotRows += S.uploadChrMap[left_id].rows.length;
        if (SEV_RANK[S.uploadChrMap[left_id].maxSev] > SEV_RANK[uploadMaxSev]) uploadMaxSev = S.uploadChrMap[left_id].maxSev;
      }
      if (isXY && S.uploadChrMap[right_id]) {
        uploadSlotRows += S.uploadChrMap[right_id].rows.length;
        if (SEV_RANK[S.uploadChrMap[right_id].maxSev] > SEV_RANK[uploadMaxSev]) uploadMaxSev = S.uploadChrMap[right_id].maxSev;
      }
    }
    if (uploadSlotRows > 0) {
      var gc = SEV_COL[uploadMaxSev];
      ctx.save();
      ctx.globalAlpha = 0.18; ctx.fillStyle = gc;
      rr(bx1-9, by1-9, bw*2+gap+18, bh_ref+18, 10); ctx.fill();
      ctx.globalAlpha = 0.55; ctx.strokeStyle = gc; ctx.lineWidth = 1.2;
      ctx.stroke(); ctx.restore();
      var bgy = by1 - 13;
      ctx.save();
      ctx.fillStyle = gc;
      ctx.beginPath(); ctx.arc(mx, bgy, 9, 0, Math.PI*2); ctx.fill();
      ctx.fillStyle = '#060a18';
      ctx.font = 'bold 8px JetBrains Mono, monospace';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(uploadSlotRows > 99 ? '99+' : String(uploadSlotRows), mx, bgy);
      ctx.restore();
    }
    drawChr(left_id,  bx1, by1, bw, bh_left);
    drawChr(right_id, bx2, by2, bw, bh2);
    ctx.font = '13px JetBrains Mono, monospace';
    ctx.fillStyle = S.hovChr === hitId ? COL.txt : COL.mut;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText(displayLabel, mx, my + bh_ref*0.5 + 6);
    var leftGenes = genes.filter(function(g){ return g.chr === left_id; });
    var rightGenes = isXY ? genes.filter(function(g){ return g.chr === right_id; }) : leftGenes;
    var filtering = anyFilterActive();
    var seenIds = {};

    function drawGeneDot(g, cx_pos, gy, isRight) {
      var hp = hlPriority(g);
      var isUploaded = !!g._uploaded;
      var dimmed = filtering && !hp;
      var gr = S.hovGene && S.hovGene.id === g.id ? 6 : (hp ? 5 : (isUploaded ? 4 : 3));
      if (dimmed) gr = 2;
      if (hp) {
        ctx.beginPath(); ctx.arc(cx_pos, gy, gr + 8, 0, Math.PI * 2);
        var glow = hp === 'ai' ? 'rgba(255,183,0,0.35)' : hp === 'drug' ? 'rgba(232,121,249,0.35)' : 'rgba(34,211,238,0.35)';
        ctx.fillStyle = glow; ctx.fill();
      }
      ctx.save();
      if (dimmed) {
        ctx.globalAlpha = 0.15;
        ctx.fillStyle = '#445';
      } else {
        ctx.shadowColor = gClr(g); ctx.shadowBlur = hp ? 14 : (isUploaded ? 10 : 6);
        ctx.fillStyle = gClr(g);
      }
      ctx.beginPath(); ctx.arc(cx_pos, gy, gr, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    leftGenes.forEach(function(g) {
      seenIds[g.id] = true;
      var gy = by1 + g.pos * bh_left;
      drawGeneDot(g, cx1, gy, false);
      if (!isXY) drawGeneDot(g, cx2, gy, true);
      geneHits.push({gene: g, cx: cx1, cy: gy, r: 8});
      if (!isXY) geneHits.push({gene: g, cx: cx2, cy: gy, r: 8});
    });
    if (isXY) {
      rightGenes.forEach(function(g) {
        var gy = by2 + g.pos * bh2;
        drawGeneDot(g, cx2, gy, true);
        if (!seenIds[g.id]) geneHits.push({gene: g, cx: cx2, cy: gy, r: 8});
      });
    }
  });
}

function drawChrDetail(chrId) {
  var d = CHR_DATA[chrId];
  if (!d) return;

  var W = cv.offsetWidth, H = cv.offsetHeight;
  ctx.fillStyle = COL.bg; ctx.fillRect(0, 0, W, H);
  chrDetailHits = [];

  var z = S.detailZoom || 1;
  var barH = Math.max(280, (H - 160) * z);
  var barW = Math.max(24, Math.min(40, W * 0.035));
  var barX = Math.round(W * 0.5 - barW * 0.5);
  var barY = Math.round(H * 0.5 - barH * 0.5);
  var cenY = barY + barH * d.c;

  rr(barX, barY, barW, barH, 13);
  ctx.fillStyle = 'rgba(20, 72, 185, 0.32)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(55, 135, 255, 0.72)';
  ctx.lineWidth = 1.0;
  ctx.stroke();

  for (var i = 0; i < 16; i++) {
    if (i % 2 === 0) {
      ctx.fillStyle = 'rgba(255,255,255,0.055)';
      ctx.fillRect(barX + 1, barY + barH * i / 16, barW - 2, barH / 16);
    }
  }

  ctx.save();
  ctx.shadowColor = COL.cen; ctx.shadowBlur = 10;
  ctx.beginPath();
  ctx.moveTo(barX, cenY - 14);
  ctx.bezierCurveTo(barX, cenY - 5, barX + barW, cenY - 5, barX + barW, cenY - 14);
  ctx.lineTo(barX + barW, cenY + 14);
  ctx.bezierCurveTo(barX + barW, cenY + 5, barX, cenY + 5, barX, cenY + 14);
  ctx.closePath();
  ctx.fillStyle = 'rgba(192, 38, 211, 0.65)';
  ctx.fill();
  ctx.restore();

  var chrLabel = chrId;
  if (chrId === 'X' && S.uploadSex === 'female') chrLabel = 'XX';
  else if (chrId === 'X' && S.uploadSex !== 'female') chrLabel = 'X / Y';

  ctx.fillStyle = 'rgba(80, 165, 255, 0.90)';
  ctx.font = 'bold 13px JetBrains Mono, monospace';
  ctx.textAlign = 'center';
  ctx.fillText('Chr ' + chrLabel, barX + barW / 2, barY - 16);
  ctx.fillStyle = COL.mut;
  ctx.font = '12px JetBrains Mono, monospace';
  ctx.textAlign = 'center';
  ctx.fillText(String(d.l) + ' Mb', barX + barW / 2, barY + barH + 20);

  var matchChrs = [chrId];
  if (chrId === 'X' && S.uploadSex !== 'female') matchChrs.push('Y');
  var genes = S.genes.filter(function(g) { return matchChrs.indexOf(g.chr) >= 0; })
    .sort(function(a, b) { return a.pos - b.pos; });

  if (genes.length === 0) {
    ctx.fillStyle = 'rgba(100, 116, 139, 0.7)';
    ctx.font = '14px DM Sans, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No genes loaded for this chromosome.', W * 0.5, barY + barH + 50);
    ctx.font = '12px DM Sans, sans-serif';
    ctx.fillText('Upload a CSV/TSV file or search for a gene.', W * 0.5, barY + barH + 70);
  }

  var filtering = anyFilterActive();

  genes.forEach(function(g, idx) {
    var gy2 = barY + barH * g.pos;
    var left = idx % 2 === 0;
    var x1 = left ? barX - 8 : barX + barW + 8;
    var len = 70 + (idx % 4) * 18;
    var x2 = left ? x1 - len : x1 + len;
    var col = gClr(g);
    var isSel = S.selGene && S.selGene.id === g.id;
    var hp = hlPriority(g);
    var isUploaded = !!g._uploaded;
    var dimmed = filtering && !hp && !isSel;

    ctx.save();
    if (dimmed) ctx.globalAlpha = 0.18;
    ctx.beginPath();
    ctx.moveTo(x1, gy2);
    ctx.lineTo(x2, gy2);
    var hlStroke = hp === 'ai' ? 'rgba(252,211,77,0.9)' : hp === 'drug' ? 'rgba(232,121,249,0.9)' : hp === 'dis' ? 'rgba(34,211,238,0.9)' : null;
    ctx.strokeStyle = (isSel || hp || isUploaded) ? (hlStroke || 'rgba(252,211,77,0.86)') : 'rgba(226,232,240,0.30)';
    ctx.lineWidth = (isSel || hp) ? 1.8 : (isUploaded ? 1.2 : 0.8);
    ctx.stroke();
    ctx.restore();

    var dotR = isSel ? 7 : (hp ? 6 : (isUploaded ? 5 : 4));
    if (dimmed) dotR = 3;

    if (hp && !dimmed) {
      ctx.beginPath(); ctx.arc(barX + barW / 2, gy2, dotR + 10, 0, Math.PI * 2);
      ctx.fillStyle = hp === 'ai' ? 'rgba(255,183,0,0.3)' : hp === 'drug' ? 'rgba(232,121,249,0.3)' : 'rgba(34,211,238,0.3)';
      ctx.fill();
    }

    ctx.save();
    if (dimmed) {
      ctx.globalAlpha = 0.18;
      ctx.fillStyle = '#445';
    } else if (isSel || hp) {
      ctx.shadowColor = hp === 'drug' ? '#e879f9' : hp === 'dis' ? '#22d3ee' : '#fcd34d';
      ctx.shadowBlur = 14;
      ctx.fillStyle = isSel ? '#fcd34d' : col;
    } else if (isUploaded) {
      ctx.shadowColor = col; ctx.shadowBlur = 10;
      ctx.fillStyle = col;
    } else {
      ctx.shadowBlur = 0;
      ctx.fillStyle = col;
    }
    ctx.beginPath();
    ctx.arc(barX + barW / 2, gy2, dotR, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    var lx = left ? (x2 - 5) : (x2 + 5);
    ctx.save();
    if (dimmed) ctx.globalAlpha = 0.18;
    ctx.font = (isSel || hp) ? 'bold 12px JetBrains Mono, monospace' : (isUploaded ? '500 11px JetBrains Mono, monospace' : '11px JetBrains Mono, monospace');
    ctx.textAlign = left ? 'right' : 'left';
    ctx.fillStyle = isSel ? '#fcd34d' : (dimmed ? '#445' : col);
    ctx.fillText(g.id, lx, gy2 + 4);
    ctx.restore();

    chrDetailHits.push({ gene: g, bx: Math.min(x1, x2) - 8, by: gy2 - 14, bw: Math.abs(x2 - x1) + 16, bh: 28 });
  });
}

function drawDNAFocus(gene) {
  var W = cv.offsetWidth, H = cv.offsetHeight;
  ctx.fillStyle = COL.bg; ctx.fillRect(0, 0, W, H);
  if (!gene) return;

  var z = S.dnaZoom || 1;
  var cx0 = W * 0.5;
  var top = H * 0.18;
  var bottom = H * 0.84;
  var amp = 52 * z;
  var turns = 7;
  var steps = 420;

  ctx.lineWidth = Math.max(1.2, 2.2 * z);
  ctx.strokeStyle = '#4f65a8';
  ctx.beginPath();
  for (var i = 0; i <= steps; i++) {
    var t = i / steps;
    var y = top + t * (bottom - top);
    var x = cx0 + Math.sin(t * turns * Math.PI * 2) * amp;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.strokeStyle = '#7f93d3';
  ctx.beginPath();
  for (var j = 0; j <= steps; j++) {
    var t2 = j / steps;
    var y2 = top + t2 * (bottom - top);
    var x2 = cx0 + Math.sin(t2 * turns * Math.PI * 2 + Math.PI) * amp;
    if (j === 0) ctx.moveTo(x2, y2); else ctx.lineTo(x2, y2);
  }
  ctx.stroke();

  for (var k = 0; k <= 70; k++) {
    var rt = k / 70;
    var ry = top + rt * (bottom - top);
    var rx1 = cx0 + Math.sin(rt * turns * Math.PI * 2) * amp;
    var rx2 = cx0 + Math.sin(rt * turns * Math.PI * 2 + Math.PI) * amp;
    ctx.beginPath();
    ctx.moveTo(rx1, ry);
    ctx.lineTo(rx2, ry);
    ctx.strokeStyle = 'rgba(252,211,77,0.35)';
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  var muts = Array.isArray(gene.muts) ? gene.muts : [];
  var labelMut = S.selMutation || (muts.length ? (muts[0].hgvs || muts[0]) : 'Selected defect');
  var defects = muts.length ? Math.min(6, muts.length) : 1;
  for (var d = 0; d < defects; d++) {
    var dt = defects === 1 ? 0.5 : (d + 1) / (defects + 1);
    var dy = top + dt * (bottom - top);
    var dx = cx0 + Math.sin(dt * turns * Math.PI * 2) * amp;
    var active = String(labelMut) === String(muts[d] && (muts[d].hgvs || muts[d]));
    ctx.beginPath();
    ctx.arc(dx, dy, active ? 8 : 6, 0, Math.PI * 2);
    ctx.fillStyle = active ? '#f87171' : '#fca5a5';
    ctx.fill();
  }

  ctx.fillStyle = COL.txt;
  ctx.textAlign = 'center';
  ctx.font = '15px JetBrains Mono, monospace';
  ctx.fillText('DNA Defect Focus — ' + gene.id, cx0, H * 0.11);
  ctx.font = '12px JetBrains Mono, monospace';
  ctx.fillStyle = '#fca5a5';
  ctx.fillText(String(labelMut), cx0, H * 0.14);
}

function draw() {
  if (S.view === 'genome') {
    cv.style.display = 'block';
    drawGenome();
  } else if (S.view === 'pair') {
    cv.style.display = 'block';
    drawChrDetail(S.selChr);
  } else if (S.view === 'dna') {
    cv.style.display = 'block';
    drawDNAFocus(S.selGene);
  } else {
    cv.style.display = 'none';
  }
  S.tick++;
  requestAnimationFrame(draw);
}

window.addEventListener('resize', resize);
resize();
draw();
