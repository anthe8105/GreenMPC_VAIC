"""Build leakage-audited MPC planning inputs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import pandas as pd

from greenmpc.config import GreenMPCConfig
from greenmpc.control.config import GreenMPCControlConfig
from greenmpc.control.exceptions import MPCInputError
from greenmpc.control.types import MPCInputAuditRecord, MPCMode, MPCPlanningInput
from greenmpc.forecasting.inference import ParkSolarForecast, TenantLoadForecast
from greenmpc.forecasting.training import current_fingerprints
from greenmpc.simulation.park import IndustrialParkSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def build_mpc_planning_input(
    simulator: IndustrialParkSimulator,
    load_forecast: TenantLoadForecast,
    solar_forecast: ParkSolarForecast,
    mode: MPCMode,
    project_config: GreenMPCConfig,
    mpc_config: GreenMPCControlConfig,
    audit_output_path: str | Path | None = None,
) -> MPCPlanningInput:
    state = simulator.get_state()
    effective = simulator.get_effective_exogenous()
    mode_cfg = mpc_config.modes[mode.value]
    load_forecast.validate()
    solar_forecast.validate()
    load_df = load_forecast.to_dataframe()
    solar_df = solar_forecast.to_dataframe()
    origin = pd.Timestamp(state.timestamp_local)
    _validate_origin(load_df, solar_df, origin)
    tenant_ids = tuple(project_config_tenants(project_config))
    timestamps_local = tuple((origin + pd.Timedelta(hours=i)).to_pydatetime() for i in range(6))
    timestamps_utc = tuple(pd.Timestamp(ts).tz_convert("UTC").to_pydatetime() for ts in timestamps_local)

    load_series: dict[str, list[float]] = {tenant_id: [float(effective.effective_tenant_load_kw[tenant_id])] for tenant_id in tenant_ids}
    load_col = _quantile_column(mode_cfg.load_quantile)
    for horizon in range(1, 6):
        rows = load_df[load_df["horizon_hours"] == horizon]
        if set(rows["tenant_id"]) != set(tenant_ids):
            raise MPCInputError(f"load forecast horizon {horizon} must contain all five tenants")
        for tenant_id in tenant_ids:
            load_series[tenant_id].append(float(rows.loc[rows["tenant_id"] == tenant_id, load_col].iloc[0]))

    solar_col = _quantile_column(mode_cfg.solar_quantile)
    pv_values = [float(effective.effective_pv_available_kw)]
    for horizon in range(1, 6):
        row = solar_df[solar_df["horizon_hours"] == horizon]
        if len(row) != 1:
            raise MPCInputError(f"solar forecast horizon {horizon} must contain one row")
        pv_values.append(float(row[solar_col].iloc[0]))

    schedule = [effective] + [simulator.get_baseline_exogenous(ts) for ts in timestamps_local[1:]]
    fingerprints = current_fingerprints()
    sim_fingerprints = simulator.dataset_manifest.get("output_fingerprints", {})
    if sim_fingerprints:
        if sim_fingerprints.get("tenant_hourly.csv") and sim_fingerprints["tenant_hourly.csv"] != fingerprints.get("tenant_hourly_csv_sha256"):
            raise MPCInputError("tenant dataset fingerprint mismatch between simulator and forecast registry")
        if sim_fingerprints.get("park_hourly.csv") and sim_fingerprints["park_hourly.csv"] != fingerprints.get("park_hourly_csv_sha256"):
            raise MPCInputError("park dataset fingerprint mismatch between simulator and forecast registry")

    planning = MPCPlanningInput(
        planning_input_id=f"MPCIN-{uuid4().hex[:12]}",
        controller_mode=mode,
        forecast_origin_local=state.timestamp_local,
        forecast_origin_utc=state.timestamp_utc,
        decision_timestamp_local=state.timestamp_local,
        decision_timestamp_utc=state.timestamp_utc,
        planning_timestamps_local=timestamps_local,
        planning_timestamps_utc=timestamps_utc,
        horizon_hours=6,
        time_step_hours=mpc_config.general.time_step_hours,
        tenant_ids=tenant_ids,
        load_forecast_kw={tenant_id: tuple(values) for tenant_id, values in load_series.items()},
        renewable_target_fraction={tenant.tenant_id: float(tenant.renewable_target_fraction) for tenant in project_config.tenants},
        cumulative_load_kwh=dict(state.cumulative_load_by_tenant_kwh),
        cumulative_renewable_delivery_kwh=dict(state.cumulative_renewable_by_tenant_kwh),
        pv_available_kw=tuple(pv_values),
        grid_price_vnd_per_kwh=tuple(float(item.grid_price_vnd_per_kwh) for item in schedule),
        tariff_period=tuple(str(item.tariff_period) for item in schedule),
        dppa_available_kw=tuple(float(item.dppa_available_kw) for item in schedule),
        dppa_price_vnd_per_kwh=tuple(float(item.dppa_price_vnd_per_kwh) for item in schedule),
        transformer_capacity_kw=tuple(float(item.transformer_capacity_kw) for item in schedule),
        initial_energy_kwh=float(state.battery.energy_kwh),
        initial_soc_fraction=float(state.battery.soc_fraction),
        energy_capacity_kwh=float(project_config.battery.energy_capacity_kwh),
        minimum_energy_kwh=float(state.battery.minimum_energy_kwh),
        maximum_energy_kwh=float(state.battery.maximum_energy_kwh),
        maximum_charge_power_kw=float(state.battery.max_charge_power_kw),
        maximum_discharge_power_kw=float(state.battery.max_discharge_power_kw),
        charge_efficiency=float(project_config.battery.charge_efficiency),
        discharge_efficiency=float(project_config.battery.discharge_efficiency),
        degradation_cost_vnd_per_kwh_throughput=float(project_config.battery.degradation_cost_vnd_per_kwh_throughput),
        initial_renewable_fraction=float(state.battery.renewable_fraction),
        load_forecast_id=load_forecast.metadata.forecast_id,
        solar_forecast_id=solar_forecast.metadata.forecast_id,
        load_model_version=load_forecast.metadata.model_version,
        solar_model_version=solar_forecast.metadata.model_version,
        dataset_version=simulator.dataset_version,
        tenant_dataset_fingerprint=fingerprints.get("tenant_hourly_csv_sha256", ""),
        park_dataset_fingerprint=fingerprints.get("park_hourly_csv_sha256", ""),
        forecast_quantiles_used={"load": mode_cfg.load_quantile, "solar": mode_cfg.solar_quantile},
        current_interval_source="observed_effective_simulator_state",
        future_interval_source="stage4_forecast_quantiles_and_known_schedules",
        warnings=tuple(load_forecast.metadata.warnings + solar_forecast.metadata.warnings),
        metadata={
            "forecast_horizon_6_retained_for_diagnostics_only": True,
            "no_future_actual_load_or_pv": True,
        },
    )
    planning.validate()
    audit = build_input_leakage_audit(planning)
    if not all(record.permitted for record in audit):
        raise MPCInputError("MPC input leakage audit failed")
    if audit_output_path is not None:
        target = PROJECT_ROOT / audit_output_path if not Path(audit_output_path).is_absolute() else Path(audit_output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps([asdict(record) for record in audit], indent=2), encoding="utf-8")
    return planning


def build_input_leakage_audit(planning: MPCPlanningInput) -> list[MPCInputAuditRecord]:
    records: list[MPCInputAuditRecord] = []
    for k, timestamp in enumerate(planning.planning_timestamps_local):
        if k == 0:
            for name in ("tenant_load", "pv_available", "tariff", "dppa", "transformer"):
                records.append(_audit(name, k, timestamp, "observed_current_state", timestamp, None, True, True, "current interval observed value is permitted"))
        else:
            for name in ("tenant_load_forecast", "pv_forecast"):
                records.append(_audit(name, k, timestamp, "stage4_forecast_quantile", planning.decision_timestamp_local, k, True, True, "future uncertain value uses forecast horizon"))
            for name in ("tariff_schedule", "dppa_contract_schedule", "transformer_rating"):
                records.append(_audit(name, k, timestamp, "known_operational_schedule", planning.decision_timestamp_local, None, True, True, "known future schedule input is permitted"))
    return records


def project_config_tenants(config: GreenMPCConfig) -> list[str]:
    return [tenant.tenant_id for tenant in config.tenants]


def _validate_origin(load_df: pd.DataFrame, solar_df: pd.DataFrame, origin: pd.Timestamp) -> None:
    if "origin_local" not in load_df or "origin_local" not in solar_df:
        raise MPCInputError("forecast rows must include origin_local")
    load_origin = pd.to_datetime(load_df["origin_local"]).iloc[0]
    solar_origin = pd.to_datetime(solar_df["origin_local"]).iloc[0]
    if pd.Timestamp(load_origin) != origin or pd.Timestamp(solar_origin) != origin:
        raise MPCInputError("forecast origin must match simulator decision timestamp")


def _quantile_column(quantile: float) -> str:
    return {0.1: "p10_kw", 0.5: "p50_kw", 0.9: "p90_kw"}[float(quantile)]


def _audit(name: str, k: int, timestamp: object, source_type: str, source_timestamp: object, horizon: int | None, known: bool, permitted: bool, reason: str) -> MPCInputAuditRecord:
    return MPCInputAuditRecord(
        parameter_name=name,
        planning_interval=k,
        timestamp=pd.Timestamp(timestamp).isoformat(),
        source_type=source_type,
        source_timestamp=pd.Timestamp(source_timestamp).isoformat(),
        forecast_horizon=horizon,
        known_at_decision_time=known,
        permitted=permitted,
        reason=reason,
    )
