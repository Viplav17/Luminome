"""
Models/pathogenicity/predict.py
Inference wrapper for the LightGBM pathogenicity classifier.

Usage:
    from Models.pathogenicity.predict import predict_pathogenicity
    result = predict_pathogenicity({
        'mutation_type': 'missense',
        'conservation_score': 8.2,
        'allele_frequency': 0.0001,
        'submission_count': 3,
        'review_status': 'single_submitter',
        'gene_pli': 0.9,
        'splicing_distance': 12,
    })
    # {'label': 'pathogenic', 'label_id': 2, 'confidence': 0.91,
    #  'probabilities': {'benign': 0.03, 'uncertain': 0.06, 'pathogenic': 0.91},
    #  'shap': [...]}
"""

import os, sys, logging
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_pathogenicity_features

log = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'pathogenicity.pkl')
LABELS   = ['benign', 'uncertain', 'pathogenic']

_cache = {}


def _load():
    if 'bundle' not in _cache:
        import joblib
        if not os.path.exists(ARTIFACT):
            raise FileNotFoundError(
                f'Model not trained yet. Run: python Models/pathogenicity/train.py'
            )
        _cache['bundle'] = joblib.load(ARTIFACT)
    return _cache['bundle']


def predict_pathogenicity(features: dict) -> dict:
    bundle = _load()
    model  = bundle['model']
    X = np.array([build_pathogenicity_features(features)], dtype=np.float32)
    proba  = model.predict_proba(X)[0]
    lid    = int(np.argmax(proba))
    result = {
        'label':         LABELS[lid],
        'label_id':      lid,
        'confidence':    round(float(proba[lid]), 4),
        'probabilities': {LABELS[i]: round(float(p), 4) for i, p in enumerate(proba)},
    }
    # SHAP explanation — only if lightgbm is available (fast tree explainer)
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(X)
        # sv is list[class] each shape (1, n_features) for multiclass
        values = sv[lid][0] if isinstance(sv, list) else sv[0]
        names  = bundle.get('feature_names', [])
        result['shap'] = [
            {'feature': names[i] if i < len(names) else f'f{i}',
             'value':   round(float(v), 4)}
            for i, v in enumerate(values)
        ]
    except Exception:
        result['shap'] = []
    return result
