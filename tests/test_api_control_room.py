from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def _create_session(controller: str = "deterministic_mpc"):
    response = client.post("/api/v1/sessions", json={"scenario_id": "normal", "controller_id": controller})
    assert response.status_code == 200, response.text
    return response.json()


def _envelope(session: dict, request_id: str):
    return {
        "request_id": request_id,
        "run_id": session["run_id"],
        "expected_timestamp": session["state"]["timestamp"],
    }


def test_api_session_initialization_and_state():
    session = _create_session()
    assert session["session_id"]
    assert session["run_id"]
    assert session["state"]["status"] == "Paused"
    state = client.get(f"/api/v1/sessions/{session['session_id']}/state")
    assert state.status_code == 200
    assert state.json()["state"]["timestamp"] == session["state"]["timestamp"]


def test_api_forecast_and_plan_do_not_execute():
    session = _create_session()
    sid = session["session_id"]
    forecast = client.post(f"/api/v1/sessions/{sid}/forecast", json=_envelope(session, "forecast-1"))
    assert forecast.status_code == 200, forecast.text
    assert forecast.json()["forecast"]["aggregate"]
    plan = client.post(f"/api/v1/sessions/{sid}/plan", json={**_envelope(session, "plan-1"), "controller_id": "deterministic_mpc"})
    assert plan.status_code == 200, plan.text
    assert plan.json()["plan"]["valid_for_execution"] is True
    state = client.get(f"/api/v1/sessions/{sid}/state").json()["state"]
    assert state["timestamp"] == session["state"]["timestamp"]


def test_api_execute_advances_one_hour_and_rejects_duplicate_request_id():
    session = _create_session()
    sid = session["session_id"]
    client.post(f"/api/v1/sessions/{sid}/plan", json={**_envelope(session, "plan-2"), "controller_id": "deterministic_mpc"})
    execute = client.post(f"/api/v1/sessions/{sid}/execute", json=_envelope(session, "execute-1"))
    assert execute.status_code == 200, execute.text
    next_state = execute.json()["state"]
    assert next_state["timestamp"] != session["state"]["timestamp"]
    duplicate = client.post(f"/api/v1/sessions/{sid}/execute", json=_envelope(session, "execute-1"))
    assert duplicate.status_code == 200
    assert duplicate.json()["state"]["timestamp"] == next_state["timestamp"]


def test_api_stale_expected_timestamp_rejected():
    session = _create_session()
    sid = session["session_id"]
    payload = _envelope(session, "stale-1")
    payload["expected_timestamp"] = "2013-01-01T00:00:00+07:00"
    response = client.post(f"/api/v1/sessions/{sid}/forecast", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TIMESTAMP_MISMATCH"


def test_api_reset_invalidates_old_run_id():
    session = _create_session()
    sid = session["session_id"]
    reset = client.post(f"/api/v1/sessions/{sid}/reset", json={"scenario_id": "normal", "controller_id": "rule_based", "run_id": session["run_id"]})
    assert reset.status_code == 200
    assert reset.json()["run_id"] != session["run_id"]
    old_payload = _envelope(session, "old-run")
    response = client.post(f"/api/v1/sessions/{sid}/forecast", json=old_payload)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RUN_ID_MISMATCH"


def test_api_auto_control_cycle_advances_and_shadow_does_not():
    auto = _create_session("rule_based")
    sid = auto["session_id"]
    response = client.post(f"/api/v1/sessions/{sid}/control-cycle", json={**_envelope(auto, "auto-1"), "operation_mode": "auto", "controller_id": "rule_based"})
    assert response.status_code == 200, response.text
    assert response.json()["state"]["timestamp"] != auto["state"]["timestamp"]

    shadow = _create_session("rule_based")
    shadow_response = client.post(
        f"/api/v1/sessions/{shadow['session_id']}/control-cycle",
        json={**_envelope(shadow, "shadow-1"), "operation_mode": "shadow", "controller_id": "rule_based"},
    )
    assert shadow_response.status_code == 200, shadow_response.text
    assert shadow_response.json()["state"]["timestamp"] == shadow["state"]["timestamp"]
    assert shadow_response.json()["action"]


def test_api_benchmark_and_provenance_are_read_only():
    benchmark = client.get("/api/v1/benchmark?valuation_price_vnd_per_kwh=1500")
    assert benchmark.status_code == 200
    assert benchmark.json()["rows"]
    provenance = client.get("/api/v1/provenance")
    assert provenance.status_code == 200
    disclosures = provenance.json()["data"]["disclosures"]
    assert any("No actual VRG" in item for item in disclosures)
