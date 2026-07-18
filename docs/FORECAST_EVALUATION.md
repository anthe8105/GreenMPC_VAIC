# Forecast Evaluation

Stage 4 uses chronological target-timestamp splitting. Target timestamps are assigned to train, validation, and test periods without shuffling. The same boundaries are used for all load tenants, load horizons, and solar horizons.

## Baselines

Load and solar are compared against:

- current value;
- previous day same hour;
- previous week same hour.

Baselines use the same test targets as the AI models. Missing baseline history is reported rather than filled with target truth.

## Metrics

Point metrics include MAE, RMSE, WAPE, normalized MAE, bias, and maximum absolute error. Quantile metrics include pinball loss for P10, P50, P90 and mean pinball loss. Interval metrics include empirical P10-P90 coverage, coverage error, interval width, below-interval frequency, and above-interval frequency.

## Interpretation

Metrics describe this public-data and scenario-assumption demonstration dataset. They must not be presented as actual VRG performance or as evidence from a deployed industrial park.
