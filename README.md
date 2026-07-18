# GreenMPC Twin

GreenMPC Twin is an offline-capable AI energy digital twin foundation for industrial-park electricity and renewable-energy management. The MVP models five scenario tenants, rooftop solar, battery storage, grid purchases, DPPA renewable purchasing, transformer constraints, renewable allocation, controller comparison, and a live web Command Center.

## Current Status

Stages 0-7 are implemented: scope, public-data acquisition, hybrid dataset construction, the controller-independent digital twin, leakage-safe forecasting, continuous GreenMPC control, closed-loop evaluation, and the offline React/FastAPI Command Center. Investment simulation, final tenant evidence reports, and physical SCADA integration remain future-stage work.

## Architecture Summary

The repository uses a layered Python `src` layout:

- `greenmpc.data`: source caching, preprocessing, alignment, scaling, provenance, and validation.
- `greenmpc.forecasting`: features, chronological splits, training, quantile forecasts, inference, and metrics.
- `greenmpc.simulation`: park state transitions, battery state, cost accounting, allocation, events, and action validation.
- `greenmpc.control`: rule-based control, MPC formulation, solver execution, validation, and fallback behavior.
- `greenmpc.evaluation`: closed-loop backtesting, controller comparison, KPIs, and scenario evaluation.
- `greenmpc.reporting`: renewable ledger, tenant summaries, CSV export, and audit-ready HTML evidence reports.
- `greenmpc.ui`: shared live-session and view-model helpers used by the Streamlit fallback and the web API adapter.
- `backend`: FastAPI adapter exposing session, forecast, planning, execution, benchmark, and provenance endpoints.
- `frontend`: React + TypeScript industrial command-center interface.

## Hybrid Data Strategy

The project will combine public measured electricity profiles, hourly Vietnam weather and irradiance data, and published tariff references with derived PV output, rescaled scenario loads, configured asset assumptions, event assumptions, and simulator-generated allocation records. All live-demo data must be cached locally before execution.

## Technology Stack

Python >=3.11 and <3.13, NumPy, pandas, scikit-learn, CVXPY, HiGHS through highspy, FastAPI, Uvicorn, Streamlit, Plotly, PyYAML, joblib, pytest, React, TypeScript, Vite, standard-library dataclasses, and standard-library logging.

No Gurobi, gurobipy, CPLEX, proprietary optimization solvers, TensorFlow, PyTorch, cloud databases, or online services are required for the live demo.

## Installation

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## Fresh Clone Demo Setup

Use these commands for a clean teammate checkout. The repository includes the compact processed runtime data, trained forecasting models, controller configs, and read-only Stage 6 evidence needed by the local React/FastAPI demo.

```bash
git clone <repository-url>
cd <repository>

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e . --no-build-isolation

python scripts/verify_runtime_assets.py
```

Windows PowerShell activation:

```powershell
.\.venv\Scripts\activate
```

Build the frontend and launch the single-URL local demo:

```bash
cd frontend
npm install
npm run build
cd ..

python scripts/run_command_center.py
```

Open:

```text
http://127.0.0.1:8000
```

Bounded fresh-clone smoke check:

```bash
python scripts/smoke_fresh_clone.py
```

Git LFS is not required for the current runtime assets. The largest required file is the processed tenant-hourly CSV, which remains below normal GitHub file-size limits.

Common setup problems:

- Missing Node.js: install a current LTS Node.js release, then rerun `npm install` inside `frontend/`.
- Missing model files: run `python scripts/verify_runtime_assets.py` to identify the missing artifact path.
- Incompatible Python environment: use Python 3.11 or 3.12 and reinstall with `python -m pip install -e . --no-build-isolation`.
- Port 8000 already in use: stop the existing local process or run `python -m uvicorn backend.main:app --port 8001` for development.
- Frontend not built: run `cd frontend && npm run build` before `python scripts/run_command_center.py`.

## Tests

```bash
python -m pytest -q
```

## Verification

```bash
python scripts/verify_stage0.py
python scripts/verify_stage1.py
python scripts/verify_stage2.py
python scripts/verify_stage3.py
```

## Public Data Acquisition

Stage 1 source acquisition uses `configs/data_sources.yaml` and stores raw files under `data/raw/`, which is excluded from Git. Provenance metadata is stored under `data/provenance/`.

```bash
python scripts/acquire_public_data.py --all
python scripts/acquire_public_data.py --status
python scripts/acquire_public_data.py --all --offline
```

Acquire one source:

```bash
python scripts/acquire_public_data.py --source uci-load
python scripts/acquire_public_data.py --source uci-steel
python scripts/acquire_public_data.py --source nasa-power
python scripts/acquire_public_data.py --source tariff
```

Use `--force` to reacquire cached files. The large UCI electricity archive is not extracted by default; use `--extract-large` only for explicit manual inspection. Expected storage depends on the external archives, with the UCI electricity ZIP being the largest raw file.

## Hybrid Dataset Build

```bash
python scripts/build_hybrid_dataset.py
python scripts/build_hybrid_dataset.py --status
python scripts/verify_stage2.py
```

Use `--force` to rebuild processed outputs. Use `--reselect-profiles --force` only when intentionally replacing `configs/selected_profiles.yaml`.

## Digital Twin Smoke

```bash
python scripts/run_digital_twin_smoke.py
python scripts/verify_stage3.py
```

The Stage 3 simulator loads the Stage 2 processed dataset, validates externally generated actions, applies runtime events to effective values, updates battery state, calculates source allocations and operating costs, and records in-memory history. The included reference action is non-optimized and exists only for simulator verification.

## Forecasting

```bash
python scripts/train_forecasters.py --task all
python scripts/train_forecasters.py --status
python scripts/evaluate_forecasters.py --split test --task all
python scripts/run_forecast_example.py
python scripts/audit_forecast_baselines.py
python scripts/verify_stage4.py
```

Stage 4 trains direct multi-horizon P10/P50/P90 forecasters for tenant load and park PV availability. Forecast features use observations available at the forecast origin and known target-calendar metadata only; future actual weather and runtime events are excluded.

Forecast reporting distinguishes AI versus reactive persistence from AI versus seasonal persistence. A pre-Stage 5 upstream correction fixed the Stage 2 PV unit conversion from NASA `Wh/m^2`; old forecasting artifacts trained on the saturated PV series are incompatible and must be regenerated after rebuilding the dataset. `scripts/audit_forecast_baselines.py` independently verifies solar persistence baselines from processed data.

## GreenMPC Control

```bash
python scripts/run_mpc_diagnostic.py
python scripts/run_mpc_example.py
python scripts/verify_stage5.py
```

Stage 5 adds a transparent six-interval continuous linear MPC using CVXPY and HIGHS. Interval 0 uses the current effective digital-twin state; intervals 1-5 use Stage 4 forecast quantiles plus known tariff, DPPA, and transformer schedules. The controller returns a first `ParkAction` and validates it with the simulator, but it does not execute simulator steps or run closed-loop benchmarks.

## Closed-Loop Evaluation

```bash
python scripts/run_closed_loop_benchmark.py --quick
python scripts/run_closed_loop_benchmark.py
python scripts/run_closed_loop_benchmark.py --scenario combined_stress
python scripts/run_closed_loop_benchmark.py --status
python scripts/verify_stage6.py
```

Stage 6 compares `rule_based`, `deterministic_mpc`, and `greenmpc_conservative` in receding-horizon simulation. KPIs are realized from simulator histories. Stress events are synthetic and unannounced, and results are not actual VRG operational savings.

## Web Command Center

Development:

Terminal 1:

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Final local demo:

```bash
cd frontend
npm install
npm run build
cd ..
python scripts/run_command_center.py
```

Focused web verification:

```bash
python -m pytest tests/test_api_control_room.py -q -x
cd frontend && npm test -- --run
python scripts/verify_web_control_room.py
```

The React/FastAPI interface is the primary competition interface. It provides Manual Approval, Auto Pilot Demo, and Shadow Mode workflows, all backed by the approved simulator, forecasters, controllers, action validation, and read-only Stage 6 evidence.

## Investment Scenario Lab

Stage 8 extends the React/FastAPI product with an Investment Lab:

```bash
python -m pytest tests/test_investment_lab.py -q -x
cd frontend && npm test -- --run
cd frontend && npm run build
python scripts/verify_stage8.py
```

The lab compares baseline infrastructure against a proposed PV/BESS/DPPA configuration using cloned digital-twin runs. It produces realized technical metrics, illustrative financial metrics, and a tenant renewable evidence ZIP. It does not retrain models, rerun Stage 6 benchmarks, mutate global configs, or claim official renewable certification.

## Streamlit Fallback

```bash
streamlit run streamlit_app.py
python scripts/verify_stage7.py
```

The Streamlit interface remains a technical fallback and debugging interface. The React/FastAPI command center should be used for the polished demo.

## Repository Structure

```text
.
├── streamlit_app.py
├── configs/
│   └── demo.yaml
├── data/
│   ├── outputs/
│   ├── processed/
│   └── raw/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_STRATEGY.md
│   ├── PROJECT_SCOPE.md
│   └── STAGE_PLAN.md
├── scripts/
│   ├── acquire_public_data.py
│   └── verify_stage0.py
├── src/
│   └── greenmpc/
├── tests/
├── pyproject.toml
├── requirements.txt
└── README.md
```

## VRG Data Disclaimer

This repository does not use actual VRG operational data, actual VRG tenant data, actual confidential DPPA contracts, actual VRG battery specifications, or actual VRG transformer topology. Tenant names are scenario labels only and must not be presented as actual companies or actual VRG tenants.

## Future Stages

Stages 0-8 are complete in this working tree. Stage 9 will harden the submission package.
