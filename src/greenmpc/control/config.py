"""Typed MPC configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from greenmpc.control.exceptions import MPCConfigError


@dataclass(frozen=True)
class MPCGeneralConfig:
    controller_name: str
    planning_horizon_hours: int
    time_step_hours: float
    current_interval_uses_observed_values: bool
    future_intervals_use_forecasts: bool
    forecast_intervals_used: int
    additional_forecast_horizon_for_diagnostics: int
    numerical_tolerance_kw: float
    energy_tolerance_kwh: float
    objective_tolerance: float
    random_seed: int


@dataclass(frozen=True)
class MPCSolverConfig:
    name: str
    verbose: bool
    time_limit_seconds: float
    accept_optimal_inaccurate: bool
    warm_start: bool
    maximum_resolve_attempts: int


@dataclass(frozen=True)
class MPCModeConfig:
    load_quantile: float
    solar_quantile: float


@dataclass(frozen=True)
class MPCBatteryControlConfig:
    enforce_no_simultaneous_charge_discharge: bool
    simultaneous_power_tolerance_kw: float
    direction_fixing_repair_enabled: bool
    terminal_reserve_enabled: bool
    terminal_soc_target_fraction: float
    terminal_reserve_is_soft: bool


@dataclass(frozen=True)
class RenewableTargetControlConfig:
    enabled: bool
    accounting_basis: str
    use_simulator_cumulative_metrics: bool
    shortfall_is_soft: bool
    battery_is_renewable_only_when_mvp_assumptions_hold: bool


@dataclass(frozen=True)
class MPCObjectiveWeightConfig:
    grid_peak_penalty_vnd_per_kw: float
    pv_curtailment_penalty_vnd_per_kwh: float
    renewable_shortfall_penalty_vnd_per_kwh: float
    terminal_reserve_shortfall_penalty_vnd_per_kwh: float
    battery_throughput_multiplier: float


@dataclass(frozen=True)
class MPCObjectiveConfig:
    include_grid_energy_cost: bool
    include_dppa_energy_cost: bool
    include_battery_degradation_proxy: bool
    include_grid_peak_penalty: bool
    include_pv_curtailment_penalty: bool
    include_renewable_shortfall_penalty: bool
    include_terminal_reserve_penalty: bool
    peak_metric: str
    weights: MPCObjectiveWeightConfig


@dataclass(frozen=True)
class MPCPostprocessingConfig:
    clip_only_within_numerical_tolerance: bool
    validate_first_action_with_simulator: bool
    reject_large_repairs: bool
    maximum_balance_repair_kw: float


@dataclass(frozen=True)
class MPCFallbackConfig:
    enabled: bool
    use_reference_feasible_action_constructor: bool
    fallback_is_evaluation_baseline: bool
    fallback_on_solver_error: bool
    fallback_on_infeasible: bool
    fallback_on_invalid_extracted_action: bool


@dataclass(frozen=True)
class MPCOutputConfig:
    plan_output_directory: str
    example_output_directory: str
    diagnostic_output_directory: str
    artifact_directory: str


@dataclass(frozen=True)
class GreenMPCControlConfig:
    schema_version: int
    general: MPCGeneralConfig
    solver: MPCSolverConfig
    modes: dict[str, MPCModeConfig]
    battery: MPCBatteryControlConfig
    renewable_targets: RenewableTargetControlConfig
    objective: MPCObjectiveConfig
    postprocessing: MPCPostprocessingConfig
    fallback: MPCFallbackConfig
    outputs: MPCOutputConfig


def load_mpc_config(path: str | Path = "configs/mpc.yaml") -> GreenMPCControlConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MPCConfigError("mpc config root must be a mapping")
    weights = _build(MPCObjectiveWeightConfig, raw["objective"]["weights"], "objective.weights")
    objective_raw = dict(raw["objective"])
    objective_raw["weights"] = weights
    cfg = GreenMPCControlConfig(
        schema_version=int(raw["schema_version"]),
        general=_build(MPCGeneralConfig, raw["general"], "general"),
        solver=_build(MPCSolverConfig, raw["solver"], "solver"),
        modes={name: _build(MPCModeConfig, value, f"modes.{name}") for name, value in raw["modes"].items()},
        battery=_build(MPCBatteryControlConfig, raw["battery"], "battery"),
        renewable_targets=_build(RenewableTargetControlConfig, raw["renewable_targets"], "renewable_targets"),
        objective=_build(MPCObjectiveConfig, objective_raw, "objective"),
        postprocessing=_build(MPCPostprocessingConfig, raw["postprocessing"], "postprocessing"),
        fallback=_build(MPCFallbackConfig, raw["fallback"], "fallback"),
        outputs=_build(MPCOutputConfig, raw["outputs"], "outputs"),
    )
    _validate(cfg)
    return cfg


def _build(cls: type[Any], data: Any, section: str) -> Any:
    if not isinstance(data, dict):
        raise MPCConfigError(f"{section} must be a mapping")
    fields = set(cls.__dataclass_fields__)
    missing = sorted(fields.difference(data))
    if missing:
        raise MPCConfigError(f"{section} missing required field(s): {', '.join(missing)}")
    extra = sorted(set(data).difference(fields))
    if extra:
        raise MPCConfigError(f"{section} has unsupported field(s): {', '.join(extra)}")
    return cls(**{name: data[name] for name in fields})


def _validate(cfg: GreenMPCControlConfig) -> None:
    if cfg.schema_version != 1:
        raise MPCConfigError("schema_version must be 1")
    g = cfg.general
    if g.planning_horizon_hours != 6:
        raise MPCConfigError("general.planning_horizon_hours must be 6")
    if g.time_step_hours != 1.0:
        raise MPCConfigError("general.time_step_hours must be 1.0")
    if not g.current_interval_uses_observed_values:
        raise MPCConfigError("general.current_interval_uses_observed_values must be true")
    if not g.future_intervals_use_forecasts:
        raise MPCConfigError("general.future_intervals_use_forecasts must be true")
    if g.forecast_intervals_used != 5:
        raise MPCConfigError("general.forecast_intervals_used must be 5")
    if g.additional_forecast_horizon_for_diagnostics != 6:
        raise MPCConfigError("general.additional_forecast_horizon_for_diagnostics must be 6")
    if g.numerical_tolerance_kw < 0 or g.energy_tolerance_kwh <= 0 or g.objective_tolerance < 0:
        raise MPCConfigError("general tolerances must be nonnegative, with energy_tolerance_kwh positive")
    if cfg.solver.name != "HIGHS":
        raise MPCConfigError("solver.name must be HIGHS")
    if cfg.solver.time_limit_seconds <= 0:
        raise MPCConfigError("solver.time_limit_seconds must be positive")
    if cfg.solver.accept_optimal_inaccurate:
        raise MPCConfigError("solver.accept_optimal_inaccurate must be false")
    if cfg.solver.maximum_resolve_attempts < 0:
        raise MPCConfigError("solver.maximum_resolve_attempts must be nonnegative")
    if set(cfg.modes) != {"expected", "conservative"}:
        raise MPCConfigError("modes must contain expected and conservative")
    if cfg.modes["expected"] != MPCModeConfig(0.5, 0.5):
        raise MPCConfigError("modes.expected must use load P50 and solar P50")
    if cfg.modes["conservative"] != MPCModeConfig(0.9, 0.1):
        raise MPCConfigError("modes.conservative must use load P90 and solar P10")
    if not 0 <= cfg.battery.terminal_soc_target_fraction <= 1:
        raise MPCConfigError("battery.terminal_soc_target_fraction must be between 0 and 1")
    if cfg.battery.simultaneous_power_tolerance_kw < 0:
        raise MPCConfigError("battery.simultaneous_power_tolerance_kw must be nonnegative")
    if cfg.renewable_targets.accounting_basis != "cumulative_to_date_plus_planning_horizon":
        raise MPCConfigError("renewable_targets.accounting_basis must be cumulative_to_date_plus_planning_horizon")
    if not cfg.renewable_targets.shortfall_is_soft:
        raise MPCConfigError("renewable_targets.shortfall_is_soft must be true")
    if cfg.objective.peak_metric != "grid_import":
        raise MPCConfigError("objective.peak_metric must be grid_import")
    for name, value in cfg.objective.weights.__dict__.items():
        if value < 0:
            raise MPCConfigError(f"objective.weights.{name} must be nonnegative")
    if cfg.fallback.fallback_is_evaluation_baseline:
        raise MPCConfigError("fallback.fallback_is_evaluation_baseline must be false")
    for name, value in cfg.outputs.__dict__.items():
        if Path(value).is_absolute():
            raise MPCConfigError(f"outputs.{name} must be a relative project path")
