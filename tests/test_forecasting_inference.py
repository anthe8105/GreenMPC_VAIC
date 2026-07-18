from __future__ import annotations

import pandas as pd
import pytest

from greenmpc.forecasting.exceptions import ForecastDataError
from greenmpc.forecasting.inference import ForecastService


def test_registered_six_hour_inference_is_deterministic() -> None:
    service = ForecastService.from_registry()
    tenant = pd.read_csv("data/processed/tenant_hourly.csv")
    park = pd.read_csv("data/processed/park_hourly.csv")
    origin = pd.Timestamp("2013-11-08 09:00:00+07:00")
    a, s = service.forecast_all(tenant, park, origin, 6)
    b, _ = service.forecast_all(tenant, park, origin, 6)
    assert len(a.predictions) == 30
    assert len(s.predictions) == 6
    assert a.predictions["p50_kw"].equals(b.predictions["p50_kw"])


def test_invalid_horizon_fails() -> None:
    service = ForecastService.from_registry()
    tenant = pd.read_csv("data/processed/tenant_hourly.csv")
    park = pd.read_csv("data/processed/park_hourly.csv")
    with pytest.raises(ForecastDataError):
        service.forecast_tenant_load(tenant, park, pd.Timestamp("2013-11-08 09:00:00+07:00"), 7)


def test_cached_model_loader_does_not_reload(monkeypatch) -> None:
    service = ForecastService.from_registry()
    calls = []
    sentinel = object()

    def fake_load_model(path):
        calls.append(path)
        return sentinel

    monkeypatch.setattr("greenmpc.forecasting.inference.load_model", fake_load_model)
    assert service._load_cached_model("load", 1, 0.5) is sentinel
    assert service._load_cached_model("load", 1, 0.5) is sentinel
    assert len(calls) == 1
