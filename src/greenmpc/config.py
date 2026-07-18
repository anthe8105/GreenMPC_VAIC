"""Typed configuration loading and validation for GreenMPC Twin."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    short_name: str
    version: str
    random_seed: int
    timezone: str
    currency: str
    synthetic_demo_notice: str


@dataclass(frozen=True)
class SimulationConfig:
    start_date: str
    end_date: str
    time_step_hours: int
    mpc_horizon_hours: int
    default_demo_timestamp: str
    numerical_tolerance: float
    strict_action_validation: bool
    action_tolerance_kw: float
    energy_tolerance_kwh: float
    maximum_event_multiplier: float
    stop_at_dataset_end: bool


@dataclass(frozen=True)
class TenantConfig:
    tenant_id: str
    display_name: str
    scenario_industry: str
    enabled: bool
    nominal_load_kw: float
    renewable_target_fraction: float
    priority_weight: float
    source_profile_placeholder: str


@dataclass(frozen=True)
class SolarConfig:
    installed_capacity_kw: float
    system_loss_fraction: float
    source_type: str
    irradiance_source_placeholder: str


@dataclass(frozen=True)
class BatteryConfig:
    energy_capacity_kwh: float
    max_charge_power_kw: float
    max_discharge_power_kw: float
    charge_efficiency: float
    discharge_efficiency: float
    minimum_soc_fraction: float
    maximum_soc_fraction: float
    initial_soc_fraction: float
    initial_renewable_fraction: float
    allow_simultaneous_charge_discharge: bool
    simultaneous_power_tolerance_kw: float
    degradation_cost_vnd_per_kwh_throughput: float
    values_are_demo_assumptions: bool


@dataclass(frozen=True)
class GridConfig:
    transformer_capacity_kw: float
    transformer_applies_to: str
    external_import_definition: list[str]
    off_peak_price_vnd_per_kwh: float
    normal_price_vnd_per_kwh: float
    peak_price_vnd_per_kwh: float
    tariff_source_placeholder: str
    tariff_effective_date_placeholder: str
    values_are_demo_reference: bool


@dataclass(frozen=True)
class DPPAConfig:
    enabled: bool
    available_capacity_kw: float
    base_price_vnd_per_kwh: float
    renewable_eligible: bool
    values_are_contract_scenario_assumptions: bool


@dataclass(frozen=True)
class ForecastingConfig:
    horizons_hours: list[int]
    quantiles: list[float]
    train_fraction: float
    validation_fraction: float
    test_fraction: float
    model_type_placeholder: str


@dataclass(frozen=True)
class MPCConfig:
    solver: str
    horizon_hours: int
    expected_load_quantile: float
    expected_solar_quantile: float
    conservative_load_quantile: float
    conservative_solar_quantile: float
    solver_time_limit_seconds: float


@dataclass(frozen=True)
class ObjectiveWeightsConfig:
    peak_demand_penalty_vnd_per_kw: float
    curtailment_penalty_vnd_per_kwh: float
    renewable_shortfall_penalty_vnd_per_kwh: float
    battery_throughput_multiplier: float


@dataclass(frozen=True)
class AccountingConfig:
    include_battery_degradation_proxy: bool
    renewable_battery_inventory_method: str
    initial_battery_renewable_status_is_assumption: bool
    count_dppa_as_renewable: bool
    count_rooftop_pv_as_renewable: bool
    count_grid_as_renewable: bool


@dataclass(frozen=True)
class EventConfig:
    cloud_reduction_fraction: float
    production_shift_multiplier: float
    high_load_multiplier: float
    default_duration_hours: int


@dataclass(frozen=True)
class ReportingConfig:
    ledger_output_path: str
    html_output_directory: str
    official_certificate_claim_allowed: bool


@dataclass(frozen=True)
class GreenMPCConfig:
    project: ProjectConfig
    simulation: SimulationConfig
    tenants: list[TenantConfig]
    solar: SolarConfig
    battery: BatteryConfig
    grid: GridConfig
    dppa: DPPAConfig
    forecasting: ForecastingConfig
    mpc: MPCConfig
    objective_weights: ObjectiveWeightsConfig
    accounting: AccountingConfig
    events: EventConfig
    reporting: ReportingConfig


REQUIRED_SECTIONS = {
    "project",
    "simulation",
    "tenants",
    "solar",
    "battery",
    "grid",
    "dppa",
    "forecasting",
    "mpc",
    "objective_weights",
    "accounting",
    "events",
    "reporting",
}


def load_config(path: str | Path) -> GreenMPCConfig:
    """Load and validate a GreenMPC YAML configuration file."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)

    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")

    missing_sections = sorted(REQUIRED_SECTIONS.difference(raw))
    if missing_sections:
        raise ValueError(f"missing required section(s): {', '.join(missing_sections)}")

    config = GreenMPCConfig(
        project=_build(ProjectConfig, raw["project"], "project"),
        simulation=_build(SimulationConfig, raw["simulation"], "simulation"),
        tenants=[
            _build(TenantConfig, tenant, f"tenants[{index}]")
            for index, tenant in enumerate(_require_list(raw["tenants"], "tenants"))
        ],
        solar=_build(SolarConfig, raw["solar"], "solar"),
        battery=_build(BatteryConfig, raw["battery"], "battery"),
        grid=_build(GridConfig, raw["grid"], "grid"),
        dppa=_build(DPPAConfig, raw["dppa"], "dppa"),
        forecasting=_build(ForecastingConfig, raw["forecasting"], "forecasting"),
        mpc=_build(MPCConfig, raw["mpc"], "mpc"),
        objective_weights=_build(
            ObjectiveWeightsConfig,
            raw["objective_weights"],
            "objective_weights",
        ),
        accounting=_build(AccountingConfig, raw["accounting"], "accounting"),
        events=_build(EventConfig, raw["events"], "events"),
        reporting=_build(ReportingConfig, raw["reporting"], "reporting"),
    )
    _validate(config)
    return config


def _build(cls: type[Any], data: Any, section: str) -> Any:
    if not isinstance(data, dict):
        raise ValueError(f"{section} must be a mapping")

    field_names = {field.name for field in cls.__dataclass_fields__.values()}
    missing = sorted(field_names.difference(data))
    if missing:
        raise ValueError(f"{section} missing required field(s): {', '.join(missing)}")

    values = {name: data[name] for name in field_names}
    try:
        return cls(**values)
    except TypeError as exc:
        raise ValueError(f"{section} could not be parsed: {exc}") from exc


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _validate(config: GreenMPCConfig) -> None:
    _validate_dates(config.simulation)
    _validate_tenants(config.tenants)
    _validate_capacities(config)
    _validate_battery(config.battery)
    _validate_grid(config.grid)
    _validate_accounting(config.accounting)
    _validate_forecasting(config.forecasting)
    _validate_mpc(config)
    _validate_reporting(config.reporting)


def _validate_dates(simulation: SimulationConfig) -> None:
    start = _parse_datetime(simulation.start_date, "simulation.start_date")
    end = _parse_datetime(simulation.end_date, "simulation.end_date")
    _parse_datetime(simulation.default_demo_timestamp, "simulation.default_demo_timestamp")
    if end <= start:
        raise ValueError("simulation.end_date must follow simulation.start_date")
    if simulation.time_step_hours <= 0:
        raise ValueError("simulation.time_step_hours must be positive")
    if simulation.mpc_horizon_hours != 6:
        raise ValueError("simulation.mpc_horizon_hours must be 6")
    if simulation.numerical_tolerance <= 0:
        raise ValueError("simulation.numerical_tolerance must be positive")
    if simulation.action_tolerance_kw <= 0:
        raise ValueError("simulation.action_tolerance_kw must be positive")
    if simulation.energy_tolerance_kwh <= 0:
        raise ValueError("simulation.energy_tolerance_kwh must be positive")
    if simulation.maximum_event_multiplier <= 0:
        raise ValueError("simulation.maximum_event_multiplier must be positive")


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except TypeError as exc:
        raise ValueError(f"{field} must be an ISO datetime string") from exc
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO datetime string") from exc


def _validate_tenants(tenants: list[TenantConfig]) -> None:
    if len(tenants) != 5:
        raise ValueError("tenants must contain exactly five MVP tenants")

    tenant_ids = [tenant.tenant_id for tenant in tenants]
    if len(set(tenant_ids)) != len(tenant_ids):
        raise ValueError("tenants.tenant_id values must be unique")

    for tenant in tenants:
        prefix = f"tenants[{tenant.tenant_id}]"
        if not 0 <= tenant.renewable_target_fraction <= 1:
            raise ValueError(f"{prefix}.renewable_target_fraction must be between 0 and 1")
        if tenant.priority_weight <= 0:
            raise ValueError(f"{prefix}.priority_weight must be positive")
        if tenant.nominal_load_kw < 0:
            raise ValueError(f"{prefix}.nominal_load_kw must be nonnegative")


def _validate_capacities(config: GreenMPCConfig) -> None:
    nonnegative_fields = {
        "solar.installed_capacity_kw": config.solar.installed_capacity_kw,
        "solar.system_loss_fraction": config.solar.system_loss_fraction,
        "battery.energy_capacity_kwh": config.battery.energy_capacity_kwh,
        "battery.max_charge_power_kw": config.battery.max_charge_power_kw,
        "battery.max_discharge_power_kw": config.battery.max_discharge_power_kw,
        "battery.degradation_cost_vnd_per_kwh_throughput": (
            config.battery.degradation_cost_vnd_per_kwh_throughput
        ),
        "grid.transformer_capacity_kw": config.grid.transformer_capacity_kw,
        "grid.off_peak_price_vnd_per_kwh": config.grid.off_peak_price_vnd_per_kwh,
        "grid.normal_price_vnd_per_kwh": config.grid.normal_price_vnd_per_kwh,
        "grid.peak_price_vnd_per_kwh": config.grid.peak_price_vnd_per_kwh,
        "dppa.available_capacity_kw": config.dppa.available_capacity_kw,
        "dppa.base_price_vnd_per_kwh": config.dppa.base_price_vnd_per_kwh,
        "objective_weights.peak_demand_penalty_vnd_per_kw": (
            config.objective_weights.peak_demand_penalty_vnd_per_kw
        ),
        "objective_weights.curtailment_penalty_vnd_per_kwh": (
            config.objective_weights.curtailment_penalty_vnd_per_kwh
        ),
        "objective_weights.renewable_shortfall_penalty_vnd_per_kwh": (
            config.objective_weights.renewable_shortfall_penalty_vnd_per_kwh
        ),
        "objective_weights.battery_throughput_multiplier": (
            config.objective_weights.battery_throughput_multiplier
        ),
    }
    for field, value in nonnegative_fields.items():
        if value < 0:
            raise ValueError(f"{field} must be nonnegative")


def _validate_battery(battery: BatteryConfig) -> None:
    for field in ("charge_efficiency", "discharge_efficiency"):
        value = getattr(battery, field)
        if not 0 < value <= 1:
            raise ValueError(f"battery.{field} must be greater than 0 and at most 1")

    if battery.minimum_soc_fraction >= battery.maximum_soc_fraction:
        raise ValueError("battery.minimum_soc_fraction must be below battery.maximum_soc_fraction")

    if not battery.minimum_soc_fraction <= battery.initial_soc_fraction <= battery.maximum_soc_fraction:
        raise ValueError(
            "battery.initial_soc_fraction must lie inside minimum_soc_fraction and maximum_soc_fraction"
        )
    if not 0 <= battery.initial_renewable_fraction <= 1:
        raise ValueError("battery.initial_renewable_fraction must be between 0 and 1")
    if battery.simultaneous_power_tolerance_kw < 0:
        raise ValueError("battery.simultaneous_power_tolerance_kw must be nonnegative")
    if not battery.values_are_demo_assumptions:
        raise ValueError("battery.values_are_demo_assumptions must be true")


def _validate_grid(grid: GridConfig) -> None:
    if grid.transformer_applies_to != "all_external_imports":
        raise ValueError("grid.transformer_applies_to must be all_external_imports")
    required = {"grid_to_tenant", "dppa_to_tenant", "dppa_to_battery"}
    if set(grid.external_import_definition) != required:
        raise ValueError(
            "grid.external_import_definition must contain grid_to_tenant, dppa_to_tenant, and dppa_to_battery"
        )


def _validate_accounting(accounting: AccountingConfig) -> None:
    if not accounting.include_battery_degradation_proxy:
        raise ValueError("accounting.include_battery_degradation_proxy must be true")
    if accounting.renewable_battery_inventory_method != "proportional_mixing":
        raise ValueError(
            "accounting.renewable_battery_inventory_method must be proportional_mixing"
        )
    if not accounting.initial_battery_renewable_status_is_assumption:
        raise ValueError(
            "accounting.initial_battery_renewable_status_is_assumption must be true"
        )
    if not accounting.count_dppa_as_renewable:
        raise ValueError("accounting.count_dppa_as_renewable must be true")
    if not accounting.count_rooftop_pv_as_renewable:
        raise ValueError("accounting.count_rooftop_pv_as_renewable must be true")
    if accounting.count_grid_as_renewable:
        raise ValueError("accounting.count_grid_as_renewable must be false")


def _validate_forecasting(forecasting: ForecastingConfig) -> None:
    if forecasting.horizons_hours != [1, 2, 3, 4, 5, 6]:
        raise ValueError("forecasting.horizons_hours must equal [1, 2, 3, 4, 5, 6]")

    required_quantiles = {0.1, 0.5, 0.9}
    quantiles = {round(float(quantile), 10) for quantile in forecasting.quantiles}
    if not required_quantiles.issubset(quantiles):
        raise ValueError("forecasting.quantiles must include 0.1, 0.5, and 0.9")

    split_sum = (
        forecasting.train_fraction
        + forecasting.validation_fraction
        + forecasting.test_fraction
    )
    if abs(split_sum - 1.0) > 1e-9:
        raise ValueError("forecasting split fractions must sum to 1")


def _validate_mpc(config: GreenMPCConfig) -> None:
    if config.mpc.solver != "HIGHS":
        raise ValueError("mpc.solver must be HIGHS")
    if config.mpc.horizon_hours != 6:
        raise ValueError("mpc.horizon_hours must be 6")


def _validate_reporting(reporting: ReportingConfig) -> None:
    if reporting.official_certificate_claim_allowed:
        raise ValueError("reporting.official_certificate_claim_allowed must be false")
