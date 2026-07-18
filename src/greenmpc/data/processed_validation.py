"""Strict processed dataset validation for Stage 2."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


SIMULATION_FORBIDDEN_COLUMNS = {"grid_import", "battery_charge", "battery_discharge", "curtailment", "cost", "renewable_allocation"}


def validate_tenant_hourly(df: pd.DataFrame, demo: object, cfg: object) -> None:
    tenant_ids = {tenant.tenant_id for tenant in demo.tenants}
    if set(df["tenant_id"].unique()) != tenant_ids:
        raise ValueError("tenant_hourly must contain exactly five configured tenants")
    if df.duplicated(["timestamp_local", "tenant_id"]).any():
        raise ValueError("tenant_hourly has duplicate timestamp-tenant pairs")
    counts = df.groupby("timestamp_local")["tenant_id"].nunique()
    if not (counts == 5).all():
        raise ValueError("every timestamp must have exactly five tenant rows")
    if (df["load_kw"] < 0).any():
        raise ValueError("tenant_hourly contains negative load")
    if not (abs(df["load_kwh"] - df["load_kw"]) < 1e-6).all():
        raise ValueError("load_kwh must equal load_kw for one-hour intervals")
    if not df["load_is_actual_vrg_data"].eq(False).all():
        raise ValueError("actual VRG flags must remain false")
    if not df["calendar_transfer_applied"].eq(True).all():
        raise ValueError("calendar transfer flags must remain true")
    for column in SIMULATION_FORBIDDEN_COLUMNS:
        if column in df.columns:
            raise ValueError(f"simulation output column is not allowed: {column}")


def validate_park_hourly(park: pd.DataFrame, tenant: pd.DataFrame, cfg: object) -> None:
    if park["timestamp_local"].duplicated().any():
        raise ValueError("park_hourly has duplicate timestamps")
    summed = tenant.groupby("timestamp_local")[["load_kw", "load_kwh"]].sum()
    merged = park.set_index("timestamp_local").join(summed, rsuffix="_tenant")
    if not (abs(merged["park_load_kw"] - merged["load_kw"]) < 1e-6).all():
        raise ValueError("park load must equal tenant sum")
    if not (abs(merged["park_load_kwh"] - merged["load_kwh"]) < 1e-6).all():
        raise ValueError("park energy must equal tenant sum")
    if (park["pv_available_kw"] < 0).any():
        raise ValueError("PV must be nonnegative")
    if (park["pv_available_kw"] > cfg.pv.installed_capacity_kw * cfg.pv.maximum_output_fraction + 1e-6).any():
        raise ValueError("PV exceeds configured capacity cap")
    if (park["grid_price_vnd_per_kwh"] < 0).any():
        raise ValueError("prices must be nonnegative")
    if (park["dppa_available_kw"] < 0).any():
        raise ValueError("DPPA availability must be nonnegative")
    for column in SIMULATION_FORBIDDEN_COLUMNS:
        if column in park.columns:
            raise ValueError(f"simulation output column is not allowed: {column}")


def validate_event_catalog(events: pd.DataFrame, tenant: pd.DataFrame, tenant_ids: list[str]) -> None:
    if events["event_id"].duplicated().any():
        raise ValueError("event IDs must be unique")
    for row in events.to_dict("records"):
        if pd.Timestamp(row["start_timestamp_local"]) >= pd.Timestamp(row["end_timestamp_local"]):
            raise ValueError("event start must precede end")
        affected = row["affected_tenant_id"]
        if pd.notna(affected) and affected and affected not in tenant_ids:
            raise ValueError("invalid event tenant reference")
        if row["applied_to_baseline_dataset"]:
            raise ValueError("events must not be applied to baseline")


def validate_selected_profiles(df: pd.DataFrame, tenant_ids: list[str]) -> None:
    if len(df) != 5:
        raise ValueError("selected profiles must contain exactly five rows")
    if df["source_client_id"].nunique() != 5:
        raise ValueError("selected source clients must be unique")
    if set(df["tenant_id"]) != set(tenant_ids):
        raise ValueError("selected profiles tenant IDs are incomplete")
    if not df["scenario_label_only"].eq(True).all():
        raise ValueError("scenario-only flags must be true")
    if not df["is_actual_industry_identity"].eq(False).all():
        raise ValueError("actual-industry flags must be false")
    if not df["is_actual_vrg_tenant"].eq(False).all():
        raise ValueError("actual-VRG flags must be false")
