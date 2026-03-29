"""
Models/trial_matching/train.py
Logistic Regression: patient genomic profile vs real ClinicalTrials.gov
eligibility signals -> match probability.

Run:
    python Models/trial_matching/train.py
"""

import os
import re
import sys
import logging

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_trial_features, TRIAL_FEATURE_NAMES

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [trial_match] %(message)s')
log = logging.getLogger(__name__)

ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'trial_matching.pkl')
CLINICAL_TRIALS = 'https://clinicaltrials.gov/api/v2/studies'


def _phase_to_num(phases: list[str]) -> int:
    txt = ' '.join(phases or []).upper()
    if 'PHASE4' in txt or 'PHASE 4' in txt:
        return 4
    if 'PHASE3' in txt or 'PHASE 3' in txt:
        return 3
    if 'PHASE2' in txt or 'PHASE 2' in txt:
        return 2
    return 1


def _age_to_years(text: str) -> int | None:
    t = (text or '').strip().lower()
    if not t or 'n/a' in t:
        return None
    m = re.match(r'^(\d+)\s*(year|years|month|months)$', t)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)
    if unit.startswith('month'):
        return max(0, val // 12)
    return val


def _contains_any(text: str, terms: list[str]) -> bool:
    s = (text or '').lower()
    return any(t in s for t in terms)


def _extract_gene_symbols(text: str) -> list[str]:
    # Coarse extraction from eligibility/title text.
    bad = {
        'DNA', 'RNA', 'AND', 'OR', 'NOT', 'WITH', 'WITHOUT', 'IN', 'OF', 'FOR',
        'ALL', 'ANY', 'WHO', 'ECOG', 'HLA', 'MRI', 'PET', 'CT', 'CAR', 'TCR',
    }
    found = re.findall(r'\b[A-Z][A-Z0-9]{1,7}\b', text or '')
    out = []
    seen = set()
    for token in found:
        if token in bad:
            continue
        if token not in seen:
            out.append(token)
            seen.add(token)
    return out[:20]


def fetch_trials(max_pages: int = 5, page_size: int = 200) -> list[dict]:
    studies = []
    page_token = None
    for _ in range(max_pages):
        params = {
            'query.term': 'cancer OR genomic OR mutation OR biomarker',
            'filter.overallStatus': 'RECRUITING,ACTIVE_NOT_RECRUITING',
            'pageSize': page_size,
        }
        if page_token:
            params['pageToken'] = page_token

        r = requests.get(CLINICAL_TRIALS, params=params, timeout=45)
        r.raise_for_status()
        data = r.json()
        chunk = data.get('studies') or []
        studies.extend(chunk)
        page_token = data.get('nextPageToken')
        if not page_token:
            break
    log.info('Fetched %d ClinicalTrials.gov studies', len(studies))
    return studies


def _study_to_base_features(study: dict) -> dict:
    ps = study.get('protocolSection') or {}
    ident = ps.get('identificationModule') or {}
    cond = ps.get('conditionsModule') or {}
    elig = ps.get('eligibilityModule') or {}
    design = ps.get('designModule') or {}
    arms = ps.get('armsInterventionsModule') or {}

    title = ident.get('briefTitle', '')
    conditions = cond.get('conditions', []) or []
    condition_txt = ' '.join(conditions)
    criteria = elig.get('eligibilityCriteria', '') or ''
    text = f'{title} {condition_txt} {criteria}'

    min_age = _age_to_years(elig.get('minimumAge'))
    max_age = _age_to_years(elig.get('maximumAge'))
    if min_age is None:
        min_age = 18
    if max_age is None:
        max_age = 80
    patient_age = (min_age + max_age) // 2
    age_eligible = int(min_age <= patient_age <= max_age)

    genes = _extract_gene_symbols(text)
    mut_terms = ['mutation', 'variant', 'alteration', 'deletion', 'amplification', 'fusion']
    biomarker_terms = ['biomarker', 'expression', 'pd-l1', 'her2', 'msi', 'tmb']
    prior_terms = ['prior therapy', 'previous treatment', 'failed', 'refractory', 'relapsed']

    interventions = ' '.join(
        [str(i.get('type', '')) for i in (arms.get('interventions') or [])]
    ).lower()

    return {
        'has_mutation_in_trial_gene': 1.0 if genes else 0.0,
        'diagnosis_match': 1.0 if conditions else 0.5,
        'age_eligible': float(age_eligible),
        'prior_treatment_match': 1.0 if _contains_any(criteria, prior_terms) else 0.6,
        'biomarker_match': 1.0 if _contains_any(text, biomarker_terms) else 0.5,
        'trial_phase': _phase_to_num(design.get('phases', [])),
        'intervention_type_match': 1.0 if interventions else 0.5,
        'mutation_type_match': 1.0 if _contains_any(text, mut_terms) else 0.4,
        'oncology_flag': 1.0 if _contains_any(text, ['cancer', 'tumor', 'carcinoma', 'neoplasm', 'oncology']) else 0.0,
        'gene_mutation_count': float(min(len(genes), 20)),
    }


def build_dataset_from_trials(studies: list[dict]) -> pd.DataFrame:
    rows = []
    for i, study in enumerate(studies):
        pos = _study_to_base_features(study)
        pos['label'] = 1
        rows.append(pos)

        # Hard negative: deliberately violate major criteria for same trial.
        neg = dict(pos)
        neg['has_mutation_in_trial_gene'] = 0.0
        neg['diagnosis_match'] = 0.0
        neg['age_eligible'] = 0.0
        neg['biomarker_match'] = 0.0
        neg['intervention_type_match'] = 0.0
        neg['mutation_type_match'] = max(0.0, pos['mutation_type_match'] - 0.5)
        neg['prior_treatment_match'] = 0.0
        neg['gene_mutation_count'] = 0.0
        neg['label'] = 0
        rows.append(neg)

        # Semi-hard negative every other trial for better decision boundary.
        if i % 2 == 0:
            semi = dict(pos)
            semi['diagnosis_match'] = 0.2
            semi['biomarker_match'] = 0.2
            semi['label'] = 0
            rows.append(semi)

    if not rows:
        raise RuntimeError('No trial-matching rows generated from ClinicalTrials.gov.')
    return pd.DataFrame(rows)


def build_X(df: pd.DataFrame) -> np.ndarray:
    return np.array([build_trial_features(r.to_dict()) for _, r in df.iterrows()], dtype=np.float32)


def train():
    studies = fetch_trials(max_pages=5, page_size=200)
    if not studies:
        raise RuntimeError('ClinicalTrials.gov returned no studies for training.')

    df = build_dataset_from_trials(studies)
    X = build_X(df)
    y = df['label'].values.astype(int)

    log.info('Training set size=%d, positive rate=%.1f%%', len(df), y.mean() * 100)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    pipe = Pipeline(
        [
            ('scaler', StandardScaler()),
            (
                'lr',
                LogisticRegression(
                    C=0.5,
                    class_weight='balanced',
                    max_iter=1000,
                    solver='lbfgs',
                    random_state=42,
                ),
            ),
        ]
    )

    cv = cross_val_score(pipe, X_tr, y_tr, cv=5, scoring='roc_auc')
    log.info('CV ROC-AUC: %.3f +/- %.3f', cv.mean(), cv.std())

    pipe.fit(X_tr, y_tr)
    preds = pipe.predict(X_te)
    proba = pipe.predict_proba(X_te)[:, 1]
    log.info('Test ROC-AUC: %.3f', roc_auc_score(y_te, proba))
    log.info('Classification report:\n%s', classification_report(y_te, preds, target_names=['no_match', 'match']))

    lr = pipe.named_steps['lr']
    coefs = lr.coef_[0].tolist()

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'pipeline': pipe, 'feature_names': TRIAL_FEATURE_NAMES, 'coefficients': coefs}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return pipe


if __name__ == '__main__':
    train()
