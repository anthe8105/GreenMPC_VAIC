# Forecast Features

Forecast features are constructed per forecast origin, direct horizon, and task.

## Load Feature Groups

- Identity: tenant ID, archetype, scenario industry, horizon.
- Current observations at origin: tenant load, park load, PV availability, weather, solar resource, tariff period and price.
- Tenant lags: 1, 2, 3, 6, 12, 24, 48, and 168 hours.
- Park load lags: 1, 24, and 168 hours.
- Tenant rolling statistics ending at origin: means, standard deviations, 24-hour min, and 24-hour max.
- Weather and solar-resource lags: configured historical lags only.
- Static scenario metadata: target P95 load and scaling factor.
- Known target calendar: hour, day of week, day of month, month, weekend flag, tariff period, and cyclic encodings.

## Solar Feature Groups

- Current observations at origin: PV availability, solar resource, temperature, humidity, precipitation, wind, and installed capacity.
- PV and solar-resource lags: 1, 2, 3, 6, 24, 48, and 168 hours.
- Weather lags: configured historical lags only.
- Rolling statistics ending at origin for PV and solar resource.
- Known target calendar and daylight flag.

## Leakage Status

The generated `data/outputs/forecast_feature_manifest.json` records each feature, timestamp offset relative to origin, availability at origin, and leakage status. Target values are excluded from model matrices.
