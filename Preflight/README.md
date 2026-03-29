# Preflight Test Suite

Use this folder to run release checks before deploying MutationMap online.

## What It Tests

- Core project files exist.
- Chromosome pair STL coverage for `pair_01` through `pair_24`.
- ML server startup and health.
- Backend startup and health.
- Backend to ML proxy (`/api/ml/*`) for all core model routes:
  - pathogenicity
  - variant classification
  - disease risk
  - drug response
  - trial match
  - rank trials

## Run

From project root:

```bash
npm run preflight
```

By default, preflight uses dedicated ports to avoid collisions with already-running dev servers:

- Backend: `3101`
- ML: `3102`

Override if needed:

```bash
set PRECHECK_BACKEND_PORT=3201
set PRECHECK_ML_PORT=3202
npm run preflight
```

Optional mode (if services are already running):

```bash
node Preflight/run-core-tests.mjs --skip-start
```

Optional python override:

```bash
set PYTHON_CMD=C:\\path\\to\\python.exe
npm run preflight
```

## Output

The script prints a pass/fail report and exits with:

- `0` when all checks pass.
- `1` when any critical check fails.

This makes it suitable for CI and manual release gating.
