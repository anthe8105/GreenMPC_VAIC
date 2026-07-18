"""Plotly chart builders for the Streamlit Control Room."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd
import plotly.graph_objects as go


def energy_flow_bar(flow: pd.DataFrame) -> go.Figure:
    """Build a compact current-source flow chart."""

    fig = go.Figure()
    if flow.empty:
        return fig
    for source, group in flow.groupby("source"):
        fig.add_bar(name=source, x=group["sink"], y=group["kw"])
    fig.update_layout(barmode="stack", height=300, margin=dict(l=20, r=20, t=30, b=30), yaxis_title="kW")
    return fig


def load_forecast_figure(load: pd.DataFrame, tenant_id: str) -> go.Figure:
    """Build a P10/P50/P90 tenant-load forecast chart."""

    fig = go.Figure()
    if load.empty:
        return fig
    frame = load[load["tenant_id"] == tenant_id].copy()
    frame["timestamp_local"] = pd.to_datetime(frame["timestamp_local"])
    fig.add_scatter(x=frame["timestamp_local"], y=frame["p90_kw"], mode="lines", line=dict(width=0), name="P90")
    fig.add_scatter(
        x=frame["timestamp_local"],
        y=frame["p10_kw"],
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(31, 119, 180, 0.18)",
        name="P10-P90",
    )
    fig.add_scatter(x=frame["timestamp_local"], y=frame["p50_kw"], mode="lines+markers", name="P50")
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=30), yaxis_title="kW")
    return fig


def solar_forecast_figure(solar: pd.DataFrame) -> go.Figure:
    """Build a P10/P50/P90 solar forecast chart."""

    fig = go.Figure()
    if solar.empty:
        return fig
    frame = solar.copy()
    frame["timestamp_local"] = pd.to_datetime(frame["timestamp_local"])
    fig.add_scatter(x=frame["timestamp_local"], y=frame["p90_kw"], mode="lines", line=dict(width=0), name="P90")
    fig.add_scatter(
        x=frame["timestamp_local"],
        y=frame["p10_kw"],
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(44, 160, 44, 0.18)",
        name="P10-P90",
    )
    fig.add_scatter(x=frame["timestamp_local"], y=frame["p50_kw"], mode="lines+markers", name="P50")
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=30), yaxis_title="kW")
    return fig


def park_plan_figure(park_plan: pd.DataFrame) -> go.Figure:
    """Build planned source mix and transformer trajectory figure."""

    fig = go.Figure()
    if park_plan.empty:
        return fig
    frame = park_plan.copy()
    frame["timestamp_local"] = pd.to_datetime(frame["timestamp_local"])
    for col, label in [
        ("pv_to_tenants_kw", "PV to tenants"),
        ("battery_discharge_kw", "Battery to tenants"),
        ("dppa_import_kw", "DPPA import"),
        ("grid_import_kw", "Grid import"),
        ("pv_curtailment_kw", "PV curtailment"),
    ]:
        if col in frame:
            fig.add_scatter(x=frame["timestamp_local"], y=frame[col], mode="lines+markers", stackgroup="energy", name=label)
    if "transformer_capacity_kw" in frame:
        fig.add_scatter(x=frame["timestamp_local"], y=frame["transformer_capacity_kw"], mode="lines", name="Transformer capacity", line=dict(dash="dash"))
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=30), yaxis_title="kW")
    return fig


def soc_figure(park_plan: pd.DataFrame) -> go.Figure:
    """Build planned battery SOC trajectory."""

    fig = go.Figure()
    if park_plan.empty:
        return fig
    frame = park_plan.copy()
    frame["timestamp_local"] = pd.to_datetime(frame["timestamp_local"])
    fig.add_scatter(x=frame["timestamp_local"], y=frame["battery_soc_start"], mode="lines+markers", name="SOC start")
    fig.add_scatter(x=frame["timestamp_local"], y=frame["battery_soc_end"], mode="lines+markers", name="SOC end")
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=30), yaxis_tickformat=".0%")
    return fig


def benchmark_cost_figure(frame: pd.DataFrame) -> go.Figure:
    """Build benchmark raw versus inventory-adjusted cost comparison."""

    fig = go.Figure()
    if frame.empty:
        return fig
    fig.add_bar(
        name="Raw operating cost",
        x=[frame["scenario_id"], frame["controller_id"]],
        y=frame["total_realized_operating_cost_proxy_vnd"],
    )
    fig.add_bar(
        name="Inventory-adjusted cost",
        x=[frame["scenario_id"], frame["controller_id"]],
        y=frame["inventory_adjusted_operating_cost_vnd"],
    )
    fig.update_layout(barmode="group", height=420, margin=dict(l=20, r=20, t=30, b=70), yaxis_title="VND")
    return fig
