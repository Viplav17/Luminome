import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

var el = document.getElementById('viewer-3d');
var taskBox = document.getElementById('next-tasks');
var taskTitle = document.getElementById('next-tasks-title');
var taskList = document.getElementById('next-task-list');
var sc, cam, rend, ctrl, items = [], pairTargets = [];
var ray = new THREE.Raycaster(), loaded = false;
var stl = new STLLoader();

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

function setNextTasks(title, lines) {
  if (!taskBox || !taskTitle || !taskList) return;
  if (!lines || !lines.length) {
    taskBox.classList.add('hidden');
    return;
  }
  taskTitle.textContent = title || 'Next Tasks';
  taskList.innerHTML = lines.map(function(line) {
    return '<li>' + String(line || '').replace(/</g, '&lt;') + '</li>';
  }).join('');
  taskBox.classList.remove('hidden');
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

function pairFolderForChr(chrId) {
  if (chrId === 'X' || chrId === 'Y') return 'pair_23';
  var n = parseInt(chrId, 10);
  if (!Number.isFinite(n)) return null;
  return 'pair_' + String(n).padStart(2, '0');
}

function chromosomeCode(chrId, side) {
  if (chrId === 'X' || chrId === 'Y') return side === 0 ? 'X' : 'Y';
  return String(chrId) + (side === 0 ? 'A' : 'B');
}

function chromosomeSTLCandidates(chrId, side) {
  var folder = pairFolderForChr(chrId);
  if (!folder) return [];
  if (chrId === 'X' || chrId === 'Y') {
    var stemXY = side === 0 ? 'x' : 'y';
    return [
      '/src/assets/models/chromosomes/pairs/' + folder + '/chr' + stemXY + '.stl',
      '/src/assets/models/chromosomes/pairs/' + folder + '/chromosome_' + stemXY + '.stl'
    ];
  }
  var n2 = String(parseInt(chrId, 10)).padStart(2, '0');
  var sideCode = side === 0 ? 'a' : 'b';
  return [
    '/src/assets/models/chromosomes/pairs/' + folder + '/chr' + n2 + '_' + sideCode + '.stl',
    '/src/assets/models/chromosomes/pairs/' + folder + '/chromosome_' + n2 + '_' + sideCode + '.stl',
    '/src/assets/models/chromosomes/pairs/' + folder + '/chr' + chrId + '_' + sideCode + '.stl'
  ];
}

function dnaMutantCandidates(chromosome) {
  var tag = String(chromosome || 'default_mutant').toLowerCase();
  return [
    '/src/assets/models/dna/mutant/' + tag + '.stl',
    '/src/assets/models/dna/mutant/chr' + tag + '.stl',
    '/src/assets/models/dna/mutant/default_mutant.stl',
    '/src/assets/models/dna_strand.stl'
  ];
}

function dnaNormalCandidates(chromosome) {
  var tag = String(chromosome || 'reference').toLowerCase();
  return [
    '/src/assets/models/dna/normal/' + tag + '.stl',
    '/src/assets/models/dna/normal/reference.stl',
    '/src/assets/models/dna_strand.stl'
  ];
}

function loadFirstSTL(paths) {
  return new Promise(function(resolve, reject) {
    var i = 0;
    function next() {
      if (i >= paths.length) {
        reject(new Error('No STL loaded'));
        return;
      }
      var p = paths[i++];
      stl.load(p, function(geo) {
        resolve({ geometry: geo, path: p });
      }, undefined, next);
    }
    next();
  });
}

function meshFromSTL(geometry, color, targetHeight) {
  var geo = geometry.clone();
  geo.computeVertexNormals();
  geo.computeBoundingBox();
  geo.center();
  geo.computeBoundingBox();
  var size = new THREE.Vector3();
  geo.boundingBox.getSize(size);
  var baseHeight = Math.max(size.y || 0, 0.0001);
  var scale = targetHeight / baseHeight;
  var mesh = new THREE.Mesh(geo, ph(color));
  mesh.scale.set(scale, scale, scale);
  return mesh;
}

function hashValue(text) {
  var s = String(text || 'x');
  var h = 0;
  for (var i = 0; i < s.length; i++) h = ((h << 5) - h) + s.charCodeAt(i);
  return Math.abs(h);
}

function buildDefectSites(gene) {
  if (!gene) return [0.52];
  var muts = Array.isArray(gene.muts) ? gene.muts : [];
  if (!muts.length) {
    return [0.25 + (hashValue(gene.id) % 50) / 100];
  }
  return muts.slice(0, 8).map(function(m, idx) {
    var key = (m && (m.hgvs || m.id || m.name)) || ('mut' + idx);
    var v = hashValue(gene.id + ':' + key) % 75;
    return 0.12 + (v / 100);
  }).sort(function(a, b) { return a - b; });
}

function addDefectMarkersOnMesh(mesh, sites) {
  var box = new THREE.Box3().setFromObject(mesh);
  var min = box.min, max = box.max;
  var x = max.x + 0.12;
  var z = (min.z + max.z) * 0.5;
  sites.forEach(function(t) {
    var y = min.y + Math.max(0.03, Math.min(0.97, t)) * (max.y - min.y);
    var dot = add(new THREE.Mesh(
      new THREE.SphereGeometry(0.1, 14, 14),
      ph(0xf87171, { emissive: 0xf87171, emissiveIntensity: 0.65 })
    ));
    dot.position.set(x, y, z);
  });
}

function showPair(chrId, gene) {
  init(); clear(); el.style.display = 'block';
  setNextTasks('Pair Navigation', [
    'Click chromosome A or B to open its DNA helix model.',
    'Rotate and zoom to inspect shape differences before entering DNA view.',
    'Use All Chromosomes to return to the home map.'
  ]);
  cam.position.set(0, 0, 9); ctrl.target.set(0, 0, 0); ctrl.update();
  var d = (window.CHR_DATA && window.CHR_DATA[chrId]) || {l:150, c:0.4};
  var h = 3 * (d.l/249), geo = chrGeom(h), pairNodes = [];
  [-1.45, 1.45].forEach(function(px2, si) {
    var fallbackMesh = add(new THREE.Mesh(geo, ph(si===0 ? 0x1e2a4a : 0x243056)));
    fallbackMesh.position.x = px2;
    pairNodes.push({ x: px2, side: si, mesh: fallbackMesh });
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
    hit.position.x = px2;
    hit.userData = {
      pair: true,
      side: si,
      chromosome: chromosomeCode(chrId, si)
    };
    pairTargets.push(hit);
  });
  makeLabel('Chr ' + chrId, 0, -h*0.5-0.7, 0);
  if (gene) makeLabel(gene.id, 0, h*0.5 - gene.pos*h + 0.45, 0.6);

  pairNodes.forEach(function(node) {
    var choices = chromosomeSTLCandidates(chrId, node.side);
    loadFirstSTL(choices).then(function(out) {
      sc.remove(node.mesh);
      var stlMesh = meshFromSTL(out.geometry, node.side === 0 ? 0x1e2a4a : 0x243056, h * 1.03);
      stlMesh.position.set(node.x, 0, 0);
      add(stlMesh);
      node.mesh = stlMesh;
    }).catch(function() {
      return null;
    });
  });
}

function showDNA(chrId, mutPos, gene, chromosome) {
  init(); clear(); el.style.display = 'block';
  setNextTasks('DNA Comparison', [
    'Red markers show detected or inferred defect locations on the selected chromosome.',
    'Right helix is your selected chromosome; left helix is the healthy reference model.',
    'Next: open gene details and run disease, drug, and trial insights for this chromosome.'
  ]);
  cam.position.set(0, 1.5, 8); ctrl.target.set(0, 0, 0); ctrl.update();
  var turns = 7, mp = typeof mutPos === 'number' ? mutPos : 0.5;
  var defectSites = buildDefectSites(gene);
  var normalFallback = add(dnaGroup(turns));
  normalFallback.position.x = -3;
  var mutantFallback = add(dnaGroup(turns));
  mutantFallback.position.x = 3;

  var ma = mp * turns * Math.PI * 2;
  var my2 = mp * turns * 0.65 - turns * 0.325;
  var centerMarker = add(new THREE.Mesh(
    new THREE.SphereGeometry(0.13, 16, 16),
    ph(0xf87171, { emissive:0xf87171, emissiveIntensity:0.6 })
  ));
  centerMarker.position.set(3 + Math.cos(ma) * 0.55, my2, Math.sin(ma) * 0.55);

  defectSites.forEach(function(t) {
    var a = t * turns * Math.PI * 2;
    var y = t * turns * 0.65 - turns * 0.325;
    var m = add(new THREE.Mesh(
      new THREE.SphereGeometry(0.08, 12, 12),
      ph(0xf87171, { emissive:0xf87171, emissiveIntensity:0.65 })
    ));
    m.position.set(3 + Math.cos(a) * 0.55, y, Math.sin(a) * 0.55);
  });

  var selectedChrom = chromosome || (S && S.selChromosome) || (String(chrId) + 'A');
  loadFirstSTL(dnaNormalCandidates(selectedChrom)).then(function(out) {
    sc.remove(normalFallback);
    var normalMesh = meshFromSTL(out.geometry, 0x1f7a58, 4.7);
    normalMesh.position.set(-3, 0, 0);
    add(normalMesh);
  }).catch(function() {
    return null;
  });

  loadFirstSTL(dnaMutantCandidates(selectedChrom)).then(function(out) {
    sc.remove(mutantFallback);
    var mutantMesh = meshFromSTL(out.geometry, 0x2d3a5e, 4.7);
    mutantMesh.position.set(3, 0, 0);
    add(mutantMesh);
    addDefectMarkersOnMesh(mutantMesh, defectSites);
  }).catch(function() {
    return null;
  });

  makeLabel('Normal', -3, -turns*0.325-1, 0);
  makeLabel((gene ? gene.id + ' ' : '') + selectedChrom, 3, -turns*0.325-1, 0);
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
  var target = hits[0].object;
  S.view = 'dna';
  S.selChromosome = target && target.userData ? target.userData.chromosome : null;
  S.mutSite = S.selGene ? S.selGene.pos : 0.5;
  showDNA(S.selChr, S.mutSite, S.selGene, S.selChromosome);
  document.getElementById('back-btn').classList.remove('hidden');
});

window.Viewer = {
  showPair: showPair,
  showDNA:  showDNA,
  hide:     function() {
    el.style.display = 'none';
    setNextTasks('', []);
  },
};
