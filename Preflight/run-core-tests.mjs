#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import process from 'node:process';

const ROOT = process.cwd();
const BACKEND_PORT = Number(process.env.PRECHECK_BACKEND_PORT || 3101);
const ML_PORT = Number(process.env.PRECHECK_ML_PORT || 3102);
const BACKEND_BASE = `http://127.0.0.1:${BACKEND_PORT}`;
const ML_BASE = `http://127.0.0.1:${ML_PORT}`;

const results = [];
const warnings = [];
const managed = [];
const lines = [];

function now() {
  return new Date().toISOString().replace('T', ' ').slice(0, 19);
}

function log(line) {
  lines.push(line);
  process.stdout.write(`${line}\n`);
}

function addResult(ok, name, detail = '') {
  results.push({ ok, name, detail });
}

function addWarning(name, detail = '') {
  warnings.push({ name, detail });
}

function exists(relPath) {
  return fs.existsSync(path.join(ROOT, relPath));
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForHealth(url, timeoutMs, label) {
  const start = Date.now();
  let last = '';
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
      last = `HTTP ${r.status}`;
    } catch (e) {
      last = e.message;
    }
    await sleep(350);
  }
  throw new Error(`${label} not healthy within ${timeoutMs}ms (${last || 'no response'})`);
}

function findPython() {
  if (process.env.PYTHON_CMD) return process.env.PYTHON_CMD;
  const winVenv = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
  const nixVenv = path.join(ROOT, '.venv', 'bin', 'python');
  if (fs.existsSync(winVenv)) return winVenv;
  if (fs.existsSync(nixVenv)) return nixVenv;
  return process.platform === 'win32' ? 'python' : 'python3';
}

function startProcess(label, cmd, args, extraEnv = {}) {
  const child = spawn(cmd, args, {
    cwd: ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
    env: { ...process.env, ...extraEnv },
  });

  let errBuffer = '';
  child.stdout.on('data', () => {});
  child.stderr.on('data', (buf) => {
    errBuffer += String(buf);
    if (errBuffer.length > 2000) errBuffer = errBuffer.slice(-2000);
  });

  managed.push({ label, child, errBufferRef: () => errBuffer });
  return child;
}

async function startServices() {
  const pythonCmd = findPython();

  startProcess('ML service', pythonCmd, ['-m', 'uvicorn', 'Models.server:app', '--host', '127.0.0.1', '--port', String(ML_PORT)]);
  await waitForHealth(`${ML_BASE}/health`, 45000, 'ML service');

  startProcess('Backend service', process.execPath, ['Backend/server.js'], {
    PORT: String(BACKEND_PORT),
    ML_BASE: ML_BASE,
  });
  await waitForHealth(`${BACKEND_BASE}/api/health`, 20000, 'Backend service');
}

async function stopServices() {
  for (const item of managed.reverse()) {
    const child = item.child;
    if (!child.killed) {
      try {
        child.kill('SIGTERM');
      } catch (_) {}
    }
  }
  await sleep(500);
  for (const item of managed) {
    const child = item.child;
    if (!child.killed) {
      try {
        child.kill('SIGKILL');
      } catch (_) {}
    }
  }
}

async function testJson(name, url, options, assertFn) {
  try {
    const r = await fetch(url, options);
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) {}

    if (!r.ok) {
      addResult(false, name, `HTTP ${r.status}: ${text.slice(0, 180)}`);
      return;
    }
    if (!data || typeof data !== 'object') {
      addResult(false, name, 'Response was not a JSON object');
      return;
    }
    if (assertFn && !assertFn(data)) {
      addResult(false, name, `Unexpected payload: ${JSON.stringify(data).slice(0, 180)}`);
      return;
    }
    addResult(true, name);
  } catch (e) {
    addResult(false, name, e.message);
  }
}

function checkCoreFiles() {
  const required = [
    'Backend/server.js',
    'Backend/api/ml.js',
    'Backend/services/ml.js',
    'Frontend/index.html',
    'Frontend/src/js/renderer.js',
    'Frontend/src/js/ui.js',
    'Frontend/src/js/ai.js',
    'Models/server.py',
    'package.json',
    'requirements.txt',
  ];

  for (const rel of required) {
    addResult(exists(rel), `Core file exists: ${rel}`, exists(rel) ? '' : 'Missing');
  }
}

function checkChromosomeSTL() {
  const indexPath = path.join(ROOT, 'Frontend', 'index.html');
  const html = fs.existsSync(indexPath) ? fs.readFileSync(indexPath, 'utf8') : '';
  const usesViewer = /src\/js\/viewer\.js/.test(html);
  addResult(!usesViewer, '2D chromosome mode active (no viewer.js script in index.html)', usesViewer ? 'viewer.js script still referenced' : '');

  const hasRenderer = /src\/js\/renderer\.js/.test(html);
  const hasUi = /src\/js\/ui\.js/.test(html);
  addResult(hasRenderer && hasUi, '2D chromosome scripts are wired in index.html', (!hasRenderer || !hasUi) ? 'renderer/ui script reference missing' : '');

}

async function runApiChecks() {
  await testJson('Backend health', `${BACKEND_BASE}/api/health`, {}, (d) => d.ok === true);
  await testJson('ML health (direct)', `${ML_BASE}/health`, {}, (d) => d.ok === true);
  await testJson('ML status via backend', `${BACKEND_BASE}/api/ml/status`, {}, (d) => typeof d === 'object');

  await testJson(
    'Core model: pathogenicity',
    `${BACKEND_BASE}/api/ml/pathogenicity`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mutation_type: 'missense',
        conservation_score: 0.82,
        allele_frequency: 0.001,
        submission_count: 4,
        review_status: 'reviewed_by_expert_panel',
        gene_pli: 0.91,
        splicing_distance: 40,
      }),
    },
    (d) => typeof d === 'object' && Object.keys(d).length > 0
  );

  await testJson(
    'Core model: variant classification',
    `${BACKEND_BASE}/api/ml/variant`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mutation_type: 'missense',
        conservation_score: 0.7,
        allele_frequency: 0.002,
        submission_count: 3,
        review_status: 'criteria_provided',
        gene_pli: 0.75,
        splicing_distance: 55,
        domain_overlap: true,
        af_popmax: 0.001,
        known_functional_impact: false,
        repeat_region: false,
        cadd_score: 21.3,
      }),
    },
    (d) => typeof d === 'object' && Object.keys(d).length > 0
  );

  await testJson(
    'Core model: disease risk',
    `${BACKEND_BASE}/api/ml/disease-risk`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        genetic_score: 0.84,
        somatic_score: 0.6,
        literature_score: 0.8,
        drug_score: 0.5,
        rna_score: 0.55,
        animal_model_score: 0.4,
        disease_category: 'oncology',
        gene_type: 'onco',
      }),
    },
    (d) => typeof d === 'object' && Object.keys(d).length > 0
  );

  await testJson(
    'Core model: drug response',
    `${BACKEND_BASE}/api/ml/drug-response`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        clinical_annotation_count: 6,
        variant_annotation_count: 3,
        evidence_strength: 7,
        pk_evidence: true,
        pd_evidence: true,
        population_diversity: 2,
        gene_pli: 0.62,
        drug_max_phase: 3,
        evidence_types: ['clinical', 'functional'],
      }),
    },
    (d) => typeof d === 'object' && Object.keys(d).length > 0
  );

  await testJson(
    'Core model: trial match',
    `${BACKEND_BASE}/api/ml/trial-match`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        has_mutation_in_trial_gene: true,
        diagnosis_match: 0.85,
        age_eligible: true,
        prior_treatment_match: 0.5,
        biomarker_match: 0.9,
        trial_phase: 2,
        intervention_type_match: true,
        mutation_type_match: 0.8,
        oncology_flag: true,
        gene_mutation_count: 2,
      }),
    },
    (d) => typeof d === 'object' && Object.keys(d).length > 0
  );

  await testJson(
    'Core model: rank trials',
    `${BACKEND_BASE}/api/ml/rank-trials`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient: {
          has_mutation_in_trial_gene: true,
          diagnosis_match: 0.8,
          age_eligible: true,
          prior_treatment_match: 0.4,
          biomarker_match: 0.85,
          trial_phase: 2,
          intervention_type_match: true,
          mutation_type_match: 0.7,
          oncology_flag: true,
          gene_mutation_count: 1,
        },
        trials: [
          {
            trial_id: 'NCT-TEST-001',
            trial_name: 'Targeted Therapy Trial A',
            has_mutation_in_trial_gene: true,
            diagnosis_match: 0.9,
            age_eligible: true,
            prior_treatment_match: 0.5,
            biomarker_match: 0.9,
            trial_phase: 2,
            intervention_type_match: true,
            mutation_type_match: 0.8,
            oncology_flag: true,
            gene_mutation_count: 1,
          },
          {
            trial_id: 'NCT-TEST-002',
            trial_name: 'Immunotherapy Trial B',
            has_mutation_in_trial_gene: false,
            diagnosis_match: 0.7,
            age_eligible: true,
            prior_treatment_match: 0.4,
            biomarker_match: 0.6,
            trial_phase: 3,
            intervention_type_match: true,
            mutation_type_match: 0.4,
            oncology_flag: true,
            gene_mutation_count: 0,
          },
        ],
      }),
    },
    (d) => typeof d === 'object' && Object.keys(d).length > 0
  );
}

function printSummary() {
  const pass = results.filter((r) => r.ok).length;
  const fail = results.length - pass;

  log('');
  log('=== Luminome Preflight Report ===');
  log(`Timestamp: ${now()}`);
  log(`Total checks: ${results.length}`);
  log(`Passed: ${pass}`);
  log(`Failed: ${fail}`);
  log('');

  for (const r of results) {
    const status = r.ok ? 'PASS' : 'FAIL';
    const detail = r.detail ? ` | ${r.detail}` : '';
    log(`[${status}] ${r.name}${detail}`);
  }

  if (warnings.length) {
    log('');
    log('Warnings:');
    for (const w of warnings) {
      const detail = w.detail ? ` | ${w.detail}` : '';
      log(`[WARN] ${w.name}${detail}`);
    }
  }

  log('');
  if (fail > 0) log('Preflight result: FAILED');
  else log('Preflight result: PASSED');

  const reportPath = path.join(ROOT, 'Preflight', 'latest-report.txt');
  fs.writeFileSync(reportPath, `${lines.join('\n')}\n`, 'utf8');
  log(`Report file: ${reportPath}`);
}

async function main() {
  const skipStart = process.argv.includes('--skip-start');

  checkCoreFiles();
  checkChromosomeSTL();

  try {
    if (!skipStart) {
      await startServices();
    } else {
      addWarning('Service startup', 'Skipped startup; using currently running services');
    }

    await runApiChecks();
  } catch (e) {
    addResult(false, 'Service startup / smoke tests', e.message);
    for (const item of managed) {
      const logs = item.errBufferRef();
      if (logs && logs.trim()) {
        addWarning(`${item.label} stderr tail`, logs.replace(/\s+/g, ' ').slice(0, 260));
      }
    }
  } finally {
    await stopServices();
  }

  printSummary();

  const failed = results.some((r) => !r.ok);
  process.exit(failed ? 1 : 0);
}

main().catch(async (e) => {
  addResult(false, 'Unhandled preflight error', e.message);
  await stopServices();
  printSummary();
  process.exit(1);
});
