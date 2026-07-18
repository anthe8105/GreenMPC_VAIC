# Model Registry

Stage 4 stores model artifacts under `models/forecasting/`.

```text
models/forecasting/
├── load/horizon_01/quantile_010.joblib
├── solar/horizon_01/quantile_010.joblib
└── model_manifest.json
```

There are 18 load models and 18 solar models: six horizons times three quantiles per task.

## Compatibility

The manifest records dataset version, tenant and park dataset fingerprints, selected-profile lock fingerprint, forecasting-config fingerprint, Python version, scikit-learn version, model metadata, and artifact hashes.

Inference validates compatibility by default and rejects mismatched datasets or configuration fingerprints.

## Git Policy

Binary `.joblib` model artifacts are generated and should normally stay out of Git. The small manifest is reviewable and may be committed if needed for challenge packaging.
