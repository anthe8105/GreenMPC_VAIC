#!/usr/bin/env python
"""Run a handcrafted six-hour MPC diagnostic, not a performance benchmark."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.config import load_config
from greenmpc.control.config import load_mpc_config
from greenmpc.control.controller import GreenMPCController
from greenmpc.control.diagnostics import plan_summary, write_plan_outputs
from greenmpc.control.types import MPCMode, MPCPlanningInput
from greenmpc.simulation.park import IndustrialParkSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_handcrafted_input(simulator: IndustrialParkSimulator, mode: MPCMode) -> MPCPlanningInput:
    cfg = simulator.config
    mpc_cfg = load_mpc_config(PROJECT_ROOT / "configs/mpc.yaml")
    state = simulator.get_state()
    exo = simulator.get_effective_exogenous()
    tenant_ids = tuple(tenant.tenant_id for tenant in cfg.tenants)
    ts_local = tuple((pd.Timestamp(state.timestamp_local) + pd.Timedelta(hours=i)).to_pydatetime() for i in range(6))
    ts_utc = tuple(pd.Timestamp(ts).tz_convert("UTC").to_pydatetime() for ts in ts_local)
    base = {tenant: [float(exo.effective_tenant_load_kw[tenant])] for tenant in tenant_ids}
    future_total = [2600, 2500, 2300, 3900, 4100, 3800] if mode is MPCMode.EXPECTED else [2800, 2700, 2500, 4300, 4500, 4200]
    weights = [1.1, 1.4, 0.9, 0.7, 1.0]
    for total in future_total[1:]:
        scale = total / sum(weights)
        for tenant, weight in zip(tenant_ids, weights):
            base[tenant].append(scale * weight)
    pv_future = [float(exo.effective_pv_available_kw), 3800, 4400, 150, 0, 0] if mode is MPCMode.EXPECTED else [float(exo.effective_pv_available_kw), 2600, 3000, 50, 0, 0]
    return MPCPlanningInput(
        planning_input_id=f"diagnostic-{mode.value}",
        controller_mode=mode,
        forecast_origin_local=state.timestamp_local,
        forecast_origin_utc=state.timestamp_utc,
        decision_timestamp_local=state.timestamp_local,
        decision_timestamp_utc=state.timestamp_utc,
        planning_timestamps_local=ts_local,
        planning_timestamps_utc=ts_utc,
        horizon_hours=6,
        time_step_hours=1.0,
        tenant_ids=tenant_ids,
        load_forecast_kw={tenant: tuple(values) for tenant, values in base.items()},
        renewable_target_fraction={tenant.tenant_id: tenant.renewable_target_fraction for tenant in cfg.tenants},
        cumulative_load_kwh=dict(state.cumulative_load_by_tenant_kwh),
        cumulative_renewable_delivery_kwh=dict(state.cumulative_renewable_by_tenant_kwh),
        pv_available_kw=tuple(pv_future),
        grid_price_vnd_per_kwh=(exo.grid_price_vnd_per_kwh, 1100, 1100, 3200, 3200, 3200),
        tariff_period=(exo.tariff_period, "off_peak", "off_peak", "peak", "peak", "peak"),
        dppa_available_kw=(exo.dppa_available_kw, 0, 0, 0, 0, 0),
        dppa_price_vnd_per_kwh=(exo.dppa_price_vnd_per_kwh, 1750, 1750, 1750, 1750, 1750),
        transformer_capacity_kw=(exo.transformer_capacity_kw, 5200, 5200, 5200, 5200, 5200),
        initial_energy_kwh=state.battery.energy_kwh,
        initial_soc_fraction=state.battery.soc_fraction,
        energy_capacity_kwh=cfg.battery.energy_capacity_kwh,
        minimum_energy_kwh=state.battery.minimum_energy_kwh,
        maximum_energy_kwh=state.battery.maximum_energy_kwh,
        maximum_charge_power_kw=state.battery.max_charge_power_kw,
        maximum_discharge_power_kw=state.battery.max_discharge_power_kw,
        charge_efficiency=cfg.battery.charge_efficiency,
        discharge_efficiency=cfg.battery.discharge_efficiency,
        degradation_cost_vnd_per_kwh_throughput=cfg.battery.degradation_cost_vnd_per_kwh_throughput,
        initial_renewable_fraction=state.battery.renewable_fraction,
        load_forecast_id="handcrafted-controller-unit-scenario",
        solar_forecast_id="handcrafted-controller-unit-scenario",
        load_model_version="handcrafted",
        solar_model_version="handcrafted",
        dataset_version=simulator.dataset_version,
        tenant_dataset_fingerprint="handcrafted",
        park_dataset_fingerprint="handcrafted",
        forecast_quantiles_used={"load": mpc_cfg.modes[mode.value].load_quantile, "solar": mpc_cfg.modes[mode.value].solar_quantile},
        current_interval_source="observed_effective_simulator_state",
        future_interval_source="stage4_forecast_quantiles_and_known_schedules",
        metadata={"handcrafted_controller_unit_scenario": True, "not_performance_benchmark": True},
    )


def main() -> int:
    project_cfg = load_config(PROJECT_ROOT / "configs/demo.yaml")
    mpc_cfg = load_mpc_config(PROJECT_ROOT / "configs/mpc.yaml")
    simulator = IndustrialParkSimulator.from_processed_files(start_timestamp="2013-04-03T11:00:00+07:00")
    controller = GreenMPCController(project_cfg, mpc_cfg)
    output_dir = PROJECT_ROOT / mpc_cfg.outputs.diagnostic_output_directory
    artifact_dir = PROJECT_ROOT / mpc_cfg.outputs.artifact_directory
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summaries = {}
    timings = {}
    for mode in (MPCMode.EXPECTED, MPCMode.CONSERVATIVE):
        planning = build_handcrafted_input(simulator.clone(), mode)
        planning.validate()
        start = time.perf_counter()
        plan = controller.solve(planning, simulator.clone())
        timings[f"{mode.value}_solve_seconds"] = time.perf_counter() - start
        write_plan_outputs(plan, output_dir, mode.value)
        plan.tenant_plan.to_csv(output_dir / f"{mode.value}_tenant_plan.csv", index=False)
        plan.park_plan.to_csv(output_dir / f"{mode.value}_park_plan.csv", index=False)
        summaries[mode.value] = plan_summary(plan)
        summaries[mode.value]["battery_charge_total_kw"] = float(plan.park_plan["battery_charge_kw"].sum())
        summaries[mode.value]["battery_discharge_total_kw"] = float(plan.park_plan["battery_discharge_kw"].sum())
        summaries[mode.value]["simultaneous_conflicts"] = list(plan.constraint_diagnostics.simultaneous_conflict_intervals)
    summary = {"label": "Handcrafted controller unit scenario, not a performance benchmark.", "timings": timings, "plans": summaries}
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_html(summary, artifact_dir / "mpc_diagnostic.html")
    print(json.dumps(summary, indent=2))
    return 0


def _write_html(summary: dict, path: Path) -> None:
    html = "<html><body><h1>Handcrafted MPC Diagnostic</h1><p>Handcrafted controller unit scenario, not a performance benchmark.</p><pre>" + json.dumps(summary, indent=2) + "</pre></body></html>"
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
