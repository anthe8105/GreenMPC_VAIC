"""GreenMPC Twin Streamlit Live Control Room."""

from __future__ import annotations

import sys
import time

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import streamlit as st

from greenmpc.ui.components import apply_command_center_style, render_benchmark, render_control_room, render_events, render_header, render_provenance
from greenmpc.ui.session import (
    CONTROLLER_OPTIONS,
    OPERATION_MODES,
    PLAYBACK_INTERVALS_SECONDS,
    can_execute_latest_plan,
    configure_live_operation,
    execute_next_hour,
    forecast_and_plan,
    pause_live_demo,
    process_control_tick,
    reset_live_run_state,
    seconds_until_next_tick,
    start_live_demo,
    switch_controller,
)
from greenmpc.ui.state import initialize_live_session, load_control_room_resources, session_fingerprint


@st.cache_resource(show_spinner="Loading GreenMPC services and offline model registry...")
def cached_resources():
    """Load heavy immutable Control Room resources once per Streamlit process."""

    return load_control_room_resources()


def main() -> None:
    """Render the offline Streamlit Control Room."""

    st.set_page_config(page_title="GreenMPC Twin Control Room", layout="wide")
    apply_command_center_style()
    resources = cached_resources()
    _ensure_session(resources)
    _live_fragment()

    session = st.session_state["live_session"]
    render_header(session, resources, seconds_until_next_tick(session))

    with st.sidebar:
        st.header("Live Demo Controls")
        operation_mode = st.selectbox("Operating mode", OPERATION_MODES, index=OPERATION_MODES.index(session.operation_mode))
        playback_interval = st.selectbox(
            "Playback speed",
            PLAYBACK_INTERVALS_SECONDS,
            index=PLAYBACK_INTERVALS_SECONDS.index(float(session.playback_interval_seconds)),
            format_func=lambda value: f"1 simulated hour every {int(value)} real seconds",
        )
        maximum_hours = st.number_input("Maximum simulated hours", min_value=1, max_value=24, value=int(session.maximum_simulated_hours), step=1)
        configure_live_operation(
            session,
            operation_mode=operation_mode,
            playback_interval_seconds=float(playback_interval),
            maximum_simulated_hours=int(maximum_hours),
        )
        cols = st.columns(2)
        if cols[0].button("Start Live Demo", use_container_width=True):
            st.session_state["live_session"] = start_live_demo(session)
            _sync_live_fields(st.session_state["live_session"])
            st.rerun()
        if cols[1].button("Pause", use_container_width=True):
            st.session_state["live_session"] = pause_live_demo(session)
            _sync_live_fields(st.session_state["live_session"])
            st.rerun()
        if st.button("Step One Hour", use_container_width=True):
            st.session_state["live_session"] = _step_one_cycle(session, resources)
            _sync_live_fields(st.session_state["live_session"])
            st.rerun()

        st.divider()
        st.header("Scenario and Planning")
        with st.form("control_room_inputs"):
            controller_id = st.selectbox("Controller", CONTROLLER_OPTIONS, index=CONTROLLER_OPTIONS.index(session.controller_id))
            scenario_id = st.selectbox("Scenario", tuple(resources.evaluation_config.scenarios), index=tuple(resources.evaluation_config.scenarios).index(session.scenario_id))
            start_timestamp = st.text_input("Demo start timestamp", value=session.start_timestamp)
            tenant_id = st.selectbox("Selected tenant", tuple(session.simulator.tenant_ids))
            valuation_price = st.selectbox("Terminal battery valuation", (1100.0, 1500.0, 2000.0, 2500.0), format_func=lambda value: f"{value:,.0f} VND/kWh")
            reset_clicked = st.form_submit_button("Reset")
            plan_clicked = st.form_submit_button("Forecast and Re-optimize")

        if reset_clicked:
            st.session_state["live_session"] = initialize_live_session(resources, scenario_id=scenario_id, controller_id=controller_id, start_timestamp=start_timestamp)
            configure_live_operation(
                st.session_state["live_session"],
                operation_mode=operation_mode,
                playback_interval_seconds=float(playback_interval),
                maximum_simulated_hours=int(maximum_hours),
            )
            reset_live_run_state(st.session_state["live_session"])
            st.session_state["initialization_fingerprint"] = session_fingerprint(st.session_state["live_session"])
            _sync_live_fields(st.session_state["live_session"])
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
            _sync_live_fields(st.session_state["live_session"])
            st.rerun()

        ready, reason = can_execute_latest_plan(st.session_state["live_session"])
        execute_label = "Approve Fallback Action" if st.session_state["live_session"].fallback_visible else "Approve & Execute Next Hour"
        shadow_mode = st.session_state["live_session"].operation_mode == "Shadow Mode"
        execute_clicked = st.button(execute_label, disabled=(not ready or shadow_mode), use_container_width=True)
        if shadow_mode:
            st.caption("Shadow Mode displays recommendations only and does not execute actions.")
        if execute_clicked:
            st.session_state["live_session"] = execute_next_hour(st.session_state["live_session"])
            _sync_live_fields(st.session_state["live_session"])
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
        _sync_live_fields(st.session_state["live_session"])


def _step_one_cycle(session, resources):
    if session.operation_mode == "Shadow Mode":
        return forecast_and_plan(session, resources)
    if session.operation_mode == "Auto Pilot Demo":
        session.live_mode_enabled = True
        session.next_control_tick = time.monotonic()
        return process_control_tick(session, resources, time.monotonic())
    ready, reason = can_execute_latest_plan(session)
    if ready:
        return execute_next_hour(session)
    session.last_error = f"Manual Approval mode requires a valid forecast and plan before stepping: {reason}"
    return session


def _sync_live_fields(session) -> None:
    st.session_state["live_mode_enabled"] = session.live_mode_enabled
    st.session_state["operation_mode"] = session.operation_mode
    st.session_state["playback_interval_seconds"] = session.playback_interval_seconds
    st.session_state["last_control_tick"] = session.last_control_tick
    st.session_state["next_control_tick"] = session.next_control_tick
    st.session_state["simulated_hours_completed"] = session.simulated_hours_completed
    st.session_state["maximum_simulated_hours"] = session.maximum_simulated_hours
    st.session_state["step_in_progress"] = session.step_in_progress
    st.session_state["run_identifier"] = session.run_identifier
    st.session_state["latest_status"] = session.latest_status
    st.session_state["latest_latency"] = dict(session.latest_latency)
    st.session_state["latest_error"] = session.last_error


def _run_due_fragment_tick() -> None:
    if "live_session" not in st.session_state:
        return
    resources = cached_resources()
    session = st.session_state["live_session"]
    before_timestamp = session.simulator.get_state().timestamp_local
    before_plan = session.plan_timestamp
    st.session_state["live_session"] = process_control_tick(session, resources)
    _sync_live_fields(st.session_state["live_session"])
    after = st.session_state["live_session"]
    if after.simulator.get_state().timestamp_local != before_timestamp or after.plan_timestamp != before_plan or after.last_error:
        st.rerun()


if hasattr(st, "fragment"):

    @st.fragment(run_every=1)
    def _live_fragment() -> None:
        _run_due_fragment_tick()

else:

    def _live_fragment() -> None:
        _run_due_fragment_tick()


if __name__ == "__main__":
    main()
