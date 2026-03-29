"""
train_all.py  — trains all 5 models and prints accuracy summary.
Run: python train_all.py
"""
import os, sys, subprocess, time

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

scripts = [
    ('Pathogenicity Classifier',     os.path.join(ROOT, 'Models', 'pathogenicity', 'train.py')),
    ('Variant Classification (VUS)', os.path.join(ROOT, 'Models', 'variant_classification', 'train.py')),
    ('Disease Risk Scorer',           os.path.join(ROOT, 'Models', 'disease_risk', 'train.py')),
    ('Drug Response Classifier',      os.path.join(ROOT, 'Models', 'drug_response', 'train.py')),
    ('Trial Matching Classifier',     os.path.join(ROOT, 'Models', 'trial_matching', 'train.py')),
]

results = []
for name, script in scripts:
    print(f'\n{"="*60}')
    print(f'Training: {name}')
    print('='*60)
    t0 = time.time()
    proc = subprocess.run(
        [PYTHON, script],
        capture_output=False,
        cwd=ROOT,
    )
    elapsed = time.time() - t0
    status = 'OK' if proc.returncode == 0 else f'FAILED (exit {proc.returncode})'
    results.append((name, status, f'{elapsed:.1f}s'))

print(f'\n{"="*60}')
print('TRAINING SUMMARY')
print('='*60)
for name, status, t in results:
    print(f'  {status:8s}  {t:6s}  {name}')

# Check artifacts exist
print('\nArtifacts:')
art_dir = os.path.join(ROOT, 'Models', 'artifacts')
for f in sorted(os.listdir(art_dir)):
    size = os.path.getsize(os.path.join(art_dir, f))
    print(f'  {f:<40s} {size/1024:.1f} KB')
