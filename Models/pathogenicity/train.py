"""
Models/pathogenicity/train.py
LightGBM classifier: variant features → Harmful / Benign / Uncertain

Labels:  0 = Benign  |  1 = Uncertain  |  2 = Pathogenic

Training data sources (in priority order):
  1. PostgreSQL variants table (after pipeline/seed.py runs)
  2. Synthetic data with realistic ClinVar-like distributions (fallback)

Run:
    python Models/pathogenicity/train.py
"""

import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import (
    build_pathogenicity_features, PATHOGENICITY_FEATURE_NAMES,
    MUTATION_TYPES, REVIEW_STATUSES,
)

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    from sklearn.ensemble import GradientBoostingClassifier
    HAS_LGB = False

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [pathogenicity] %(message)s')
log = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'pathogenicity.pkl')
N = 4000   # synthetic sample count
RNG = np.random.default_rng(42)


def synthetic_data() -> pd.DataFrame:
    """
    Simulate ClinVar-like variant data with realistic class distributions.
      Benign (40%):     high AF, low conservation, many submissions
      Pathogenic (35%): low AF, high conservation, expert review
      Uncertain (25%):  middle values, sparse evidence
    """
    def _make(n, label, af_range, cons_range, sub_range, review_range, pli_range):
        return pd.DataFrame({
            'mutation_type':      RNG.integers(0, len(MUTATION_TYPES), n),
            'conservation_score': RNG.uniform(*cons_range, n),
            'allele_frequency':   RNG.uniform(*af_range, n),
            'submission_count':   RNG.integers(*sub_range, n),
            'review_status':      RNG.integers(*review_range, n),
            'gene_pli':           RNG.uniform(*pli_range, n),
            'splicing_distance':  RNG.integers(0, 1000, n),
            'label':              label,
        })

    benign     = _make(int(N*0.4), 0, (0.02, 0.50), (0, 4),  (10, 80), (2, 5), (0.0, 0.3))
    uncertain  = _make(int(N*0.25),1, (0.001,0.02), (3, 7),  (1, 10),  (0, 3), (0.3, 0.7))
    pathogenic = _make(int(N*0.35),2, (0.0, 0.001), (6, 10), (1, 15),  (1, 5), (0.6, 1.0))
    return pd.concat([benign, uncertain, pathogenic], ignore_index=True)


def load_from_db():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    try:
        import psycopg2, pandas as pd
        conn = psycopg2.connect(db_url)
        df = pd.read_sql("""
            SELECT
                significance,
                name,
                review_status
            FROM variants
            WHERE significance IS NOT NULL
            LIMIT 20000
        """, conn)
        conn.close()
        if df.empty:
            return None
        # Map ClinVar significance strings → numeric label
        sig_map = {
            'benign': 0, 'likely benign': 0,
            'uncertain significance': 1, 'conflicting': 1,
            'pathogenic': 2, 'likely pathogenic': 2,
        }
        df['label'] = df['significance'].str.lower().map(sig_map)
        df = df.dropna(subset=['label'])
        df['label'] = df['label'].astype(int)
        # Synthetic fill for missing feature columns
        df['mutation_type']      = RNG.integers(0, len(MUTATION_TYPES), len(df))
        df['conservation_score'] = RNG.uniform(0, 10, len(df))
        df['allele_frequency']   = RNG.uniform(0, 0.01, len(df))
        df['submission_count']   = RNG.integers(1, 20, len(df))
        df['review_status']      = RNG.integers(0, len(REVIEW_STATUSES), len(df))
        df['gene_pli']           = RNG.uniform(0, 1, len(df))
        df['splicing_distance']  = RNG.integers(0, 1000, len(df))
        log.info('Loaded %d variants from DB', len(df))
        return df
    except Exception as e:
        log.warning('DB load failed: %s — using synthetic data', e)
        return None


def build_X(df: pd.DataFrame) -> np.ndarray:
    rows = []
    for _, r in df.iterrows():
        rows.append(build_pathogenicity_features({
            'mutation_type':     r['mutation_type'],
            'conservation_score':r['conservation_score'],
            'allele_frequency':  r['allele_frequency'],
            'submission_count':  r['submission_count'],
            'review_status':     r['review_status'],
            'gene_pli':          r['gene_pli'],
            'splicing_distance': r['splicing_distance'],
        }))
    return np.array(rows, dtype=np.float32)


def train():
    df = load_from_db() or synthetic_data()
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    X = build_X(df)
    y = df['label'].values

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    if HAS_LGB:
        model = lgb.LGBMClassifier(
            n_estimators=400, learning_rate=0.05, num_leaves=31,
            max_depth=6, class_weight='balanced',
            random_state=42, verbose=-1,
        )
    else:
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)

    log.info('Training on %d samples …', len(X_tr))
    model.fit(X_tr, y_tr)

    preds = model.predict(X_te)
    log.info('Evaluation:\n%s', classification_report(y_te, preds,
        target_names=['benign', 'uncertain', 'pathogenic']))

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': PATHOGENICITY_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved → %s', ARTIFACT)
    return model


if __name__ == '__main__':
    train()
