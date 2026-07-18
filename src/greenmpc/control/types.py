"""Typed MPC planning inputs and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any

import pandas as pd

from greenmpc.control.exceptions import MPCInputError
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.validation import ActionValidationResult


class MPCMode(str, Enum):
    EXPECTED = "expected"
    CONSERVATIVE = "conservative"


@dataclass(frozen=True)
class MPCPlanningInput:
    planning_input_id: str
    controller_mode: MPCMode
    forecast_origin_local: datetime
    forecast_origin_utc: datetime
    decision_timestamp_local: datetime
    decision_timestamp_utc: datetime
    planning_timestamps_local: tuple[datetime, ...]
    planning_timestamps_utc: tuple[datetime, ...]
    horizon_hours: int
    time_step_hours: float
    tenant_ids: tuple[str, ...]
    load_forecast_kw: dict[str, tuple[float, ...]]
    renewable_target_fraction: dict[str, float]
    cumulative_load_kwh: dict[str, float]
    cumulative_renewable_delivery_kwh: dict[str, float]
    pv_available_kw: tuple[float, ...]
    grid_price_vnd_per_kwh: tuple[float, ...]
    tariff_period: tuple[str, ...]
    dppa_available_kw: tuple[float, ...]
    dppa_price_vnd_per_kwh: tuple[float, ...]
    transformer_capacity_kw: tuple[float, ...]
    initial_energy_kwh: float
    initial_soc_fraction: float
    energy_capacity_kwh: float
    minimum_energy_kwh: float
    maximum_energy_kwh: float
    maximum_charge_power_kw: float
    maximum_discharge_power_kw: float
    charge_efficiency: float
    discharge_efficiency: float
    degradation_cost_vnd_per_kwh_throughput: float
    initial_renewable_fraction: float
    load_forecast_id: str
    solar_forecast_id: str
    load_model_version: str
    solar_model_version: str
    dataset_version: str
    tenant_dataset_fingerprint: str
    park_dataset_fingerprint: str
    forecast_quantiles_used: dict[str, float]
    current_interval_source: str
    future_interval_source: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.horizon_hours != 6:
            raise MPCInputError("planning input horizon_hours must be 6")
        if self.time_step_hours != 1.0:
            raise MPCInputError("planning input time_step_hours must be 1.0")
        if len(self.planning_timestamps_local) != 6 or len(self.planning_timestamps_utc) != 6:
            raise MPCInputError("planning input must contain exactly six timestamps")
        if len(self.tenant_ids) != 5 or len(set(self.tenant_ids)) != 5:
            raise MPCInputError("planning input must contain exactly five unique tenants")
        if self.planning_timestamps_local[0] != self.decision_timestamp_local:
            raise MPCInputError("interval zero must match current simulator timestamp")
        for previous, current in zip(self.planning_timestamps_local, self.planning_timestamps_local[1:]):
            if pd.Timestamp(current) - pd.Timestamp(previous) != pd.Timedelta(hours=1):
                raise MPCInputError("planning timestamps must be strictly hourly")
        for tenant_id in self.tenant_ids:
            if tenant_id not in self.load_forecast_kw:
                raise MPCInputError(f"load_forecast_kw missing tenant {tenant_id}")
            if len(self.load_forecast_kw[tenant_id]) != 6:
                raise MPCInputError(f"load_forecast_kw[{tenant_id}] must contain six values")
            _finite_nonnegative(self.load_forecast_kw[tenant_id], f"load_forecast_kw[{tenant_id}]")
        for name in ("pv_available_kw", "grid_price_vnd_per_kwh", "dppa_available_kw", "dppa_price_vnd_per_kwh", "transformer_capacity_kw"):
            values = getattr(self, name)
            if len(values) != 6:
                raise MPCInputError(f"{name} must contain six values")
            _finite_nonnegative(values, name)
        if any(value <= 0 for value in self.transformer_capacity_kw):
            raise MPCInputError("transformer_capacity_kw values must be positive")
        if self.energy_capacity_kwh <= 0 or self.initial_energy_kwh < 0 or self.minimum_energy_kwh < 0 or self.maximum_energy_kwh <= self.minimum_energy_kwh:
            raise MPCInputError("battery energy parameters are invalid")
        if not 0 < self.charge_efficiency <= 1 or not 0 < self.discharge_efficiency <= 1:
            raise MPCInputError("battery efficiencies must be in (0, 1]")
        if self.current_interval_source != "observed_effective_simulator_state":
            raise MPCInputError("interval zero must use observed effective simulator state")
        if self.future_interval_source != "stage4_forecast_quantiles_and_known_schedules":
            raise MPCInputError("future intervals must use forecasts and known schedules")


@dataclass(frozen=True)
class MPCInputAuditRecord:
    parameter_name: str
    planning_interval: int
    timestamp: str
    source_type: str
    source_timestamp: str
    forecast_horizon: int | None
    known_at_decision_time: bool
    permitted: bool
    reason: str


@dataclass(frozen=True)
class MPCObjectiveBreakdown:
    grid_energy_cost_vnd: float
    dppa_energy_cost_vnd: float
    battery_degradation_proxy_cost_vnd: float
    operating_cost_proxy_vnd: float
    grid_peak_penalty_vnd: float
    pv_curtailment_penalty_vnd: float
    renewable_shortfall_penalty_vnd: float
    terminal_reserve_penalty_vnd: float
    total_control_objective: float


@dataclass(frozen=True)
class MPCConstraintDiagnostics:
    minimum_battery_energy_margin_kwh: float
    maximum_battery_energy_margin_kwh: float
    maximum_transformer_margin_kw: float
    maximum_dppa_margin_kw: float
    maximum_pv_balance_residual_kw: float
    maximum_tenant_balance_residual_kw: float
    simultaneous_conflict_intervals: tuple[int, ...]
    active_constraint_codes: tuple[str, ...]
    renewable_shortfall_by_tenant_kwh: dict[str, float]
    terminal_reserve_shortfall_kwh: float


@dataclass(frozen=True)
class MPCSolverDiagnostics:
    solver_name: str
    solver_status: str
    solve_time_seconds: float | None
    setup_time_seconds: float | None
    iteration_count: int | None
    resolve_count: int
    direction_repair_applied: bool
    fallback_used: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class MPCPlanResult:
    plan_id: str
    controller_name: str
    controller_mode: MPCMode
    created_at_utc: datetime
    planning_input: MPCPlanningInput
    objective_breakdown: MPCObjectiveBreakdown
    solver_diagnostics: MPCSolverDiagnostics
    constraint_diagnostics: MPCConstraintDiagnostics
    tenant_plan: pd.DataFrame
    park_plan: pd.DataFrame
    first_action: ParkAction | None
    valid_for_execution: bool
    simulator_validation_result: ActionValidationResult | None
    fallback_action: ParkAction | None
    fallback_reason: str | None
    warnings: tuple[str, ...]
    metadata: dict[str, Any]


def _finite_nonnegative(values: tuple[float, ...] | list[float], field: str) -> None:
    for index, value in enumerate(values):
        if not isfinite(float(value)):
            raise MPCInputError(f"{field}[{index}] must be finite")
        if float(value) < 0:
            raise MPCInputError(f"{field}[{index}] must be nonnegative")
