#!/usr/bin/env python
"""Verify Stage 7 Streamlit Control Room without launching a server."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts/verify_stage6.py")], cwd=PROJECT_ROOT, capture_output=True, text=True)
    checks.append(("Stage 6 verification passes", result.returncode == 0, _first(result.stdout) or _first(result.stderr)))

    try:
        importlib.import_module("streamlit_app")
        checks.append(("Streamlit app imports", True, "streamlit_app"))
    except Exception as exc:
        checks.append(("Streamlit app imports", False, str(exc)))

    try:
        from greenmpc.ui.session import (
            can_execute_latest_plan,
            configure_live_operation,
            execute_next_hour,
            forecast_and_plan,
            process_control_tick,
            start_live_demo,
        )
        from greenmpc.ui.state import initialize_live_session, load_control_room_resources
        from greenmpc.ui.view_models import benchmark_view, current_kpis, energy_topology, rolling_history_frame

        resources = load_control_room_resources(PROJECT_ROOT)
        session = initialize_live_session(
            resources,
            scenario_id="normal",
            controller_id="deterministic_mpc",
            start_timestamp=resources.evaluation_config.start_timestamp,
        )
        initial_timestamp = session.simulator.get_state().timestamp_local
        checks.append(("cached services initialize", True, f"{resources.load_seconds:.3f}s"))
        checks.append(("simulator session initializes", bool(current_kpis(session)), initial_timestamp.isoformat()))

        session = forecast_and_plan(session, resources)
        checks.append(("forecast bundle generated", session.latest_load_forecast is not None and session.latest_solar_forecast is not None, "load and solar"))
        checks.append(("deterministic MPC plan generated", session.latest_action is not None and session.latest_validation is not None, session.controller_id))
        ready, reason = can_execute_latest_plan(session)
        checks.append(("first action validated", ready, reason))
        session = execute_next_hour(session)
        next_timestamp = session.simulator.get_state().timestamp_local
        checks.append(("timestamp advances one hour", str(next_timestamp - initial_timestamp) == "1:00:00", next_timestamp.isoformat()))
        ready_after, reason_after = can_execute_latest_plan(session)
        checks.append(("previous plan becomes stale", not ready_after and "No validated action" in reason_after, reason_after))
        checks.append(("rolling history updates", len(rolling_history_frame(session)) == 1, "one executed row"))

        session.controller_id = "greenmpc_conservative"
        session.fallback_visible = True
        session.fallback_reason = "test fallback visibility"
        checks.append(("fallback visibility logic", session.fallback_visible and bool(session.fallback_reason), session.fallback_reason))

        auto = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
        configure_live_operation(auto, operation_mode="Auto Pilot Demo", playback_interval_seconds=2.0, maximum_simulated_hours=3)
        start_live_demo(auto, now=10.0)
        process_control_tick(auto, resources, now=12.0)
        checks.append(("Auto Pilot advances one hour", auto.simulated_hours_completed == 1 and len(auto.execution_history) == 1, auto.simulator.get_state().timestamp_local.isoformat()))
        _, topology_edges = energy_topology(auto)
        checks.append(("topology has active flows", not topology_edges.empty and topology_edges["kw"].sum() > 0, f"{len(topology_edges)} edges"))

        shadow = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
        configure_live_operation(shadow, operation_mode="Shadow Mode", playback_interval_seconds=2.0, maximum_simulated_hours=3)
        shadow_start = shadow.simulator.get_state().timestamp_local
        start_live_demo(shadow, now=20.0)
        process_control_tick(shadow, resources, now=22.0)
        checks.append(("Shadow Mode plans without execution", shadow.latest_action is not None and shadow.simulator.get_state().timestamp_local == shadow_start, shadow.latest_status))

        benchmark = benchmark_view(resources, 1500.0)
        checks.append(("benchmark summaries load read-only", not benchmark.empty and "inventory_adjusted_operating_cost_vnd" in benchmark, f"{len(benchmark)} rows"))
    except Exception as exc:
        checks.append(("Control Room workflow smoke", False, str(exc)))

    checks.append(("no Streamlit in core layers", _no_forbidden_import("streamlit", ("simulation", "forecasting", "control", "evaluation")), "core packages"))
    checks.append(("no Investment Lab or Stage 8", _no_stage8(), "source/docs scan"))

    print("check | result | detail")
    print("----- | ------ | ------")
    failed = False
    for name, ok, detail in checks:
        failed = failed or not ok
        print(f"{name} | {'PASS' if ok else 'FAIL'} | {detail}")
    return 1 if failed else 0


def _first(text: str) -> str:
    return next((line for line in text.splitlines() if line.strip()), "")


def _no_forbidden_import(term: str, packages: tuple[str, ...]) -> bool:
    paths = [str(PROJECT_ROOT / "src/greenmpc" / package) for package in packages]
    result = subprocess.run(["rg", "-n", "-i", term, *paths], text=True, capture_output=True, timeout=10)
    return result.returncode == 1


def _no_stage8() -> bool:
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    result = subprocess.run(
        ["rg", "-n", "-i", "investment lab|stage 8|capex optimization", "src/greenmpc", "streamlit_app.py"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        env=env,
    )
    return result.returncode == 1


if __name__ == "__main__":
    raise SystemExit(main())
