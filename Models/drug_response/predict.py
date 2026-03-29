"""
Models/drug_response/predict.py
Inference wrapper — predicts patient drug response category from genotype
+ PharmGKB evidence features.
"""

import os, sys, logging
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import build_drug_response_features

log      = logging.getLogger(__name__)
ARTIFACT = os.path.join(ROOT, 'Models', 'artifacts', 'drug_response.pkl')

_cache = {}


def _load():
    if 'bundle' not in _cache:
        import joblib
        if not os.path.exists(ARTIFACT):
            raise FileNotFoundError('Run: python Models/drug_response/train.py')
        _cache['bundle'] = joblib.load(ARTIFACT)
    return _cache['bundle']


def predict_drug_response(features: dict) -> dict:
    """
    features: clinical_annotation_count, variant_annotation_count,
              evidence_strength, pk_evidence, pd_evidence,
              population_diversity, gene_pli, drug_max_phase,
              evidence_types (list of str)

    Returns:
      response: 'poor' | 'intermediate' | 'good' | 'adverse'
      confidence: float
      probabilities: {class: float}
      important_features: top-3 feature importances
    """
    bundle  = _load()
    model   = bundle['model']
    classes = bundle.get('classes', ['poor', 'intermediate', 'good', 'adverse'])

    X     = np.array([build_drug_response_features(features)], dtype=np.float32)
    proba = model.predict_proba(X)[0]
    lid   = int(np.argmax(proba))

    # Top-3 feature importances (global, not per-sample for RF)
    imp   = model.feature_importances_
    names = bundle.get('feature_names', [f'f{i}' for i in range(len(imp))])
    top3  = sorted(zip(names, imp), key=lambda x: -x[1])[:3]

    return {
        'response':     classes[lid],
        'label_id':     lid,
        'confidence':   round(float(proba[lid]), 4),
        'probabilities': {classes[i]: round(float(p), 4) for i, p in enumerate(proba)},
        'important_features': [
            {'feature': n, 'importance': round(float(v), 4)} for n, v in top3
        ],
    }
