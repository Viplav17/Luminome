# Luminome (Rev-UC-26)

## Team

- Viplav Nagpal
- Romila Gholse
- Eesha Madan
- Sohana Gowda

## Final Project Story

This README is the real journey of the project, in plain language.

We started with a big idea: a genomics app that looked advanced, felt interactive, and still gave useful clinical-style insights. We wanted users to upload DNA reports, explore chromosomes, inspect mutation-level details, and ask AI questions safely.

## What We Wanted To Build

At the beginning, the dream was:
- 3D chromosome models (STL)
- Rich gene exploration
- AI-assisted discovery
- ML-backed prediction endpoints

It looked great in theory.

## What Went Wrong (And Why)

The 3D path turned out to be much harder to keep stable than expected.

Main issues:
- STL naming and folder structure mismatches
- Pair handling differences (expected A/B files vs actual uploaded files)
- XX/XY edge cases for sex chromosomes
- Fragile click/visibility behavior even after fixes

In short: we could keep patching it, but reliability stayed inconsistent.

## The Big Pivot

We made a deliberate decision to stop depending on runtime 3D.

Instead, we moved to a 2D canvas-first experience that is easier to maintain and test:
- Genome overview
- Vertical chromosome detail view
- DNA defect focus view with zoom

This was not giving up. It was choosing stability over visual complexity.

## What Works Well Now

### Frontend
- Chromosome browsing is stable and responsive
- Gene selection opens details in the side panel
- DNA defect view is accessible from selected genes
- Upload supports CSV/TSV and overlays severity data
- Sex-aware upload behavior:
  - Male report hides XX card
  - Female report hides XY card
- Disease and drug class filters highlight relevant genes across the genome
- AI natural language queries light up matching genes spatially
- Downloadable PDF summary report after uploading patient data

### Backend + ML + AI
- Backend and ML service communicate reliably
- Trial matching compatibility issues were fixed
- AI flow is now safer:
  - personal model first
  - Gemini fallback if needed
  - known-gene filtering to avoid fake outputs

### Release Safety
- `npm run preflight` checks core files, health endpoints, and model routes
- Latest verified state: checks passing

## Synthetic Upload Data

We expanded sample upload data from tiny files to large stress-test inputs (1500+ rows).

Files:
- `Frontend/sample_uploads/synthetic_male_dna_report.csv`
- `Frontend/sample_uploads/synthetic_female_dna_report.tsv`

These are useful for validating upload parsing, UI scaling, sorting, and XX/XY visibility behavior.

## Current Architecture

- Frontend: HTML/CSS/JavaScript canvas
- Backend: Node.js/Express
- ML service: Python/FastAPI
- AI fallback chain: Personal model -> Gemini
- Validation gate: Preflight script

## Ideas We Dropped (For Now)

- Production STL/3D chromosome viewer
- 3D helix dependency in core flow

We may revisit 3D later as an optional enhancement, not as a core dependency.

## What We Learned

- A stable product beats a flashy but fragile one
- Strict data conventions matter a lot in genomics tooling
- Preflight automation prevents late surprises
- AI should always be constrained by known domain data

## How To Run

1. Install dependencies
- `pip install -r requirements.txt`
- `npm install`

2. Run checks
- `npm run preflight`

3. Start services
- Start ML service first
- Start backend service second

---

Final status: Luminome is now a dependable, test-friendly genomics platform with practical AI fallback, strong upload testing support, and a clean path to deployment.
