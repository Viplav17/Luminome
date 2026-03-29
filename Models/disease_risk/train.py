import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_disease_risk_features, DISEASE_RISK_FEATURE_NAMES, DISEASE_CATEGORIES, GENE_TYPES

logging.basicConfig(level=logging.INFO, format='%(asctime)s [disease_risk] %(message)s')
log = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'disease_risk.pkl')
N = 4000
RNG = np.random.default_rng(42)

def synthetic_data():
    def _make(n, sr):
        base = RNG.uniform(*sr, n)
        return pd.DataFrame({
            'genetic_score':      np.clip(base+RNG.normal(0,.1,n),0,1),
            'somatic_score':      np.clip(base+RNG.normal(0,.15,n),0,1),
            'literature_score':   np.clip(base+RNG.normal(0,.12,n),0,1),
            'drug_score':         np.clip(base+RNG.normal(0,.2,n),0,1),
            'rna_score':          np.clip(base+RNG.normal(0,.15,n),0,1),
            'animal_model_score': np.clip(base+RNG.normal(0,.18,n),0,1),
            'disease_category':   RNG.integers(0,len(DISEASE_CATEGORIES),n),
            'gene_type':          RNG.integers(0,len(GENE_TYPES),n),
            'score': base,
        })
    return pd.concat([_make(int(N*.4),(0,.3)),_make(int(N*.35),(.3,.6)),_make(int(N*.25),(.6,1))], ignore_index=True)

def build_X(df):
    return np.array([build_disease_risk_features({
        'genetic_score': float(r['genetic_score']),
        'somatic_score': float(r['somatic_score']),
        'literature_score': float(r['literature_score']),
        'drug_score': float(r['drug_score']),
        'rna_score': float(r['rna_score']),
        'animal_model_score': float(r['animal_model_score']),
        'disease_category': int(r['disease_category']),
        'gene_type': int(r['gene_type']),
    }) for _, r in df.iterrows()], dtype=np.float32)

def train():
    df = synthetic_data().sample(frac=1, random_state=42).reset_index(drop=True)
    X, y = build_X(df), df['score'].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=.2, random_state=42)
    model = GradientBoostingRegressor(n_estimators=200, max_depth=4, random_state=42)
    log.info('Training %d samples...', len(X_tr))
    model.fit(X_tr, y_tr)
    p = model.predict(X_te)
    log.info('MAE=%.4f  R2=%.4f', mean_absolute_error(y_te,p), r2_score(y_te,p))
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': DISEASE_RISK_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return model

if __name__ == '__main__':
    train()
