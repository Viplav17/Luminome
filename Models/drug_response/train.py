import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_drug_response_features, DRUG_RESPONSE_FEATURE_NAMES, RESPONSE_CLASSES, EVIDENCE_TYPES

logging.basicConfig(level=logging.INFO, format='%(asctime)s [drug_response] %(message)s')
log = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'drug_response.pkl')
N = 4000
RNG = np.random.default_rng(42)

def synthetic_data():
    def _make(n, label, ca_r, va_r, str_r, pli_r):
        return pd.DataFrame({
            'clinical_annotation_count': RNG.integers(*ca_r, n),
            'variant_annotation_count':  RNG.integers(*va_r, n),
            'evidence_strength':         RNG.integers(*str_r, n),
            'pk_evidence':               (RNG.random(n)<.5).astype(int),
            'pd_evidence':               (RNG.random(n)<.5).astype(int),
            'population_diversity':      RNG.uniform(0,1,n),
            'gene_pli':                  RNG.uniform(*pli_r,n),
            'drug_max_phase':            RNG.integers(1,5,n),
            'et0': (RNG.random(n)<.6).astype(int),
            'et1': (RNG.random(n)<.4).astype(int),
            'et2': (RNG.random(n)<.3).astype(int),
            'et3': (RNG.random(n)<.5).astype(int),
            'et4': (RNG.random(n)<.2).astype(int),
            'label': label,
        })
    return pd.concat([
        _make(int(N*.2),  0, (1,5),  (1,5),  (3,6), (0,.3)),
        _make(int(N*.3),  1, (3,15), (3,15), (2,5), (.2,.6)),
        _make(int(N*.35), 2, (8,30), (8,30), (0,3), (.5,1)),
        _make(int(N*.15), 3, (2,10), (2,10), (1,4), (.3,.8)),
    ], ignore_index=True)

def build_X(df):
    return np.array([build_drug_response_features({
        'clinical_annotation_count': int(r['clinical_annotation_count']),
        'variant_annotation_count':  int(r['variant_annotation_count']),
        'evidence_strength':         int(r['evidence_strength']),
        'pk_evidence':               int(r['pk_evidence']),
        'pd_evidence':               int(r['pd_evidence']),
        'population_diversity':      float(r['population_diversity']),
        'gene_pli':                  float(r['gene_pli']),
        'drug_max_phase':            int(r['drug_max_phase']),
        'evidence_types': [EVIDENCE_TYPES[i] for i in range(len(EVIDENCE_TYPES)) if r.get(f'et{i}',0)],
    }) for _, r in df.iterrows()], dtype=np.float32)

def train():
    df = synthetic_data().sample(frac=1, random_state=42).reset_index(drop=True)
    X, y = build_X(df), df['label'].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=.2, stratify=y, random_state=42)
    model = GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)
    log.info('Training %d samples...', len(X_tr))
    model.fit(X_tr, y_tr)
    log.info('\n%s', classification_report(y_te, model.predict(X_te), target_names=RESPONSE_CLASSES))
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': DRUG_RESPONSE_FEATURE_NAMES, 'classes': RESPONSE_CLASSES}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return model

if __name__ == '__main__':
    train()
