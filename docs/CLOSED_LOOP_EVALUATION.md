# Closed-Loop Evaluation

Stage 6 compares three controllers in receding-horizon operation:

- `rule_based`: current-observation-only deterministic baseline. It uses no forecasts and no optimization.
- `deterministic_mpc`: Stage 5 GreenMPC expected mode using P50 load and P50 PV forecasts.
- `greenmpc_conservative`: quantile-conservative deterministic MPC using P90 load and P10 PV forecasts.

The benchmark runner clones one identical simulator state per controller and executes exactly one action per simulated hour. MPC controllers replan every hour; the remaining five plan intervals are not executed.

## Observed History

Forecast inputs are built from processed history plus realized event-adjusted observations through the current forecast origin. Completed benchmark timestamps and the current origin use effective load, PV, and DPPA values from the simulator. Stage 2 processed files are not modified.

The same forecast bundle is generated once per scenario timestamp and reused by both MPC modes. The rule-based baseline does not consume forecasts.

## Event Visibility

Stress events are synthetic and unannounced. They affect realized simulator load, PV, and DPPA. Future event effects are not manually inserted into forecast quantiles; controllers observe their impact only as time advances.

## Metrics

KPIs are calculated from executed simulator history, not planned MPC objectives. Reported operating-cost proxy includes grid energy cost, DPPA energy cost, and battery degradation proxy. MPC objective penalties are control preferences, not electricity bills.

These benchmark results use hybrid public/scenario data and are not actual VRG operating savings.

## Audit Corrections

Benchmark cache reuse is exact-match only. The manifest records requested and
completed hours, run mode, scenarios, controllers, timestamps, event
definitions, event visibility, dataset/model/MPC/evaluation fingerprints,
initial battery state, random seed, and a Stage 6 software-version identifier.
A 24-hour quick run is not compatible with a 72-hour full request.

The rule-based baseline writes `data/outputs/stage6_audit/rule_based_battery_trace.csv`.
Each row records tariff period, SOC, charge/discharge headroom, load, PV, DPPA,
transformer headroom, selected branch, battery power, and the reason for using
or not using the battery. The controller remains current-observation only and
uses no forecasts or optimization.

MPC fallback events write `data/outputs/stage6_audit/conservative_fallbacks.csv`.
Fallbacks are counted separately from successful GreenMPC planning and include
solver status, selected conservative load/PV values, fallback action,
validation status, and an inferred hard-constraint diagnostic.

Forecast diagnostics compare forecast origin `t` to realized event-adjusted
targets at `t+h` for horizons 1 through 6. The diagnostics include actual
values, P10/P50/P90, absolute error, bias, interval width, and interval
coverage.
