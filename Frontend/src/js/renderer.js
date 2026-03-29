var cv = document.getElementById('genome-canvas');
var ctx = cv.getContext('2d');

var COL = {
  bg:'#060a18', brd:'#1e2a4a', cen:'#2d3a5e',
  ts:'#f87171', onco:'#60a5fa', oth:'#34d399', ai:'#fcd34d',
  txt:'#e2e8f0', mut:'#64748b', acc:'#8b7cf8',
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
var chrHits = [], geneHits = [];

function resize() {
  var dpr = window.devicePixelRatio || 1;
  cv.width = cv.offsetWidth * dpr;
  cv.height = cv.offsetHeight * dpr;
  ctx = cv.getContext('2d');
  ctx.scale(dpr, dpr);
}

function gClr(g) {
  if (S.aiGenes.indexOf(g.id) >= 0) return COL.ai;
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
  var hov = S.hovChr === id;
  rr(bx, by, bw, ph, r);
  ctx.fillStyle = hov ? '#2a3966' : '#19243a'; ctx.fill();
  ctx.strokeStyle = hov ? COL.acc : COL.brd; ctx.lineWidth = 0.6; ctx.stroke();
  rr(bx, cy, bw, qh, r);
  ctx.fillStyle = hov ? '#243462' : '#141e36'; ctx.fill();
  ctx.strokeStyle = hov ? COL.acc : COL.brd; ctx.lineWidth = 0.6; ctx.stroke();
  ctx.fillStyle = COL.cen; ctx.fillRect(bx, cy - 1.5, bw, 3);
}

function visGenes() {
  return !S.filter ? S.genes : S.genes.filter(function(g) {
    return (g.dis||[]).some(function(d) { return d.cat === S.filter; });
  });
}

function drawGenome() {
  var W = cv.offsetWidth, H = cv.offsetHeight;
  ctx.fillStyle = COL.bg; ctx.fillRect(0, 0, W, H);
  var cw = W/COLS, ch = H/ROWS;
  chrHits = []; geneHits = [];
  var genes = visGenes();
  CHR_ORD.forEach(function(id, i) {
    var col = i%COLS, row = Math.floor(i/COLS);
    var mx = col*cw + cw*0.5, my = row*ch + ch*0.5;
    var bh = (CHR_DATA[id].l/MAX_L)*ch*0.62, bw = 14;
    var bx = mx-bw*0.5, by = my-bh*0.5;
    chrHits.push({id:id, bx:bx, by:by, bw:bw, bh:bh, mx:mx});
    drawChr(id, bx, by, bw, bh);
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.fillStyle = S.hovChr === id ? COL.txt : COL.mut;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText(id, mx, by+bh+6);
    genes.filter(function(g){return g.chr===id;}).forEach(function(g) {
      var gy = by + g.pos*bh;
      var gr = S.hovGene && S.hovGene.id===g.id ? 4 : 2.5;
      var isAI = S.aiGenes.indexOf(g.id) >= 0;
      if (isAI) {
        ctx.beginPath(); ctx.arc(mx, gy, gr+5, 0, Math.PI*2);
        ctx.fillStyle = 'rgba(252,211,77,0.15)'; ctx.fill();
      }
      ctx.beginPath(); ctx.arc(mx, gy, gr, 0, Math.PI*2);
      ctx.fillStyle = gClr(g); ctx.fill();
      geneHits.push({gene:g, cx:mx, cy:gy, r:gr+4});
    });
  });
}

function draw() {
  if (S.view === 'genome') {
    cv.style.display = 'block';
    drawGenome();
  } else {
    cv.style.display = 'none';
  }
  S.tick++;
  requestAnimationFrame(draw);
}

window.addEventListener('resize', resize);
resize();
draw();
