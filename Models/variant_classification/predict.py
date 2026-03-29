"""
Models/variant_classification/predict.py
Inference wrapper — returns continuous pathogenicity score 0–1 for a VUS.
"""

import os, sys, logging
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_variant_features

log      = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'variant_classification.pkl')

_cache = {}


def _load():
    if 'bundle' not in _cache:
        import joblib
        if not os.path.exists(ARTIFACT):
            raise FileNotFoundError('Run: python Models/variant_classification/train.py')
        _cache['bundle'] = joblib.load(ARTIFACT)
    return _cache['bundle']


def _interpret(score: float) -> str:
    if score < 0.3:  return 'likely_benign'
    if score < 0.55: return 'uncertain'
    if score < 0.75: return 'likely_pathogenic'
    return 'pathogenic'


def predict_variant(features: dict) -> dict:
    """
    features: same keys as build_variant_features expects.
    Returns: {'score': float, 'interpretation': str, 'shap': [...]}
    """
    bundle = _load()
    model  = bundle['model']
    X = np.array([build_variant_features(features)], dtype=np.float32)
    score = float(np.clip(model.predict(X)[0], 0.0, 1.0))

    result = {
        'score':          round(score, 4),
        'interpretation': _interpret(score),
    }

    try:
        import shap
        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(X)[0]
        names = bundle.get('feature_names', [])
        result['shap'] = [
            {'feature': names[i] if i < len(names) else f'f{i}',
             'value':   round(float(v), 4)}
            for i, v in enumerate(sv)
        ]
    except Exception:
        result['shap'] = []

    return result
