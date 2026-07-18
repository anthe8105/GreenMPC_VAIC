# Web Command Center

Stage 7 now includes a React + FastAPI command center as the primary competition interface. The existing Streamlit app remains available as a technical fallback.

## Architecture

The browser talks to versioned FastAPI routes under `/api/v1`. FastAPI is a thin adapter over the approved Python core: processed data loading, `ForecastService`, digital-twin simulation, rule-based control, deterministic MPC, conservative MPC, validation, fallback handling, benchmark summaries, and provenance metadata.

Heavy immutable resources are cached once per backend process. Mutable simulator state is isolated per in-memory session and guarded by a per-session lock.

## Endpoints

- `GET /api/v1/health`
- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{session_id}/reset`
- `GET /api/v1/sessions/{session_id}/state`
- `POST /api/v1/sessions/{session_id}/forecast`
- `POST /api/v1/sessions/{session_id}/plan`
- `POST /api/v1/sessions/{session_id}/execute`
- `POST /api/v1/sessions/{session_id}/control-cycle`
- `GET /api/v1/benchmark`
- `GET /api/v1/provenance`
- `GET /api/v1/investment/defaults`
- `POST /api/v1/investment/analyses`
- `GET /api/v1/investment/analyses`
- `GET /api/v1/investment/analyses/{analysis_id}`
- `GET /api/v1/investment/analyses/{analysis_id}/result`
- `POST /api/v1/investment/analyses/{analysis_id}/cancel`
- `GET /api/v1/investment/analyses/{analysis_id}/export`

Every mutating request carries `request_id`, `run_id`, and `expected_timestamp`. Duplicate and stale execution requests are rejected or returned idempotently without advancing the simulator twice.

## Modes

Manual Approval requires explicit forecast/plan and execute actions.

Auto Pilot Demo uses a bounded frontend timer. Each tick sends one control-cycle request, the backend forecasts, replans, validates, and executes exactly one simulated hour.

Shadow Mode forecasts and plans on each tick but never executes automatically.

## Build And Launch

Development:

```bash
python -m uvicorn backend.main:app --reload --port 8000
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

After dependencies and frontend assets are installed, the runtime is offline and serves one local URL.

## Investment Lab

The Investment Lab is the Stage 8 product page. It guides users through defining a target, configuring a proposal, running a bounded digital-twin analysis, comparing baseline against proposal, and exporting tenant renewable evidence. The backend uses in-memory jobs and writes completed analyses under `data/outputs/stage8_investment`. Stage 6 benchmark files remain read-only.

## Disclosures

The interface uses hybrid public/scenario data. PV is derived from NASA POWER irradiance and is not measured inverter output. Tariff, DPPA, tenant labels, scaling, and stress events are scenario assumptions. Benchmark evidence is read-only and does not rerun Stage 6.
