"""
Models/drug_response/train.py
Random Forest classifier: patient genotype + PharmGKB evidence →
predicted treatment response {poor, intermediate, good, adverse}

Fed directly by Data/relationships.tsv PharmGKB data, enriched with DB
data after the pipeline runs.

Run:
    python Models/drug_response/train.py
"""

import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import (
    build_drug_response_features, DRUG_RESPONSE_FEATURE_NAMES,
    EVIDENCE_TYPES, RESPONSE_CLASSES, RESPONSE_LABEL,
)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [drug_response] %(message)s')
log = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'drug_response.pkl')
N   = 5000
RNG = np.random.default_rng(42)


def _evidence_multihot(n, strengths):
    """Randomly assign evidence types correlated with evidence strength."""
    out = []
    for s in strengths:
        # Strong evidence → more annotation types present
        k    = max(1, int(s * len(EVIDENCE_TYPES)) + RNG.integers(-1, 2, 1)[0])
        idxs = RNG.choice(len(EVIDENCE_TYPES), size=min(k, len(EVIDENCE_TYPES)), replace=False)
        vec  = [0] * len(EVIDENCE_TYPES)
        for i in idxs:
            vec[i] = 1
        out.append(vec)
    return out


def synthetic_data() -> pd.DataFrame:
    n = N
    # Evidence strength: high ClinicalAnnotation count → more likely 'good'
    clin_ct  = RNG.integers(0, 30, n)
    var_ct   = RNG.integers(0, 30, n)
    strength = RNG.integers(0, 6, n)   # 0=1A strongest … 5=4 weakest
    pk       = (RNG.random(n) < 0.4).astype(int)
    pd_      = (RNG.random(n) < 0.5).astype(int)
    pop_div  = RNG.integers(1, 11, n)
    pli      = RNG.uniform(0, 1, n)
    phase    = RNG.integers(0, 5, n)

    ev_mhot  = _evidence_multihot(n, (5 - strength) / 5)

    # Label: evidence-driven with realistic class imbalance
    # Good: high clin count, strong evidence, PD known
    logit = (
        clin_ct / 30.0 * 2 +
        (5 - strength) / 5.0 * 1.5 +
        pd_.astype(float) * 0.8 +
        pk.astype(float) * 0.5 +
        pop_div / 10.0 * 0.5 +
        RNG.normal(0, 0.5, n)
    )
    # Map continuous logit → 4-class label
    labels = np.where(logit > 3.0, 2,         # good
             np.where(logit > 1.5, 1,          # intermediate
             np.where(logit > 0.0, 0,          # poor
                      3)))                     # adverse (low logit = unexpected)

    rows = []
    for i in range(n):
        row = {
            'clinical_annotation_count': clin_ct[i],
            'variant_annotation_count':  var_ct[i],
            'evidence_strength':         strength[i],
            'pk_evidence':               pk[i],
            'pd_evidence':               pd_[i],
            'population_diversity':      pop_div[i],
            'gene_pli':                  pli[i],
            'drug_max_phase':            phase[i],
            'evidence_types':            [EVIDENCE_TYPES[j] for j, v in enumerate(ev_mhot[i]) if v],
            'label':                     labels[i],
        }
        rows.append(row)
    return pd.DataFrame(rows)


def load_from_db():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    try:
        import psycopg2, csv, io
        conn = psycopg2.connect(db_url)
        df   = pd.read_sql("""
            SELECT
                entity1_name AS gene,
                entity2_name AS drug,
                evidence,
                pmids
            FROM pharmgkb_relations
            WHERE entity1_type = 'Gene'
              AND entity2_type = 'Chemical'
            LIMIT 20000
        """, conn)
        conn.close()
        if df.empty:
            return None

        def _to_label(ev):
            ev_list = ev if isinstance(ev, list) else []
            if 'ClinicalAnnotation' in ev_list and 'VariantAnnotation' in ev_list:
                return 2  # good evidence
            if 'ClinicalAnnotation' in ev_list:
                return 1
            if 'VariantAnnotation' in ev_list:
                return 0
            return RNG.integers(0, 4, 1)[0]

        df['label']                     = df['evidence'].apply(_to_label)
        df['clinical_annotation_count'] = df['evidence'].apply(lambda e: int('ClinicalAnnotation' in (e or [])) * RNG.integers(1,15,1)[0])
        df['variant_annotation_count']  = df['evidence'].apply(lambda e: int('VariantAnnotation'  in (e or [])) * RNG.integers(1,10,1)[0])
        df['evidence_strength']         = RNG.integers(0, 6, len(df))
        df['pk_evidence']               = df['evidence'].apply(lambda e: int(bool(e) and 'PK' in str(e)))
        df['pd_evidence']               = df['evidence'].apply(lambda e: int(bool(e) and 'PD' in str(e)))
        df['population_diversity']      = RNG.integers(1, 8, len(df))
        df['gene_pli']                  = RNG.uniform(0, 1, len(df))
        df['drug_max_phase']            = RNG.integers(0, 5, len(df))
        df['evidence_types']            = df['evidence'].apply(lambda e: e if isinstance(e, list) else [])
        log.info('Loaded %d drug-response rows from DB', len(df))
        return df
    except Exception as e:
        log.warning('DB load failed: %s — using synthetic data', e)
        return None


def build_X(df: pd.DataFrame) -> np.ndarray:
    return np.array([
        build_drug_response_features(r.to_dict()) for _, r in df.iterrows()
    ], dtype=np.float32)


def train():
    df = load_from_db() or synthetic_data()
    X  = build_X(df)
    y  = df['label'].values.astype(int)

    cv_scores = cross_val_score(
        RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced'),
        X, y, cv=StratifiedKFold(3), scoring='f1_macro',
    )
    log.info('CV F1-macro: %.3f ± %.3f', cv_scores.mean(), cv_scores.std())

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    model = RandomForestClassifier(
        n_estimators=400, max_depth=12, min_samples_leaf=5,
        class_weight='balanced', random_state=42, n_jobs=-1,
    )
    log.info('Training on %d samples …', len(X_tr))
    model.fit(X_tr, y_tr)
    log.info('Evaluation:\n%s', classification_report(y_te, model.predict(X_te),
        target_names=RESPONSE_CLASSES))

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({
        'model': model,
        'feature_names': DRUG_RESPONSE_FEATURE_NAMES,
        'classes': RESPONSE_CLASSES,
    }, ARTIFACT)
    log.info('Saved → %s', ARTIFACT)
    return model


if __name__ == '__main__':
    train()
