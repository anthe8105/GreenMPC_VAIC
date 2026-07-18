from __future__ import annotations

import pandas as pd
import pytest

from greenmpc.config import load_config
from greenmpc.control.config import load_mpc_config
from greenmpc.control.controller import GreenMPCController
from greenmpc.control.exceptions import MPCSolverError
from greenmpc.control.types import MPCMode
from greenmpc.forecasting.inference import ForecastService
from greenmpc.simulation.park import IndustrialParkSimulator


def test_plan_with_fallback_labels_current_step_reference_action(monkeypatch):
    tenant = pd.read_csv("data/processed/tenant_hourly.csv")
    park = pd.read_csv("data/processed/park_hourly.csv")
    origin = pd.Timestamp("2013-11-08T09:00:00+07:00")
    service = ForecastService.from_registry("configs/forecasting.yaml")
    forecasts = service.forecast_all(tenant, park, origin, 6)
    sim = IndustrialParkSimulator.from_processed_files(start_timestamp=origin.isoformat())
    controller = GreenMPCController(load_config("configs/demo.yaml"), load_mpc_config("configs/mpc.yaml"))

    def broken(*args, **kwargs):
        raise MPCSolverError("synthetic failure")

    monkeypatch.setattr(controller, "solve", broken)
    result = controller.plan_with_fallback(sim, forecasts[0], forecasts[1], MPCMode.EXPECTED)
    assert result.fallback_action is not None
    assert result.fallback_action.controller_name == "safe_reference_fallback"
    assert result.fallback_action.metadata["uses_forecast"] is False
    assert result.valid_for_execution
