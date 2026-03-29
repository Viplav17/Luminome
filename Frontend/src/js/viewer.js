import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

var el = document.getElementById('viewer-3d');
var sc, cam, rend, ctrl, items = [], pairTargets = [];
var ray = new THREE.Raycaster(), loaded = false;

function init() {
  if (loaded) return; loaded = true;
  sc = new THREE.Scene();
  sc.background = new THREE.Color(0x060a18);
  cam = new THREE.PerspectiveCamera(55, el.offsetWidth/el.offsetHeight, 0.1, 1000);
  cam.position.set(0, 0, 9);
  rend = new THREE.WebGLRenderer({antialias:true});
  rend.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  rend.setSize(el.offsetWidth, el.offsetHeight);
  rend.toneMapping = THREE.ACESFilmicToneMapping;
  el.appendChild(rend.domElement);
  ctrl = new OrbitControls(cam, rend.domElement);
  ctrl.enableDamping = true; ctrl.dampingFactor = 0.07;
  sc.add(new THREE.AmbientLight(0xffffff, 0.4));
  var d1 = new THREE.DirectionalLight(0xffffff, 0.9); d1.position.set(4,8,6); sc.add(d1);
  var d2 = new THREE.DirectionalLight(0x8b7cf8, 0.4); d2.position.set(-4,-4,-4); sc.add(d2);
  window.addEventListener('resize', function() {
    cam.aspect = el.offsetWidth/el.offsetHeight;
    cam.updateProjectionMatrix();
    rend.setSize(el.offsetWidth, el.offsetHeight);
  });
  (function loop() { requestAnimationFrame(loop); ctrl.update(); rend.render(sc, cam); })();
}

function clear() {
  items.forEach(function(o) {
    sc.remove(o);
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      Array.isArray(o.material) ? o.material.forEach(function(m){m.dispose();}) : o.material.dispose();
    }
  });
  items = []; pairTargets = [];
}

function add(o) { sc.add(o); items.push(o); return o; }

function ph(col, extra) {
  return new THREE.MeshPhongMaterial(Object.assign({color:col, shininess:55, specular:0x4a5a8a}, extra||{}));
}

function chrGeom(h) {
  var r = 0.17, n = 24, pts = [];
  for (var i = 0; i <= n; i++) {
    var t = i/n, y = (t-0.5)*h;
    var cap = Math.min(t/0.08, 1, (1-t)/0.08);
    pts.push(new THREE.Vector2(r * Math.sin(cap*Math.PI*0.5 + 0.01), y));
  }
  return new THREE.LatheGeometry(pts, 20);
}

function strandGeom(turns, phase) {
  var n = turns*40, pts = [];
  for (var i = 0; i < n; i++) {
    var t = i/n, a = t*turns*Math.PI*2 + (phase||0);
    pts.push(new THREE.Vector3(Math.cos(a)*0.55, t*turns*0.65 - turns*0.325, Math.sin(a)*0.55));
  }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), n, 0.038, 8);
}

function rungsGroup(turns) {
  var grp = new THREE.Group(), n = turns*7;
  var rc = [0x34d399, 0x60a5fa, 0xf87171, 0xfcd34d];
  for (var i = 0; i < n; i++) {
    var t = i/n, a = t*turns*Math.PI*2, y = t*turns*0.65 - turns*0.325;
    var p1 = new THREE.Vector3(Math.cos(a)*0.55, y, Math.sin(a)*0.55);
    var p2 = new THREE.Vector3(Math.cos(a+Math.PI)*0.55, y, Math.sin(a+Math.PI)*0.55);
    grp.add(new THREE.Mesh(
      new THREE.TubeGeometry(new THREE.CatmullRomCurve3([p1,p2]), 2, 0.012, 4),
      new THREE.MeshPhongMaterial({color:rc[i%4]})
    ));
  }
  return grp;
}

function dnaGroup(turns) {
  var g = new THREE.Group();
  g.add(new THREE.Mesh(strandGeom(turns, 0), ph(0x1e2a4a)));
  g.add(new THREE.Mesh(strandGeom(turns, Math.PI), ph(0x2d3a5e)));
  g.add(rungsGroup(turns));
  return g;
}

function makeLabel(txt, x, y, z) {
  var c = document.createElement('canvas'); c.width=256; c.height=56;
  var cx2 = c.getContext('2d');
  cx2.font = '500 20px JetBrains Mono, sans-serif';
  cx2.fillStyle = '#e2e8f0'; cx2.textAlign = 'center'; cx2.textBaseline = 'middle';
  cx2.fillText(txt, 128, 28);
  var sp = new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(c), transparent:true}));
  sp.scale.set(2.4, 0.55, 1); sp.position.set(x, y, z);
  return add(sp);
}

function showPair(chrId, gene) {
  init(); clear(); el.style.display = 'block';
  cam.position.set(0, 0, 9); ctrl.target.set(0, 0, 0); ctrl.update();
  var d = (window.CHR_DATA && window.CHR_DATA[chrId]) || {l:150, c:0.4};
  var h = 3 * (d.l/249), geo = chrGeom(h);
  [-1.15, 1.15].forEach(function(px2, si) {
    add(new THREE.Mesh(geo, ph(si===0 ? 0x1e2a4a : 0x243056))).position.x = px2;
    var cen = add(new THREE.Mesh(
      new THREE.CylinderGeometry(0.22, 0.22, 0.07, 16),
      ph(0x8b7cf8, {emissive:0x3b2f8a, emissiveIntensity:0.35})
    ));
    cen.position.set(px2, h*0.5 - d.c*h, 0);
    if (gene && gene.pos != null) {
      var dot = add(new THREE.Mesh(
        new THREE.SphereGeometry(0.09, 12, 12),
        ph(0xf87171, {emissive:0xf87171, emissiveIntensity:0.5})
      ));
      dot.position.set(px2 + (si===0 ? -0.3 : 0.3), h*0.5 - gene.pos*h, 0);
    }
    var hit = add(new THREE.Mesh(
      new THREE.CylinderGeometry(0.45, 0.45, h, 12),
      new THREE.MeshBasicMaterial({visible:false})
    ));
    hit.position.x = px2; hit.userData = {pair:true, side:si};
    pairTargets.push(hit);
  });
  makeLabel('Chr ' + chrId, 0, -h*0.5-0.7, 0);
  if (gene) makeLabel(gene.id, 0, h*0.5 - gene.pos*h + 0.45, 0.6);
  try {
    new STLLoader().load('/src/assets/models/chromosome_pair.stl',
      function(g2) { clear(); _buildPairFromSTL(g2, chrId, gene, h, d); },
      undefined, function(){}
    );
  } catch(e) {}
}

function _buildPairFromSTL(geo, chrId, gene, h, d) {
  el.style.display = 'block';
  [-1.15, 1.15].forEach(function(px2, si) {
    var m = add(new THREE.Mesh(geo, ph(si===0 ? 0x1e2a4a : 0x243056)));
    m.position.x = px2;
    if (gene && gene.pos != null) {
      var dot = add(new THREE.Mesh(new THREE.SphereGeometry(0.09,12,12), ph(0xf87171,{emissive:0xf87171,emissiveIntensity:0.5})));
      dot.position.set(px2 + (si===0?-0.3:0.3), h*0.5-gene.pos*h, 0);
    }
    var hit = add(new THREE.Mesh(new THREE.CylinderGeometry(0.45,0.45,h,12), new THREE.MeshBasicMaterial({visible:false})));
    hit.position.x = px2; hit.userData = {pair:true, side:si};
    pairTargets.push(hit);
  });
  makeLabel('Chr ' + chrId, 0, -h*0.5-0.7, 0);
  if (gene) makeLabel(gene.id, 0, h*0.5-gene.pos*h+0.45, 0.6);
}

function showDNA(chrId, mutPos, gene) {
  init(); clear(); el.style.display = 'block';
  cam.position.set(0, 1.5, 8); ctrl.target.set(0, 0, 0); ctrl.update();
  var turns = 7, mp = typeof mutPos === 'number' ? mutPos : 0.5;
  var ng = add(dnaGroup(turns)); ng.position.x = -3;
  var mg = add(dnaGroup(turns)); mg.position.x = 3;
  var ma = mp*turns*Math.PI*2;
  var my2 = mp*turns*0.65 - turns*0.325;
  var mkr = add(new THREE.Mesh(
    new THREE.SphereGeometry(0.13, 16, 16),
    ph(0xf87171, {emissive:0xf87171, emissiveIntensity:0.6})
  ));
  mkr.position.set(3+Math.cos(ma)*0.55, my2, Math.sin(ma)*0.55);
  var ring = add(new THREE.Mesh(
    new THREE.TorusGeometry(0.28, 0.025, 8, 32),
    new THREE.MeshPhongMaterial({color:0xf87171, transparent:true, opacity:0.55})
  ));
  ring.position.set(3+Math.cos(ma)*0.55, my2, Math.sin(ma)*0.55);
  ring.rotation.x = Math.PI/2;
  makeLabel('Normal', -3, -turns*0.325-1, 0);
  makeLabel(gene ? gene.id : 'Mutant', 3, -turns*0.325-1, 0);
  try {
    new STLLoader().load('/src/assets/models/dna_strand.stl', function(){}, undefined, function(){});
  } catch(e) {}
}

el.addEventListener('click', function(e) {
  if (S.view !== 'pair' || !pairTargets.length) return;
  var rect = el.getBoundingClientRect();
  var mouse = new THREE.Vector2(
    ((e.clientX-rect.left)/rect.width)*2-1,
    -((e.clientY-rect.top)/rect.height)*2+1
  );
  ray.setFromCamera(mouse, cam);
  var hits = ray.intersectObjects(pairTargets);
  if (!hits.length) return;
  S.view = 'dna';
  S.mutSite = S.selGene ? S.selGene.pos : 0.5;
  showDNA(S.selChr, S.mutSite, S.selGene);
  document.getElementById('back-btn').classList.remove('hidden');
});

window.Viewer = {
  showPair: showPair,
  showDNA:  showDNA,
  hide:     function() { el.style.display = 'none'; },
};
