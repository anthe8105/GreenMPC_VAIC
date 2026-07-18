"""Resource loading and session helpers for the Streamlit Control Room."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.config import GreenMPCConfig, load_config
from greenmpc.control import GreenMPCController
from greenmpc.control.config import GreenMPCControlConfig, load_mpc_config
from greenmpc.evaluation.history_adapter import ObservedHistoryAdapter
from greenmpc.evaluation.scenarios import EvaluationConfig, build_scenarios, load_evaluation_config
from greenmpc.forecasting.inference import ForecastService, ParkSolarForecast, TenantLoadForecast
from greenmpc.simulation.park import IndustrialParkSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ControlRoomResources:
    """Heavy immutable services and data loaded once per app process."""

    project_config: GreenMPCConfig
    mpc_config: GreenMPCControlConfig
    evaluation_config: EvaluationConfig
    tenant_hourly: pd.DataFrame
    park_hourly: pd.DataFrame
    event_catalog: pd.DataFrame
    forecast_service: ForecastService
    controller: GreenMPCController
    benchmark_metrics: pd.DataFrame
    terminal_inventory_costs: pd.DataFrame
    terminal_inventory_sensitivity: pd.DataFrame
    dataset_manifest: dict[str, Any]
    model_manifest: dict[str, Any]
    processed_lineage: dict[str, Any]
    load_seconds: float


@dataclass
class LiveControlSession:
    """Mutable state for one interactive Control Room session."""

    simulator: IndustrialParkSimulator
    history_adapter: ObservedHistoryAdapter
    scenario_id: str
    controller_id: str
    start_timestamp: str
    latest_load_forecast: TenantLoadForecast | None = None
    latest_solar_forecast: ParkSolarForecast | None = None
    latest_plan: Any | None = None
    latest_action: Any | None = None
    latest_validation: Any | None = None
    plan_timestamp: str | None = None
    plan_is_stale: bool = True
    fallback_visible: bool = False
    fallback_reason: str | None = None
    last_error: str | None = None
    timings: dict[str, float] = field(default_factory=dict)
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    active_event_ids: list[str] = field(default_factory=list)


def load_control_room_resources(project_root: Path = PROJECT_ROOT) -> ControlRoomResources:
    """Load heavy read-only resources for the offline Control Room."""

    start = time.perf_counter()
    project_config = load_config(project_root / "configs/demo.yaml")
    mpc_config = load_mpc_config(project_root / "configs/mpc.yaml")
    evaluation_config = load_evaluation_config(project_root / "configs/evaluation.yaml")
    tenant = pd.read_csv(project_root / "data/processed/tenant_hourly.csv")
    park = pd.read_csv(project_root / "data/processed/park_hourly.csv")
    events_path = project_root / "data/processed/scenario_events.csv"
    events = pd.read_csv(events_path) if events_path.exists() else pd.DataFrame()
    forecast_service = ForecastService.from_registry(project_root / "configs/forecasting.yaml")
    controller = GreenMPCController(project_config, mpc_config)
    benchmark_dir = project_root / evaluation_config.output_directory
    benchmark_metrics = _read_csv_if_exists(benchmark_dir / "controller_scenario_metrics.csv")
    terminal_costs = _read_csv_if_exists(project_root / "data/outputs/stage6_audit/terminal_inventory_adjusted_costs.csv")
    terminal_sensitivity = _read_csv_if_exists(project_root / "data/outputs/stage6_audit/terminal_inventory_sensitivity.csv")
    dataset_manifest = _read_json(project_root / "data/processed/dataset_manifest.json")
    model_manifest = _read_json(project_root / "models/forecasting/model_manifest.json")
    lineage = _read_json(project_root / "data/provenance/processed_lineage.json")
    return ControlRoomResources(
        project_config=project_config,
        mpc_config=mpc_config,
        evaluation_config=evaluation_config,
        tenant_hourly=tenant,
        park_hourly=park,
        event_catalog=events,
        forecast_service=forecast_service,
        controller=controller,
        benchmark_metrics=benchmark_metrics,
        terminal_inventory_costs=terminal_costs,
        terminal_inventory_sensitivity=terminal_sensitivity,
        dataset_manifest=dataset_manifest,
        model_manifest=model_manifest,
        processed_lineage=lineage,
        load_seconds=time.perf_counter() - start,
    )


def initialize_live_session(
    resources: ControlRoomResources,
    *,
    scenario_id: str,
    controller_id: str,
    start_timestamp: str | None = None,
) -> LiveControlSession:
    """Create a deterministic simulator session and inject selected scenario events."""

    start_ts = start_timestamp or resources.evaluation_config.start_timestamp
    simulator = IndustrialParkSimulator.from_processed_files(start_timestamp=start_ts)
    scenarios = build_scenarios(resources.evaluation_config, start_ts)
    active_event_ids: list[str] = []
    if scenario_id not in scenarios:
        raise ValueError(f"unknown scenario_id: {scenario_id}")
    for event in scenarios[scenario_id].events:
        simulator.inject_event(event)
        active_event_ids.append(event.event_id)
    adapter = ObservedHistoryAdapter(
        resources.tenant_hourly,
        resources.park_hourly,
        tuple(simulator.tenant_ids),
    )
    session = LiveControlSession(
        simulator=simulator,
        history_adapter=adapter,
        scenario_id=scenario_id,
        controller_id=controller_id,
        start_timestamp=pd.Timestamp(start_ts).isoformat(),
        active_event_ids=active_event_ids,
    )
    return session


def invalidate_plan(session: LiveControlSession) -> None:
    """Mark the current plan/action stale so it cannot be executed twice."""

    session.latest_plan = None
    session.latest_action = None
    session.latest_validation = None
    session.plan_timestamp = None
    session.plan_is_stale = True
    session.fallback_visible = False
    session.fallback_reason = None


def session_fingerprint(session: LiveControlSession) -> str:
    """Return a compact deterministic fingerprint for UI initialization checks."""

    state = session.simulator.get_state()
    payload = {
        "timestamp": state.timestamp_local.isoformat(),
        "scenario": session.scenario_id,
        "controller": session.controller_id,
        "battery_energy": round(state.battery.energy_kwh, 6),
        "active_events": sorted(session.active_event_ids),
    }
    return json.dumps(payload, sort_keys=True)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()
