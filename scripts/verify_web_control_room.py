"""Bounded verification for the React/FastAPI command-center adapter.

This verifier intentionally does not call Stage 6/Stage 7 verifiers, run
benchmarks, retrain models, or launch a persistent web server.
"""

from __future__ import annotations

import sys
import re
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    client = TestClient(app)

    try:
        health = client.get("/api/v1/health")
        checks.append(("health endpoint", health.status_code == 200, health.text))

        session = client.post("/api/v1/sessions", json={"scenario_id": "normal", "controller_id": "deterministic_mpc"})
        checks.append(("session create", session.status_code == 200, session.text))
        body = session.json()
        sid = body["session_id"]
        run_id = body["run_id"]
        timestamp = body["state"]["timestamp"]

        state = client.get(f"/api/v1/sessions/{sid}/state")
        checks.append(("initial state read", state.status_code == 200, state.text))

        forecast = client.post(
            f"/api/v1/sessions/{sid}/forecast",
            json=_envelope(run_id, timestamp, "verify-forecast"),
        )
        checks.append(("six-hour forecast", forecast.status_code == 200 and bool(forecast.json()["forecast"]["aggregate"]), forecast.text))

        plan = client.post(
            f"/api/v1/sessions/{sid}/plan",
            json={**_envelope(run_id, timestamp, "verify-plan"), "controller_id": "deterministic_mpc"},
        )
        plan_body = plan.json() if plan.status_code == 200 else {}
        checks.append(("deterministic MPC plan", plan.status_code == 200 and plan_body["plan"]["valid_for_execution"], plan.text))
        checks.append(("fallback fields serialized", "fallback_active" in plan_body and "fallback_reason" in plan_body, str(plan_body)))

        execute = client.post(
            f"/api/v1/sessions/{sid}/execute",
            json=_envelope(run_id, timestamp, "verify-execute"),
        )
        execute_body = execute.json() if execute.status_code == 200 else {}
        advanced = execute.status_code == 200 and execute_body["state"]["timestamp"] != timestamp
        checks.append(("one-hour execution", advanced, execute.text))

        duplicate = client.post(
            f"/api/v1/sessions/{sid}/execute",
            json=_envelope(run_id, timestamp, "verify-execute-duplicate"),
        )
        checks.append(("duplicate stale execute rejected", duplicate.status_code == 409, duplicate.text))

        shadow_session = client.post("/api/v1/sessions", json={"scenario_id": "normal", "controller_id": "deterministic_mpc"}).json()
        shadow_timestamp = shadow_session["state"]["timestamp"]
        shadow = client.post(
            f"/api/v1/sessions/{shadow_session['session_id']}/control-cycle",
            json={
                **_envelope(shadow_session["run_id"], shadow_timestamp, "verify-shadow"),
                "operation_mode": "shadow",
                "controller_id": "deterministic_mpc",
            },
        )
        checks.append(("shadow cycle does not advance", shadow.status_code == 200 and shadow.json()["state"]["timestamp"] == shadow_timestamp, shadow.text))

        benchmark = client.get("/api/v1/benchmark?valuation_price_vnd_per_kwh=1500")
        checks.append(("benchmark read only", benchmark.status_code == 200 and bool(benchmark.json()["rows"]), benchmark.text))

        provenance = client.get("/api/v1/provenance")
        pdata = provenance.json().get("data", {}) if provenance.status_code == 200 else {}
        checks.append(("provenance disclosures", provenance.status_code == 200 and any("No actual VRG" in item for item in pdata.get("disclosures", [])), provenance.text))

        frontend_index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
        checks.append(("compiled frontend assets", frontend_index.exists(), str(frontend_index)))

        checks.append(("no stage8/wastewater web surface", _no_forbidden_terms(), "backend/frontend scan"))
    except Exception as exc:
        checks.append(("unexpected verifier exception", False, str(exc)))

    _print_table(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


def _envelope(run_id: str, timestamp: str, request_id: str) -> dict[str, str]:
    return {"run_id": run_id, "expected_timestamp": timestamp, "request_id": request_id}


def _no_forbidden_terms() -> bool:
    forbidden = (
        re.compile(r"wastewater", re.IGNORECASE),
        re.compile(r"effluent", re.IGNORECASE),
        re.compile(r"\bcod\b", re.IGNORECASE),
        re.compile(r"\bbod\b", re.IGNORECASE),
        re.compile(r"aeration", re.IGNORECASE),
        re.compile(r"investment lab", re.IGNORECASE),
        re.compile(r"stage 8", re.IGNORECASE),
    )
    files = list((PROJECT_ROOT / "backend").rglob("*.py")) + [
        path for path in (PROJECT_ROOT / "frontend" / "src").rglob("*.*") if ".test." not in path.name
    ]
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in forbidden):
            return False
    return True


def _print_table(checks: list[tuple[str, bool, str]]) -> None:
    width = max(len(name) for name, _, _ in checks)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        suffix = "" if ok else f" :: {detail[:220]}"
        print(f"{name:<{width}}  {status}{suffix}")


if __name__ == "__main__":
    raise SystemExit(main())
