"""
Models/variant_classification/train.py
Gradient Boosting regressor: VUS features → pathogenicity score 0–1

Resolves variants of uncertain significance (VUS) — the grey zone ClinVar
hasn't definitively classed — by predicting a continuous confidence score.

Score interpretation:
  0.0–0.3  → likely benign
  0.3–0.7  → uncertain
  0.7–1.0  → likely pathogenic

Run:
    python Models/variant_classification/train.py
"""

import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_variant_features, VARIANT_FEATURE_NAMES

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [variant_class] %(message)s')
log  = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'variant_classification.pkl')
N   = 5000
RNG = np.random.default_rng(42)


def _score_from_features(row) -> float:
    """Deterministic ground-truth score for synthetic samples."""
    s  = 0.0
    s += (1 - row['allele_frequency'] / 0.5) * 0.35
    s += (row['conservation_score'] / 10.0)  * 0.30
    s += row['domain_overlap']               * 0.15
    s += row['known_functional_impact']      * 0.10
    s += (1 - row['repeat_region'])          * 0.05
    s += (row['cadd_score'] / 50.0)          * 0.05
    return float(np.clip(s + RNG.normal(0, 0.05), 0, 1))


def synthetic_data() -> pd.DataFrame:
    n = N
    af   = RNG.beta(0.5, 5, n)
    cons = RNG.uniform(0, 10, n)
    cadd = RNG.uniform(0, 50, n)
    dom  = (RNG.random(n) < 0.3).astype(float)
    kfi  = (RNG.random(n) < 0.25).astype(float)
    rep  = (RNG.random(n) < 0.2).astype(float)

    df = pd.DataFrame({
        'mutation_type':         RNG.integers(0, 7, n),
        'conservation_score':    cons,
        'allele_frequency':      af,
        'submission_count':      RNG.integers(1, 30, n),
        'review_status':         RNG.integers(0, 5, n),
        'gene_pli':              RNG.uniform(0, 1, n),
        'splicing_distance':     RNG.integers(0, 1000, n),
        'domain_overlap':        dom,
        'af_popmax':             af * RNG.uniform(1, 1.5, n),
        'known_functional_impact': kfi,
        'repeat_region':         rep,
        'cadd_score':            cadd,
    })
    df['label'] = df.apply(_score_from_features, axis=1)
    return df


def build_X(df: pd.DataFrame) -> np.ndarray:
    return np.array([
        build_variant_features(r.to_dict()) for _, r in df.iterrows()
    ], dtype=np.float32)


def train():
    df = synthetic_data()
    X  = build_X(df)
    y  = df['label'].values.astype(np.float32)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    model = GradientBoostingRegressor(
        n_estimators=500, learning_rate=0.04, max_depth=5,
        subsample=0.8, min_samples_leaf=10, random_state=42,
    )
    log.info('Training on %d samples …', len(X_tr))
    model.fit(X_tr, y_tr)

    preds = model.predict(X_te)
    log.info('MAE=%.4f  R²=%.4f', mean_absolute_error(y_te, preds), r2_score(y_te, preds))

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': VARIANT_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved → %s', ARTIFACT)
    return model


if __name__ == '__main__':
    train()
