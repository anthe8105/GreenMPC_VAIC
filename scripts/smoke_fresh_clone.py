#!/usr/bin/env python
"""One-cycle fresh-clone smoke test for the React/FastAPI runtime adapter.

This script uses the in-process FastAPI test client. It does not launch a
server, train models, run benchmarks, or call historical stage verifiers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app


def iso_hour_plus_one(timestamp: str) -> str:
    return (datetime.fromisoformat(timestamp) + timedelta(hours=1)).isoformat()


def post_checked(client: TestClient, path: str, payload: dict) -> dict:
    response = client.post(path, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"{path} failed with {response.status_code}: {response.text}")
    return response.json()


def main() -> int:
    client = TestClient(app)
    health = client.get("/api/v1/health")
    if health.status_code != 200:
        raise RuntimeError(f"health failed: {health.status_code} {health.text}")

    created = post_checked(
        client,
        "/api/v1/sessions",
        {"scenario_id": "normal", "controller_id": "deterministic_mpc"},
    )
    session_id = created["session_id"]
    run_id = created["run_id"]
    timestamp = created["state"]["timestamp"]

    envelope = lambda: {"request_id": uuid4().hex, "run_id": run_id, "expected_timestamp": timestamp}
    forecast = post_checked(client, f"/api/v1/sessions/{session_id}/forecast", envelope())
    if not forecast.get("forecast", {}).get("aggregate"):
        raise RuntimeError("forecast aggregate is empty")

    plan_payload = envelope() | {"controller_id": "deterministic_mpc", "generate_forecast_if_missing": False}
    plan = post_checked(client, f"/api/v1/sessions/{session_id}/plan", plan_payload)
    if not plan.get("plan", {}).get("valid_for_execution"):
        raise RuntimeError(f"plan is not valid for execution: {plan.get('plan')}")

    executed = post_checked(client, f"/api/v1/sessions/{session_id}/execute", envelope())
    new_timestamp = executed["state"]["timestamp"]
    if new_timestamp != iso_hour_plus_one(timestamp):
        raise RuntimeError(f"timestamp did not advance exactly one hour: {timestamp} -> {new_timestamp}")
    if len(executed["history"]) != 1:
        raise RuntimeError(f"expected one executed history row, got {len(executed['history'])}")

    duplicate = client.post(f"/api/v1/sessions/{session_id}/execute", json=envelope())
    if duplicate.status_code != 409:
        raise RuntimeError(f"stale/duplicate execute was not rejected: {duplicate.status_code} {duplicate.text}")

    benchmark = client.get("/api/v1/benchmark?valuation_price_vnd_per_kwh=1500")
    if benchmark.status_code != 200 or not benchmark.json().get("rows"):
        raise RuntimeError(f"benchmark view failed: {benchmark.status_code} {benchmark.text}")

    provenance = client.get("/api/v1/provenance")
    if provenance.status_code != 200 or not provenance.json().get("data"):
        raise RuntimeError(f"provenance view failed: {provenance.status_code} {provenance.text}")

    print("Fresh-clone smoke PASS")
    print(f"session_id={session_id}")
    print(f"started={timestamp}")
    print(f"advanced={new_timestamp}")
    print(f"completed_at={datetime.now(UTC).isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
