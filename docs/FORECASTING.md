# Forecasting

Stage 4 trains reproducible probabilistic forecasters for the five scenario tenants and park-level rooftop-PV availability.

## Forecast Semantics

At forecast origin `t`, observations up to and including `t` may be used. The models predict direct horizons `t+1` through `t+6`.

Load forecasting uses one global multi-tenant model per horizon and quantile. Solar forecasting uses one park-level model per horizon and quantile. Quantiles are trained separately for P10, P50, and P90.

## Allowed and Forbidden Inputs

Known target calendar features are allowed because the calendar is known at forecast origin. Actual future load, actual future weather, future solar resource, future PV, and Stage 2 runtime event catalog entries are forbidden as primary model inputs.

## Quantiles

Raw quantile predictions are preserved. Corrected predictions are produced by monotonic rearrangement so P10 <= P50 <= P90. Negative predictions are clipped to zero. Solar forecasts are clipped to installed PV capacity and definite nighttime predictions are forced to zero.

## Limitations

The models forecast scenario-labeled, rescaled public measured load shapes and derived PV availability. They do not represent actual VRG forecasting performance and do not include event effects, MPC, or controller logic.
