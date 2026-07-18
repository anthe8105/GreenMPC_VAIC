#!/usr/bin/env python
"""Run a one-step real-data GreenMPC planning example."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.config import load_config
from greenmpc.control.config import load_mpc_config
from greenmpc.control.controller import GreenMPCController
from greenmpc.control.diagnostics import plan_summary
from greenmpc.control.types import MPCMode
from greenmpc.forecasting.inference import ForecastService
from greenmpc.simulation.park import IndustrialParkSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    project_cfg = load_config(PROJECT_ROOT / "configs/demo.yaml")
    mpc_cfg = load_mpc_config(PROJECT_ROOT / "configs/mpc.yaml")
    output_dir = PROJECT_ROOT / mpc_cfg.outputs.example_output_directory
    artifact_dir = PROJECT_ROOT / mpc_cfg.outputs.artifact_directory
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    tenant = pd.read_csv(PROJECT_ROOT / "data/processed/tenant_hourly.csv")
    park = pd.read_csv(PROJECT_ROOT / "data/processed/park_hourly.csv")
    origin = pd.Timestamp("2013-11-08T09:00:00+07:00")

    t0 = time.perf_counter()
    service = ForecastService.from_registry(PROJECT_ROOT / "configs/forecasting.yaml")
    controller = GreenMPCController(project_cfg, mpc_cfg)
    simulator = IndustrialParkSimulator.from_processed_files(start_timestamp=origin.isoformat())
    init_seconds = time.perf_counter() - t0

    forecast_start = time.perf_counter()
    load_forecast, solar_forecast = service.forecast_all(tenant, park, origin, horizon_hours=6)
    forecast_seconds = time.perf_counter() - forecast_start
    load_forecast.to_dataframe().to_csv(output_dir / "load_forecast.csv", index=False)
    solar_forecast.to_dataframe().to_csv(output_dir / "solar_forecast.csv", index=False)

    plans = {}
    timings = {"controller_initialization_seconds": init_seconds, "forecast_generation_seconds": forecast_seconds}
    for mode in (MPCMode.EXPECTED, MPCMode.CONSERVATIVE):
        build_start = time.perf_counter()
        audit_path = mpc_cfg.outputs.example_output_directory + "/mpc_input_leakage_manifest.json" if mode is MPCMode.EXPECTED else None
        planning = controller.build_input(simulator.clone(), load_forecast, solar_forecast, mode, audit_path)
        timings[f"{mode.value}_input_build_seconds"] = time.perf_counter() - build_start
        solve_start = time.perf_counter()
        plan = controller.solve(planning, simulator.clone())
        timings[f"{mode.value}_cold_solve_seconds"] = time.perf_counter() - solve_start
        clone = simulator.clone()
        clone.step(plan.first_action)
        plan.tenant_plan.to_csv(output_dir / f"{mode.value}_tenant_plan.csv", index=False)
        plan.park_plan.to_csv(output_dir / f"{mode.value}_park_plan.csv", index=False)
        (output_dir / f"{mode.value}_first_action.json").write_text(json.dumps(plan.first_action.to_dict(), indent=2), encoding="utf-8")
        summary = plan_summary(plan)
        summary["one_step_execution_final_soc"] = clone.get_state().battery.soc_fraction
        (output_dir / f"{mode.value}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        plans[mode.value] = plan

    for mode in (MPCMode.EXPECTED, MPCMode.CONSERVATIVE):
        planning = plans[mode.value].planning_input
        samples = []
        first_objective = None
        for _ in range(20):
            start = time.perf_counter()
            plan = controller.solve(planning, simulator.clone())
            samples.append(time.perf_counter() - start)
            if first_objective is None:
                first_objective = plan.objective_breakdown.total_control_objective
            elif abs(first_objective - plan.objective_breakdown.total_control_objective) > 1e-4:
                raise RuntimeError("warm repeated solve objective changed beyond tolerance")
        timings[f"{mode.value}_warm_mean_seconds"] = statistics.mean(samples)
        timings[f"{mode.value}_warm_median_seconds"] = statistics.median(samples)
        timings[f"{mode.value}_warm_p95_seconds"] = sorted(samples)[int(0.95 * len(samples)) - 1]
        timings[f"{mode.value}_warm_min_seconds"] = min(samples)
        timings[f"{mode.value}_warm_max_seconds"] = max(samples)

    summary = {
        "origin": origin.isoformat(),
        "timings": timings,
        "expected": plan_summary(plans["expected"]),
        "conservative": plan_summary(plans["conservative"]),
        "label": "One-step planning example only; not a Stage 6 closed-loop benchmark.",
    }
    (output_dir / "example_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_html(plans, summary, artifact_dir / "mpc_example.html")
    print(json.dumps(summary, indent=2))
    return 0


def _write_html(plans: dict[MPCMode, object], summary: dict, path: Path) -> None:
    expected = plans[MPCMode.EXPECTED].park_plan
    conservative = plans[MPCMode.CONSERVATIVE].park_plan
    html = [
        "<html><body><h1>GreenMPC One-Step Example</h1>",
        "<p>Actual operating-cost proxy is reported separately from control penalties. This is not a closed-loop benchmark.</p>",
        "<h2>Summary</h2><pre>",
        json.dumps(summary, indent=2),
        "</pre><h2>Expected Park Plan</h2>",
        expected.to_html(index=False),
        "<h2>Conservative Park Plan</h2>",
        conservative.to_html(index=False),
        "</body></html>",
    ]
    path.write_text("".join(html), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
