"""
Models/server.py
FastAPI inference server — exposes all 5 ML models over HTTP on port 3002.
Node.js backend calls this service for predictions.

Start:
    python Models/server.py
    # or: uvicorn Models.server:app --port 3002 --reload

Endpoints:
    POST /predict/pathogenicity
    POST /predict/variant
    POST /predict/disease-risk
    POST /predict/drug-response
    POST /predict/trial-match
    POST /predict/rank-trials
    GET  /health
    GET  /models/status
"""

import os, sys, logging
from contextlib import asynccontextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s [ml-server] %(message)s')
log = logging.getLogger(__name__)

# ── Lazy model registry ───────────────────────────────────────────────────────

MODELS: dict[str, Any] = {}

def _try_load(name: str, loader_fn):
    try:
        MODELS[name] = loader_fn()
        log.info('Loaded model: %s', name)
    except FileNotFoundError as e:
        log.warning('Model not trained yet — %s: %s', name, e)
        MODELS[name] = None
    except Exception as e:
        log.error('Failed to load %s: %s', name, e)
        MODELS[name] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info('Loading ML models …')
    from Models.pathogenicity.predict      import predict_pathogenicity
    from Models.variant_classification.predict import predict_variant
    from Models.disease_risk.predict       import predict_disease_risk, batch_predict
    from Models.drug_response.predict      import predict_drug_response
    from Models.trial_matching.predict     import predict_trial_match, rank_trials

    # Pre-warm each model's cache by importing (they load on first call)
    MODELS['pathogenicity']   = predict_pathogenicity
    MODELS['variant']         = predict_variant
    MODELS['disease_risk']    = predict_disease_risk
    MODELS['disease_risk_batch'] = batch_predict
    MODELS['drug_response']   = predict_drug_response
    MODELS['trial_match']     = predict_trial_match
    MODELS['rank_trials']     = rank_trials
    log.info('All model functions registered')
    yield
    log.info('ML server shutting down')


app = FastAPI(title='MutationMap ML Service', version='1.0.0', lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=['http://localhost:3001', 'http://localhost:3000'],
    allow_methods=['*'], allow_headers=['*'],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PathogenicityIn(BaseModel):
    mutation_type:      str   = 'other'
    conservation_score: float = 0.0
    allele_frequency:   float = 0.0
    submission_count:   int   = 1
    review_status:      str   = 'no_criteria'
    gene_pli:           float = 0.0
    splicing_distance:  int   = 500


class VariantIn(PathogenicityIn):
    domain_overlap:           bool  = False
    af_popmax:                float = 0.0
    known_functional_impact:  bool  = False
    repeat_region:            bool  = False
    cadd_score:               float = 0.0


class DiseaseRiskIn(BaseModel):
    genetic_score:      float = 0.0
    somatic_score:      float = 0.0
    literature_score:   float = 0.0
    drug_score:         float = 0.0
    rna_score:          float = 0.0
    animal_model_score: float = 0.0
    disease_category:   str   = 'other'
    gene_type:          str   = 'other'


class DiseaseRiskBatchIn(BaseModel):
    records: list[DiseaseRiskIn]


class DrugResponseIn(BaseModel):
    clinical_annotation_count: int        = 0
    variant_annotation_count:  int        = 0
    evidence_strength:         int        = 5
    pk_evidence:               bool       = False
    pd_evidence:               bool       = False
    population_diversity:      int        = 1
    gene_pli:                  float      = 0.0
    drug_max_phase:            int        = 0
    evidence_types:            list[str]  = Field(default_factory=list)


class TrialMatchIn(BaseModel):
    has_mutation_in_trial_gene: bool  = False
    diagnosis_match:            float = 0.0
    age_eligible:               bool  = True
    prior_treatment_match:      float = 0.0
    biomarker_match:            float = 0.0
    trial_phase:                int   = 1
    intervention_type_match:    bool  = False
    mutation_type_match:        float = 0.0
    oncology_flag:              bool  = False
    gene_mutation_count:        int   = 0


class TrialIn(TrialMatchIn):
    trial_id:   str = ''
    trial_name: str = ''


class RankTrialsIn(BaseModel):
    patient:  TrialMatchIn
    trials:   list[TrialIn]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require(name: str):
    fn = MODELS.get(name)
    if fn is None:
        raise HTTPException(status_code=503,
            detail=f'Model "{name}" not trained. Run: python Models/{name}/train.py')
    return fn


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get('/health')
def health():
    return {'ok': True, 'service': 'ml'}


@app.get('/models/status')
def models_status():
    import os
    artifact_dir = os.path.join(ROOT, 'Models', 'artifacts')
    names = ['pathogenicity', 'variant_classification', 'disease_risk',
             'drug_response', 'trial_matching']
    return {
        n: os.path.exists(os.path.join(artifact_dir, f'{n}.pkl'))
        for n in names
    }


@app.post('/predict/pathogenicity')
def predict_pathogenicity_route(body: PathogenicityIn):
    fn = _require('pathogenicity')
    try:
        return fn(body.model_dump())
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post('/predict/variant')
def predict_variant_route(body: VariantIn):
    fn = _require('variant')
    try:
        return fn(body.model_dump())
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post('/predict/disease-risk')
def predict_disease_risk_route(body: DiseaseRiskIn):
    fn = _require('disease_risk')
    try:
        return fn(body.model_dump())
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post('/predict/disease-risk/batch')
def batch_disease_risk_route(body: DiseaseRiskBatchIn):
    fn = _require('disease_risk_batch')
    try:
        return fn([r.model_dump() for r in body.records])
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post('/predict/drug-response')
def predict_drug_response_route(body: DrugResponseIn):
    fn = _require('drug_response')
    try:
        return fn(body.model_dump())
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post('/predict/trial-match')
def predict_trial_match_route(body: TrialMatchIn):
    fn = _require('trial_match')
    try:
        return fn(body.model_dump())
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post('/predict/rank-trials')
def rank_trials_route(body: RankTrialsIn):
    fn = _require('rank_trials')
    try:
        patient = body.patient.model_dump()
        trials  = [t.model_dump() for t in body.trials]
        return fn(patient, trials)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('Models.server:app', host='0.0.0.0', port=3002, reload=False)
