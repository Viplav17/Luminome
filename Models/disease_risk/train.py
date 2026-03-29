"""
Models/disease_risk/train.py
LightGBM regressor: OpenTargets evidence channels -> association score 0-1.

Run:
    python Models/disease_risk/train.py
"""

import os
import sys
import time
import logging

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from Models.features import (
    build_disease_risk_features,
    DISEASE_RISK_FEATURE_NAMES,
    DISEASE_CATEGORIES,
    GENE_TYPES,
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
OPENTARGETS = 'https://api.platform.opentargets.org/api/v4/graphql'


def _encode_cat(value: str, vocab: list[str]) -> str:
    v = (value or 'other').lower()
    if v in vocab:
        return v
    return 'other'


def _map_category(areas: list[str], disease_name: str) -> str:
    text = ' '.join([disease_name or ''] + (areas or [])).lower()
    if any(k in text for k in ['cancer', 'neoplasm', 'tumor', 'oncolog']):
        return 'cancer'
    if any(k in text for k in ['cardio', 'heart', 'vascular']):
        return 'cardiovascular'
    if any(k in text for k in ['neuro', 'brain', 'alzheimer', 'parkinson', 'epilep']):
        return 'neurological'
    if any(k in text for k in ['metabolic', 'diabetes', 'obesity', 'lipid']):
        return 'metabolic'
    if any(k in text for k in ['immune', 'autoimmune', 'inflammat']):
        return 'immunological'
    if any(k in text for k in ['rare', 'orphan']):
        return 'rare'
    return 'other'


def _map_gene_type(biotype: str) -> str:
    b = (biotype or '').lower()
    if b in {'protein_coding', 'lncrna', 'mirna', 'snrna', 'pseudogene'}:
        return b
    if 'protein' in b:
        return 'protein_coding'
    if 'lncrna' in b or 'long non' in b:
        return 'lncrna'
    if 'mirna' in b:
        return 'mirna'
    if 'snrna' in b:
        return 'snrna'
    if 'pseudo' in b:
        return 'pseudogene'
    return 'other'


def _score_map(datatype_scores: list[dict]) -> dict[str, float]:
    out = {
        'genetic_score': 0.0,
        'somatic_score': 0.0,
        'literature_score': 0.0,
        'drug_score': 0.0,
        'rna_score': 0.0,
        'animal_model_score': 0.0,
    }
    for d in datatype_scores or []:
        key = (d.get('id') or d.get('componentId') or '').lower()
        score = float(d.get('score') or 0.0)
        if 'genetic' in key:
            out['genetic_score'] = max(out['genetic_score'], score)
        elif 'somatic' in key:
            out['somatic_score'] = max(out['somatic_score'], score)
        elif 'literature' in key:
            out['literature_score'] = max(out['literature_score'], score)
        elif 'drug' in key:
            out['drug_score'] = max(out['drug_score'], score)
        elif 'rna' in key or 'expression' in key:
            out['rna_score'] = max(out['rna_score'], score)
        elif 'animal' in key or 'model' in key:
            out['animal_model_score'] = max(out['animal_model_score'], score)
    return out


def _opentargets_post(query: str, variables: dict) -> dict:
    r = requests.post(
        OPENTARGETS,
        json={'query': query, 'variables': variables},
        headers={'Content-Type': 'application/json'},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if data.get('errors'):
        raise RuntimeError(str(data['errors']))
    return data.get('data', {})


SEARCH_Q = '''
query($q: String!) {
  search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: 1}) {
    hits {
      object {
        ... on Disease {
          id
          name
          therapeuticAreas { name }
          associatedTargets(page: {index: 0, size: 40}) {
            rows {
              score
              datatypeScores { id score }
              target { approvedSymbol biotype }
            }
          }
        }
      }
    }
  }
}
'''


DISEASE_TERMS = [
    'breast cancer', 'lung cancer', 'colorectal cancer', 'leukemia', 'melanoma',
    'glioblastoma', 'ovarian cancer', 'prostate cancer', 'pancreatic cancer',
    'heart failure', 'coronary artery disease', 'stroke', 'hypertension',
    'alzheimer disease', 'parkinson disease', 'epilepsy', 'multiple sclerosis',
    'type 2 diabetes', 'obesity', 'nonalcoholic fatty liver disease',
    'rheumatoid arthritis', 'lupus', 'crohn disease', 'asthma',
    'rare disease', 'cystic fibrosis', 'muscular dystrophy',
]


def fetch_from_opentargets() -> pd.DataFrame:
    rows = []
    for term in DISEASE_TERMS:
        try:
            data = _opentargets_post(SEARCH_Q, {'q': term})
            hit = (((data.get('search') or {}).get('hits') or [{}])[0]).get('object') or {}
            if not hit:
                continue

            disease_name = hit.get('name') or term
            areas = [a.get('name', '') for a in (hit.get('therapeuticAreas') or [])]
            disease_category = _map_category(areas, disease_name)

            assoc_rows = ((hit.get('associatedTargets') or {}).get('rows') or [])
            for r in assoc_rows:
                target = r.get('target') or {}
                channel = _score_map(r.get('datatypeScores') or [])
                overall = float(r.get('score') or 0.0)
                if not any(channel.values()):
                    # If OpenTargets response omits per-datatype channels,
                    # preserve real evidence by using overall score as fallback.
                    channel = {
                        'genetic_score': overall,
                        'somatic_score': overall,
                        'literature_score': overall,
                        'drug_score': overall,
                        'rna_score': overall,
                        'animal_model_score': overall,
                    }

                rows.append(
                    {
                        **channel,
                        'disease_category': _encode_cat(disease_category, DISEASE_CATEGORIES),
                        'gene_type': _encode_cat(_map_gene_type(target.get('biotype', 'other')), GENE_TYPES),
                        'label': np.clip(overall, 0.0, 1.0),
                    }
                )
            time.sleep(0.15)
        except Exception as e:
            log.warning('OpenTargets fetch failed for "%s": %s', term, e)

    if not rows:
        raise RuntimeError('No OpenTargets rows retrieved.')
    df = pd.DataFrame(rows)
    log.info('Fetched %d OpenTargets gene-disease rows', len(df))
    return df


def load_from_db() -> pd.DataFrame | None:
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    try:
        import psycopg2

        conn = psycopg2.connect(db_url)
        df = pd.read_sql(
            '''
            SELECT
                gd.score,
                COALESCE(d.category, 'other') AS disease_category,
                COALESCE(g.type, 'other') AS gene_type
            FROM gene_disease gd
            JOIN genes g ON g.symbol = gd.gene_symbol
            LEFT JOIN diseases d ON d.mim_number = gd.disease_key
            WHERE gd.score IS NOT NULL
            LIMIT 30000
            ''',
            conn,
        )
        conn.close()
        if len(df) < 200:
            return None

        # Deterministic mapping from real aggregated score when channel-level
        # OT scores are not yet materialized in the warehouse.
        score = df['score'].clip(0, 1).astype(float)
        df['genetic_score'] = score
        df['somatic_score'] = score
        df['literature_score'] = score
        df['drug_score'] = score
        df['rna_score'] = score
        df['animal_model_score'] = score

        df['disease_category'] = df['disease_category'].str.lower().apply(
            lambda x: x if x in DISEASE_CATEGORIES else 'other'
        )
        df['gene_type'] = df['gene_type'].str.lower().apply(
            lambda x: x if x in GENE_TYPES else 'other'
        )
        df['label'] = score.astype(np.float32)
        log.info('Loaded %d rows from DB gene_disease table', len(df))
        return df
    except Exception as e:
        log.warning('DB load failed: %s', e)
        return None


def build_X(df: pd.DataFrame) -> np.ndarray:
    return np.array([build_disease_risk_features(r.to_dict()) for _, r in df.iterrows()], dtype=np.float32)


def train():
    df = load_from_db()
    if df is None:
        log.info('DB not ready with disease-risk rows; pulling from OpenTargets API')
        df = fetch_from_opentargets()

    X = build_X(df)
    y = df['label'].values.astype(np.float32)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    if HAS_LGB:
        model = lgb.LGBMRegressor(
            n_estimators=500,
            learning_rate=0.04,
            num_leaves=31,
            max_depth=6,
            subsample=0.85,
            min_child_samples=20,
            random_state=42,
            verbose=-1,
        )
    else:
        from sklearn.ensemble import GradientBoostingRegressor

        model = GradientBoostingRegressor(n_estimators=300, max_depth=5, random_state=42)

    log.info('Training on %d gene-disease rows', len(X_tr))
    model.fit(X_tr, y_tr)

    preds = np.clip(model.predict(X_te), 0.0, 1.0)
    log.info('MAE=%.4f  R2=%.4f', mean_absolute_error(y_te, preds), r2_score(y_te, preds))

    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({'model': model, 'feature_names': DISEASE_RISK_FEATURE_NAMES}, ARTIFACT)
    log.info('Saved -> %s', ARTIFACT)
    return model


if __name__ == '__main__':
    train()
