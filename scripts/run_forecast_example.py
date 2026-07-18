#!/usr/bin/env python
"""Run a deterministic six-hour forecast example."""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd
import plotly.graph_objects as go

from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.inference import ForecastService
from greenmpc.forecasting.splits import assign_chronological_splits
from greenmpc.forecasting.features import build_solar_features
from greenmpc.forecasting.training import PROJECT_ROOT as ROOT


def main() -> int:
    cfg = load_forecasting_config(ROOT / "configs/forecasting.yaml")
    tenant = pd.read_csv(ROOT / "data/processed/tenant_hourly.csv")
    park = pd.read_csv(ROOT / "data/processed/park_hourly.csv")
    solar_features = build_solar_features(park, cfg).frame
    split, _, _ = assign_chronological_splits(solar_features, cfg)
    origin = pd.Timestamp(split[split["split"] == "test"]["forecast_origin_local"].iloc[0])
    service = ForecastService.from_registry()
    start = time.perf_counter()
    load_forecast, solar_forecast = service.forecast_all(tenant, park, origin, 6)
    latency = time.perf_counter() - start
    output = ROOT / "data/outputs/stage4_example"
    output.mkdir(parents=True, exist_ok=True)
    load_df = load_forecast.to_dataframe()
    solar_df = solar_forecast.to_dataframe()
    load_df.to_csv(output / "load_forecast.csv", index=False)
    solar_df.to_csv(output / "solar_forecast.csv", index=False)
    _write_example_html(load_df, solar_df, ROOT / "artifacts/forecast_example.html")
    print(f"origin: {origin}")
    print("horizons: [1, 2, 3, 4, 5, 6]")
    print(f"model_version: {load_forecast.metadata.model_version}")
    print(f"inference_latency_seconds: {latency}")
    print("load_forecast:")
    print(load_df[["timestamp_local", "tenant_id", "horizon_hours", "p10_kw", "p50_kw", "p90_kw", "quantile_corrected", "clipped_to_zero"]].to_string(index=False))
    print("solar_forecast:")
    print(solar_df[["timestamp_local", "horizon_hours", "p10_kw", "p50_kw", "p90_kw", "quantile_corrected", "clipped_to_zero", "clipped_to_capacity", "forced_nighttime_zero"]].to_string(index=False))
    print("data_quality_status: OK")
    return 0


def _write_example_html(load: pd.DataFrame, solar: pd.DataFrame, path: Path) -> None:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=load["timestamp_local"], y=load["p50_kw"], mode="markers", name="tenant P50 forecast"))
    fig.add_trace(go.Scatter(x=solar["timestamp_local"], y=solar["p50_kw"], mode="lines+markers", name="solar P50 forecast"))
    fig.add_trace(go.Scatter(x=solar["timestamp_local"], y=solar["p90_kw"], mode="lines", name="P90 interval upper"))
    fig.add_trace(go.Scatter(x=solar["timestamp_local"], y=solar["p10_kw"], mode="lines", name="P10 interval lower"))
    fig.update_layout(title="Forecast example: future actuals may be displayed for evaluation only; not actual VRG performance", template="plotly_white")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(path, include_plotlyjs=True)


if __name__ == "__main__":
    raise SystemExit(main())
