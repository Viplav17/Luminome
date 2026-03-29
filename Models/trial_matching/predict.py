"""
Models/trial_matching/predict.py
Inference wrapper — ranks a list of trials for a given patient profile
and returns match probabilities + human-readable explanations.
"""

import os, sys, logging
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_trial_features, TRIAL_FEATURE_NAMES

log      = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'trial_matching.pkl')

_cache = {}

# Human-readable explanation templates keyed by feature name
_EXPLANATIONS = {
    'has_mutation_in_trial_gene':   'Patient carries a mutation in the trial\'s target gene.',
    'diagnosis_match':              'Patient diagnosis overlaps with trial indication.',
    'age_eligible':                 'Patient age meets trial inclusion criteria.',
    'prior_treatment_match':        'Prior treatment history aligns with trial requirements.',
    'biomarker_match':              'Patient biomarker profile matches trial eligibility.',
    'trial_phase_norm':             'Trial phase is appropriate for this patient stage.',
    'intervention_type_match':      'Intervention type matches patient\'s treatment pathway.',
    'mutation_type_match':          'Mutation type is consistent with trial\'s target mechanism.',
    'oncology_flag':                'Trial targets an oncology indication relevant to patient.',
    'gene_mutation_count_norm':     'Mutation burden is compatible with trial eligibility.',
}


def _load():
    if 'bundle' not in _cache:
        import joblib
        if not os.path.exists(ARTIFACT):
            raise FileNotFoundError('Run: python Models/trial_matching/train.py')
        _cache['bundle'] = joblib.load(ARTIFACT)
    return _cache['bundle']


def _build_explanation(feature_vec: list[float], coefs: list[float],
                        names: list[str], threshold: float = 0.1) -> list[str]:
    """
    Return list of human-readable reasons for the match,
    based on logistic regression coefficients × feature values.
    Only include features where contribution exceeds threshold.
    """
    contribs = [c * v for c, v in zip(coefs, feature_vec)]
    top = sorted(
        [(names[i], contribs[i]) for i in range(len(names)) if contribs[i] > threshold],
        key=lambda x: -x[1],
    )[:4]
    return [_EXPLANATIONS.get(n, n.replace('_', ' ').capitalize()) for n, _ in top]


def predict_trial_match(patient_features: dict) -> dict:
    """
    Score a single patient-trial pair.

    patient_features: has_mutation_in_trial_gene, diagnosis_match, age_eligible,
                      prior_treatment_match, biomarker_match, trial_phase,
                      intervention_type_match, mutation_type_match,
                      oncology_flag, gene_mutation_count

    Returns: {'match_probability': float, 'match': bool, 'explanation': [str]}
    """
    bundle = _load()
    pipe   = bundle['pipeline']
    coefs  = bundle.get('coefficients', [])
    names  = bundle.get('feature_names', TRIAL_FEATURE_NAMES)

    vec  = build_trial_features(patient_features)
    X    = np.array([vec], dtype=np.float32)
    prob = float(pipe.predict_proba(X)[0, 1])

    return {
        'match_probability': round(prob, 4),
        'match':             prob >= 0.5,
        'explanation':       _build_explanation(vec, coefs, names),
    }


def rank_trials(patient_features_base: dict, trials: list[dict]) -> list[dict]:
    """
    Rank a list of trials for a patient.

    trials: list of dicts, each containing trial-specific fields that
            override or extend patient_features_base.
            Must include 'trial_id' and 'trial_name'.

    Returns: sorted list with match_probability, match, explanation.
    """
    bundle = _load()
    pipe   = bundle['pipeline']
    coefs  = bundle.get('coefficients', [])
    names  = bundle.get('feature_names', TRIAL_FEATURE_NAMES)

    results = []
    for trial in trials:
        merged = {**patient_features_base, **trial}
        vec    = build_trial_features(merged)
        X      = np.array([vec], dtype=np.float32)
        prob   = float(pipe.predict_proba(X)[0, 1])
        results.append({
            'trial_id':          trial.get('trial_id', ''),
            'trial_name':        trial.get('trial_name', ''),
            'match_probability': round(prob, 4),
            'match':             prob >= 0.5,
            'explanation':       _build_explanation(vec, coefs, names),
        })

    return sorted(results, key=lambda x: -x['match_probability'])
