from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from greenmpc.simulation.events import RuntimeEvent, apply_events, validate_event
from greenmpc.simulation.exceptions import EventValidationError
from tests._simulation_helpers import TENANTS, state


def event(event_type: str, s, **kwargs) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=f"E-{event_type}",
        event_type=event_type,
        event_name=event_type,
        start_timestamp_local=s.timestamp_local,
        end_timestamp_local=s.timestamp_local + timedelta(hours=2),
        duration_hours=2,
        affected_tenant_id=kwargs.get("affected_tenant_id"),
        load_multiplier=kwargs.get("load_multiplier", 1.0),
        pv_multiplier=kwargs.get("pv_multiplier", 1.0),
        dppa_multiplier=kwargs.get("dppa_multiplier", 1.0),
        description="test",
    )


def test_cloud_event_changes_effective_pv_only(sim_config) -> None:
    s = state()
    exo, record = apply_events(s.exogenous, [event("cloud_event", s, pv_multiplier=0.5)], TENANTS)
    assert exo.effective_pv_available_kw == s.exogenous.baseline_pv_available_kw * 0.5
    assert s.exogenous.baseline_pv_available_kw == 150.0
    assert record is not None


def test_tenant_production_event_affects_one_tenant() -> None:
    s = state()
    exo, _ = apply_events(s.exogenous, [event("production_shift_event", s, affected_tenant_id=TENANTS[0], load_multiplier=1.25)], TENANTS)
    assert exo.effective_tenant_load_kw[TENANTS[0]] == 125.0
    assert exo.effective_tenant_load_kw[TENANTS[1]] == 100.0


def test_high_load_and_combined_events_are_multiplicative() -> None:
    s = state()
    exo, _ = apply_events(s.exogenous, [event("high_load_event", s, load_multiplier=1.2), event("combined_stress_event", s, load_multiplier=1.1, pv_multiplier=0.5, dppa_multiplier=0.8)], TENANTS)
    assert round(exo.effective_tenant_load_kw[TENANTS[0]], 6) == 132.0
    assert exo.effective_pv_available_kw == 75.0
    assert exo.dppa_available_kw == 400.0


def test_invalid_tenant_event_fails(sim_config) -> None:
    s = state()
    with pytest.raises(EventValidationError):
        validate_event(event("production_shift_event", s, affected_tenant_id="Bad"), TENANTS, sim_config)


def test_past_event_injection_fails(sim_config) -> None:
    s = state()
    with pytest.raises(EventValidationError):
        validate_event(replace(event("cloud_event", s), start_timestamp_local=s.timestamp_local - timedelta(hours=1)), TENANTS, sim_config, s.timestamp_local)
