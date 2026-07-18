"""GreenMPC Twin Streamlit Live Control Room."""

from __future__ import annotations

import sys
import time

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import streamlit as st

from greenmpc.ui.components import render_benchmark, render_control_room, render_events, render_header, render_provenance
from greenmpc.ui.session import CONTROLLER_OPTIONS, can_execute_latest_plan, execute_next_hour, forecast_and_plan, run_next_hours, switch_controller
from greenmpc.ui.state import initialize_live_session, load_control_room_resources, session_fingerprint


@st.cache_resource(show_spinner="Loading GreenMPC services and offline model registry...")
def cached_resources():
    """Load heavy immutable Control Room resources once per Streamlit process."""

    return load_control_room_resources()


def main() -> None:
    """Render the offline Streamlit Control Room."""

    st.set_page_config(page_title="GreenMPC Twin Control Room", layout="wide")
    resources = cached_resources()
    _ensure_session(resources)

    session = st.session_state["live_session"]
    render_header(session, resources)

    with st.sidebar:
        st.header("Controls")
        with st.form("control_room_inputs"):
            controller_id = st.selectbox("Controller", CONTROLLER_OPTIONS, index=CONTROLLER_OPTIONS.index(session.controller_id))
            scenario_id = st.selectbox("Scenario", tuple(resources.evaluation_config.scenarios), index=tuple(resources.evaluation_config.scenarios).index(session.scenario_id))
            start_timestamp = st.text_input("Demo start timestamp", value=session.start_timestamp)
            tenant_id = st.selectbox("Selected tenant", tuple(session.simulator.tenant_ids))
            valuation_price = st.selectbox("Terminal battery valuation", (1100.0, 1500.0, 2000.0, 2500.0), format_func=lambda value: f"{value:,.0f} VND/kWh")
            reset_clicked = st.form_submit_button("Initialize / Reset Demo")
            plan_clicked = st.form_submit_button("Forecast and Re-optimize")

        if reset_clicked:
            st.session_state["live_session"] = initialize_live_session(resources, scenario_id=scenario_id, controller_id=controller_id, start_timestamp=start_timestamp)
            st.session_state["initialization_fingerprint"] = session_fingerprint(st.session_state["live_session"])
            st.rerun()

        if controller_id != session.controller_id:
            switch_controller(session, controller_id)
        if scenario_id != session.scenario_id:
            st.info("Scenario changes take effect after Initialize / Reset Demo.")

        if plan_clicked:
            with st.spinner("Generating forecasts and solving the selected action..."):
                try:
                    st.session_state["live_session"] = forecast_and_plan(session, resources)
                except Exception as exc:
                    session.last_error = str(exc)
                    st.session_state["live_session"] = session
            st.rerun()

        ready, reason = can_execute_latest_plan(st.session_state["live_session"])
        execute_clicked = st.button("Execute Next Hour", disabled=not ready)
        if execute_clicked:
            st.session_state["live_session"] = execute_next_hour(st.session_state["live_session"])
            st.rerun()

        run_three_clicked = st.button("Run Next 3 Hours")
        if run_three_clicked:
            progress = st.progress(0)
            for index in range(3):
                st.session_state["live_session"] = run_next_hours(st.session_state["live_session"], resources, hours=1)
                progress.progress((index + 1) / 3)
                if st.session_state["live_session"].last_error:
                    break
            st.rerun()

        st.caption(f"Resource cold-load time: {resources.load_seconds:.2f}s")
        if st.session_state["live_session"].timings:
            st.json(st.session_state["live_session"].timings)

    if session.last_error:
        st.error(session.last_error)

    tabs = st.tabs(["Live Control", "Benchmark Evidence", "Provenance"])
    with tabs[0]:
        render_control_room(st.session_state["live_session"], resources, tenant_id)
        render_events(st.session_state["live_session"])
    with tabs[1]:
        render_benchmark(resources, valuation_price)
    with tabs[2]:
        render_provenance(resources, st.session_state["live_session"].scenario_id)


def _ensure_session(resources) -> None:
    if "live_session" not in st.session_state:
        start = time.perf_counter()
        st.session_state["live_session"] = initialize_live_session(
            resources,
            scenario_id="normal",
            controller_id="deterministic_mpc",
            start_timestamp=resources.evaluation_config.start_timestamp,
        )
        st.session_state["initialization_fingerprint"] = session_fingerprint(st.session_state["live_session"])
        st.session_state["ui_initialization_seconds"] = time.perf_counter() - start


if __name__ == "__main__":
    main()
