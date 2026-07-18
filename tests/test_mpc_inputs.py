from __future__ import annotations

import pandas as pd

from greenmpc.config import load_config
from greenmpc.control.config import load_mpc_config
from greenmpc.control.controller import GreenMPCController
from greenmpc.control.types import MPCMode
from greenmpc.forecasting.inference import ForecastService
from greenmpc.simulation.park import IndustrialParkSimulator


def test_real_input_uses_observed_current_and_forecast_future_quantiles():
    tenant = pd.read_csv("data/processed/tenant_hourly.csv")
    park = pd.read_csv("data/processed/park_hourly.csv")
    origin = pd.Timestamp("2013-11-08T09:00:00+07:00")
    service = ForecastService.from_registry("configs/forecasting.yaml")
    load_forecast, solar_forecast = service.forecast_all(tenant, park, origin, 6)
    sim = IndustrialParkSimulator.from_processed_files(start_timestamp=origin.isoformat())
    controller = GreenMPCController(load_config("configs/demo.yaml"), load_mpc_config("configs/mpc.yaml"))
    planning = controller.build_input(sim, load_forecast, solar_forecast, MPCMode.CONSERVATIVE)
    assert planning.current_interval_source == "observed_effective_simulator_state"
    assert planning.future_interval_source == "stage4_forecast_quantiles_and_known_schedules"
    assert planning.forecast_quantiles_used == {"load": 0.9, "solar": 0.1}
    assert planning.pv_available_kw[0] == sim.get_effective_exogenous().effective_pv_available_kw
    assert len(planning.planning_timestamps_local) == 6
