#!/usr/bin/env python
"""Run a deterministic 24-hour Stage 3 digital-twin smoke test."""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from greenmpc.simulation.park import IndustrialParkSimulator
from greenmpc.simulation.reference_action import build_reference_action


def run_smoke() -> dict:
    init_start = time.perf_counter()
    simulator = IndustrialParkSimulator.from_processed_files()
    init_seconds = time.perf_counter() - init_start
    start_timestamp = simulator.get_state().timestamp_local
    initial_soc = simulator.get_state().battery.soc_fraction

    step_seconds: list[float] = []
    for index in range(24):
        action = build_reference_action(simulator.get_state(), simulator.config, action_id=f"SMOKE-{index:03d}")
        step_start = time.perf_counter()
        simulator.step(action)
        step_seconds.append(time.perf_counter() - step_start)

    clone_start = time.perf_counter()
    event_simulator = simulator.clone()
    clone_seconds = time.perf_counter() - clone_start
    cloud_event = next(event for event in event_simulator._catalog_events.values() if event.event_type == "cloud_event")
    event_simulator.reset(cloud_event.start_timestamp_local)
    baseline_pv = event_simulator.get_baseline_exogenous().baseline_pv_available_kw
    event_simulator.activate_catalog_event(cloud_event.event_id)
    event_pv = event_simulator.get_effective_exogenous().effective_pv_available_kw

    output_dir = PROJECT_ROOT / "data/outputs/stage3_smoke"
    exported = simulator.export_history(output_dir)
    html_path = PROJECT_ROOT / "artifacts/digital_twin_smoke.html"
    _write_html(simulator, html_path, baseline_pv, event_pv, cloud_event.event_id)
    summary = simulator.summary()
    summary.update(
        {
            "start_timestamp": start_timestamp.isoformat(),
            "initial_soc": initial_soc,
            "initialization_seconds": init_seconds,
            "average_step_seconds": sum(step_seconds) / len(step_seconds),
            "clone_seconds": clone_seconds,
            "history_memory_bytes_approx": sum(path.stat().st_size for path in exported.values()),
            "cloud_event_id": cloud_event.event_id,
            "cloud_event_baseline_pv_kw": baseline_pv,
            "cloud_event_effective_pv_kw": event_pv,
            "history_output_directory": str(output_dir),
            "html_path": str(html_path),
        }
    )
    return summary


def main() -> int:
    try:
        summary = run_smoke()
    except Exception as exc:  # pragma: no cover - script failure path
        print(f"FAIL Stage 3 smoke test: {exc}")
        return 1
    print("PASS Stage 3 digital-twin smoke")
    for key in (
        "start_timestamp",
        "end_timestamp",
        "steps_executed",
        "total_load_served_kwh",
        "pv_direct_use_kwh",
        "pv_curtailment_kwh",
        "grid_energy_kwh",
        "dppa_energy_kwh",
        "battery_throughput_kwh",
        "initial_soc",
        "final_soc",
        "total_operating_cost_vnd",
        "peak_external_import_kw",
        "renewable_share",
        "event_affected_steps",
        "invalid_action_count",
        "cloud_event_baseline_pv_kw",
        "cloud_event_effective_pv_kw",
        "initialization_seconds",
        "average_step_seconds",
        "clone_seconds",
        "history_memory_bytes_approx",
        "history_output_directory",
        "html_path",
    ):
        print(f"{key}: {summary.get(key)}")
    return 0


def _write_html(simulator: IndustrialParkSimulator, path: Path, baseline_pv: float, event_pv: float, cloud_event_id: str) -> None:
    park = simulator.get_park_energy_history()
    states = simulator.get_state_history()
    if park.empty or states.empty:
        raise ValueError("smoke history is empty")
    park["timestamp_local"] = pd.to_datetime(park["timestamp_local"])
    states["timestamp_local"] = pd.to_datetime(states["timestamp_local"])
    fig = make_subplots(
        rows=5,
        cols=1,
        shared_xaxes=True,
        subplot_titles=(
            "Reference non-optimized energy-source flows",
            "Battery SOC",
            "External import",
            "PV availability and curtailment",
            f"Cloud-event PV comparison ({cloud_event_id})",
        ),
    )
    fig.add_trace(go.Scatter(x=park["timestamp_local"], y=park["total_effective_load_kwh"], name="load served kWh"), row=1, col=1)
    fig.add_trace(go.Scatter(x=park["timestamp_local"], y=park["total_pv_to_tenants_kwh"], name="direct PV kWh"), row=1, col=1)
    fig.add_trace(go.Scatter(x=park["timestamp_local"], y=park["total_dppa_to_tenants_kwh"], name="DPPA to tenants kWh"), row=1, col=1)
    fig.add_trace(go.Scatter(x=park["timestamp_local"], y=park["total_grid_to_tenants_kwh"], name="grid to tenants kWh"), row=1, col=1)
    fig.add_trace(go.Scatter(x=states["timestamp_local"], y=states["battery_soc_fraction"], name="SOC"), row=2, col=1)
    fig.add_trace(go.Scatter(x=park["timestamp_local"], y=park["external_import_kwh"], name="external import kWh"), row=3, col=1)
    fig.add_trace(go.Scatter(x=park["timestamp_local"], y=park["pv_curtailment_kwh"], name="PV curtailed kWh"), row=4, col=1)
    fig.add_trace(go.Bar(x=["baseline PV", "event PV"], y=[baseline_pv, event_pv], name="cloud event PV kW"), row=5, col=1)
    fig.update_layout(
        title="GreenMPC Twin Stage 3 Digital-Twin Smoke: reference action is non-optimized",
        height=1100,
        template="plotly_white",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(path, include_plotlyjs=True)


if __name__ == "__main__":
    raise SystemExit(main())
