"""Closed-loop Stage 6 benchmark runner."""

from __future__ import annotations

import hashlib
import json
import platform
import time
from pathlib import Path
from typing import Any

import pandas as pd

from greenmpc.config import load_config
from greenmpc.control import GreenMPCController, MPCMode
from greenmpc.evaluation.history_adapter import ObservedHistoryAdapter
from greenmpc.evaluation.metrics import (
    controller_metrics,
    paired_comparisons,
    reconcile_metric_row,
    recompute_metrics_from_histories,
)
from greenmpc.evaluation.rule_based import build_rule_based_action_with_trace
from greenmpc.evaluation.scenarios import EvaluationConfig, build_scenarios, load_evaluation_config
from greenmpc.forecasting.artifacts import file_sha256
from greenmpc.forecasting.inference import ForecastService
from greenmpc.forecasting.training import current_fingerprints
from greenmpc.simulation.park import IndustrialParkSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTROLLERS = ("rule_based", "deterministic_mpc", "greenmpc_conservative")
SOFTWARE_VERSION = "stage6_audit_v4"


def run_benchmark(
    *,
    quick: bool = False,
    hours: int | None = None,
    scenario_filter: str | None = None,
    force: bool = False,
    profile: bool = False,
) -> dict[str, Any]:
    cfg = load_evaluation_config(PROJECT_ROOT / "configs/evaluation.yaml")
    output_dir = PROJECT_ROOT / cfg.output_directory
    manifest_path = output_dir / "benchmark_manifest.json"
    selected_hours = int(hours or (cfg.quick_hours if quick else cfg.default_hours))
    run_mode = "custom" if hours is not None else ("quick" if quick else "full")
    scenario_ids = _requested_scenarios(cfg, scenario_filter)
    controllers = tuple(cfg.controllers)
    cache_identity = _cache_identity(cfg, selected_hours, run_mode, scenario_ids, controllers)
    if manifest_path.exists() and not force:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if _is_cache_compatible(existing, cache_identity):
            if "minimum_completed_hours" not in existing and "completed_hours" in existing:
                existing["minimum_completed_hours"] = existing["completed_hours"]
            print(f"Reusing compatible Stage 6 benchmark outputs at {output_dir}")
            return existing
        print("Existing Stage 6 benchmark cache is incompatible; rebuilding.")
    return _execute(cfg, selected_hours, scenario_filter, output_dir, run_mode, controllers, cache_identity, profile)


def _execute(
    cfg: EvaluationConfig,
    hours: int,
    scenario_filter: str | None,
    output_dir: Path,
    run_mode: str,
    controllers: tuple[str, ...],
    cache_identity: dict[str, Any],
    profile: bool = False,
) -> dict[str, Any]:
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
    audit_dir = PROJECT_ROOT / "data/outputs/stage6_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    metrics_rows: list[dict] = []
    forecast_prediction_rows: list[dict] = []
    forecast_diag_rows: list[dict] = []
    runtime_rows: list[dict] = []
    initial_signatures: dict[str, dict[str, Any]] = {}
    all_plan_diag: list[dict] = []
    rule_trace_rows: list[dict] = []
    fallback_rows: list[dict] = []

    for scenario_id, scenario in scenarios.items():
        if profile:
            print(f"[profile] scenario={scenario_id} hours={hours} controllers={','.join(controllers)}", flush=True)
        base_sim = IndustrialParkSimulator.from_processed_files(start_timestamp=cfg.start_timestamp)
        for event in scenario.events:
            base_sim.inject_event(event)
        initial = _state_signature(base_sim)
        initial_signatures[scenario_id] = initial
        sims = {controller_id: base_sim.clone() for controller_id in controllers}
        if len({json.dumps(_state_signature(sim), sort_keys=True) for sim in sims.values()}) != 1:
            raise RuntimeError("controllers do not start from identical state")
        adapter = ObservedHistoryAdapter(tenant_base, park_base, tuple(base_sim.tenant_ids))
        forecast_cache: dict[str, tuple] = {}
        actual_by_timestamp: dict[pd.Timestamp, dict[str, Any]] = {}
        runtimes = {
            controller_id: {
                "forecast_time_seconds": 0.0,
                "planning_time_seconds": 0.0,
                "validation_time_seconds": 0.0,
                "step_time_seconds": 0.0,
                "benchmark_time_seconds": 0.0,
                "fallback_reasons": [],
            }
            for controller_id in controllers
        }
        fallback_counts = {controller_id: 0 for controller_id in controllers}
        planning_failures = {controller_id: 0 for controller_id in controllers}
        scenario_start = time.perf_counter()

        for step in range(hours):
            step_profile_start = time.perf_counter()
            origin = pd.Timestamp(sims["rule_based"].get_state().timestamp_local)
            observed = sims["rule_based"].get_effective_exogenous()
            actual_by_timestamp[origin] = {
                "loads": dict(observed.effective_tenant_load_kw),
                "pv": float(observed.effective_pv_available_kw),
                "event_affected": bool(observed.active_event_ids),
                "active_event_ids": ",".join(observed.active_event_ids),
            }
            adapter.record_observation(observed)
            forecast_key = f"{scenario_id}:{origin.isoformat()}:{adapter.fingerprint(origin)}:{cache_identity['model_registry_fingerprint']}"
            if forecast_key not in forecast_cache:
                tenant_hist, park_hist, audit = adapter.histories_through(origin)
                t0 = time.perf_counter()
                forecast_cache[forecast_key] = (*forecast_service.forecast_all(tenant_hist, park_hist, origin, 6), audit)
                forecast_elapsed = time.perf_counter() - t0
                for controller_id in controllers:
                    runtimes[controller_id]["forecast_time_seconds"] += forecast_elapsed
            load_forecast, solar_forecast, audit = forecast_cache[forecast_key]
            forecast_prediction_rows.extend(_forecast_prediction_rows(scenario_id, origin, load_forecast, solar_forecast, audit))

            for controller_id, sim in sims.items():
                plan_start = time.perf_counter()
                if controller_id == "rule_based":
                    action, trace = build_rule_based_action_with_trace(sim.get_state(), project_cfg, action_id=f"RB-{scenario_id}-{step:03d}")
                    rule_trace_rows.append({"scenario_id": scenario_id, "controller_id": controller_id, **trace})
                    plan_diag = {
                        "scenario_id": scenario_id,
                        "controller_id": controller_id,
                        "timestamp_local": origin.isoformat(),
                        "fallback_used": False,
                        "solver_status": "not_used",
                        "mode": "current_observation",
                    }
                else:
                    mode = MPCMode.EXPECTED if controller_id == "deterministic_mpc" else MPCMode.CONSERVATIVE
                    plan = controller.plan_with_fallback(sim, load_forecast, solar_forecast, mode)
                    action = plan.first_action
                    if plan.solver_diagnostics.fallback_used:
                        fallback_counts[controller_id] += 1
                        runtimes[controller_id]["fallback_reasons"].append(plan.fallback_reason or "unknown")
                        fallback_rows.append(_fallback_record(scenario_id, controller_id, origin, plan, action))
                    plan_diag = {
                        "scenario_id": scenario_id,
                        "controller_id": controller_id,
                        "timestamp_local": origin.isoformat(),
                        "fallback_used": plan.solver_diagnostics.fallback_used,
                        "fallback_reason": plan.fallback_reason,
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
            if profile:
                elapsed_step = time.perf_counter() - step_profile_start
                print(
                    f"[profile] scenario={scenario_id} step={step + 1}/{hours} origin={origin.isoformat()} "
                    f"elapsed={elapsed_step:.3f}s forecast_cache={len(forecast_cache)}",
                    flush=True,
                )
        elapsed = time.perf_counter() - scenario_start
        scenario_predictions = [row for row in forecast_prediction_rows if row["scenario"] == scenario_id]
        forecast_diag_rows.extend(_forecast_diagnostic_rows(scenario_predictions, actual_by_timestamp))
        for controller_id, sim in sims.items():
            runtimes[controller_id]["benchmark_time_seconds"] = elapsed
            history_dir = output_dir / scenario_id / controller_id
            sim.export_history(history_dir)
            pd.DataFrame([row for row in forecast_prediction_rows if row["scenario"] == scenario_id]).to_csv(history_dir / "forecasts.csv", index=False)
            pd.DataFrame([row for row in all_plan_diag if row["scenario_id"] == scenario_id and row["controller_id"] == controller_id]).to_csv(history_dir / "plan_diagnostics.csv", index=False)
            row = controller_metrics(sim, scenario_id, controller_id, fallback_counts[controller_id], planning_failures[controller_id], runtimes[controller_id])
            row["requested_hours"] = hours
            row["completed_hours"] = row["completed_steps"]
            metrics_rows.append(row)
            runtime_rows.append({"scenario_id": scenario_id, "controller_id": controller_id, **runtimes[controller_id]})

    metrics = pd.DataFrame(metrics_rows)
    paired = paired_comparisons(metrics)
    forecast_diag = pd.DataFrame(forecast_diag_rows)
    runtime = pd.DataFrame(runtime_rows)
    _reconcile_all_metrics(metrics, output_dir, audit_dir)
    metrics.to_csv(output_dir / "controller_scenario_metrics.csv", index=False)
    paired.to_csv(output_dir / "paired_controller_comparison.csv", index=False)
    forecast_diag.to_csv(output_dir / "forecast_diagnostics.csv", index=False)
    runtime.to_csv(output_dir / "runtime_metrics.csv", index=False)
    pd.DataFrame(rule_trace_rows).to_csv(audit_dir / "rule_based_battery_trace.csv", index=False)
    pd.DataFrame(fallback_rows).to_csv(audit_dir / "conservative_fallbacks.csv", index=False)
    _write_rule_summary(rule_trace_rows, audit_dir / "rule_based_battery_summary.json")
    _write_fallback_summary(fallback_rows, audit_dir / "conservative_fallback_summary.json")
    start_ts = pd.Timestamp(cfg.start_timestamp)
    end_ts = start_ts + pd.Timedelta(hours=hours - 1)
    summary = {
        "stage": 6,
        "software_version": SOFTWARE_VERSION,
        "requested_hours": hours,
        "completed_hours": int(metrics["completed_steps"].min()) if not metrics.empty else 0,
        "minimum_completed_hours": int(metrics["completed_steps"].min()) if not metrics.empty else 0,
        "hours": hours,
        "run_mode": run_mode,
        "requested_scenarios": list(scenarios),
        "requested_controllers": list(controllers),
        "scenarios": list(scenarios),
        "controllers": list(controllers),
        "start_timestamp": start_ts.isoformat(),
        "end_timestamp": end_ts.isoformat(),
        "event_visibility_policy": cfg.event_visibility_policy,
        "initial_state_signatures": initial_signatures,
        "fingerprints": current_fingerprints(),
        **cache_identity,
        "total_runtime_seconds": time.perf_counter() - started,
        "completed_successfully": True,
        "no_future_actual_data_policy": "observed-history adapter records realized effective observations through origin; forecast diagnostics compare predictions with realized t+h targets after execution",
    }
    if summary["completed_hours"] != hours:
        raise RuntimeError(f"completed_hours {summary['completed_hours']} does not equal requested_hours {hours}")
    if profile:
        print("[profile] runtime by controller", flush=True)
        for row in runtime_rows:
            print(
                "[profile] "
                f"scenario={row['scenario_id']} controller={row['controller_id']} "
                f"forecast={row['forecast_time_seconds']:.3f}s planning={row['planning_time_seconds']:.3f}s "
                f"validation={row['validation_time_seconds']:.3f}s step={row['step_time_seconds']:.3f}s",
                flush=True,
            )
    (output_dir / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "benchmark_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_html(metrics, paired, forecast_diag, PROJECT_ROOT / cfg.artifact_path)
    return summary


def _requested_scenarios(cfg: EvaluationConfig, scenario_filter: str | None) -> tuple[str, ...]:
    if scenario_filter:
        return (scenario_filter,)
    return tuple(cfg.scenarios)


def _cache_identity(
    cfg: EvaluationConfig,
    hours: int,
    run_mode: str,
    scenario_ids: tuple[str, ...],
    controllers: tuple[str, ...],
) -> dict[str, Any]:
    project_cfg = load_config(PROJECT_ROOT / "configs/demo.yaml")
    payload = {
        "evaluation_config_fingerprint": _file_sha(PROJECT_ROOT / "configs/evaluation.yaml"),
        "dataset_fingerprints": current_fingerprints(),
        "model_registry_fingerprint": _file_sha(PROJECT_ROOT / "models/forecasting/model_manifest.json"),
        "mpc_config_fingerprint": _file_sha(PROJECT_ROOT / "configs/mpc.yaml"),
        "scenario_ids": list(scenario_ids),
        "controller_ids": list(controllers),
        "benchmark_start_timestamp": cfg.start_timestamp,
        "requested_duration_hours": hours,
        "run_mode": run_mode,
        "event_definitions": {scenario_id: cfg.scenarios[scenario_id] for scenario_id in scenario_ids},
        "event_visibility_policy": cfg.event_visibility_policy,
        "initial_battery_state": {
            "soc_fraction": project_cfg.battery.initial_soc_fraction,
            "renewable_fraction": project_cfg.battery.initial_renewable_fraction,
            "capacity_kwh": project_cfg.battery.energy_capacity_kwh,
        },
        "random_seed": 42,
        "software_version": SOFTWARE_VERSION,
        "python_version": platform.python_version(),
    }
    return {**payload, "cache_fingerprint": _object_hash(payload)}


def _is_cache_compatible(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        existing.get("cache_fingerprint") == expected["cache_fingerprint"]
        and existing.get("requested_hours") == expected["requested_duration_hours"]
        and existing.get("completed_hours") == expected["requested_duration_hours"]
        and existing.get("run_mode") == expected["run_mode"]
        and existing.get("requested_scenarios") == expected["scenario_ids"]
        and existing.get("requested_controllers") == expected["controller_ids"]
        and bool(existing.get("completed_successfully")) is True
    )


def _state_signature(sim: IndustrialParkSimulator) -> dict[str, Any]:
    state = sim.get_state()
    return {
        "timestamp": state.timestamp_local.isoformat(),
        "battery_energy": state.battery.energy_kwh,
        "battery_soc": state.battery.soc_fraction,
        "tenant_ids": list(sim.tenant_ids),
        "dataset_version": sim.dataset_version,
    }


def _forecast_prediction_rows(scenario_id, origin, load_forecast, solar_forecast, audit):
    rows = []
    load = load_forecast.to_dataframe()
    solar = solar_forecast.to_dataframe()
    for _, row in load.iterrows():
        rows.append(
            {
                "scenario": scenario_id,
                "forecast_origin": origin.isoformat(),
                "target_timestamp": pd.Timestamp(row["timestamp_local"]).isoformat(),
                "horizon_hours": int(row["horizon_hours"]),
                "task": "load",
                "tenant_id": row["tenant_id"],
                "p10": float(row["p10_kw"]),
                "p50": float(row["p50_kw"]),
                "p90": float(row["p90_kw"]),
                **audit,
            }
        )
    for _, row in solar.iterrows():
        rows.append(
            {
                "scenario": scenario_id,
                "forecast_origin": origin.isoformat(),
                "target_timestamp": pd.Timestamp(row["timestamp_local"]).isoformat(),
                "horizon_hours": int(row["horizon_hours"]),
                "task": "solar",
                "tenant_id": "",
                "p10": float(row["p10_kw"]),
                "p50": float(row["p50_kw"]),
                "p90": float(row["p90_kw"]),
                **audit,
            }
        )
    return rows


def _forecast_diagnostic_rows(predictions: list[dict], actual_by_timestamp: dict[pd.Timestamp, dict[str, Any]]) -> list[dict]:
    rows: list[dict] = []
    for row in predictions:
        target = pd.Timestamp(row["target_timestamp"])
        actual_row = actual_by_timestamp.get(target)
        if actual_row is None:
            continue
        if row["task"] == "load":
            actual = float(actual_row["loads"][row["tenant_id"]])
        else:
            actual = float(actual_row["pv"])
        rows.append(
            {
                "forecast_origin": row["forecast_origin"],
                "target_timestamp": row["target_timestamp"],
                "horizon_hours": row["horizon_hours"],
                "scenario": row["scenario"],
                "event_affected": bool(actual_row["event_affected"]),
                "task": row["task"],
                "tenant_id": row["tenant_id"],
                "actual": actual,
                "p10": row["p10"],
                "p50": row["p50"],
                "p90": row["p90"],
                "absolute_error": abs(row["p50"] - actual),
                "bias": row["p50"] - actual,
                "interval_width": row["p90"] - row["p10"],
                "interval_covered": row["p10"] <= actual <= row["p90"],
                "future_observations_used": row["future_observations_used"],
                "all_five_tenants_aligned": row["all_five_tenants_aligned"],
            }
        )
    return rows


def _fallback_record(scenario_id: str, controller_id: str, origin: pd.Timestamp, plan, action) -> dict:
    planning = plan.planning_input
    validation = plan.simulator_validation_result
    inferred = _infer_fallback_root_cause(planning)
    return {
        "scenario": scenario_id,
        "controller": controller_id,
        "timestamp": origin.isoformat(),
        "planning_input_id": planning.planning_input_id,
        "forecast_origin": pd.Timestamp(planning.forecast_origin_local).isoformat(),
        "selected_p90_or_mode_load_values": json.dumps(planning.load_forecast_kw, sort_keys=True),
        "selected_p10_or_mode_solar_values": json.dumps(list(planning.pv_available_kw)),
        "initial_soc": planning.initial_soc_fraction,
        "transformer_capacity": json.dumps(list(planning.transformer_capacity_kw)),
        "dppa_availability": json.dumps(list(planning.dppa_available_kw)),
        "solver_status": plan.solver_diagnostics.solver_status,
        "solver_message": "; ".join(plan.solver_diagnostics.warnings),
        "failure_reason": plan.fallback_reason or "unknown",
        "first_failed_constraint_or_diagnostic": inferred,
        "fallback_action": json.dumps(action.to_dict(), sort_keys=True),
        "fallback_action_valid": bool(validation.valid),
    }


def _infer_fallback_root_cause(planning) -> str:
    """Classify the first obvious hard-capacity infeasibility in an MPC input."""

    energy = float(planning.initial_energy_kwh)
    for index, timestamp in enumerate(planning.planning_timestamps_local):
        total_load = sum(float(values[index]) for values in planning.load_forecast_kw.values())
        max_external = float(planning.transformer_capacity_kw[index])
        max_battery = min(
            float(planning.maximum_discharge_power_kw),
            max(0.0, (energy - float(planning.minimum_energy_kwh)) * float(planning.discharge_efficiency)),
        )
        max_supply = float(planning.pv_available_kw[index]) + max_external + max_battery
        if total_load > max_supply + 1e-6:
            return (
                "forecasted hard supply infeasibility at interval "
                f"{index} ({pd.Timestamp(timestamp).isoformat()}): load {total_load:.3f} kW exceeds "
                f"PV {float(planning.pv_available_kw[index]):.3f} + transformer {max_external:.3f} + "
                f"battery power/energy {max_battery:.3f} kW"
            )
        required_battery = max(0.0, total_load - float(planning.pv_available_kw[index]) - max_external)
        if required_battery > 0:
            energy -= required_battery / float(planning.discharge_efficiency)
            if energy < float(planning.minimum_energy_kwh) - 1e-6:
                return (
                    "forecasted coupled battery-energy infeasibility by interval "
                    f"{index} ({pd.Timestamp(timestamp).isoformat()}): required battery discharge depletes "
                    f"energy to {energy:.3f} kWh below minimum {float(planning.minimum_energy_kwh):.3f} kWh"
                )
        elif float(planning.pv_available_kw[index]) > total_load:
            surplus_charge = min(
                float(planning.maximum_charge_power_kw),
                float(planning.pv_available_kw[index]) - total_load,
                max(0.0, (float(planning.maximum_energy_kwh) - energy) / float(planning.charge_efficiency)),
            )
            energy += surplus_charge * float(planning.charge_efficiency)
    return "LP infeasible without simple supply-capacity violation; likely coupled horizon constraint or direction-repair/numerical issue"


def _reconcile_all_metrics(metrics: pd.DataFrame, output_dir: Path, audit_dir: Path) -> None:
    rows = []
    errors: list[str] = []
    for _, metric in metrics.iterrows():
        history_dir = output_dir / str(metric["scenario_id"]) / str(metric["controller_id"])
        recomputed = recompute_metrics_from_histories(history_dir)
        mismatch = reconcile_metric_row(metric, recomputed, tolerance=1e-5)
        rows.append({"scenario_id": metric["scenario_id"], "controller_id": metric["controller_id"], "mismatch_count": len(mismatch), "mismatches": "; ".join(mismatch), **recomputed})
        errors.extend([f"{metric['scenario_id']}/{metric['controller_id']}: {item}" for item in mismatch])
        if recomputed["action_count"] != metric["requested_hours"]:
            errors.append(f"{metric['scenario_id']}/{metric['controller_id']}: action count does not equal requested hours")
        if recomputed["tenant_energy_rows"] != metric["requested_hours"] * 5:
            errors.append(f"{metric['scenario_id']}/{metric['controller_id']}: tenant row count does not equal requested hours * 5")
    pd.DataFrame(rows).to_csv(audit_dir / "kpi_reconciliation.csv", index=False)
    if errors:
        raise RuntimeError("realized KPI reconciliation failed: " + " | ".join(errors[:5]))


def _write_rule_summary(rows: list[dict], path: Path) -> None:
    frame = pd.DataFrame(rows)
    if frame.empty:
        summary = {"row_count": 0, "error": "no rule-based trace rows"}
    else:
        normal_combined = frame[frame["scenario_id"].isin(["normal", "combined_stress"])]
        summary = {
            "row_count": int(len(frame)),
            "normal_and_combined_rows": int(len(normal_combined)),
            "total_charge_kwh": float(frame["charge_power_kw"].sum()),
            "total_discharge_kwh": float(frame["discharge_power_kw"].sum()),
            "decision_branch_counts": frame["decision_branch"].value_counts().to_dict(),
            "uses_forecast_any": bool(frame["uses_forecast"].any()),
            "uses_optimization_any": bool(frame["uses_optimization"].any()),
            "conclusion": "battery policy is active when excess PV, peak tariff, or transformer pressure conditions occur",
        }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _write_fallback_summary(rows: list[dict], path: Path) -> None:
    frame = pd.DataFrame(rows)
    if frame.empty:
        summary = {"fallback_count": 0, "root_causes": {}}
    else:
        summary = {
            "fallback_count": int(len(frame)),
            "fallbacks_by_scenario": frame.groupby("scenario").size().to_dict(),
            "fallbacks_by_controller": frame.groupby("controller").size().to_dict(),
            "solver_reasons": frame["failure_reason"].value_counts().to_dict(),
            "root_causes": frame["first_failed_constraint_or_diagnostic"].value_counts().to_dict(),
            "all_fallback_actions_valid": bool(frame["fallback_action_valid"].all()),
        }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _file_sha(path: Path) -> str:
    return file_sha256(path) if path.exists() else "missing"


def _object_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _write_html(metrics: pd.DataFrame, paired: pd.DataFrame, forecast: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    forecast_summary = (
        forecast.groupby(["scenario", "task", "event_affected"])
        .agg(sample_count=("actual", "size"), mae=("absolute_error", "mean"), coverage=("interval_covered", "mean"))
        .reset_index()
        if not forecast.empty
        else pd.DataFrame()
    )
    html = [
        "<html><body><h1>Closed-Loop Controller Benchmark</h1>",
        "<p>Hybrid public/scenario data. Synthetic stress events. Results are not actual VRG operational savings.</p>",
        "<h2>Controller Scenario Metrics</h2>",
        metrics.to_html(index=False),
        "<h2>Paired Comparisons</h2>",
        paired.to_html(index=False),
        "<h2>Forecast Diagnostics</h2>",
        forecast_summary.to_html(index=False),
        "</body></html>",
    ]
    path.write_text("".join(html), encoding="utf-8")
