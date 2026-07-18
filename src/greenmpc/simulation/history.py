"""In-memory simulation history and explicit export helpers."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.simulation.accounting import ParkEnergyRecord, TenantEnergyRecord
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.events import EventEffectRecord
from greenmpc.simulation.state import ParkState
from greenmpc.simulation.validation import ConstraintViolation


@dataclass
class SimulationHistory:
    states: list[ParkState] = field(default_factory=list)
    actions: list[ParkAction] = field(default_factory=list)
    tenant_energy: list[TenantEnergyRecord] = field(default_factory=list)
    park_energy: list[ParkEnergyRecord] = field(default_factory=list)
    event_effects: list[EventEffectRecord] = field(default_factory=list)
    violations: list[ConstraintViolation] = field(default_factory=list)

    def clear(self) -> None:
        self.states.clear()
        self.actions.clear()
        self.tenant_energy.clear()
        self.park_energy.clear()
        self.event_effects.clear()
        self.violations.clear()

    def to_frames(self) -> dict[str, pd.DataFrame]:
        return {
            "states": pd.DataFrame([_state_row(state) for state in self.states]),
            "actions": pd.DataFrame([_serializable(action.to_dict()) for action in self.actions]),
            "tenant_energy": pd.DataFrame([_serializable(asdict(row)) for row in self.tenant_energy]),
            "park_energy": pd.DataFrame([_serializable(asdict(row)) for row in self.park_energy]),
            "event_effects": pd.DataFrame([_serializable(asdict(row)) for row in self.event_effects]),
            "violations": pd.DataFrame([_serializable(asdict(row)) for row in self.violations]),
        }

    def export_history(self, output_directory: str | Path, summary: dict[str, Any]) -> dict[str, Path]:
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        frames = self.to_frames()
        paths: dict[str, Path] = {}
        for name, frame in frames.items():
            path = output / f"{name}.csv"
            frame.to_csv(path, index=False)
            paths[name] = path
        summary_path = output / "simulation_summary.json"
        summary_path.write_text(json.dumps(_serializable(summary), indent=2), encoding="utf-8")
        paths["simulation_summary"] = summary_path
        return paths


@dataclass(frozen=True)
class StepResult:
    previous_state: ParkState
    effective_exogenous_state: object
    requested_action: ParkAction
    executed_action: ParkAction
    validation_result: object
    next_state: ParkState
    tenant_energy_records: list[TenantEnergyRecord]
    park_energy_record: ParkEnergyRecord
    event_effect_record: EventEffectRecord | None
    warnings: list[str]
    execution_timestamp_utc: object


def _state_row(state: ParkState) -> dict[str, Any]:
    return {
        "timestamp_local": state.timestamp_local.isoformat(),
        "timestamp_utc": state.timestamp_utc.isoformat(),
        "step_index": state.step_index,
        "battery_energy_kwh": state.battery.energy_kwh,
        "battery_soc_fraction": state.battery.soc_fraction,
        "battery_renewable_energy_kwh": state.battery.renewable_energy_kwh,
        "effective_load_kw": sum(state.exogenous.effective_tenant_load_kw.values()),
        "pv_available_kw": state.exogenous.effective_pv_available_kw,
        "grid_price_vnd_per_kwh": state.exogenous.grid_price_vnd_per_kwh,
        "dppa_available_kw": state.exogenous.dppa_available_kw,
        "cumulative_cost_vnd": state.cumulative.total_operating_cost_vnd,
        "cumulative_renewable_share": (
            0.0
            if state.cumulative.total_load_energy_kwh <= 0
            else state.cumulative.renewable_energy_to_tenants_kwh / state.cumulative.total_load_energy_kwh
        ),
        "active_event_ids": ",".join(state.exogenous.active_event_ids),
    }


def _serializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
