"""
Models/trial_matching/train.py
Logistic Regression: patient genomic profile vs trial eligibility
criteria → match probability 0–1 + explanation per trial.

This is Medpace's core use case: given a patient's sequencing results,
return the trials they qualify for with a human-readable explanation
that clinicians and IRB reviewers can audit.

Run:
    python Models/trial_matching/train.py
"""

import os, sys, logging, joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, classification_report

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_trial_features, TRIAL_FEATURE_NAMES

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [trial_match] %(message)s')
log = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'trial_matching.pkl')
N   = 8000   # more samples for logistic regression to generalise well
RNG = np.random.default_rng(42)


def synthetic_data() -> pd.DataFrame:
    """
    Simulate patient-trial pairs.
    Positive (match=1, ~30%): patient has the target mutation, diagnosis matches,
                              meets age/biomarker criteria.
    Negative (match=0, ~70%): mismatch on ≥1 critical criterion.
    """
    n = N

    has_mut   = (RNG.random(n) < 0.45).astype(float)
    diag_sim  = RNG.beta(2, 3, n)
    age_ok    = (RNG.random(n) < 0.75).astype(float)
    prior_tx  = RNG.beta(1.5, 3, n)
    bio_match = RNG.beta(1.5, 3, n)
    phase     = RNG.integers(1, 5, n)
    iv_match  = (RNG.random(n) < 0.5).astype(float)
    mut_match = RNG.beta(2, 3, n)
    oncology  = (RNG.random(n) < 0.4).astype(float)
    mut_count = RNG.integers(0, 20, n)

    # Logistic ground-truth score
    logit = (
        has_mut   * 2.5 +
        diag_sim  * 2.0 +
        age_ok    * 1.5 +
        bio_match * 1.2 +
        prior_tx  * 0.8 +
        mut_match * 0.8 +
        iv_match  * 0.5 +
        oncology  * 0.4 +
        RNG.normal(0, 0.6, n)
    )
    prob   = 1 / (1 + np.exp(-logit + 4))   # shift so ~30% positive
    labels = (RNG.random(n) < prob).astype(int)

    return pd.DataFrame({
        'has_mutation_in_trial_gene': has_mut,
        'diagnosis_match':            diag_sim,
        'age_eligible':               age_ok,
        'prior_treatment_match':      prior_tx,
        'biomarker_match':            bio_match,
        'trial_phase':                phase,
        'intervention_type_match':    iv_match,
        'mutation_type_match':        mut_match,
        'oncology_flag':              oncology,
        'gene_mutation_count':        mut_count,
        'label':                      labels,
    })


def build_X(df: pd.DataFrame) -> np.ndarray:
    return np.array([
        build_trial_features(r.to_dict()) for _, r in df.iterrows()
    ], dtype=np.float32)


def train():
    df = synthetic_data()
    X  = build_X(df)
    y  = df['label'].values

    pos_rate = y.mean()
    log.info('Positive match rate: %.1f%%', pos_rate * 100)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('lr', LogisticRegression(
            C=0.5, class_weight='balanced', max_iter=1000,
            solver='lbfgs', random_state=42,
        )),
    ])

    cv = cross_val_score(pipe, X_tr, y_tr, cv=5, scoring='roc_auc')
    log.info('CV ROC-AUC: %.3f ± %.3f', cv.mean(), cv.std())

    pipe.fit(X_tr, y_tr)
    preds = pipe.predict(X_te)
    proba = pipe.predict_proba(X_te)[:, 1]
    log.info('Test ROC-AUC: %.3f', roc_auc_score(y_te, proba))
    log.info('Classification report:\n%s', classification_report(y_te, preds,
        target_names=['no_match', 'match']))

    # Store coefficients + names for explanation
    lr      = pipe.named_steps['lr']
    coefs   = lr.coef_[0].tolist()

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({
        'pipeline':      pipe,
        'feature_names': TRIAL_FEATURE_NAMES,
        'coefficients':  coefs,
    }, ARTIFACT)
    log.info('Saved → %s', ARTIFACT)
    return pipe


if __name__ == '__main__':
    train()
