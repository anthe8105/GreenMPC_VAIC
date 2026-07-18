# Forecast Evaluation

Stage 4 uses chronological target-timestamp splitting. Target timestamps are assigned to train, validation, and test periods without shuffling. The same boundaries are used for all load tenants, load horizons, and solar horizons.

## Baselines

Load and solar are compared against:

- current value;
- previous day same hour;
- previous week same hour.

Baselines use the same test targets as the AI models. Missing baseline history is reported rather than filled with target truth.

Stage 4 reporting separates:

- AI versus reactive persistence: comparison against the current-value baseline.
- AI versus seasonal persistence: comparison against previous-day and previous-week same-hour baselines.

On the current calendar-transferred demo PV dataset, previous-day and previous-week solar persistence can be extremely strong because the derived PV series is heavily clipped at installed capacity during positive-PV hours. If seasonal persistence remains better than the learned model, report: "The learned model improves over reactive persistence but does not outperform the strong seasonal baseline on this calendar-transferred dataset."

The independent audit script `scripts/audit_forecast_baselines.py` recomputes these baselines directly from `park_hourly.csv` and `tenant_hourly.csv`. It stores lag-source timestamps alongside target timestamps so target reuse is visible.

## Metrics

Point metrics include MAE, RMSE, WAPE, normalized MAE, bias, and maximum absolute error. Quantile metrics include pinball loss for P10, P50, P90 and mean pinball loss. Interval metrics include empirical P10-P90 coverage, coverage error, interval width, below-interval frequency, and above-interval frequency.

## Interpretation

Metrics describe this public-data and scenario-assumption demonstration dataset. They must not be presented as actual VRG performance or as evidence from a deployed industrial park.

Coverage above the nominal P10-P90 80% interval is overcoverage. It indicates conservative intervals or clipping effects, not automatically well-calibrated uncertainty.
