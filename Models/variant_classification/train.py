import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_variant_features, VARIANT_FEATURE_NAMES, MUTATION_TYPES, REVIEW_STATUSES

logging.basicConfig(level=logging.INFO, format='%(asctime)s [variant_class] %(message)s')
log = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'variant_classification.pkl')
N = 4000
RNG = np.random.default_rng(42)

def synthetic_data():
    def _make(n, sc_r, af_r, cs_r, cadd_r, pli_r, dp):
        base = RNG.uniform(*sc_r, n)
        return pd.DataFrame({
            'mutation_type': RNG.integers(0,len(MUTATION_TYPES),n),
            'conservation_score': RNG.uniform(*cs_r,n),
            'allele_frequency': RNG.uniform(*af_r,n),
            'submission_count': RNG.integers(1,30,n),
            'review_status': RNG.integers(0,len(REVIEW_STATUSES),n),
            'gene_pli': RNG.uniform(*pli_r,n),
            'splicing_distance': RNG.integers(0,1000,n),
            'domain_overlap': (RNG.random(n)<dp).astype(int),
            'af_popmax': RNG.uniform(*af_r,n),
            'known_functional_impact': (RNG.random(n)<.5).astype(int),
            'repeat_region': (RNG.random(n)<.2).astype(int),
            'cadd_score': RNG.uniform(*cadd_r,n),
            'score': base,
        })
    return pd.concat([
        _make(int(N*.4),  (0,.25),   (.02,.5),  (0,4),  (0,10),  (0,.3), .1),
        _make(int(N*.25), (.35,.65), (.001,.02), (3,7),  (10,25), (.3,.7),.4),
        _make(int(N*.35), (.75,1),   (0,.001),   (6,10), (25,50), (.6,1), .7),
    ], ignore_index=True)

def build_X(df):
    return np.array([build_variant_features({
        'mutation_type': int(r['mutation_type']),
        'conservation_score': float(r['conservation_score']),
        'allele_frequency': float(r['allele_frequency']),
        'submission_count': int(r['submission_count']),
        'review_status': int(r['review_status']),
        'gene_pli': float(r['gene_pli']),
        'splicing_distance': int(r['splicing_distance']),
        'domain_overlap': int(r['domain_overlap']),
        'af_popmax': float(r['af_popmax']),
        'known_functional_impact': int(r['known_functional_impact']),
        'repeat_region': int(r['repeat_region']),
        'cadd_score': float(r['cadd_score']),
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
    joblib.dump({'model': model, 'feature_names': VARIANT_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return model

if __name__ == '__main__':
    train()
