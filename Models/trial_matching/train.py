import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_trial_features, TRIAL_FEATURE_NAMES

logging.basicConfig(level=logging.INFO, format='%(asctime)s [trial_match] %(message)s')
log = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'trial_matching.pkl')
N = 4000
RNG = np.random.default_rng(42)

def synthetic_data():
    def _make(n, label, gene_p, diag_p, phase_r):
        return pd.DataFrame({
            'has_mutation_in_trial_gene': (RNG.random(n)<gene_p).astype(int),
            'diagnosis_match':            np.clip(RNG.uniform(0,1,n)*diag_p*2,0,1),
            'age_eligible':               (RNG.random(n)<.8).astype(int),
            'prior_treatment_match':      RNG.uniform(0,1,n),
            'biomarker_match':            np.clip(RNG.uniform(0,1,n)*gene_p,0,1),
            'trial_phase':                RNG.integers(*phase_r,n),
            'intervention_type_match':    (RNG.random(n)<gene_p).astype(int),
            'mutation_type_match':        np.clip(RNG.uniform(0,1,n)*gene_p,0,1),
            'oncology_flag':              (RNG.random(n)<.4).astype(int),
            'gene_mutation_count':        RNG.integers(0,10,n),
            'label': label,
        })
    return pd.concat([
        _make(int(N*.5), 0, .1, .1, (1,3)),
        _make(int(N*.5), 1, .85,.85,(2,5)),
    ], ignore_index=True)

def build_X(df):
    return np.array([build_trial_features({
        'has_mutation_in_trial_gene': int(r['has_mutation_in_trial_gene']),
        'diagnosis_match':            float(r['diagnosis_match']),
        'age_eligible':               int(r['age_eligible']),
        'prior_treatment_match':      float(r['prior_treatment_match']),
        'biomarker_match':            float(r['biomarker_match']),
        'trial_phase':                int(r['trial_phase']),
        'intervention_type_match':    int(r['intervention_type_match']),
        'mutation_type_match':        float(r['mutation_type_match']),
        'oncology_flag':              int(r['oncology_flag']),
        'gene_mutation_count':        int(r['gene_mutation_count']),
    }) for _, r in df.iterrows()], dtype=np.float32)

def train():
    df = synthetic_data().sample(frac=1, random_state=42).reset_index(drop=True)
    X, y = build_X(df), df['label'].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=.2, stratify=y, random_state=42)
    model = GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)
    log.info('Training %d samples...', len(X_tr))
    model.fit(X_tr, y_tr)
    log.info('\n%s', classification_report(y_te, model.predict(X_te), target_names=['no_match','match']))
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': TRIAL_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return model

if __name__ == '__main__':
    train()
