from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from tests._simulation_helpers import TENANTS


def tiny_history(hours: int = 220) -> tuple[pd.DataFrame, pd.DataFrame]:
    ts = pd.date_range("2013-01-01 00:00:00+07:00", periods=hours, freq="h")
    tenant_rows = []
    for tenant_index, tenant in enumerate(TENANTS):
        for i, stamp in enumerate(ts):
            load = 100 + tenant_index * 10 + (i % 24)
            tenant_rows.append({
                "timestamp_local": stamp.isoformat(),
                "timestamp_utc": stamp.tz_convert("UTC").isoformat(),
                "tenant_id": tenant,
                "archetype": f"a{tenant_index}",
                "scenario_industry": f"industry{tenant_index}",
                "load_kw": float(load),
                "load_kwh": float(load),
                "target_p95_load_kw": 200.0,
                "scaling_factor": 1.0,
                "load_is_actual_vrg_data": False,
                "calendar_transfer_applied": True,
            })
    park_rows = []
    for i, stamp in enumerate(ts):
        pv = max(0.0, 500.0 if 7 <= stamp.hour <= 17 else 0.0)
        park_rows.append({
            "timestamp_local": stamp.isoformat(),
            "timestamp_utc": stamp.tz_convert("UTC").isoformat(),
            "park_load_kw": float(sum(100 + j * 10 + (i % 24) for j in range(5))),
            "park_load_kwh": float(sum(100 + j * 10 + (i % 24) for j in range(5))),
            "pv_available_kw": pv,
            "pv_available_kwh": pv,
            "installed_pv_capacity_kw": 1000.0,
            "temperature_c": 25.0,
            "relative_humidity_pct": 80.0,
            "precipitation": 0.0,
            "wind_speed": 2.0,
            "solar_resource_raw": pv / 1000.0,
            "grid_price_vnd_per_kwh": 1000.0,
            "tariff_period": "normal",
            "weather_quality_flag": "ok",
            "load_quality_flag": "ok",
            "pv_quality_flag": "ok",
            "dataset_quality_flag": "ok",
        })
    return pd.DataFrame(tenant_rows), pd.DataFrame(park_rows)


def mutated_forecast_config(tmp_path: Path, mutate) -> Path:
    data = yaml.safe_load(Path("configs/forecasting.yaml").read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "forecasting.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path
