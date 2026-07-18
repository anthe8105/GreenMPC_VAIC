"""Stage 6 evaluation scenario loading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from greenmpc.simulation.events import RuntimeEvent


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    description: str
    events: tuple[RuntimeEvent, ...]


@dataclass(frozen=True)
class EvaluationConfig:
    schema_version: int
    start_timestamp: str
    default_hours: int
    quick_hours: int
    event_visibility_policy: str
    controllers: tuple[str, ...]
    scenarios: dict[str, dict[str, Any]]
    output_directory: str
    artifact_path: str


def load_evaluation_config(path: str | Path = "configs/evaluation.yaml") -> EvaluationConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return EvaluationConfig(
        schema_version=int(raw["schema_version"]),
        start_timestamp=str(raw["benchmark"]["start_timestamp"]),
        default_hours=int(raw["benchmark"]["default_hours"]),
        quick_hours=int(raw["benchmark"]["quick_hours"]),
        event_visibility_policy=str(raw["benchmark"]["event_visibility_policy"]),
        controllers=tuple(raw["controllers"]),
        scenarios=dict(raw["scenarios"]),
        output_directory=str(raw["outputs"]["output_directory"]),
        artifact_path=str(raw["outputs"]["artifact_path"]),
    )


def build_scenarios(cfg: EvaluationConfig, start_timestamp: str | datetime) -> dict[str, ScenarioDefinition]:
    start = pd.Timestamp(start_timestamp)
    result: dict[str, ScenarioDefinition] = {}
    for scenario_id, raw in cfg.scenarios.items():
        events = []
        for event_raw in raw.get("events", []):
            event_start = start + pd.Timedelta(hours=int(event_raw["offset_hours"]))
            duration = int(event_raw["duration_hours"])
            events.append(
                RuntimeEvent(
                    event_id=str(event_raw["event_id"]),
                    event_type=str(event_raw["event_type"]),
                    event_name=str(event_raw["event_id"]),
                    start_timestamp_local=event_start.to_pydatetime(),
                    end_timestamp_local=(event_start + pd.Timedelta(hours=duration)).to_pydatetime(),
                    duration_hours=duration,
                    affected_tenant_id=event_raw.get("affected_tenant_id") or None,
                    load_multiplier=float(event_raw["load_multiplier"]),
                    pv_multiplier=float(event_raw["pv_multiplier"]),
                    dppa_multiplier=float(event_raw["dppa_multiplier"]),
                    description=str(raw.get("description", "")),
                    source="stage6_evaluation_config",
                    is_synthetic=True,
                    enabled=True,
                )
            )
        result[scenario_id] = ScenarioDefinition(scenario_id, str(raw.get("description", "")), tuple(events))
    return result
