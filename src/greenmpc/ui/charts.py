"""Plotly chart builders for the Streamlit Control Room."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd
import plotly.graph_objects as go


SOURCE_COLORS = {
    "pv": "rgba(35, 213, 171, 0.85)",
    "dppa": "rgba(80, 160, 255, 0.85)",
    "grid": "rgba(255, 185, 80, 0.85)",
    "battery": "rgba(180, 120, 255, 0.85)",
    "curtailment": "rgba(255, 95, 120, 0.65)",
}


def apply_dark_layout(fig: go.Figure, height: int = 320) -> go.Figure:
    """Apply the command-center visual theme to a Plotly figure."""

    fig.update_layout(
        template="plotly_dark",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(9, 17, 29, 0.94)",
        font=dict(color="#e8f1ff"),
        margin=dict(l=20, r=20, t=32, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def placeholder_figure(title: str, message: str) -> go.Figure:
    """Build a non-empty designed placeholder panel."""

    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=16, color="#9fb3c8"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(title=title)
    return apply_dark_layout(fig, 300)


def energy_flow_bar(flow: pd.DataFrame) -> go.Figure:
    """Build a compact current-source flow chart."""

    fig = go.Figure()
    if flow.empty:
        return placeholder_figure("Current Energy Flow", "No executed flow yet")
    for source, group in flow.groupby("source"):
        fig.add_bar(name=source, x=group["sink"], y=group["kw"])
    fig.update_layout(barmode="stack", yaxis_title="kW")
    return apply_dark_layout(fig, 300)


def energy_topology_figure(nodes: pd.DataFrame, edges: pd.DataFrame) -> go.Figure:
    """Build a live energy topology with scaled source-to-sink connections."""

    if nodes.empty or edges.empty:
        return placeholder_figure("Live Energy Topology", "Topology waiting for current state")
    node_names = nodes["node"].tolist()
    index = {name: i for i, name in enumerate(node_names)}
    active = edges.copy()
    active["shown_kw"] = active["kw"].where(active["kw"] > 1e-6, 0.1)
    colors = [
        SOURCE_COLORS.get(style, "rgba(120, 140, 160, 0.35)") if is_active else "rgba(80, 90, 105, 0.18)"
        for style, is_active in zip(active["style"], active["active"])
    ]
    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node=dict(
                    label=node_names,
                    pad=18,
                    thickness=15,
                    color=["#21d5ab", "#50a0ff", "#ffb950", "#b478ff", "#d9e6ff", "#ff5f78"] + ["#24364f"] * 5,
                ),
                link=dict(
                    source=[index[source] for source in active["source"]],
                    target=[index[target] for target in active["target"]],
                    value=active["shown_kw"],
                    color=colors,
                    customdata=active["kw"],
                    hovertemplate="%{source.label} -> %{target.label}<br>%{customdata:.1f} kW<extra></extra>",
                ),
            )
        ]
    )
    return apply_dark_layout(fig, 420)


def load_forecast_figure(load: pd.DataFrame, tenant_id: str) -> go.Figure:
    """Build a P10/P50/P90 tenant-load forecast chart."""

    fig = go.Figure()
    if load.empty:
        return placeholder_figure("Tenant Load Forecast", "Click Forecast and Re-optimize")
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
    fig.update_layout(yaxis_title="kW")
    return apply_dark_layout(fig, 320)


def solar_forecast_figure(solar: pd.DataFrame) -> go.Figure:
    """Build a P10/P50/P90 solar forecast chart."""

    fig = go.Figure()
    if solar.empty:
        return placeholder_figure("Solar Forecast", "Click Forecast and Re-optimize")
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
    fig.update_layout(yaxis_title="kW")
    return apply_dark_layout(fig, 320)


def aggregate_forecast_figure(frame: pd.DataFrame) -> go.Figure:
    """Build combined total-load and solar forecast panel."""

    if frame.empty:
        return placeholder_figure("Six-Hour Forecast", "No forecast generated yet")
    fig = go.Figure()
    data = frame.copy()
    data["timestamp_local"] = pd.to_datetime(data["timestamp_local"])
    for series, group in data.groupby("series"):
        fill = "rgba(35, 213, 171, 0.16)" if series == "Solar PV" else "rgba(80, 160, 255, 0.16)"
        fig.add_scatter(x=group["timestamp_local"], y=group["p90_kw"], mode="lines", line=dict(width=0), showlegend=False)
        fig.add_scatter(x=group["timestamp_local"], y=group["p10_kw"], mode="lines", fill="tonexty", fillcolor=fill, line=dict(width=0), name=f"{series} P10-P90")
        fig.add_scatter(x=group["timestamp_local"], y=group["p50_kw"], mode="lines+markers", name=f"{series} P50")
        fig.add_scatter(x=group["timestamp_local"], y=group["current_observed_kw"], mode="markers", marker=dict(symbol="diamond", size=9), name=f"{series} observed")
    fig.update_layout(yaxis_title="kW")
    return apply_dark_layout(fig, 360)


def park_plan_figure(park_plan: pd.DataFrame) -> go.Figure:
    """Build planned source mix and transformer trajectory figure."""

    fig = go.Figure()
    if park_plan.empty:
        return placeholder_figure("Dispatch Plan", "Plan not ready")
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
    fig.update_layout(yaxis_title="kW")
    return apply_dark_layout(fig, 350)


def soc_figure(park_plan: pd.DataFrame) -> go.Figure:
    """Build planned battery SOC trajectory."""

    fig = go.Figure()
    if park_plan.empty:
        return placeholder_figure("Battery SOC Plan", "Plan not ready")
    frame = park_plan.copy()
    frame["timestamp_local"] = pd.to_datetime(frame["timestamp_local"])
    fig.add_scatter(x=frame["timestamp_local"], y=frame["battery_soc_start"], mode="lines+markers", name="SOC start")
    fig.add_scatter(x=frame["timestamp_local"], y=frame["battery_soc_end"], mode="lines+markers", name="SOC end")
    fig.update_layout(yaxis_tickformat=".0%")
    return apply_dark_layout(fig, 280)


def rolling_history_figure(history: pd.DataFrame) -> go.Figure:
    """Build rolling recent-history chart that grows with executed steps."""

    if history.empty:
        return placeholder_figure("Live History", "Execute a step to start the rolling history")
    frame = history.copy()
    frame["timestamp_local"] = pd.to_datetime(frame["timestamp_local"])
    fig = go.Figure()
    for col, label in [
        ("park_load_kw", "Park load"),
        ("pv_to_tenants_kw", "PV"),
        ("grid_import_kw", "Grid"),
        ("dppa_import_kw", "DPPA"),
        ("battery_power_kw", "Battery power"),
    ]:
        if col in frame:
            fig.add_scatter(x=frame["timestamp_local"], y=frame[col], mode="lines+markers", name=label)
    fig.add_scatter(x=frame["timestamp_local"], y=frame["soc_fraction"] * frame["park_load_kw"].max(), mode="lines", name="SOC scaled", line=dict(dash="dot"))
    fig.update_layout(yaxis_title="kW / scaled SOC")
    return apply_dark_layout(fig, 360)


def benchmark_cost_figure(frame: pd.DataFrame) -> go.Figure:
    """Build benchmark raw versus inventory-adjusted cost comparison."""

    fig = go.Figure()
    if frame.empty:
        return placeholder_figure("Benchmark Cost Comparison", "Benchmark summary not loaded")
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
    fig.update_layout(barmode="group", yaxis_title="VND")
    return apply_dark_layout(fig, 420)
