"""
Models/disease_risk/train.py
LightGBM regressor: OpenTargets-like evidence scores → gene-disease
association confidence score 0–1.

Powers the chromosome viewer disease filter — this score determines which
genes glow and how brightly when a researcher clicks e.g. "breast cancer".

Run:
    python Models/disease_risk/train.py
"""

import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import (
    build_disease_risk_features, DISEASE_RISK_FEATURE_NAMES,
    DISEASE_CATEGORIES, GENE_TYPES,
)

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [disease_risk] %(message)s')
log = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'disease_risk.pkl')
N   = 6000
RNG = np.random.default_rng(42)


def synthetic_data() -> pd.DataFrame:
    """
    Simulate OpenTargets-style gene-disease evidence.
    High-confidence pairs: strong genetic + literature scores.
    Low-confidence pairs:  weak / single-source evidence.
    """
    n = N
    genetic  = RNG.beta(1.5, 4, n)
    somatic  = RNG.beta(1.2, 5, n)
    lit      = RNG.beta(2, 3, n)
    drug     = RNG.beta(1, 6, n)
    rna      = RNG.beta(1.5, 4, n)
    animal   = RNG.beta(1, 5, n)

    # Ground truth: weighted combination of evidence, plus noise
    truth = (
        genetic  * 0.30 +
        somatic  * 0.20 +
        lit      * 0.20 +
        drug     * 0.15 +
        rna      * 0.10 +
        animal   * 0.05 +
        RNG.normal(0, 0.04, n)
    ).clip(0, 1)

    return pd.DataFrame({
        'genetic_score':      genetic,
        'somatic_score':      somatic,
        'literature_score':   lit,
        'drug_score':         drug,
        'rna_score':          rna,
        'animal_model_score': animal,
        'disease_category':   RNG.integers(0, len(DISEASE_CATEGORIES), n),
        'gene_type':          RNG.integers(0, len(GENE_TYPES), n),
        'label':              truth.astype(np.float32),
    })


def load_from_db():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        df   = pd.read_sql("""
            SELECT
                gd.score,
                d.category AS disease_category,
                g.type     AS gene_type
            FROM gene_disease gd
            JOIN genes    g ON g.symbol = gd.gene_symbol
            LEFT JOIN diseases d ON d.mim_number = gd.disease_key
            WHERE gd.score IS NOT NULL
            LIMIT 30000
        """, conn)
        conn.close()
        if df.empty:
            return None
        # Synthesise sub-scores from aggregated score (approximation until
        # full OpenTargets ingest adds individual channel columns)
        for col, w in [('genetic_score', 0.30), ('somatic_score', 0.20),
                       ('literature_score', 0.20), ('drug_score', 0.15),
                       ('rna_score', 0.10), ('animal_model_score', 0.05)]:
            df[col] = (df['score'] * w / max(w, 0.01) + RNG.normal(0, 0.05, len(df))).clip(0, 1)
        df['disease_category'] = df['disease_category'].fillna('other').apply(
            lambda x: DISEASE_CATEGORIES.index(x) if x in DISEASE_CATEGORIES else len(DISEASE_CATEGORIES)-1
        )
        df['gene_type'] = df['gene_type'].fillna('other').apply(
            lambda x: GENE_TYPES.index(x) if x in GENE_TYPES else len(GENE_TYPES)-1
        )
        df['label'] = df['score'].clip(0, 1).astype(np.float32)
        log.info('Loaded %d gene-disease pairs from DB', len(df))
        return df
    except Exception as e:
        log.warning('DB load failed: %s — using synthetic data', e)
        return None


def build_X(df: pd.DataFrame) -> np.ndarray:
    return np.array([
        build_disease_risk_features(r.to_dict()) for _, r in df.iterrows()
    ], dtype=np.float32)


def train():
    df = load_from_db() or synthetic_data()
    X  = build_X(df)
    y  = df['label'].values.astype(np.float32)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    if HAS_LGB:
        model = lgb.LGBMRegressor(
            n_estimators=500, learning_rate=0.04, num_leaves=31,
            max_depth=6, subsample=0.85, min_child_samples=20,
            random_state=42, verbose=-1,
        )
    else:
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(n_estimators=300, max_depth=5, random_state=42)

    log.info('Training on %d gene-disease pairs …', len(X_tr))
    model.fit(X_tr, y_tr)

    preds = model.predict(X_te)
    log.info('MAE=%.4f  R²=%.4f', mean_absolute_error(y_te, preds), r2_score(y_te, preds))

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': DISEASE_RISK_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved → %s', ARTIFACT)
    return model


if __name__ == '__main__':
    train()
