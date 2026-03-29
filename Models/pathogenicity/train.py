import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_pathogenicity_features, PATHOGENICITY_FEATURE_NAMES, MUTATION_TYPES, REVIEW_STATUSES

logging.basicConfig(level=logging.INFO, format='%(asctime)s [pathogenicity] %(message)s')
log = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'pathogenicity.pkl')
N = 4000
RNG = np.random.default_rng(42)

def synthetic_data():
    def _make(n, label, af_r, cs_r, sub_r, rev_r, pli_r):
        return pd.DataFrame({
            'mutation_type':      RNG.integers(0, len(MUTATION_TYPES), n),
            'conservation_score': RNG.uniform(*cs_r, n),
            'allele_frequency':   RNG.uniform(*af_r, n),
            'submission_count':   RNG.integers(*sub_r, n),
            'review_status':      RNG.integers(*rev_r, n),
            'gene_pli':           RNG.uniform(*pli_r, n),
            'splicing_distance':  RNG.integers(0, 1000, n),
            'label': label,
        })
    return pd.concat([
        _make(int(N*.4),  0, (.02,.5),   (0,4),  (10,80), (2,5), (0,.3)),
        _make(int(N*.25), 1, (.001,.02), (3,7),  (1,10),  (0,3), (.3,.7)),
        _make(int(N*.35), 2, (0,.001),   (6,10), (1,15),  (1,5), (.6,1)),
    ], ignore_index=True)

def build_X(df):
    return np.array([build_pathogenicity_features({
        'mutation_type': int(r['mutation_type']),
        'conservation_score': float(r['conservation_score']),
        'allele_frequency': float(r['allele_frequency']),
        'submission_count': int(r['submission_count']),
        'review_status': int(r['review_status']),
        'gene_pli': float(r['gene_pli']),
        'splicing_distance': int(r['splicing_distance']),
    }) for _, r in df.iterrows()], dtype=np.float32)

def train():
    df = synthetic_data().sample(frac=1, random_state=42).reset_index(drop=True)
    X, y = build_X(df), df['label'].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=.2, stratify=y, random_state=42)
    model = GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)
    log.info('Training %d samples...', len(X_tr))
    model.fit(X_tr, y_tr)
    report = classification_report(y_te, model.predict(X_te), target_names=['benign','uncertain','pathogenic'])
    log.info('\n%s', report)
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': PATHOGENICITY_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return model

if __name__ == '__main__':
    train()
