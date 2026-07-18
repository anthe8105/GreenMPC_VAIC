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
