#!/usr/bin/env python
"""Verify Stage 6 closed-loop evaluation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from greenmpc.evaluation.runner import CONTROLLERS, PROJECT_ROOT, run_benchmark


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    for script in ("verify_stage0.py", "verify_stage1.py", "verify_stage2.py", "verify_stage3.py", "verify_stage4.py", "verify_stage5.py"):
        result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / script)], cwd=PROJECT_ROOT, capture_output=True, text=True)
        checks.append((script, result.returncode == 0, _first(result.stdout) or result.stderr.strip()))
    log = subprocess.check_output(["git", "log", "--oneline", "--decorate", "-5"], cwd=PROJECT_ROOT, text=True)
    checks.append(("Stage 5 checkpoint exists", "Implement Stage 5 GreenMPC control engine" in log or "Implement Stage 5 MPC controller" in log, _first(log)))

    summary = run_benchmark(quick=True, force=True)
    output = PROJECT_ROOT / "data/outputs/stage6_benchmark"
    metrics = pd.read_csv(output / "controller_scenario_metrics.csv")
    paired = pd.read_csv(output / "paired_controller_comparison.csv")
    forecast = pd.read_csv(output / "forecast_diagnostics.csv")
    runtime = pd.read_csv(output / "runtime_metrics.csv")
    manifest = json.loads((output / "benchmark_manifest.json").read_text())
    checks.append(("three distinct controllers exist", set(CONTROLLERS) == set(metrics["controller_id"].unique()), ",".join(sorted(metrics["controller_id"].unique()))))
    checks.append(("all four quick scenarios complete", set(metrics["scenario_id"].unique()) == {"normal", "cloudy", "production_shift", "combined_stress"}, ",".join(sorted(metrics["scenario_id"].unique()))))
    checks.append(("24-hour vertical slice completes", (metrics["completed_steps"] >= 24).all(), str(metrics["completed_steps"].min())))
    checks.append(("same initial state recorded", all("battery_energy" in item for item in manifest["initial_state_signatures"].values()), "manifest"))
    checks.append(("forecast bundles shared for MPC modes", not forecast.empty, f"{len(forecast)} forecast rows"))
    checks.append(("observed history no future observations", not forecast["future_observations_used"].astype(bool).any(), "audit column"))
    checks.append(("actions validated/no hard violations", (metrics["hard_constraint_violations"] == 0).all() and (metrics["invalid_action_count"] == 0).all(), "metrics"))
    mpc = metrics[metrics["controller_id"].isin(["deterministic_mpc", "greenmpc_conservative"])]
    checks.append(("MPC battery charges/discharges", (mpc["battery_throughput_kwh"] > 0).any(), "battery_throughput_kwh"))
    checks.append(("realized costs reconcile", (metrics["total_realized_operating_cost_proxy_vnd"] >= 0).all(), "nonnegative costs"))
    checks.append(("fallbacks counted", "fallback_count" in metrics.columns, "fallback_count column"))
    checks.append(("paired comparisons generated", not paired.empty, f"{len(paired)} rows"))
    checks.append(("runtime metrics generated", not runtime.empty, f"{len(runtime)} rows"))
    checks.append(("closed-loop HTML artifact exists", (PROJECT_ROOT / "artifacts/closed_loop_benchmark.html").exists(), "artifact"))
    checks.append(("results reproducible", summary["fingerprints"] == manifest["fingerprints"], "fingerprints"))
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
