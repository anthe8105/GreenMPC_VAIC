"""Closed-loop Stage 6 benchmark runner."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from greenmpc.config import load_config
from greenmpc.control import GreenMPCController, MPCMode
from greenmpc.evaluation.history_adapter import ObservedHistoryAdapter
from greenmpc.evaluation.metrics import controller_metrics, paired_comparisons
from greenmpc.evaluation.rule_based import build_rule_based_action
from greenmpc.evaluation.scenarios import EvaluationConfig, ScenarioDefinition, build_scenarios, load_evaluation_config
from greenmpc.forecasting.inference import ForecastService
from greenmpc.forecasting.training import current_fingerprints
from greenmpc.simulation.park import IndustrialParkSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTROLLERS = ("rule_based", "deterministic_mpc", "greenmpc_conservative")


def run_benchmark(
    *,
    quick: bool = False,
    hours: int | None = None,
    scenario_filter: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    cfg = load_evaluation_config(PROJECT_ROOT / "configs/evaluation.yaml")
    output_dir = PROJECT_ROOT / cfg.output_directory
    manifest_path = output_dir / "benchmark_manifest.json"
    selected_hours = int(hours or (cfg.quick_hours if quick else cfg.default_hours))
    if manifest_path.exists() and not force:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("fingerprints") == current_fingerprints() and existing.get("minimum_completed_hours", 0) >= min(selected_hours, cfg.quick_hours):
            print(f"Reusing compatible Stage 6 benchmark outputs at {output_dir}")
            return existing
    return _execute(cfg, selected_hours, scenario_filter, output_dir)


def _execute(cfg: EvaluationConfig, hours: int, scenario_filter: str | None, output_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    project_cfg = load_config(PROJECT_ROOT / "configs/demo.yaml")
    tenant_base = pd.read_csv(PROJECT_ROOT / "data/processed/tenant_hourly.csv")
    park_base = pd.read_csv(PROJECT_ROOT / "data/processed/park_hourly.csv")
    scenarios = build_scenarios(cfg, cfg.start_timestamp)
    if scenario_filter:
        scenarios = {scenario_filter: scenarios[scenario_filter]}
    forecast_service = ForecastService.from_registry(PROJECT_ROOT / "configs/forecasting.yaml")
    controller = GreenMPCController.from_config()
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_rows: list[dict] = []
    forecast_rows: list[dict] = []
    runtime_rows: list[dict] = []
    initial_signatures: dict[str, dict[str, Any]] = {}
    all_plan_diag: list[dict] = []

    for scenario_id, scenario in scenarios.items():
        base_sim = IndustrialParkSimulator.from_processed_files(start_timestamp=cfg.start_timestamp)
        for event in scenario.events:
            base_sim.inject_event(event)
        initial = _state_signature(base_sim)
        initial_signatures[scenario_id] = initial
        sims = {controller_id: base_sim.clone() for controller_id in CONTROLLERS}
        if len({json.dumps(_state_signature(sim), sort_keys=True) for sim in sims.values()}) != 1:
            raise RuntimeError("controllers do not start from identical state")
        adapter = ObservedHistoryAdapter(tenant_base, park_base, tuple(base_sim.tenant_ids))
        forecast_cache: dict[str, tuple] = {}
        runtimes = {controller_id: {"forecast_time_seconds": 0.0, "planning_time_seconds": 0.0, "validation_time_seconds": 0.0, "step_time_seconds": 0.0, "benchmark_time_seconds": 0.0, "fallback_reasons": []} for controller_id in CONTROLLERS}
        fallback_counts = {controller_id: 0 for controller_id in CONTROLLERS}
        planning_failures = {controller_id: 0 for controller_id in CONTROLLERS}
        scenario_start = time.perf_counter()

        for step in range(hours):
            origin = pd.Timestamp(sims["rule_based"].get_state().timestamp_local)
            observed = sims["rule_based"].get_effective_exogenous()
            adapter.record_observation(observed)
            forecast_key = f"{scenario_id}:{origin.isoformat()}:{adapter.fingerprint(origin)}"
            if forecast_key not in forecast_cache:
                tenant_hist, park_hist, audit = adapter.histories_through(origin)
                t0 = time.perf_counter()
                forecast_cache[forecast_key] = (*forecast_service.forecast_all(tenant_hist, park_hist, origin, 6), audit)
                forecast_elapsed = time.perf_counter() - t0
                for controller_id in CONTROLLERS:
                    runtimes[controller_id]["forecast_time_seconds"] += forecast_elapsed
            load_forecast, solar_forecast, audit = forecast_cache[forecast_key]
            forecast_rows.extend(_forecast_diagnostics_rows(scenario_id, origin, load_forecast, solar_forecast, observed, audit))

            for controller_id, sim in sims.items():
                plan_start = time.perf_counter()
                if controller_id == "rule_based":
                    action = build_rule_based_action(sim.get_state(), project_cfg, action_id=f"RB-{scenario_id}-{step:03d}")
                    plan_diag = {"scenario_id": scenario_id, "controller_id": controller_id, "timestamp_local": origin.isoformat(), "fallback_used": False, "solver_status": "not_used", "mode": "current_observation"}
                else:
                    mode = MPCMode.EXPECTED if controller_id == "deterministic_mpc" else MPCMode.CONSERVATIVE
                    plan = controller.plan_with_fallback(sim, load_forecast, solar_forecast, mode)
                    action = plan.first_action
                    if plan.solver_diagnostics.fallback_used:
                        fallback_counts[controller_id] += 1
                        runtimes[controller_id]["fallback_reasons"].append(plan.fallback_reason or "unknown")
                    plan_diag = {
                        "scenario_id": scenario_id,
                        "controller_id": controller_id,
                        "timestamp_local": origin.isoformat(),
                        "fallback_used": plan.solver_diagnostics.fallback_used,
                        "solver_status": plan.solver_diagnostics.solver_status,
                        "mode": mode.value,
                        "objective": plan.objective_breakdown.total_control_objective,
                    }
                runtimes[controller_id]["planning_time_seconds"] += time.perf_counter() - plan_start
                validation_start = time.perf_counter()
                validation = sim.validate_action(action)
                runtimes[controller_id]["validation_time_seconds"] += time.perf_counter() - validation_start
                if not validation.valid:
                    raise RuntimeError(f"{controller_id} produced invalid action at {origin}: {validation.violations[0].message}")
                step_start = time.perf_counter()
                sim.step(action)
                runtimes[controller_id]["step_time_seconds"] += time.perf_counter() - step_start
                all_plan_diag.append(plan_diag)
        elapsed = time.perf_counter() - scenario_start
        for controller_id, sim in sims.items():
            runtimes[controller_id]["benchmark_time_seconds"] = elapsed
            sim.export_history(output_dir / scenario_id / controller_id)
            pd.DataFrame([row for row in forecast_rows if row["scenario_id"] == scenario_id]).to_csv(output_dir / scenario_id / controller_id / "forecasts.csv", index=False)
            pd.DataFrame([row for row in all_plan_diag if row["scenario_id"] == scenario_id and row["controller_id"] == controller_id]).to_csv(output_dir / scenario_id / controller_id / "plan_diagnostics.csv", index=False)
            metrics_rows.append(controller_metrics(sim, scenario_id, controller_id, fallback_counts[controller_id], planning_failures[controller_id], runtimes[controller_id]))
            runtime_rows.append({"scenario_id": scenario_id, "controller_id": controller_id, **runtimes[controller_id]})

    metrics = pd.DataFrame(metrics_rows)
    paired = paired_comparisons(metrics)
    forecast_diag = pd.DataFrame(forecast_rows)
    runtime = pd.DataFrame(runtime_rows)
    metrics.to_csv(output_dir / "controller_scenario_metrics.csv", index=False)
    paired.to_csv(output_dir / "paired_controller_comparison.csv", index=False)
    forecast_diag.to_csv(output_dir / "forecast_diagnostics.csv", index=False)
    runtime.to_csv(output_dir / "runtime_metrics.csv", index=False)
    summary = {
        "stage": 6,
        "hours": hours,
        "minimum_completed_hours": hours,
        "scenarios": list(scenarios),
        "controllers": list(CONTROLLERS),
        "event_visibility_policy": cfg.event_visibility_policy,
        "initial_state_signatures": initial_signatures,
        "fingerprints": current_fingerprints(),
        "total_runtime_seconds": time.perf_counter() - started,
        "no_future_actual_data_policy": "observed-history adapter records realized effective observations through origin; future actual features are forbidden by Stage 4 feature manifest",
    }
    (output_dir / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "benchmark_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_html(metrics, paired, PROJECT_ROOT / cfg.artifact_path)
    return summary


def _state_signature(sim: IndustrialParkSimulator) -> dict[str, Any]:
    state = sim.get_state()
    return {
        "timestamp": state.timestamp_local.isoformat(),
        "battery_energy": state.battery.energy_kwh,
        "battery_soc": state.battery.soc_fraction,
        "tenant_ids": list(sim.tenant_ids),
        "dataset_version": sim.dataset_version,
    }


def _forecast_diagnostics_rows(scenario_id, origin, load_forecast, solar_forecast, observed, audit):
    rows = []
    load = load_forecast.to_dataframe()
    solar = solar_forecast.to_dataframe()
    for tenant_id, actual in observed.effective_tenant_load_kw.items():
        h1 = load[(load["tenant_id"] == tenant_id) & (load["horizon_hours"] == 1)]
        if not h1.empty:
            rows.append({"scenario_id": scenario_id, "forecast_origin": origin.isoformat(), "task": "load_h1_current_effective_proxy", "tenant_id": tenant_id, "p50_kw": float(h1["p50_kw"].iloc[0]), "realized_kw": float(actual), "absolute_error_kw": abs(float(h1["p50_kw"].iloc[0]) - float(actual)), **audit})
    h1s = solar[solar["horizon_hours"] == 1]
    if not h1s.empty:
        rows.append({"scenario_id": scenario_id, "forecast_origin": origin.isoformat(), "task": "solar_h1_current_effective_proxy", "tenant_id": "", "p50_kw": float(h1s["p50_kw"].iloc[0]), "realized_kw": float(observed.effective_pv_available_kw), "absolute_error_kw": abs(float(h1s["p50_kw"].iloc[0]) - float(observed.effective_pv_available_kw)), **audit})
    return rows


def _write_html(metrics: pd.DataFrame, paired: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    html = [
        "<html><body><h1>Closed-Loop Controller Benchmark</h1>",
        "<p>Hybrid public/scenario data. Synthetic stress events. Results are not actual VRG operational savings.</p>",
        "<h2>Controller Scenario Metrics</h2>",
        metrics.to_html(index=False),
        "<h2>Paired Comparisons</h2>",
        paired.to_html(index=False),
        "</body></html>",
    ]
    path.write_text("".join(html), encoding="utf-8")
