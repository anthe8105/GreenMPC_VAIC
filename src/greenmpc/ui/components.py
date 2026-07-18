"""Streamlit rendering components for the live Control Room."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd
import streamlit as st

from greenmpc.ui import charts
from greenmpc.ui.session import can_execute_latest_plan
from greenmpc.ui.state import ControlRoomResources, LiveControlSession
from greenmpc.ui.view_models import (
    action_preview,
    aggregate_forecast_frame,
    alert_cards,
    benchmark_view,
    current_energy_flow,
    current_kpis,
    energy_topology,
    forecast_frames,
    objective_breakdown,
    plan_frames,
    primary_kpi_cards,
    provenance_summary,
    recommended_action_card,
    rolling_history_frame,
    secondary_kpi_cards,
    solver_diagnostics,
    tenant_summary,
    ui_status,
)


def apply_command_center_style() -> None:
    """Apply a dark industrial command-center skin."""

    st.markdown(
        """
        <style>
        .stApp { background: #07111f; color: #e8f1ff; }
        [data-testid="stSidebar"] { background: #0b1728; border-right: 1px solid #1f3552; }
        .block-container { padding-top: 1.2rem; max-width: 1500px; }
        .gm-header {
            border: 1px solid #24405f; border-radius: 14px; padding: 18px 20px;
            background: linear-gradient(135deg, #0e2138 0%, #091729 62%, #10271f 100%);
            box-shadow: 0 16px 40px rgba(0,0,0,0.25);
        }
        .gm-title { font-size: 30px; font-weight: 760; letter-spacing: 0; margin: 0 0 10px 0; color: #f6fbff; }
        .gm-chip { display: inline-block; padding: 6px 10px; border-radius: 999px; margin: 4px 6px 0 0; background: #142842; border: 1px solid #2d4e74; color: #d7e8ff; font-size: 13px; }
        .gm-chip.good { border-color: #24c99a; color: #aefce4; background: #0c2b25; }
        .gm-chip.warn { border-color: #ffbf5c; color: #ffe1af; background: #332614; }
        .gm-card {
            min-height: 104px; padding: 16px 16px; border-radius: 14px; border: 1px solid #23425f;
            background: #0d1c30; box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }
        .gm-card.small { min-height: 80px; }
        .gm-label { color: #9fb3c8; font-size: 13px; line-height: 1.2; margin-bottom: 8px; white-space: normal; }
        .gm-value { color: #ffffff; font-size: 26px; font-weight: 740; line-height: 1.15; white-space: normal; overflow-wrap: anywhere; }
        .gm-detail { color: #6fd9bd; font-size: 12px; margin-top: 8px; }
        .gm-section { color: #f5fbff; margin: 12px 0 8px 0; font-size: 20px; font-weight: 700; }
        .gm-alert { padding: 10px 12px; border-radius: 10px; margin-bottom: 8px; border: 1px solid #31506f; background: #0d2036; }
        .gm-alert.error { border-color: #ff5f78; background: #331621; color: #ffd5dc; }
        .gm-alert.warning { border-color: #ffbf5c; background: #302412; color: #ffe2b4; }
        .gm-alert.info { border-color: #50a0ff; background: #11233b; color: #d5e8ff; }
        div[data-testid="stMetricValue"] { white-space: normal; overflow-wrap: anywhere; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(session: LiveControlSession, resources: ControlRoomResources, countdown_seconds: float | None = None) -> None:
    """Render top-level status and disclosure."""

    kpis = current_kpis(session)
    status = ui_status(session, countdown_seconds)
    state_class = "good" if status["status"] in {"Running", "Plan Ready", "Shadow Recommendation"} else "warn"
    st.markdown(
        f"""
        <div class="gm-header">
          <div class="gm-title">GreenMPC Twin — Eco-Industrial Park Command Center</div>
          <span class="gm-chip">{kpis["timestamp_local"]}</span>
          <span class="gm-chip {state_class}">{status["status"]}</span>
          <span class="gm-chip">{status["operation_mode"]}</span>
          <span class="gm-chip">{session.controller_id}</span>
          <span class="gm-chip">{session.scenario_id}</span>
          <span class="gm-chip good">offline compatible</span>
          <span class="gm-chip">next step: {status["countdown"]}</span>
          <span class="gm-chip">hours: {status["completed_hours"]}/{status["maximum_hours"]}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(resources.project_config.project.synthetic_demo_notice)
    st.warning("Synthetic scenario demo using public/rescaled data. No actual VRG operational data is claimed.")


def render_kpis(session: LiveControlSession) -> None:
    """Render current KPI cards."""

    cols = st.columns(4)
    for col, card in zip(cols, primary_kpi_cards(session)):
        col.markdown(_card_html(card), unsafe_allow_html=True)
    small_cols = st.columns(3)
    secondary = secondary_kpi_cards(session)
    for index, card in enumerate(secondary):
        small_cols[index % 3].markdown(_card_html(card, small=True), unsafe_allow_html=True)


def render_control_room(session: LiveControlSession, resources: ControlRoomResources, tenant_id: str) -> None:
    """Render the main operational state, forecast, plan, and diagnostics."""

    render_kpis(session)
    _render_alerts(session)
    left, right = st.columns([1, 1])
    with left:
        st.markdown('<div class="gm-section">Live Energy Topology</div>', unsafe_allow_html=True)
        nodes, edges = energy_topology(session)
        st.plotly_chart(charts.energy_topology_figure(nodes, edges), use_container_width=True)
        st.dataframe(edges[["source", "target", "kw", "active", "style"]], use_container_width=True, hide_index=True)
    with right:
        st.markdown('<div class="gm-section">Tenant View</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([tenant_summary(session, tenant_id)]), use_container_width=True, hide_index=True)

    load, solar = forecast_frames(session)
    tenant_plan, park_plan = plan_frames(session)
    st.markdown('<div class="gm-section">Forecast and Plan</div>', unsafe_allow_html=True)
    st.plotly_chart(charts.aggregate_forecast_figure(aggregate_forecast_frame(session)), use_container_width=True)
    fcols = st.columns(2)
    fcols[0].plotly_chart(charts.load_forecast_figure(load, tenant_id), use_container_width=True)
    fcols[1].plotly_chart(charts.solar_forecast_figure(solar), use_container_width=True)
    pcols = st.columns(2)
    pcols[0].plotly_chart(charts.park_plan_figure(park_plan), use_container_width=True)
    pcols[1].plotly_chart(charts.soc_figure(park_plan), use_container_width=True)
    if not tenant_plan.empty:
        st.dataframe(tenant_plan, use_container_width=True, hide_index=True)

    st.markdown('<div class="gm-section">Recommended Action and Diagnostics</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([recommended_action_card(session)]), use_container_width=True, hide_index=True)
    st.dataframe(action_preview(session), use_container_width=True, hide_index=True)
    diag = solver_diagnostics(session)
    if diag.get("fallback_used"):
        st.error(f"Fallback visible: {diag.get('fallback_reason') or 'fallback action returned'}")
    st.json(diag)
    obj = objective_breakdown(session)
    if not obj.empty:
        st.dataframe(obj, use_container_width=True, hide_index=True)
    ready, reason = can_execute_latest_plan(session)
    st.caption(f"Execution gate: {reason}")

    st.markdown('<div class="gm-section">Rolling Live History</div>', unsafe_allow_html=True)
    st.plotly_chart(charts.rolling_history_figure(rolling_history_frame(session)), use_container_width=True)


def render_events(session: LiveControlSession) -> None:
    """Render active synthetic event definitions."""

    state = session.simulator.get_state()
    events = session.simulator.list_active_events(state.timestamp_local)
    rows = [
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "affected_tenant": event.affected_tenant_id,
            "load_multiplier": event.load_multiplier,
            "pv_multiplier": event.pv_multiplier,
            "dppa_multiplier": event.dppa_multiplier,
            "start": event.start_timestamp_local.isoformat(),
            "end": event.end_timestamp_local.isoformat(),
            "visibility": "unannounced synthetic stress test",
        }
        for event in events
    ]
    st.subheader("Events and Assumptions")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Runtime events modify effective simulator inputs only; Stage 2 baseline files remain unchanged.")


def render_benchmark(resources: ControlRoomResources, valuation_price: float) -> None:
    """Render read-only Stage 6 benchmark evidence."""

    st.subheader("Closed-Loop Benchmark Evidence")
    frame = benchmark_view(resources, valuation_price)
    if frame.empty:
        st.info("Benchmark summaries were not found.")
        return
    cols = [
        "scenario_id",
        "controller_id",
        "total_realized_operating_cost_proxy_vnd",
        "inventory_adjusted_operating_cost_vnd",
        "park_renewable_share",
        "peak_grid_import_kw",
        "peak_external_import_kw",
        "battery_throughput_kwh",
        "final_soc",
        "renewable_shortfall_total_kwh",
        "fallback_count",
    ]
    st.plotly_chart(charts.benchmark_cost_figure(frame), use_container_width=True)
    st.dataframe(frame[[col for col in cols if col in frame.columns]], use_container_width=True, hide_index=True)
    st.caption(
        "Raw operating cost is unchanged. Inventory-adjusted cost values terminal battery energy only as a fairness diagnostic; rankings can change with the valuation price."
    )


def render_provenance(resources: ControlRoomResources, scenario_id: str) -> None:
    """Render provenance and trust disclosures."""

    st.subheader("Provenance and Trust")
    summary = provenance_summary(resources, scenario_id)
    for key, value in summary.items():
        if key == "disclosures":
            continue
        st.write(f"**{key}:** {value}")
    for disclosure in summary["disclosures"]:
        st.info(disclosure)


def _render_alerts(session: LiveControlSession) -> None:
    alerts = alert_cards(session)
    if not alerts:
        st.markdown('<div class="gm-alert info">No active operational alerts.</div>', unsafe_allow_html=True)
        return
    for alert in alerts:
        st.markdown(f'<div class="gm-alert {alert["severity"]}">{alert["message"]}</div>', unsafe_allow_html=True)


def _card_html(card: dict[str, str], small: bool = False) -> str:
    detail = f'<div class="gm-detail">{card.get("detail", "")}</div>' if card.get("detail") else ""
    cls = "gm-card small" if small else "gm-card"
    return f'<div class="{cls}"><div class="gm-label">{card["label"]}</div><div class="gm-value">{card["value"]}</div>{detail}</div>'
