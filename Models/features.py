"""
Models/features.py
Shared feature-engineering constants and helpers used by all 5 models.
"""

import numpy as np

# ── Categorical vocabularies ──────────────────────────────────────────────────

MUTATION_TYPES = [
    'missense', 'synonymous', 'frameshift', 'nonsense',
    'splice_site', 'inframe_indel', 'other',
]

REVIEW_STATUSES = [
    'no_criteria', 'single_submitter', 'multiple_submitters',
    'expert_panel', 'practice_guideline',
]

GENE_TYPES = [
    'protein_coding', 'lncRNA', 'miRNA',
    'snRNA', 'pseudogene', 'other',
]

DISEASE_CATEGORIES = [
    'cancer', 'cardiovascular', 'neurological',
    'metabolic', 'immunological', 'rare', 'other',
]

EVIDENCE_TYPES = [
    'ClinicalAnnotation', 'VariantAnnotation', 'MultilinkAnnotation',
    'Literature', 'AutomatedAnnotation',
]

RESPONSE_CLASSES = ['poor', 'intermediate', 'good', 'adverse']
RESPONSE_LABEL = {c: i for i, c in enumerate(RESPONSE_CLASSES)}

INTERVENTION_TYPES = [
    'targeted_therapy', 'chemotherapy', 'immunotherapy',
    'hormone_therapy', 'radiation', 'surgery', 'other',
]


# ── Encoding helpers ──────────────────────────────────────────────────────────

def encode_cat(val: str, vocab: list[str]) -> int:
    """Return index in vocab; unknown values map to last (= 'other')."""
    try:
        return vocab.index(str(val).lower())
    except ValueError:
        return len(vocab) - 1


def encode_multihot(vals: list[str], vocab: list[str]) -> list[int]:
    """One-hot encode a list of values against vocab."""
    idx = {v: i for i, v in enumerate(vocab)}
    vec = [0] * len(vocab)
    for v in vals:
        if v in idx:
            vec[idx[v]] = 1
    return vec


def clamp(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(np.clip(val, lo, hi))


# ── Pathogenicity feature builder ─────────────────────────────────────────────

def build_pathogenicity_features(d: dict) -> list[float]:
    """
    d keys: mutation_type, conservation_score, allele_frequency,
            submission_count, review_status, gene_pli, splicing_distance
    """
    return [
        encode_cat(d.get('mutation_type', 'other'), MUTATION_TYPES),
        clamp(float(d.get('conservation_score', 0)) / 10.0),
        clamp(float(d.get('allele_frequency', 0))),
        min(float(d.get('submission_count', 1)), 100) / 100.0,
        encode_cat(d.get('review_status', 'no_criteria'), REVIEW_STATUSES),
        clamp(float(d.get('gene_pli', 0))),
        min(float(d.get('splicing_distance', 1000)), 1000) / 1000.0,
    ]

PATHOGENICITY_FEATURE_NAMES = [
    'mutation_type', 'conservation_score_norm', 'allele_frequency',
    'submission_count_norm', 'review_status', 'gene_pli', 'splicing_distance_norm',
]


# ── Variant classification feature builder ────────────────────────────────────

def build_variant_features(d: dict) -> list[float]:
    """
    Extends pathogenicity features with structural/population features.
    d extra keys: domain_overlap, af_popmax, known_functional_impact, repeat_region
    """
    base = build_pathogenicity_features(d)
    return base + [
        float(bool(d.get('domain_overlap', False))),
        clamp(float(d.get('af_popmax', 0))),
        float(bool(d.get('known_functional_impact', False))),
        float(bool(d.get('repeat_region', False))),
        clamp(float(d.get('cadd_score', 0)) / 50.0),     # CADD score normalised
    ]

VARIANT_FEATURE_NAMES = PATHOGENICITY_FEATURE_NAMES + [
    'domain_overlap', 'af_popmax', 'known_functional_impact',
    'repeat_region', 'cadd_score_norm',
]


# ── Disease risk feature builder ──────────────────────────────────────────────

def build_disease_risk_features(d: dict) -> list[float]:
    """
    d keys: genetic_score, somatic_score, literature_score, drug_score,
            rna_score, animal_model_score, disease_category, gene_type
    """
    return [
        clamp(float(d.get('genetic_score',      0))),
        clamp(float(d.get('somatic_score',       0))),
        clamp(float(d.get('literature_score',    0))),
        clamp(float(d.get('drug_score',          0))),
        clamp(float(d.get('rna_score',           0))),
        clamp(float(d.get('animal_model_score',  0))),
        encode_cat(d.get('disease_category', 'other'), DISEASE_CATEGORIES),
        encode_cat(d.get('gene_type', 'other'),        GENE_TYPES),
    ]

DISEASE_RISK_FEATURE_NAMES = [
    'genetic_score', 'somatic_score', 'literature_score',
    'drug_score', 'rna_score', 'animal_model_score',
    'disease_category', 'gene_type',
]


# ── Drug response feature builder ─────────────────────────────────────────────

def build_drug_response_features(d: dict) -> list[float]:
    """
    d keys: clinical_annotation_count, variant_annotation_count,
            evidence_strength (0=1A, 1=1B, 2=2A, 3=2B, 4=3, 5=4),
            pk_evidence, pd_evidence, population_diversity,
            gene_pli, drug_max_phase, evidence_types (list)
    """
    mhot = encode_multihot(d.get('evidence_types', []), EVIDENCE_TYPES)
    return [
        min(float(d.get('clinical_annotation_count', 0)), 50) / 50.0,
        min(float(d.get('variant_annotation_count',  0)), 50) / 50.0,
        float(d.get('evidence_strength', 5)) / 5.0,
        float(bool(d.get('pk_evidence', False))),
        float(bool(d.get('pd_evidence', False))),
        min(float(d.get('population_diversity', 1)), 10) / 10.0,
        clamp(float(d.get('gene_pli', 0))),
        float(d.get('drug_max_phase', 0)) / 4.0,
    ] + mhot

DRUG_RESPONSE_FEATURE_NAMES = [
    'clinical_annotation_count_norm', 'variant_annotation_count_norm',
    'evidence_strength_norm', 'pk_evidence', 'pd_evidence',
    'population_diversity_norm', 'gene_pli', 'drug_max_phase_norm',
] + [f'evidence_{e}' for e in EVIDENCE_TYPES]


# ── Trial matching feature builder ────────────────────────────────────────────

def build_trial_features(d: dict) -> list[float]:
    """
    d keys: has_mutation_in_trial_gene, diagnosis_match, age_eligible,
            prior_treatment_match, biomarker_match, trial_phase,
            intervention_type_match, mutation_type_match,
            oncology_flag, gene_mutation_count
    """
    return [
        float(bool(d.get('has_mutation_in_trial_gene', False))),
        clamp(float(d.get('diagnosis_match',        0))),
        float(bool(d.get('age_eligible',            True))),
        clamp(float(d.get('prior_treatment_match',  0))),
        clamp(float(d.get('biomarker_match',        0))),
        float(d.get('trial_phase', 1)) / 4.0,
        float(bool(d.get('intervention_type_match', False))),
        clamp(float(d.get('mutation_type_match',    0))),
        float(bool(d.get('oncology_flag',           False))),
        min(float(d.get('gene_mutation_count', 0)), 20) / 20.0,
    ]

TRIAL_FEATURE_NAMES = [
    'has_mutation_in_trial_gene', 'diagnosis_match', 'age_eligible',
    'prior_treatment_match', 'biomarker_match', 'trial_phase_norm',
    'intervention_type_match', 'mutation_type_match',
    'oncology_flag', 'gene_mutation_count_norm',
]
