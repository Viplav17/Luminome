"""
Models/disease_risk/predict.py
Inference wrapper — returns association confidence score 0–1 per gene-disease pair.
Used by the frontend to determine chromosome glow intensity in the disease filter.
"""

import os, sys, logging
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_disease_risk_features

log      = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'disease_risk.pkl')

_cache = {}


def _load():
    if 'bundle' not in _cache:
        import joblib
        if not os.path.exists(ARTIFACT):
            raise FileNotFoundError('Run: python Models/disease_risk/train.py')
        _cache['bundle'] = joblib.load(ARTIFACT)
    return _cache['bundle']


def predict_disease_risk(features: dict) -> dict:
    """
    features: genetic_score, somatic_score, literature_score, drug_score,
              rna_score, animal_model_score, disease_category, gene_type

    Returns: {'score': float, 'tier': str, 'shap': [...]}
    Tier: 'high' ≥0.7 | 'moderate' ≥0.4 | 'low' <0.4
    """
    bundle = _load()
    model  = bundle['model']
    X = np.array([build_disease_risk_features(features)], dtype=np.float32)
    score = float(np.clip(model.predict(X)[0], 0.0, 1.0))
    tier = 'high' if score >= 0.7 else ('moderate' if score >= 0.4 else 'low')

    result = {'score': round(score, 4), 'tier': tier}

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


def batch_predict(records: list[dict]) -> list[dict]:
    """Score multiple gene-disease pairs at once."""
    bundle = _load()
    model  = bundle['model']
    X = np.array([build_disease_risk_features(r) for r in records], dtype=np.float32)
    scores = model.predict(X).clip(0, 1)
    return [
        {'score': round(float(s), 4),
         'tier': 'high' if s >= 0.7 else ('moderate' if s >= 0.4 else 'low')}
        for s in scores
    ]
