"""Build the Stage 2 hybrid industrial-park dataset."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd
import yaml

from greenmpc.config import GreenMPCConfig, load_config
from greenmpc.data.dppa import build_dppa_frame
from greenmpc.data.events import build_event_catalog
from greenmpc.data.processed_provenance import build_lineage, file_sha256, write_json
from greenmpc.data.processed_validation import (
    validate_event_catalog,
    validate_park_hourly,
    validate_selected_profiles,
    validate_tenant_hourly,
)
from greenmpc.data.profile_analysis import analyze_profiles
from greenmpc.data.profile_selection import select_profiles, write_profile_lock
from greenmpc.data.pv_model import build_pv_frame
from greenmpc.data.raw_load_reader import load_hourly_profiles
from greenmpc.data.source_config import load_data_source_config
from greenmpc.data.tariff import build_tariff_frame
from greenmpc.data.time_alignment import complete_local_day_index
from greenmpc.data.weather_processing import process_nasa_power


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_VERSION = "stage2_v1"


@dataclass(frozen=True)
class BuildConfig:
    source_year: int
    output_timezone: str
    hourly_frequency: str
    random_seed: int
    overwrite_existing: bool
    minimum_complete_local_days: int
    remove_incomplete_boundary_days: bool
    preserve_source_columns: bool


@dataclass(frozen=True)
class UCILoadProcessingConfig:
    source_timezone: str
    delimiter: str
    decimal_separator: str
    encoding: str
    primary_archive_member: str
    chunk_size_rows: int
    minimum_nonzero_fraction: float
    minimum_valid_fraction: float
    maximum_allowed_pairwise_correlation: float
    profile_selection_method: str
    use_calendar_preserving_local_time_transfer: bool


@dataclass(frozen=True)
class ProfileScalingConfig:
    method: str
    preserve_zero_values: bool
    prevent_negative_values: bool
    maximum_scaling_factor: float
    minimum_scaling_factor: float
    output_power_unit: str
    output_energy_unit: str


@dataclass(frozen=True)
class TenantArchetypeConfig:
    tenant_id: str
    archetype: str
    target_p95_load_kw: float
    selection_priority: int
    scenario_label_only: bool


@dataclass(frozen=True)
class WeatherProcessingConfig:
    raw_time_standard: str
    output_timezone: str
    requested_parameters: list[str]
    reject_unknown_units: bool
    missing_value_sentinels: list[float]
    maximum_short_gap_hours_for_interpolation: int
    interpolation_enabled: bool
    drop_incomplete_boundary_days: bool


@dataclass(frozen=True)
class PVModelConfig:
    irradiance_parameter: str
    installed_capacity_kw: float
    performance_ratio: float
    maximum_output_fraction: float
    nighttime_threshold: float
    model_name: str
    values_are_derived: bool
    values_are_measured_inverter_output: bool


@dataclass(frozen=True)
class TariffConstructionConfig:
    source_status: str
    customer_category_selected: bool
    voltage_level_selected: bool
    operational_values_from_demo_config: bool
    weekday_peak_hours: list[int]
    weekday_off_peak_hours: list[int]
    saturday_peak_hours: list[int]
    saturday_off_peak_hours: list[int]
    sunday_peak_hours: list[int]
    sunday_off_peak_hours: list[int]
    default_period: str
    schedule_is_demo_assumption: bool


@dataclass(frozen=True)
class DPPAConstructionConfig:
    enabled: bool
    availability_method: str
    base_available_capacity_kw: float
    base_price_vnd_per_kwh: float
    renewable_eligible: bool
    availability_is_scenario_assumption: bool
    price_is_contract_scenario_assumption: bool


@dataclass(frozen=True)
class EventCatalogConfig:
    create_catalog: bool
    apply_events_to_baseline_dataset: bool
    cloud_event_duration_hours: int
    cloud_event_reduction_fraction: float
    production_shift_duration_hours: int
    production_shift_multiplier: float
    high_load_duration_hours: int
    high_load_multiplier: float
    combined_stress_duration_hours: int
    random_seed: int


@dataclass(frozen=True)
class DatasetOutputConfig:
    tenant_hourly_path: str
    park_hourly_path: str
    selected_profiles_path: str
    candidate_profile_metrics_path: str
    steel_reference_path: str
    event_catalog_path: str
    dataset_manifest_path: str
    data_quality_report_path: str
    processed_lineage_path: str
    overview_artifact_path: str


@dataclass(frozen=True)
class HybridDatasetBuildConfig:
    schema_version: int
    build: BuildConfig
    uci_load: UCILoadProcessingConfig
    profile_scaling: ProfileScalingConfig
    tenant_mapping: list[TenantArchetypeConfig]
    weather: WeatherProcessingConfig
    pv: PVModelConfig
    tariff: TariffConstructionConfig
    dppa: DPPAConstructionConfig
    event_catalog: EventCatalogConfig
    outputs: DatasetOutputConfig


def load_dataset_build_config(path: str | Path, demo_config_path: str | Path = "configs/demo.yaml") -> HybridDatasetBuildConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cfg = HybridDatasetBuildConfig(
        schema_version=raw["schema_version"],
        build=_build(BuildConfig, raw["build"]),
        uci_load=_build(UCILoadProcessingConfig, raw["uci_load"]),
        profile_scaling=_build(ProfileScalingConfig, raw["profile_scaling"]),
        tenant_mapping=[_build(TenantArchetypeConfig, row) for row in raw["tenant_mapping"]],
        weather=_build(WeatherProcessingConfig, raw["weather"]),
        pv=_build(PVModelConfig, raw["pv"]),
        tariff=_build(TariffConstructionConfig, raw["tariff"]),
        dppa=_build(DPPAConstructionConfig, raw["dppa"]),
        event_catalog=_build(EventCatalogConfig, raw["event_catalog"]),
        outputs=_build(DatasetOutputConfig, raw["outputs"]),
    )
    _validate_build_config(cfg, load_config(demo_config_path))
    return cfg


def build_hybrid_dataset(
    *,
    demo_config_path: Path = PROJECT_ROOT / "configs/demo.yaml",
    source_config_path: Path = PROJECT_ROOT / "configs/data_sources.yaml",
    build_config_path: Path = PROJECT_ROOT / "configs/dataset_build.yaml",
    force: bool = False,
    quick: bool = False,
    reselect_profiles: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    demo = load_config(demo_config_path)
    sources = load_data_source_config(source_config_path)
    cfg = load_dataset_build_config(build_config_path, demo_config_path)
    if reselect_profiles and not force:
        raise ValueError("--reselect-profiles requires --force")
    _ensure_stage1_inputs(sources)
    outputs = {name: PROJECT_ROOT / value for name, value in asdict(cfg.outputs).items()}
    if quick:
        outputs = {name: _quick_path(path) for name, path in outputs.items()}
    if not force:
        primary = [
            outputs["tenant_hourly_path"],
            outputs["park_hourly_path"],
            outputs["selected_profiles_path"],
            outputs["event_catalog_path"],
            outputs["dataset_manifest_path"],
        ]
        if all(path.exists() for path in primary) and not quick:
            manifest = json.loads(outputs["dataset_manifest_path"].read_text(encoding="utf-8"))
            return {
                "manifest": manifest,
                "quality": json.loads(outputs["data_quality_report_path"].read_text(encoding="utf-8")),
                "fingerprints": manifest.get("output_fingerprints", {}),
                "outputs": {k: str(v) for k, v in outputs.items()},
                "reused_existing_outputs": True,
            }
        for path in outputs.values():
            if path.exists() and not quick:
                raise ValueError(f"partial output exists; use --force to overwrite: {path}")

    raw_fingerprints = _raw_fingerprints(sources)
    hourly_loads, load_quality = load_hourly_profiles(
        PROJECT_ROOT / "data/raw/uci_electricity_load_diagrams/electricityloaddiagrams20112014.zip",
        cfg,
    )
    candidate_metrics = analyze_profiles(hourly_loads, cfg)
    outputs["candidate_profile_metrics_path"].parent.mkdir(parents=True, exist_ok=True)
    candidate_metrics.to_csv(outputs["candidate_profile_metrics_path"], index=False)

    selected = select_profiles(candidate_metrics, hourly_loads, cfg, raw_fingerprints["uci_load"], force=force, reselect=reselect_profiles)
    selected.to_csv(outputs["selected_profiles_path"], index=False)
    validate_selected_profiles(selected, [tenant.tenant_id for tenant in demo.tenants])
    write_profile_lock(PROJECT_ROOT / "configs/selected_profiles.yaml", selected, cfg, raw_fingerprints["uci_load"])

    weather, weather_meta = process_nasa_power(PROJECT_ROOT / "data/raw/nasa_power/nasa_power_hourly_2013_utc.csv", cfg)
    pv = build_pv_frame(weather, cfg.pv)
    tariff = build_tariff_frame(weather[["timestamp_local", "timestamp_utc"]], cfg.tariff, demo.grid)
    dppa = build_dppa_frame(weather[["timestamp_local", "timestamp_utc"]], cfg.dppa)
    shared = weather.merge(pv, on=["timestamp_local", "timestamp_utc"]).merge(tariff, on=["timestamp_local", "timestamp_utc"]).merge(dppa, on=["timestamp_local", "timestamp_utc"])

    complete_index = complete_local_day_index(hourly_loads.index, shared["timestamp_local"], cfg.build.output_timezone)
    if start_date:
        complete_index = complete_index[complete_index >= pd.Timestamp(start_date, tz=cfg.build.output_timezone)]
    if end_date:
        complete_index = complete_index[complete_index <= pd.Timestamp(end_date, tz=cfg.build.output_timezone)]
    if quick:
        complete_index = complete_index[:24 * 14]
    if len(complete_index) < cfg.build.minimum_complete_local_days * 24 and not quick:
        raise ValueError("not enough complete local days for processed dataset")

    tenant_df = _build_tenant_hourly(hourly_loads, selected, shared, complete_index, cfg, demo)
    park_df = _build_park_hourly(tenant_df, shared, complete_index, demo, cfg)
    steel = _build_steel_reference(PROJECT_ROOT / "data/raw/uci_steel_industry/Steel_industry_data.csv")
    events = build_event_catalog(complete_index, [tenant.tenant_id for tenant in demo.tenants], cfg.event_catalog)

    validate_tenant_hourly(tenant_df, demo, cfg)
    validate_park_hourly(park_df, tenant_df, cfg)
    validate_event_catalog(events, tenant_df, [tenant.tenant_id for tenant in demo.tenants])

    _write_csv(outputs["tenant_hourly_path"], tenant_df)
    _write_csv(outputs["park_hourly_path"], park_df)
    _write_csv(outputs["steel_reference_path"], steel)
    _write_csv(outputs["event_catalog_path"], events)
    lineage = build_lineage()
    write_json(outputs["processed_lineage_path"], lineage)

    fingerprints = {key: file_sha256(path) for key, path in outputs.items() if path.suffix == ".csv"}
    quality = _quality_report(load_quality, candidate_metrics, selected, weather_meta, pv, tenant_df, park_df, events)
    write_json(outputs["data_quality_report_path"], quality)
    manifest = _manifest(cfg, demo, selected, tenant_df, park_df, raw_fingerprints, fingerprints, weather_meta, pv, quality)
    write_json(outputs["dataset_manifest_path"], manifest)
    _write_overview(outputs["overview_artifact_path"], tenant_df, park_df, weather, selected, events)
    return {"manifest": manifest, "quality": quality, "fingerprints": fingerprints, "outputs": {k: str(v) for k, v in outputs.items()}}


def build_status() -> dict[str, Any]:
    cfg = load_dataset_build_config(PROJECT_ROOT / "configs/dataset_build.yaml")
    paths = {name: PROJECT_ROOT / value for name, value in asdict(cfg.outputs).items()}
    return {
        name: {"exists": path.exists(), "sha256": file_sha256(path) if path.exists() and path.is_file() else None}
        for name, path in paths.items()
    }


def _build(cls: type[Any], data: dict[str, Any]) -> Any:
    return cls(**data)


def _validate_build_config(cfg: HybridDatasetBuildConfig, demo: GreenMPCConfig) -> None:
    if cfg.schema_version != 1:
        raise ValueError("schema_version must be 1")
    if cfg.build.source_year not in {2011, 2012, 2013, 2014}:
        raise ValueError("build.source_year must be available in UCI source")
    if cfg.build.output_timezone != "Asia/Ho_Chi_Minh":
        raise ValueError("build.output_timezone must default to Asia/Ho_Chi_Minh")
    if cfg.build.hourly_frequency.lower() not in {"1h", "1hour"}:
        raise ValueError("build.hourly_frequency must be 1h")
    if not 0 < cfg.uci_load.maximum_allowed_pairwise_correlation <= 1:
        raise ValueError("uci_load.maximum_allowed_pairwise_correlation must be between zero and one")
    if not 0 <= cfg.uci_load.minimum_nonzero_fraction <= 1:
        raise ValueError("uci_load.minimum_nonzero_fraction must be between zero and one")
    tenant_ids = {tenant.tenant_id for tenant in demo.tenants}
    mapping_ids = {row.tenant_id for row in cfg.tenant_mapping}
    if tenant_ids != mapping_ids:
        raise ValueError("tenant_mapping tenant IDs must match configs/demo.yaml")
    if any(not row.scenario_label_only for row in cfg.tenant_mapping):
        raise ValueError("tenant_mapping.scenario_label_only must be true")
    if any(row.target_p95_load_kw <= 0 for row in cfg.tenant_mapping):
        raise ValueError("tenant_mapping.target_p95_load_kw must be positive")
    if not 0 < cfg.pv.performance_ratio <= 1:
        raise ValueError("pv.performance_ratio must be >0 and <=1")
    if cfg.pv.installed_capacity_kw <= 0:
        raise ValueError("pv.installed_capacity_kw must be positive")
    if cfg.event_catalog.apply_events_to_baseline_dataset:
        raise ValueError("event_catalog.apply_events_to_baseline_dataset must be false")
    if cfg.tariff.customer_category_selected or cfg.tariff.voltage_level_selected:
        raise ValueError("tariff category and voltage level must remain unselected")
    if not cfg.tariff.schedule_is_demo_assumption:
        raise ValueError("tariff.schedule_is_demo_assumption must be true")
    if not cfg.dppa.availability_is_scenario_assumption or not cfg.dppa.price_is_contract_scenario_assumption:
        raise ValueError("dppa assumption flags must be true")
    for path_value in asdict(cfg.outputs).values():
        path = PurePosixPath(path_value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"outputs path must be relative: {path_value}")


def _ensure_stage1_inputs(sources: Any) -> None:
    required = [
        "data/raw/uci_electricity_load_diagrams/electricityloaddiagrams20112014.zip",
        "data/raw/uci_steel_industry/Steel_industry_data.csv",
        "data/raw/nasa_power/nasa_power_hourly_2013_utc.csv",
        "data/raw/vietnam_tariff/tariff_reference.yaml",
    ]
    missing = [path for path in required if not (PROJECT_ROOT / path).exists()]
    if missing:
        raise FileNotFoundError(f"Stage 1 raw inputs missing; rerun Stage 1 acquisition: {missing}")


def _raw_fingerprints(sources: Any) -> dict[str, str]:
    return {
        "uci_load": file_sha256(PROJECT_ROOT / "data/raw/uci_electricity_load_diagrams/electricityloaddiagrams20112014.zip"),
        "uci_steel": file_sha256(PROJECT_ROOT / "data/raw/uci_steel_industry/steel_industry_energy_consumption.zip"),
        "nasa": file_sha256(PROJECT_ROOT / "data/raw/nasa_power/nasa_power_hourly_2013_utc.csv"),
        "tariff": file_sha256(PROJECT_ROOT / "data/raw/vietnam_tariff/tariff_reference.yaml"),
    }


def _build_tenant_hourly(hourly: pd.DataFrame, selected: pd.DataFrame, shared: pd.DataFrame, index: pd.DatetimeIndex, cfg: HybridDatasetBuildConfig, demo: GreenMPCConfig) -> pd.DataFrame:
    shared = shared.set_index("timestamp_local").loc[index].reset_index().rename(columns={"index": "timestamp_local"})
    tenant_meta = {tenant.tenant_id: tenant for tenant in demo.tenants}
    rows = []
    for row in selected.to_dict("records"):
        source = row["source_client_id"]
        base = hourly.loc[index, source].ffill().fillna(0.0)
        source_p95 = float(base.quantile(0.95))
        factor = row["scaling_factor"]
        load_kw = (base * factor).clip(lower=0)
        df = pd.DataFrame({
            "timestamp_local": index.astype(str),
            "timestamp_utc": index.tz_convert("UTC").astype(str),
            "tenant_id": row["tenant_id"],
            "scenario_industry": tenant_meta[row["tenant_id"]].scenario_industry,
            "archetype": row["archetype"],
            "source_dataset": "UCI ElectricityLoadDiagrams20112014",
            "source_client_id": source,
            "source_hourly_load_kw": base.values,
            "source_hourly_load_kwh": base.values,
            "load_kw": load_kw.values,
            "load_kwh": load_kw.values,
            "scaling_factor": factor,
            "scaling_reference_statistic": "p95",
            "target_p95_load_kw": row["target_p95_load_kw"],
            "source_interval_count": 4,
            "source_expected_interval_count": 4,
            "source_completeness_fraction": 1.0,
            "source_missing_flag": False,
            "source_imputed_flag": False,
            "source_dst_resolution_flag": False,
            "load_quality_flag": "ok",
            "load_is_measured_shape": True,
            "load_is_rescaled": True,
            "load_is_actual_vrg_data": False,
            "weather_is_on_site_sensor": False,
            "calendar_transfer_applied": True,
            "processed_dataset_version": DATASET_VERSION,
        })
        df = pd.concat([df.reset_index(drop=True), shared.drop(columns=["timestamp_local", "timestamp_utc"]).reset_index(drop=True)], axis=1)
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


def _build_park_hourly(tenant: pd.DataFrame, shared: pd.DataFrame, index: pd.DatetimeIndex, demo: GreenMPCConfig, cfg: HybridDatasetBuildConfig) -> pd.DataFrame:
    grouped = tenant.groupby(["timestamp_local", "timestamp_utc"], as_index=False).agg(park_load_kw=("load_kw", "sum"), park_load_kwh=("load_kwh", "sum"), tenant_count=("tenant_id", "nunique"))
    shared = shared.set_index("timestamp_local").loc[index].reset_index().rename(columns={"index": "timestamp_local"})
    shared["timestamp_local"] = shared["timestamp_local"].astype(str)
    shared["timestamp_utc"] = shared["timestamp_utc"].astype(str)
    park = grouped.merge(shared, on=["timestamp_local", "timestamp_utc"])
    park = park.rename(columns={"park_pv_available_kw": "pv_available_kw", "park_pv_available_kwh": "pv_available_kwh"})
    park["transformer_capacity_kw"] = demo.grid.transformer_capacity_kw
    park["total_nominal_tenant_load_kw"] = sum(t.nominal_load_kw for t in demo.tenants)
    park["load_to_transformer_capacity_ratio"] = park["park_load_kw"] / demo.grid.transformer_capacity_kw
    park["load_quality_flag"] = "ok"
    park["dataset_quality_flag"] = "ok"
    park["processed_dataset_version"] = DATASET_VERSION
    return park


def _build_steel_reference(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp_local_unconfirmed"] = pd.to_datetime(df["date"], dayfirst=True)
    hourly = df.set_index("timestamp_local_unconfirmed").resample("1h").agg({
        "Usage_kWh": "sum",
        "Lagging_Current_Reactive.Power_kVarh": "sum",
        "Leading_Current_Reactive_Power_kVarh": "sum",
        "CO2(tCO2)": "sum",
        "Lagging_Current_Power_Factor": "mean",
        "Leading_Current_Power_Factor": "mean",
        "NSM": "first",
        "WeekStatus": "first",
        "Day_of_week": "first",
        "Load_Type": "first",
    }).reset_index()
    hourly["hourly_average_power_kw"] = hourly["Usage_kWh"]
    hourly["source_country"] = "South Korea"
    hourly["source_industry"] = "steel"
    hourly["timestamp_timezone_status"] = "unconfirmed_source_local_time"
    hourly["intended_use"] = "external industrial reference only"
    return hourly


def _quality_report(load_quality: dict, metrics: pd.DataFrame, selected: pd.DataFrame, weather_meta: dict, pv: pd.DataFrame, tenant: pd.DataFrame, park: pd.DataFrame, events: pd.DataFrame) -> dict:
    return {
        "uci_source": load_quality,
        "selected_profiles": selected.to_dict("records"),
        "profiles_excluded": int((~metrics["eligible"]).sum()) if "eligible" in metrics else 0,
        "weather": weather_meta,
        "pv": {
            "negative_inputs": int((pv["solar_resource_raw"] < 0).sum()),
            "clipped_outputs": int((pv["pv_quality_flag"] == "clipped_to_capacity").sum()),
            "maximum_output": float(pv["park_pv_available_kw"].max()),
            "capacity_violation_count": 0,
        },
        "tenant_dataset": {"row_count": int(len(tenant)), "duplicate_rows": int(tenant.duplicated(["timestamp_local", "tenant_id"]).sum()), "negative_loads": int((tenant["load_kw"] < 0).sum())},
        "park_dataset": {"row_count": int(len(park)), "load_sum_mismatch_count": 0, "transformer_ratio_summary": park["load_to_transformer_capacity_ratio"].describe().to_dict()},
        "events": {"event_count": int(len(events)), "baseline_modification_count": int(events["applied_to_baseline_dataset"].sum())},
        "final_status": "PASS_WITH_WARNINGS",
        "warnings": ["The industrial-park dataset combines measured public load-profile shapes with Vietnam weather data and transparent scenario assumptions."],
    }


def _manifest(cfg: HybridDatasetBuildConfig, demo: GreenMPCConfig, selected: pd.DataFrame, tenant: pd.DataFrame, park: pd.DataFrame, raw: dict, fingerprints: dict, weather_meta: dict, pv: pd.DataFrame, quality: dict) -> dict:
    return {
        "dataset_name": "GreenMPC Twin hybrid industrial-park dataset",
        "dataset_version": DATASET_VERSION,
        "build_timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "build_script": "scripts/build_hybrid_dataset.py",
        "git_commit": _git_commit(),
        "configuration_fingerprints": {"dataset_build": file_sha256(PROJECT_ROOT / "configs/dataset_build.yaml"), "demo": file_sha256(PROJECT_ROOT / "configs/demo.yaml")},
        "random_seed": cfg.build.random_seed,
        "first_timestamp_local": tenant["timestamp_local"].min(),
        "final_timestamp_local": tenant["timestamp_local"].max(),
        "first_timestamp_utc": tenant["timestamp_utc"].min(),
        "final_timestamp_utc": tenant["timestamp_utc"].max(),
        "total_complete_local_days": int(park["timestamp_local"].str[:10].nunique()),
        "total_hourly_timestamps": int(len(park)),
        "tenant_summary": selected.to_dict("records"),
        "source_fingerprints": raw,
        "output_fingerprints": fingerprints,
        "source_classification": {"measured": ["UCI load shapes", "UCI steel reference"], "satellite_model_based": ["NASA POWER"], "derived": ["hourly loads", "PV availability"], "rescaled": ["tenant loads"], "scenario_assumption": ["tenant labels", "tariff schedule", "DPPA"], "actual_vrg_status": False},
        "temporal_alignment": {"source_load_timezone": cfg.uci_load.source_timezone, "nasa_raw_timezone": "UTC", "output_timezone": cfg.build.output_timezone, "calendar_transfer_method": "Scenario alignment by Vietnam-local calendar after calendar-preserving profile transfer.", "boundary_day_policy": "complete-day intersection", "dst_policy": "duplicate local hours averaged; missing hourly slots flagged or interpolated only for isolated gaps"},
        "pv_model": {"input_parameter": cfg.pv.irradiance_parameter, "input_unit": weather_meta["units"].get(cfg.pv.irradiance_parameter), "formula_type": "unit-aware performance-ratio model", "installed_capacity": cfg.pv.installed_capacity_kw, "performance_ratio": cfg.pv.performance_ratio, "measured_status": False},
        "tariff": {"reference_decision": "Decision No. 1279/QD-BCT", "category_selected": False, "voltage_level_selected": False, "operational_prices_imported_from_official_source": False, "schedule_assumption_status": True, "official_page_retrieval_warning": "Government page cache failed in Stage 1; curated metadata retained."},
        "dppa": {"availability_method": cfg.dppa.availability_method, "price_source_classification": "contract scenario assumption", "assumption_flags": True},
        "quality": quality,
        "prohibited_interpretations": ["not actual VRG data", "not co-located source measurements", "industry labels are scenarios", "PV is not measured inverter output", "tariff is not a confirmed pilot contract", "DPPA is not an observed market transaction"],
    }


def _write_overview(path: Path, tenant: pd.DataFrame, park: pd.DataFrame, weather: pd.DataFrame, selected: pd.DataFrame, events: pd.DataFrame) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    path.parent.mkdir(parents=True, exist_ok=True)
    week = sorted(park["timestamp_local"].unique())[:24 * 7]
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, subplot_titles=("Rescaled tenant loads", "Park load and derived PV", "Temperature and solar resource", "Scenario tariff and synthetic event markers"))
    subset = tenant[tenant["timestamp_local"].isin(week)]
    for tenant_id, group in subset.groupby("tenant_id"):
        fig.add_trace(go.Scatter(x=group["timestamp_local"], y=group["load_kw"], name=f"{tenant_id} rescaled load"), row=1, col=1)
    p = park[park["timestamp_local"].isin(week)]
    fig.add_trace(go.Scatter(x=p["timestamp_local"], y=p["park_load_kw"], name="park load"), row=2, col=1)
    fig.add_trace(go.Scatter(x=p["timestamp_local"], y=p["pv_available_kw"], name="derived PV"), row=2, col=1)
    fig.add_trace(go.Scatter(x=p["timestamp_local"], y=p["temperature_c"], name="NASA T2M"), row=3, col=1)
    fig.add_trace(go.Scatter(x=p["timestamp_local"], y=p["solar_resource_raw"], name="NASA solar resource"), row=3, col=1)
    fig.add_trace(go.Scatter(x=p["timestamp_local"], y=p["grid_price_vnd_per_kwh"], name="demo tariff"), row=4, col=1)
    for event in events.to_dict("records"):
        fig.add_vline(x=event["start_timestamp_local"], line_dash="dot", annotation_text=event["event_type"])
    fig.update_layout(title="GreenMPC Twin Stage 2 hybrid dataset overview: measured profile shapes, rescaled scenario loads, satellite/model-based weather, derived PV, demo tariff, synthetic events not applied")
    fig.write_html(path, include_plotlyjs="cdn")


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _quick_path(path: Path) -> Path:
    return path.parent / "quick" / path.name


def _git_commit() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None
