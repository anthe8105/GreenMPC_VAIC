"""Typed configuration for the Stage 8 Investment Scenario Lab."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class InvestmentDefaultsConfig:
    controller_id: str
    scenario_id: str
    duration_hours: int
    terminal_inventory_valuation_vnd_per_kwh: float


@dataclass(frozen=True)
class InvestmentDurationConfig:
    smoke_hours: int
    quick_hours: int
    evidence_hours: int


@dataclass(frozen=True)
class InvestmentPVConfig:
    capacity_min_multiplier: float
    capacity_max_multiplier: float
    capacity_step_kw: float


@dataclass(frozen=True)
class InvestmentBatteryConfig:
    energy_min_multiplier: float
    energy_max_multiplier: float
    power_min_multiplier: float
    power_max_multiplier: float
    energy_step_kwh: float
    power_step_kw: float


@dataclass(frozen=True)
class InvestmentFinancialConfig:
    pv_capex_vnd_per_kwp: float
    bess_energy_capex_vnd_per_kwh: float
    bess_power_capex_vnd_per_kw: float
    fixed_implementation_cost_vnd: float
    annual_pv_om_fraction: float
    annual_bess_om_fraction: float
    project_life_years: int
    annual_operating_days: int
    discount_rate: float
    terminal_battery_valuation_prices_vnd_per_kwh: list[float]
    assumptions_version: str


@dataclass(frozen=True)
class InvestmentOutputConfig:
    output_directory: str
    cache_directory: str
    export_directory: str


@dataclass(frozen=True)
class InvestmentConfig:
    schema_version: int
    defaults: InvestmentDefaultsConfig
    durations: InvestmentDurationConfig
    pv: InvestmentPVConfig
    battery: InvestmentBatteryConfig
    financial: InvestmentFinancialConfig
    outputs: InvestmentOutputConfig


def load_investment_config(path: str | Path) -> InvestmentConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("investment config root must be a mapping")
    cfg = InvestmentConfig(
        schema_version=int(raw["schema_version"]),
        defaults=_build(InvestmentDefaultsConfig, raw["defaults"], "defaults"),
        durations=_build(InvestmentDurationConfig, raw["durations"], "durations"),
        pv=_build(InvestmentPVConfig, raw["pv"], "pv"),
        battery=_build(InvestmentBatteryConfig, raw["battery"], "battery"),
        financial=_build(InvestmentFinancialConfig, raw["financial"], "financial"),
        outputs=_build(InvestmentOutputConfig, raw["outputs"], "outputs"),
    )
    _validate(cfg)
    return cfg


def _build(cls: type[Any], data: Any, section: str) -> Any:
    if not isinstance(data, dict):
        raise ValueError(f"{section} must be a mapping")
    fields = {field.name for field in cls.__dataclass_fields__.values()}
    missing = sorted(fields.difference(data))
    if missing:
        raise ValueError(f"{section} missing required field(s): {', '.join(missing)}")
    return cls(**{field: data[field] for field in fields})


def _validate(cfg: InvestmentConfig) -> None:
    if cfg.schema_version != 1:
        raise ValueError("schema_version must be 1")
    allowed_controllers = {"rule_based", "deterministic_mpc", "greenmpc_conservative"}
    if cfg.defaults.controller_id not in allowed_controllers:
        raise ValueError("defaults.controller_id is unsupported")
    allowed_scenarios = {"normal", "cloudy", "production_shift", "combined_stress"}
    if cfg.defaults.scenario_id not in allowed_scenarios:
        raise ValueError("defaults.scenario_id is unsupported")
    durations = {cfg.durations.smoke_hours, cfg.durations.quick_hours, cfg.durations.evidence_hours}
    if durations != {6, 24, 72}:
        raise ValueError("durations must contain 6, 24, and 72 hour modes")
    if cfg.defaults.duration_hours not in durations:
        raise ValueError("defaults.duration_hours must be one of the configured durations")
    if not 0 < cfg.pv.capacity_min_multiplier <= cfg.pv.capacity_max_multiplier:
        raise ValueError("pv capacity multipliers must be positive and ordered")
    if cfg.pv.capacity_step_kw <= 0:
        raise ValueError("pv.capacity_step_kw must be positive")
    if cfg.battery.energy_step_kwh <= 0 or cfg.battery.power_step_kw <= 0:
        raise ValueError("battery step sizes must be positive")
    for field in (
        "pv_capex_vnd_per_kwp",
        "bess_energy_capex_vnd_per_kwh",
        "bess_power_capex_vnd_per_kw",
        "fixed_implementation_cost_vnd",
    ):
        if getattr(cfg.financial, field) < 0:
            raise ValueError(f"financial.{field} must be nonnegative")
    if cfg.financial.annual_operating_days <= 0:
        raise ValueError("financial.annual_operating_days must be positive")
    if cfg.financial.project_life_years <= 0:
        raise ValueError("financial.project_life_years must be positive")
    if not all(price > 0 for price in cfg.financial.terminal_battery_valuation_prices_vnd_per_kwh):
        raise ValueError("terminal battery valuation prices must be positive")
    for path_field in ("output_directory", "cache_directory", "export_directory"):
        path = Path(getattr(cfg.outputs, path_field))
        if path.is_absolute():
            raise ValueError(f"outputs.{path_field} must be a relative project path")
