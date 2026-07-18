"""Typed state models for the industrial-park simulator."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from greenmpc.config import BatteryConfig
from greenmpc.simulation.exceptions import SimulationDataError


def _frozen_float_map(values: Mapping[str, float]) -> Mapping[str, float]:
    return MappingProxyType({str(key): float(value) for key, value in values.items()})


def _frozen_str_tuple(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(value) for value in values)


@dataclass(frozen=True)
class BatteryState:
    """Battery inventory state with explicit energy and renewable content units."""

    energy_kwh: float
    soc_fraction: float
    renewable_energy_kwh: float
    renewable_fraction: float
    minimum_energy_kwh: float
    maximum_energy_kwh: float
    max_charge_power_kw: float
    max_discharge_power_kw: float
    last_charge_power_kw: float = 0.0
    last_discharge_power_kw: float = 0.0

    @classmethod
    def from_config(cls, battery: BatteryConfig) -> "BatteryState":
        total = battery.energy_capacity_kwh * battery.initial_soc_fraction
        renewable = total * battery.initial_renewable_fraction
        return cls.from_energy(
            energy_kwh=total,
            renewable_energy_kwh=renewable,
            energy_capacity_kwh=battery.energy_capacity_kwh,
            minimum_soc_fraction=battery.minimum_soc_fraction,
            maximum_soc_fraction=battery.maximum_soc_fraction,
            max_charge_power_kw=battery.max_charge_power_kw,
            max_discharge_power_kw=battery.max_discharge_power_kw,
        )

    @classmethod
    def from_energy(
        cls,
        *,
        energy_kwh: float,
        renewable_energy_kwh: float,
        energy_capacity_kwh: float,
        minimum_soc_fraction: float,
        maximum_soc_fraction: float,
        max_charge_power_kw: float,
        max_discharge_power_kw: float,
        last_charge_power_kw: float = 0.0,
        last_discharge_power_kw: float = 0.0,
    ) -> "BatteryState":
        if energy_capacity_kwh <= 0:
            raise SimulationDataError("battery.energy_capacity_kwh must be positive")
        soc = energy_kwh / energy_capacity_kwh
        renewable_fraction = 0.0 if energy_kwh <= 0 else renewable_energy_kwh / energy_kwh
        return cls(
            energy_kwh=float(energy_kwh),
            soc_fraction=float(soc),
            renewable_energy_kwh=float(renewable_energy_kwh),
            renewable_fraction=float(renewable_fraction),
            minimum_energy_kwh=float(energy_capacity_kwh * minimum_soc_fraction),
            maximum_energy_kwh=float(energy_capacity_kwh * maximum_soc_fraction),
            max_charge_power_kw=float(max_charge_power_kw),
            max_discharge_power_kw=float(max_discharge_power_kw),
            last_charge_power_kw=float(last_charge_power_kw),
            last_discharge_power_kw=float(last_discharge_power_kw),
        )

    def __post_init__(self) -> None:
        tolerance = 1e-6
        if self.energy_kwh < self.minimum_energy_kwh - tolerance:
            raise SimulationDataError("battery energy is below minimum energy")
        if self.energy_kwh > self.maximum_energy_kwh + tolerance:
            raise SimulationDataError("battery energy is above maximum energy")
        if self.renewable_energy_kwh < -tolerance:
            raise SimulationDataError("battery renewable energy cannot be negative")
        if self.renewable_energy_kwh > self.energy_kwh + tolerance:
            raise SimulationDataError("battery renewable energy cannot exceed total energy")


@dataclass(frozen=True)
class ExogenousState:
    """Immutable exogenous values for one simulator timestep."""

    timestamp_local: datetime
    timestamp_utc: datetime
    baseline_tenant_load_kw: Mapping[str, float]
    effective_tenant_load_kw: Mapping[str, float]
    baseline_pv_available_kw: float
    effective_pv_available_kw: float
    grid_price_vnd_per_kwh: float
    tariff_period: str
    dppa_available_kw: float
    dppa_price_vnd_per_kwh: float
    transformer_capacity_kw: float
    active_event_ids: tuple[str, ...] = field(default_factory=tuple)
    active_event_types: tuple[str, ...] = field(default_factory=tuple)
    data_quality_flags: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_tenant_load_kw", _frozen_float_map(self.baseline_tenant_load_kw))
        object.__setattr__(self, "effective_tenant_load_kw", _frozen_float_map(self.effective_tenant_load_kw))
        object.__setattr__(self, "active_event_ids", _frozen_str_tuple(self.active_event_ids))
        object.__setattr__(self, "active_event_types", _frozen_str_tuple(self.active_event_types))
        object.__setattr__(self, "data_quality_flags", MappingProxyType(dict(self.data_quality_flags)))

    def __deepcopy__(self, memo: dict) -> "ExogenousState":
        return self

    def with_effective_values(
        self,
        *,
        effective_tenant_load_kw: Mapping[str, float],
        effective_pv_available_kw: float,
        dppa_available_kw: float,
        active_event_ids: tuple[str, ...],
        active_event_types: tuple[str, ...],
    ) -> "ExogenousState":
        return replace(
            self,
            effective_tenant_load_kw=effective_tenant_load_kw,
            effective_pv_available_kw=effective_pv_available_kw,
            dppa_available_kw=dppa_available_kw,
            active_event_ids=active_event_ids,
            active_event_types=active_event_types,
        )


@dataclass(frozen=True)
class CumulativeMetrics:
    elapsed_steps: int = 0
    total_load_energy_kwh: float = 0.0
    grid_energy_kwh: float = 0.0
    dppa_energy_kwh: float = 0.0
    direct_pv_energy_kwh: float = 0.0
    battery_discharge_energy_kwh: float = 0.0
    renewable_energy_to_tenants_kwh: float = 0.0
    pv_curtailed_energy_kwh: float = 0.0
    battery_charge_energy_kwh: float = 0.0
    battery_throughput_kwh: float = 0.0
    grid_cost_vnd: float = 0.0
    dppa_cost_vnd: float = 0.0
    battery_degradation_proxy_cost_vnd: float = 0.0
    total_operating_cost_vnd: float = 0.0
    peak_grid_import_kw: float = 0.0
    peak_external_import_kw: float = 0.0
    transformer_violation_count: int = 0
    invalid_action_count: int = 0
    event_affected_step_count: int = 0


@dataclass(frozen=True)
class ParkState:
    """Complete simulator state exposed as a safe immutable snapshot."""

    step_index: int
    timestamp_local: datetime
    timestamp_utc: datetime
    battery: BatteryState
    exogenous: ExogenousState
    cumulative: CumulativeMetrics
    cumulative_load_by_tenant_kwh: Mapping[str, float]
    cumulative_renewable_by_tenant_kwh: Mapping[str, float]
    cumulative_grid_by_tenant_kwh: Mapping[str, float]
    cumulative_pv_by_tenant_kwh: Mapping[str, float]
    cumulative_dppa_by_tenant_kwh: Mapping[str, float]
    cumulative_battery_by_tenant_kwh: Mapping[str, float]
    last_action_id: str | None = None
    last_controller_name: str | None = None
    last_validation_status: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "cumulative_load_by_tenant_kwh",
            "cumulative_renewable_by_tenant_kwh",
            "cumulative_grid_by_tenant_kwh",
            "cumulative_pv_by_tenant_kwh",
            "cumulative_dppa_by_tenant_kwh",
            "cumulative_battery_by_tenant_kwh",
        ):
            object.__setattr__(self, name, _frozen_float_map(getattr(self, name)))

    def __deepcopy__(self, memo: dict) -> "ParkState":
        return self
