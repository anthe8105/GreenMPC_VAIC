#!/usr/bin/env python
"""Verify Stage 6 closed-loop evaluation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from greenmpc.evaluation.runner import CONTROLLERS, PROJECT_ROOT, _cache_identity
from greenmpc.evaluation.scenarios import load_evaluation_config


REQUIRED_FORECAST_COLUMNS = {
    "forecast_origin",
    "target_timestamp",
    "horizon_hours",
    "scenario",
    "event_affected",
    "task",
    "tenant_id",
    "actual",
    "p10",
    "p50",
    "p90",
    "absolute_error",
    "interval_covered",
}


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    for script in ("verify_stage0.py", "verify_stage1.py", "verify_stage2.py", "verify_stage3.py", "verify_stage4.py", "verify_stage5.py"):
        result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / script)], cwd=PROJECT_ROOT, capture_output=True, text=True)
        checks.append((script, result.returncode == 0, _first(result.stdout) or result.stderr.strip()))
    log = subprocess.check_output(["git", "log", "--oneline", "--decorate", "-5"], cwd=PROJECT_ROOT, text=True)
    checks.append(("Stage 5 checkpoint exists", "Implement Stage 5 GreenMPC control engine" in log or "Implement Stage 5 MPC controller" in log, _first(log)))

    output = PROJECT_ROOT / "data/outputs/stage6_benchmark"
    audit = PROJECT_ROOT / "data/outputs/stage6_audit"
    manifest_path = output / "benchmark_manifest.json"
    checks.append(("benchmark manifest exists", manifest_path.exists(), str(manifest_path)))
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    metrics = pd.read_csv(output / "controller_scenario_metrics.csv")
    paired = pd.read_csv(output / "paired_controller_comparison.csv")
    forecast = pd.read_csv(output / "forecast_diagnostics.csv")
    runtime = pd.read_csv(output / "runtime_metrics.csv")
    rule_trace = pd.read_csv(audit / "rule_based_battery_trace.csv")
    fallback = pd.read_csv(audit / "conservative_fallbacks.csv") if (audit / "conservative_fallbacks.csv").exists() else pd.DataFrame()
    kpi = pd.read_csv(audit / "kpi_reconciliation.csv")

    cfg = load_evaluation_config(PROJECT_ROOT / "configs/evaluation.yaml")
    quick_identity = _cache_identity(cfg, cfg.quick_hours, "quick", tuple(cfg.scenarios), tuple(cfg.controllers))
    full_identity = _cache_identity(cfg, cfg.default_hours, "full", tuple(cfg.scenarios), tuple(cfg.controllers))
    checks.append(("quick and full cache identities differ", quick_identity["cache_fingerprint"] != full_identity["cache_fingerprint"], "cache fingerprints"))
    checks.append(("full benchmark contains 72 steps", manifest.get("requested_hours") == 72 and manifest.get("completed_hours") == 72 and (metrics["completed_steps"] == 72).all(), str(manifest.get("completed_hours"))))
    checks.append(("three distinct controllers exist", set(CONTROLLERS) == set(metrics["controller_id"].unique()), ",".join(sorted(metrics["controller_id"].unique()))))
    checks.append(("all four scenarios complete", set(metrics["scenario_id"].unique()) == {"normal", "cloudy", "production_shift", "combined_stress"}, ",".join(sorted(metrics["scenario_id"].unique()))))
    checks.append(("same initial state recorded", all("battery_energy" in item for item in manifest.get("initial_state_signatures", {}).values()), "manifest"))
    checks.append(("forecast bundles generated", not forecast.empty, f"{len(forecast)} diagnostic rows"))
    checks.append(("forecast diagnostics schema", REQUIRED_FORECAST_COLUMNS.issubset(forecast.columns), ",".join(sorted(forecast.columns))))
    target_after_origin = (pd.to_datetime(forecast["target_timestamp"]) > pd.to_datetime(forecast["forecast_origin"])).all()
    checks.append(("forecast diagnostics use t+h targets", target_after_origin and set(forecast["horizon_hours"].unique()) == {1, 2, 3, 4, 5, 6}, "target timestamps and horizons"))
    checks.append(("coverage and WAPE inputs reported", "interval_covered" in forecast and "absolute_error" in forecast and "actual" in forecast, "forecast columns"))
    checks.append(("observed history no future observations", not forecast["future_observations_used"].astype(bool).any(), "audit column"))
    checks.append(("actions validated/no hard violations", (metrics["hard_constraint_violations"] == 0).all() and (metrics["invalid_action_count"] == 0).all(), "metrics"))
    mpc = metrics[metrics["controller_id"].isin(["deterministic_mpc", "greenmpc_conservative"])]
    checks.append(("MPC battery charges/discharges", (mpc["battery_throughput_kwh"] > 0).any(), "battery_throughput_kwh"))
    rb = metrics[metrics["controller_id"] == "rule_based"]
    checks.append(("rule-based battery behavior audited", not rule_trace.empty and (rb["battery_throughput_kwh"] > 0).all() and not rule_trace["uses_forecast"].astype(bool).any(), "rule trace"))
    if fallback.empty:
        fallback_ok = True
        fallback_detail = "no fallbacks"
    else:
        fallback_ok = fallback["first_failed_constraint_or_diagnostic"].fillna("").str.len().gt(0).all() and fallback["fallback_action_valid"].astype(bool).all()
        fallback_detail = f"{len(fallback)} fallback rows"
    checks.append(("conservative fallback causes recorded", fallback_ok, fallback_detail))
    checks.append(("realized KPI recomputation matches summaries", (kpi["mismatch_count"] == 0).all(), f"{len(kpi)} rows"))
    checks.append(("fallbacks counted", "fallback_count" in metrics.columns, "fallback_count column"))
    checks.append(("paired comparisons generated", not paired.empty, f"{len(paired)} rows"))
    checks.append(("runtime metrics generated", not runtime.empty, f"{len(runtime)} rows"))
    checks.append(("closed-loop HTML artifact exists", (PROJECT_ROOT / "artifacts/closed_loop_benchmark.html").exists(), "artifact"))
    checks.append(("results marked successful", bool(manifest.get("completed_successfully")), "manifest"))
    control_text = "\n".join(path.read_text(encoding="utf-8") for path in (PROJECT_ROOT / "src/greenmpc/evaluation").glob("*.py"))
    checks.append(("no Streamlit or Stage 7", "streamlit" not in control_text.lower() and "stage 7" not in control_text.lower(), "evaluation package"))

    print("check | result | detail")
    print("----- | ------ | ------")
    failed = False
    for name, ok, detail in checks:
        failed = failed or not ok
        print(f"{name} | {'PASS' if ok else 'FAIL'} | {detail}")
    return 1 if failed else 0


def _first(text: str) -> str:
    return next((line for line in text.splitlines() if line.strip()), "")


if __name__ == "__main__":
    raise SystemExit(main())
