"""Controller-independent industrial-park digital twin simulator."""

from __future__ import annotations

import copy
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.config import GreenMPCConfig, load_config
from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.processed_validation import validate_event_catalog, validate_park_hourly, validate_tenant_hourly
from greenmpc.simulation.accounting import compute_step_accounting
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.events import RuntimeEvent, apply_events, validate_event
from greenmpc.simulation.exceptions import InvalidActionError, SimulationDataError, SimulationFinishedError
from greenmpc.simulation.history import SimulationHistory, StepResult
from greenmpc.simulation.state import BatteryState, CumulativeMetrics, ExogenousState, ParkState
from greenmpc.simulation.validation import ActionValidationResult, validate_action


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class IndustrialParkSimulator:
    """Deterministic simulator that validates and executes external actions."""

    def __init__(
        self,
        config: GreenMPCConfig,
        tenant_hourly: pd.DataFrame,
        park_hourly: pd.DataFrame,
        event_catalog: pd.DataFrame | None = None,
        start_timestamp: datetime | str | None = None,
        activated_event_ids: list[str] | None = None,
        dataset_manifest: dict | None = None,
    ) -> None:
        self.config = config
        self.tenant_ids = [tenant.tenant_id for tenant in config.tenants]
        self.tenant_targets = {tenant.tenant_id: tenant.renewable_target_fraction for tenant in config.tenants}
        self._tenant_hourly = _prepare_tenant_frame(tenant_hourly)
        self._park_hourly = _prepare_park_frame(park_hourly)
        build_cfg = load_dataset_build_config(PROJECT_ROOT / "configs/dataset_build.yaml")
        validate_tenant_hourly(self._tenant_hourly.reset_index(drop=True), config, build_cfg)
        validate_park_hourly(self._park_hourly.reset_index(drop=True), self._tenant_hourly.reset_index(drop=True), build_cfg)
        if event_catalog is None:
            event_catalog = pd.DataFrame()
        self._event_catalog_frame = _prepare_event_frame(event_catalog)
        if not self._event_catalog_frame.empty:
            validate_event_catalog(self._event_catalog_frame.reset_index(drop=True), self._tenant_hourly.reset_index(drop=True), self.tenant_ids)
        self.dataset_manifest = dataset_manifest or {}
        self.dataset_version = _dataset_version(self._park_hourly, self.dataset_manifest)
        self._timestamps = list(self._park_hourly.index.unique())
        if len(self._timestamps) < 2:
            raise SimulationDataError("processed dataset must contain at least two timestamps")
        self._catalog_events = {
            row["event_id"]: RuntimeEvent.from_catalog_row(row)
            for row in self._event_catalog_frame.reset_index(drop=True).to_dict("records")
        }
        self._initial_activated_event_ids = list(activated_event_ids or [])
        self._initial_timestamp = self._choose_start_timestamp(start_timestamp)
        self._history = SimulationHistory()
        self._runtime_events: dict[str, RuntimeEvent] = {}
        self._state: ParkState
        self.reset(self._initial_timestamp)
        for event_id in self._initial_activated_event_ids:
            self.activate_catalog_event(event_id)

    @classmethod
    def from_processed_files(
        cls,
        config_path: str | Path = PROJECT_ROOT / "configs/demo.yaml",
        tenant_hourly_path: str | Path = PROJECT_ROOT / "data/processed/tenant_hourly.csv",
        park_hourly_path: str | Path = PROJECT_ROOT / "data/processed/park_hourly.csv",
        event_catalog_path: str | Path = PROJECT_ROOT / "data/processed/scenario_events.csv",
        manifest_path: str | Path = PROJECT_ROOT / "data/processed/dataset_manifest.json",
        start_timestamp: datetime | str | None = None,
        activated_event_ids: list[str] | None = None,
    ) -> "IndustrialParkSimulator":
        config = load_config(config_path)
        tenant = pd.read_csv(tenant_hourly_path)
        park = pd.read_csv(park_hourly_path)
        events = pd.read_csv(event_catalog_path) if Path(event_catalog_path).exists() else pd.DataFrame()
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8")) if Path(manifest_path).exists() else {}
        return cls(config, tenant, park, events, start_timestamp, activated_event_ids, manifest)

    def reset(self, start_timestamp: datetime | str | None = None) -> None:
        timestamp = self._choose_start_timestamp(start_timestamp or self._initial_timestamp)
        self._step_index = self._timestamps.index(timestamp)
        self._runtime_events = {
            event_id: replace(event, enabled=(event_id in self._initial_activated_event_ids))
            for event_id, event in self._catalog_events.items()
        }
        self._history.clear()
        zeros = {tenant_id: 0.0 for tenant_id in self.tenant_ids}
        battery = BatteryState.from_config(self.config.battery)
        exogenous = self._baseline_exogenous(timestamp)
        self._state = ParkState(
            step_index=self._step_index,
            timestamp_local=timestamp.to_pydatetime(),
            timestamp_utc=exogenous.timestamp_utc,
            battery=battery,
            exogenous=exogenous,
            cumulative=CumulativeMetrics(),
            cumulative_load_by_tenant_kwh=zeros,
            cumulative_renewable_by_tenant_kwh=zeros,
            cumulative_grid_by_tenant_kwh=zeros,
            cumulative_pv_by_tenant_kwh=zeros,
            cumulative_dppa_by_tenant_kwh=zeros,
            cumulative_battery_by_tenant_kwh=zeros,
        )

    def clone(self) -> "IndustrialParkSimulator":
        cloned = copy.copy(self)
        cloned._runtime_events = copy.deepcopy(self._runtime_events)
        cloned._history = copy.deepcopy(self._history)
        cloned._state = copy.deepcopy(self._state)
        return cloned

    def get_state(self) -> ParkState:
        return copy.deepcopy(self._state)

    def get_baseline_exogenous(self, timestamp: datetime | str | None = None) -> ExogenousState:
        return copy.deepcopy(self._baseline_exogenous(self._resolve_timestamp(timestamp)))

    def get_effective_exogenous(self, timestamp: datetime | str | None = None) -> ExogenousState:
        baseline = self._baseline_exogenous(self._resolve_timestamp(timestamp))
        effective, _ = apply_events(baseline, list(self._runtime_events.values()), self.tenant_ids)
        return effective

    def get_exogenous_window(self, horizon_hours: int, effective: bool = True) -> list[ExogenousState]:
        start = self._step_index
        end = min(start + horizon_hours, len(self._timestamps))
        getter = self.get_effective_exogenous if effective else self.get_baseline_exogenous
        return [getter(timestamp) for timestamp in self._timestamps[start:end]]

    def validate_action(self, action: ParkAction) -> ActionValidationResult:
        effective, _ = apply_events(self._baseline_exogenous(self._timestamps[self._step_index]), list(self._runtime_events.values()), self.tenant_ids)
        state = replace(self._state, exogenous=effective)
        return validate_action(state, action, self.config)

    def step(self, action: ParkAction) -> StepResult:
        if self.is_finished():
            raise SimulationFinishedError("simulator is already at the final executable timestep")
        previous = self.get_state()
        baseline = self._baseline_exogenous(self._timestamps[self._step_index])
        effective, event_record = apply_events(baseline, list(self._runtime_events.values()), self.tenant_ids)
        validation_state = replace(self._state, exogenous=effective)
        result = validate_action(validation_state, action, self.config)
        if not result.valid:
            raise InvalidActionError(_validation_message(result), result)
        accounting = compute_step_accounting(
            previous_battery=self._state.battery,
            previous_cumulative=self._state.cumulative,
            previous_load_by_tenant=dict(self._state.cumulative_load_by_tenant_kwh),
            previous_renewable_by_tenant=dict(self._state.cumulative_renewable_by_tenant_kwh),
            previous_grid_by_tenant=dict(self._state.cumulative_grid_by_tenant_kwh),
            previous_pv_by_tenant=dict(self._state.cumulative_pv_by_tenant_kwh),
            previous_dppa_by_tenant=dict(self._state.cumulative_dppa_by_tenant_kwh),
            previous_battery_by_tenant=dict(self._state.cumulative_battery_by_tenant_kwh),
            exogenous=effective,
            action=action,
            tenant_targets=self.tenant_targets,
            config=self.config,
        )
        next_index = self._step_index + 1
        next_baseline = self._baseline_exogenous(self._timestamps[next_index])
        next_effective, _ = apply_events(next_baseline, list(self._runtime_events.values()), self.tenant_ids)
        next_state = ParkState(
            step_index=next_index,
            timestamp_local=next_effective.timestamp_local,
            timestamp_utc=next_effective.timestamp_utc,
            battery=accounting.next_battery,
            exogenous=next_effective,
            cumulative=accounting.cumulative,
            cumulative_load_by_tenant_kwh=accounting.cumulative_load_by_tenant_kwh,
            cumulative_renewable_by_tenant_kwh=accounting.cumulative_renewable_by_tenant_kwh,
            cumulative_grid_by_tenant_kwh=accounting.cumulative_grid_by_tenant_kwh,
            cumulative_pv_by_tenant_kwh=accounting.cumulative_pv_by_tenant_kwh,
            cumulative_dppa_by_tenant_kwh=accounting.cumulative_dppa_by_tenant_kwh,
            cumulative_battery_by_tenant_kwh=accounting.cumulative_battery_by_tenant_kwh,
            last_action_id=action.action_id,
            last_controller_name=action.controller_name,
            last_validation_status="valid",
        )
        self._state = next_state
        self._step_index = next_index
        self._history.actions.append(action)
        self._history.tenant_energy.extend(accounting.tenant_records)
        self._history.park_energy.append(accounting.park_record)
        if event_record is not None:
            self._history.event_effects.append(event_record)
        self._history.states.append(next_state)
        return StepResult(
            previous_state=previous,
            effective_exogenous_state=effective,
            requested_action=action,
            executed_action=action,
            validation_result=result,
            next_state=next_state,
            tenant_energy_records=accounting.tenant_records,
            park_energy_record=accounting.park_record,
            event_effect_record=event_record,
            warnings=result.warnings,
            execution_timestamp_utc=datetime.now(timezone.utc),
        )

    def run_actions(self, actions: Iterable[ParkAction]) -> list[StepResult]:
        results = []
        for action in actions:
            results.append(self.step(action))
        return results

    def inject_event(self, event: RuntimeEvent) -> None:
        validate_event(event, self.tenant_ids, self.config, self._state.timestamp_local)
        self._runtime_events[event.event_id] = event

    def activate_catalog_event(self, event_id: str) -> None:
        if event_id not in self._runtime_events:
            if event_id not in self._catalog_events:
                raise SimulationDataError(f"unknown catalog event_id: {event_id}")
            self._runtime_events[event_id] = self._catalog_events[event_id]
        event = replace(self._runtime_events[event_id], enabled=True)
        validate_event(event, self.tenant_ids, self.config)
        self._runtime_events[event_id] = event

    def deactivate_event(self, event_id: str) -> None:
        if event_id in self._runtime_events:
            self._runtime_events[event_id] = replace(self._runtime_events[event_id], enabled=False)

    def remove_runtime_event(self, event_id: str) -> None:
        self._runtime_events.pop(event_id, None)

    def clear_runtime_events(self) -> None:
        self._runtime_events.clear()

    def list_active_events(self, timestamp: datetime | str | None = None) -> list[RuntimeEvent]:
        resolved = self._resolve_timestamp(timestamp).to_pydatetime()
        return [event for event in sorted(self._runtime_events.values(), key=lambda item: item.event_id) if event.is_active(resolved)]

    def get_active_events(self, timestamp: datetime | str | None = None) -> list[RuntimeEvent]:
        return self.list_active_events(timestamp)

    def preview_event_effects(self, timestamp: datetime | str | None = None):
        baseline = self._baseline_exogenous(self._resolve_timestamp(timestamp))
        return apply_events(baseline, list(self._runtime_events.values()), self.tenant_ids)

    def get_state_history(self):
        return self._history.to_frames()["states"]

    def get_action_history(self):
        return self._history.to_frames()["actions"]

    def get_tenant_energy_history(self):
        return self._history.to_frames()["tenant_energy"]

    def get_park_energy_history(self):
        return self._history.to_frames()["park_energy"]

    def get_event_effect_history(self):
        return self._history.to_frames()["event_effects"]

    def get_violation_history(self):
        return self._history.to_frames()["violations"]

    def export_history(self, output_directory: str | Path) -> dict[str, Path]:
        return self._history.export_history(output_directory, self.summary())

    def is_finished(self) -> bool:
        return self._step_index >= len(self._timestamps) - 1

    def remaining_steps(self) -> int:
        return max(0, len(self._timestamps) - 1 - self._step_index)

    def summary(self) -> dict:
        cumulative = self._state.cumulative
        park = self._history.park_energy
        min_soc = min((record.battery_soc_after for record in park), default=self._state.battery.soc_fraction)
        max_soc = max((record.battery_soc_after for record in park), default=self._state.battery.soc_fraction)
        return {
            "simulation_id": "stage3_digital_twin",
            "dataset_version": self.dataset_version,
            "start_timestamp": self._initial_timestamp.isoformat(),
            "end_timestamp": self._state.timestamp_local.isoformat(),
            "steps_executed": cumulative.elapsed_steps,
            "controller_names_observed": sorted({action.controller_name for action in self._history.actions}),
            "total_load_served_kwh": cumulative.total_load_energy_kwh,
            "total_renewable_delivery_kwh": cumulative.renewable_energy_to_tenants_kwh,
            "renewable_share": 0.0 if cumulative.total_load_energy_kwh <= 0 else cumulative.renewable_energy_to_tenants_kwh / cumulative.total_load_energy_kwh,
            "pv_direct_use_kwh": cumulative.direct_pv_energy_kwh,
            "pv_curtailment_kwh": cumulative.pv_curtailed_energy_kwh,
            "dppa_energy_kwh": cumulative.dppa_energy_kwh,
            "grid_energy_kwh": cumulative.grid_energy_kwh,
            "battery_discharge_kwh": cumulative.battery_discharge_energy_kwh,
            "battery_throughput_kwh": cumulative.battery_throughput_kwh,
            "initial_soc": self.config.battery.initial_soc_fraction,
            "final_soc": self._state.battery.soc_fraction,
            "minimum_soc": min_soc,
            "maximum_soc": max_soc,
            "peak_grid_import_kw": cumulative.peak_grid_import_kw,
            "peak_external_import_kw": cumulative.peak_external_import_kw,
            "transformer_utilization_maximum": max((record.transformer_utilization_fraction for record in park), default=0.0),
            "total_grid_cost_vnd": cumulative.grid_cost_vnd,
            "total_dppa_cost_vnd": cumulative.dppa_cost_vnd,
            "degradation_proxy_cost_vnd": cumulative.battery_degradation_proxy_cost_vnd,
            "total_operating_cost_vnd": cumulative.total_operating_cost_vnd,
            "event_affected_steps": cumulative.event_affected_step_count,
            "invalid_action_count": cumulative.invalid_action_count,
            "warnings": [],
            "assumptions": [
                "reference actions are non-optimized simulator verification actions",
                "initial battery renewable-energy status is a configurable demo assumption",
                "all external imports pass through the shared transformer in the MVP topology",
            ],
        }

    def _baseline_exogenous(self, timestamp: pd.Timestamp) -> ExogenousState:
        park = self._park_hourly.loc[timestamp]
        tenant_rows = self._tenant_hourly[self._tenant_hourly.index == timestamp]
        loads = {row["tenant_id"]: float(row["load_kw"]) for _, row in tenant_rows.iterrows()}
        if set(loads) != set(self.tenant_ids):
            raise SimulationDataError(f"timestamp {timestamp} does not contain all five tenants")
        return ExogenousState(
            timestamp_local=timestamp.to_pydatetime(),
            timestamp_utc=pd.Timestamp(park["timestamp_utc"]).to_pydatetime(),
            baseline_tenant_load_kw=loads,
            effective_tenant_load_kw=loads,
            baseline_pv_available_kw=float(park["pv_available_kw"]),
            effective_pv_available_kw=float(park["pv_available_kw"]),
            grid_price_vnd_per_kwh=float(park["grid_price_vnd_per_kwh"]),
            tariff_period=str(park["tariff_period"]),
            dppa_available_kw=float(park["dppa_available_kw"]),
            dppa_price_vnd_per_kwh=float(park["dppa_price_vnd_per_kwh"]),
            transformer_capacity_kw=float(park["transformer_capacity_kw"]),
            data_quality_flags={
                "weather": str(park.get("weather_quality_flag", "ok")),
                "load": str(park.get("load_quality_flag", "ok")),
                "pv": str(park.get("pv_quality_flag", "ok")),
                "dataset": str(park.get("dataset_quality_flag", "ok")),
            },
        )

    def _resolve_timestamp(self, timestamp: datetime | str | pd.Timestamp | None) -> pd.Timestamp:
        if timestamp is None:
            return self._timestamps[self._step_index]
        return self._choose_start_timestamp(timestamp, allow_final=True)

    def _choose_start_timestamp(self, timestamp: datetime | str | pd.Timestamp | None, allow_final: bool = False) -> pd.Timestamp:
        if timestamp is None:
            configured = pd.Timestamp(self.config.simulation.default_demo_timestamp)
            timestamp = configured if configured in self._timestamps[:-1] else self._timestamps[0]
        candidate = pd.Timestamp(timestamp)
        if candidate.tzinfo is None:
            raise SimulationDataError("start timestamp must be timezone-aware")
        if candidate not in self._timestamps:
            raise SimulationDataError(f"timestamp is not present in processed data: {candidate}")
        if not allow_final and candidate == self._timestamps[-1]:
            raise SimulationDataError("cannot start on final dataset row because no next state exists")
        return candidate


def _prepare_tenant_frame(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy(deep=True)
    prepared["timestamp_local"] = pd.to_datetime(prepared["timestamp_local"])
    prepared["timestamp_utc"] = pd.to_datetime(prepared["timestamp_utc"])
    return prepared.set_index("timestamp_local", drop=False).sort_index()


def _prepare_park_frame(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy(deep=True)
    prepared["timestamp_local"] = pd.to_datetime(prepared["timestamp_local"])
    prepared["timestamp_utc"] = pd.to_datetime(prepared["timestamp_utc"])
    return prepared.set_index("timestamp_local", drop=False).sort_index()


def _prepare_event_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    prepared = df.copy(deep=True)
    prepared["start_timestamp_local"] = pd.to_datetime(prepared["start_timestamp_local"])
    prepared["end_timestamp_local"] = pd.to_datetime(prepared["end_timestamp_local"])
    return prepared


def _dataset_version(park: pd.DataFrame, manifest: dict) -> str:
    if manifest.get("dataset_version"):
        return str(manifest["dataset_version"])
    if "processed_dataset_version" in park.columns:
        return str(park["processed_dataset_version"].iloc[0])
    return "unknown"


def _validation_message(result: ActionValidationResult) -> str:
    first = result.violations[0].message if result.violations else "invalid action"
    return f"action failed validation with {len(result.violations)} violation(s): {first}"
