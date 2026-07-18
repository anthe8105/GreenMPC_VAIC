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
    benchmark_view,
    current_energy_flow,
    current_kpis,
    forecast_frames,
    objective_breakdown,
    plan_frames,
    provenance_summary,
    solver_diagnostics,
    tenant_summary,
)


def render_header(session: LiveControlSession, resources: ControlRoomResources) -> None:
    """Render top-level status and disclosure."""

    kpis = current_kpis(session)
    st.title("GreenMPC Twin Control Room")
    cols = st.columns([1.5, 1, 1, 1, 1])
    cols[0].metric("Local timestamp", str(kpis["timestamp_local"]))
    cols[1].metric("Controller", session.controller_id)
    cols[2].metric("Scenario", session.scenario_id)
    cols[3].metric("Model/data", "compatible")
    cols[4].metric("Offline", "yes")
    st.caption(resources.project_config.project.synthetic_demo_notice)
    st.warning("Synthetic scenario demo using public/rescaled data. No actual VRG operational data is claimed.")


def render_kpis(session: LiveControlSession) -> None:
    """Render current KPI cards."""

    kpis = current_kpis(session)
    cols = st.columns(8)
    cols[0].metric("Park load", f"{kpis['park_load_kw']:,.0f} kW")
    cols[1].metric("PV availability", f"{kpis['pv_available_kw']:,.0f} kW")
    cols[2].metric("Battery SOC", f"{kpis['battery_soc_fraction']:.1%}")
    cols[3].metric("Peak grid import", f"{kpis['grid_import_kw_last_peak']:,.0f} kW")
    cols[4].metric("Peak external import", f"{kpis['external_import_kw_last_peak']:,.0f} kW")
    cols[5].metric("Transformer util.", f"{kpis['transformer_utilization_fraction']:.1%}")
    cols[6].metric("Renewable share", f"{kpis['renewable_share_fraction']:.1%}")
    cols[7].metric("Cost proxy", f"{kpis['operating_cost_vnd']/1_000_000:,.2f}M VND")


def render_control_room(session: LiveControlSession, resources: ControlRoomResources, tenant_id: str) -> None:
    """Render the main operational state, forecast, plan, and diagnostics."""

    render_kpis(session)
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Current Energy Flow")
        st.plotly_chart(charts.energy_flow_bar(current_energy_flow(session)), use_container_width=True)
        st.dataframe(current_energy_flow(session), use_container_width=True, hide_index=True)
    with right:
        st.subheader("Tenant View")
        st.dataframe(pd.DataFrame([tenant_summary(session, tenant_id)]), use_container_width=True, hide_index=True)

    load, solar = forecast_frames(session)
    tenant_plan, park_plan = plan_frames(session)
    st.subheader("Forecast and Plan")
    fcols = st.columns(2)
    fcols[0].plotly_chart(charts.load_forecast_figure(load, tenant_id), use_container_width=True)
    fcols[1].plotly_chart(charts.solar_forecast_figure(solar), use_container_width=True)
    pcols = st.columns(2)
    pcols[0].plotly_chart(charts.park_plan_figure(park_plan), use_container_width=True)
    pcols[1].plotly_chart(charts.soc_figure(park_plan), use_container_width=True)
    if not tenant_plan.empty:
        st.dataframe(tenant_plan, use_container_width=True, hide_index=True)

    st.subheader("First Action and Diagnostics")
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
