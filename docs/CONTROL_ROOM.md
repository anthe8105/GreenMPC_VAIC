# Control Room

Stage 7 adds a fully offline Live Control Room for the approved GreenMPC Twin stack. The primary competition interface is the React + FastAPI command center documented in [WEB_COMMAND_CENTER.md](WEB_COMMAND_CENTER.md). The Streamlit app remains as a technical fallback and debugging interface.

## Launch

Primary web command center:

```bash
cd frontend
npm install
npm run build
cd ..
python scripts/run_command_center.py
```

Streamlit fallback:

```bash
streamlit run streamlit_app.py
```

The app loads processed Stage 2 data, Stage 4 forecast models, the Stage 5 MPC controller, and Stage 6 benchmark summaries from local files only.

## Resource Caching

Heavy read-only resources are loaded through `st.cache_resource`:

- project, forecasting, MPC, and evaluation configuration;
- processed tenant and park data;
- `ForecastService` and the model registry;
- `GreenMPCController`;
- Stage 6 benchmark summary tables;
- dataset, model, and lineage metadata.

Mutable demo state lives in `st.session_state`. Resetting the demo creates a fresh simulator, observed-history adapter, scenario events, and empty forecast/plan/action state.

## Operation Modes

The Control Room supports three explicit modes:

- `Manual Approval`: forecast and planning require **Forecast and Re-optimize**. Execution requires **Approve & Execute Next Hour** or **Approve Fallback Action**.
- `Auto Pilot Demo`: the UI advances the simulated digital twin on a bounded schedule. Each control cycle reads current state, forecasts, plans, validates, executes one hour, invalidates the old plan, and refreshes views.
- `Shadow Mode`: the UI forecasts and optimizes on schedule but never executes automatically. It displays the recommended action as advisory output.

The default mode is `Manual Approval`, paused, with a five-second playback interval. Auto runs are limited to 24 simulated hours by default.

## Live Workflow

1. Initialize or reset the deterministic demo timestamp.
2. Inspect current load, PV, tariff, DPPA, transformer, and battery state.
3. Select `rule_based`, `deterministic_mpc`, or `greenmpc_conservative`.
4. Click **Forecast and Re-optimize**.
5. The app generates one shared six-hour load and solar forecast bundle.
6. MPC modes solve a six-interval plan; rule-based mode creates a current-observation-only action.
7. The first action is validated by the simulator.
8. Click **Execute Next Hour** to advance exactly one simulated hour.
9. The old plan is invalidated after execution and cannot be reused.

`Run Next 3 Hours` repeats the same reforecast, replan, validate, execute sequence one hour at a time. There is no unlimited automatic loop.

## Live Timing

Streamlit fragment-based periodic reruns check the live clock once per second when supported by the installed Streamlit version. Forecasting and MPC are triggered only when the configured playback interval has expired. The app records:

- running, paused, planning, executing, fallback, and error status;
- next-step countdown;
- completed and maximum simulated hours;
- most recent forecast, planning, validation, and execution latency;
- a run identifier that is reset on demo reset.

The live engine guards against overlapping reruns by marking a step in progress and remembering the processed tick key. Pausing prevents new control ticks. Reset cancels the active run identifier and invalidates any stale plan.

## Command Center Layout

The live tab uses a dark industrial command-center layout. Four primary cards show renewable share, cumulative operating cost, battery SOC, and transformer utilization. Secondary cards show park load, PV availability, grid import, DPPA import, external import, and renewable shortfall.

The topology panel shows Rooftop PV, DPPA, Grid, BESS, Park bus, curtailment, and all five tenants. Connections remain visible when inactive and scale by current kW when active.

## Controllers

- `rule_based`: transparent current-observation-only baseline. It uses no forecast and no optimization.
- `deterministic_mpc`: GreenMPC expected mode with P50 tenant-load and P50 solar forecasts.
- `greenmpc_conservative`: quantile-conservative deterministic MPC with P90 tenant-load and P10 solar forecasts.

Fallbacks from Stage 5 are shown visibly with the original failure reason. They are current-step safety actions, not successful GreenMPC optimization and not the Stage 6 rule-based baseline.

## Safety

Widget changes do not forecast, solve, or mutate the simulator. Expensive work is behind explicit buttons. Execution is disabled when:

- no action exists;
- the action failed validation;
- the plan timestamp no longer matches the simulator timestamp;
- the old plan has already been executed or invalidated.

Invalid actions preserve simulator state and display the exact validation error.

## Benchmark Evidence

The benchmark tab reads existing Stage 6 outputs only. It does not rerun simulations. It shows:

- realized operating-cost proxy;
- terminal battery inventory-adjusted cost;
- renewable share;
- peak grid and external import;
- battery throughput;
- final SOC;
- renewable shortfall;
- fallback count.

The terminal inventory valuation selector recomputes a diagnostic from stored histories. It does not overwrite realized operating cost.

## Provenance

The provenance tab states that:

- load shapes come from public measured profiles and are scenario-rescaled;
- weather and irradiance come from NASA POWER;
- PV is derived by the corrected Stage 2 formula and is not measured inverter output;
- tariffs and DPPA are demo assumptions;
- tenant industries and stress events are scenario constructs;
- no actual VRG operational data is claimed.

## Limitations

The Control Room is an offline competition demonstration. It is not connected to SCADA, does not issue physical commands, does not implement investment optimization, and does not generate audit-ready tenant reports.
