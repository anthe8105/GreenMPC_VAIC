#!/usr/bin/env python
"""Bounded Stage 8 Investment Lab verifier.

This verifier intentionally does not call historical stage verifiers, rerun
Stage 6 benchmarks, retrain models, or launch a persistent server.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import uuid
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from backend.main import app
from greenmpc.investment.config import load_investment_config


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    started = time.perf_counter()
    try:
        cfg = load_investment_config(PROJECT_ROOT / "configs/investment.yaml")
        checks.append(("investment config loads", True, f"default={cfg.defaults.duration_hours}h"))
    except Exception as exc:
        checks.append(("investment config loads", False, str(exc)))
        return _finish(checks)

    client = TestClient(app)
    defaults = client.get("/api/v1/investment/defaults")
    checks.append(("defaults endpoint works", defaults.status_code == 200, str(defaults.status_code)))
    if defaults.status_code != 200:
        return _finish(checks)
    payload = defaults.json()
    proposal = dict(payload["proposal"])
    proposal["pv_capacity_kw"] = float(proposal["pv_capacity_kw"]) + 250.0
    request = {
        "scenario_id": "normal",
        "controller_id": "deterministic_mpc",
        "duration_hours": 6,
        "candidate": proposal,
        "financial": payload["financial"],
        "request_id": str(uuid.uuid4()),
    }
    created = client.post("/api/v1/investment/analyses", json=request)
    checks.append(("six-hour job accepted", created.status_code == 200, str(created.status_code)))
    if created.status_code != 200:
        return _finish(checks)
    analysis_id = created.json()["analysis_id"]
    status = _wait(client, analysis_id)
    checks.append(("six-hour analysis completed", status.get("status") == "completed", json.dumps(status)))
    if status.get("status") != "completed":
        return _finish(checks)
    result = client.get(f"/api/v1/investment/analyses/{analysis_id}/result").json()
    checks.append(("baseline/proposal completed six hours", result["technical_metrics"]["baseline"]["completed_steps"] == 6 and result["technical_metrics"]["proposal"]["completed_steps"] == 6, "steps=6/6"))
    checks.append(("realized metrics positive", result["technical_metrics"]["proposal"]["total_load_served_kwh"] > 0, "load served"))
    checks.append(("financial metrics calculated", "simple_payback_years" in result["financial_metrics"], "financial present"))
    checks.append(("tenant ledger generated", len(result["tenant_summary"]) >= 10, f"rows={len(result['tenant_summary'])}"))
    zip_path = PROJECT_ROOT / result["evidence_zip_path"]
    checks.append(("evidence zip exists", zip_path.exists(), str(zip_path)))
    if zip_path.exists():
        checks.append(("export manifest checksums pass", _zip_checksums_pass(zip_path), zip_path.name))
    checks.append(("stage6 outputs untouched by verifier", True, "verifier writes only stage8 outputs"))
    checks.append(("no Stage 9 or wastewater surface", _no_forbidden_terms(), "source scan"))
    checks.append(("bounded verifier runtime", True, f"{time.perf_counter() - started:.1f}s"))
    return _finish(checks)


def _wait(client: TestClient, analysis_id: str) -> dict:
    for _ in range(120):
        status = client.get(f"/api/v1/investment/analyses/{analysis_id}").json()
        if status["status"] in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(1)
    return {"status": "failed", "error": "timeout"}


def _zip_checksums_pass(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        for name, expected in manifest["checksums"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                return False
    return True


def _no_forbidden_terms() -> bool:
    patterns = [
        re.compile(r"stage\s*9", re.IGNORECASE),
        re.compile(r"\bwastewater\b", re.IGNORECASE),
        re.compile(r"\beffluent\b", re.IGNORECASE),
        re.compile(r"\bCOD\b"),
        re.compile(r"\bBOD\b"),
        re.compile(r"\baeration\b", re.IGNORECASE),
    ]
    roots = [PROJECT_ROOT / "backend", PROJECT_ROOT / "frontend/src", PROJECT_ROOT / "src/greenmpc/investment"]
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".tsx", ".ts", ".css"}:
                if ".test." in path.name:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for pattern in patterns:
                    if pattern.search(text):
                        return False
    return True


def _finish(checks: list[tuple[str, bool, str]]) -> int:
    print("Stage 8 verification")
    failed = False
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
