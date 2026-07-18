from __future__ import annotations

import hashlib
import json
import time
import uuid
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from greenmpc.investment.analysis import (
    CandidateInfrastructure,
    FinancialAssumptions,
    InvestmentAnalysisRequest,
    _financial_metrics,
    scale_park_for_candidate,
    validate_candidate,
)
from greenmpc.investment.config import load_investment_config


def test_investment_defaults_load_from_configuration():
    cfg = load_investment_config("configs/investment.yaml")
    client = TestClient(app)
    response = client.get("/api/v1/investment/defaults")
    assert response.status_code == 200
    data = response.json()
    assert data["defaults"]["duration_hours"] == cfg.defaults.duration_hours
    assert data["baseline"]["pv_capacity_kw"] > 0
    assert data["proposal"]["pv_capacity_kw"] != data["baseline"]["pv_capacity_kw"]


def test_invalid_physical_inputs_are_rejected():
    candidate = _candidate()
    with pytest.raises(ValueError, match="pv_capacity_kw"):
        validate_candidate(CandidateInfrastructure(**{**candidate.__dict__, "pv_capacity_kw": -1.0}))
    with pytest.raises(ValueError, match="initial_soc_fraction"):
        validate_candidate(CandidateInfrastructure(**{**candidate.__dict__, "minimum_soc_fraction": 0.8, "initial_soc_fraction": 0.2}))


def test_pv_capacity_scaling_is_consistent_and_non_mutating():
    park = pd.DataFrame(
        {
            "pv_available_kw": [0.0, 500.0, 2000.0],
            "pv_available_kwh": [0.0, 500.0, 2000.0],
            "installed_pv_capacity_kw": [2500.0, 2500.0, 2500.0],
            "pv_clipped_to_capacity": [False, False, False],
            "dppa_available_kw": [1500.0, 1500.0, 1500.0],
            "dppa_price_vnd_per_kwh": [1750.0, 1750.0, 1750.0],
            "transformer_capacity_kw": [5200.0, 5200.0, 5200.0],
        }
    )
    candidate = CandidateInfrastructure(**{**_candidate().__dict__, "pv_capacity_kw": 5000.0, "dppa_available_kw": 1200.0, "dppa_price_vnd_per_kwh": 1600.0})
    scaled = scale_park_for_candidate(park, 2500.0, candidate)
    assert scaled["pv_available_kw"].tolist() == [0.0, 1000.0, 4000.0]
    assert scaled["installed_pv_capacity_kw"].eq(5000.0).all()
    assert scaled["dppa_available_kw"].eq(1200.0).all()
    assert park["pv_available_kw"].tolist() == [0.0, 500.0, 2000.0]


def test_financial_metrics_and_payback_policy():
    baseline = _candidate()
    proposal = CandidateInfrastructure(**{**baseline.__dict__, "pv_capacity_kw": baseline.pv_capacity_kw * 1.2})
    financial = _financial()
    metrics = _financial_metrics(
        baseline,
        proposal,
        {"inventory_adjusted_operating_cost_vnd": 1000.0},
        {"inventory_adjusted_operating_cost_vnd": 900.0},
        financial,
        10,
    )
    assert metrics["period_operating_savings_vnd"] == 100.0
    assert metrics["annualized_operating_savings_vnd"] == 100.0 * financial.annual_operating_days * 24 / 10
    no_savings = _financial_metrics(
        baseline,
        proposal,
        {"inventory_adjusted_operating_cost_vnd": 900.0},
        {"inventory_adjusted_operating_cost_vnd": 1000.0},
        financial,
        10,
    )
    assert no_savings["simple_payback_years"] is None


def test_six_hour_candidate_smoke_completes_and_export_checksums_pass():
    client = TestClient(app)
    defaults = client.get("/api/v1/investment/defaults").json()
    payload = {
        "scenario_id": "normal",
        "controller_id": "deterministic_mpc",
        "duration_hours": 6,
        "candidate": defaults["proposal"],
        "financial": defaults["financial"],
        "request_id": str(uuid.uuid4()),
    }
    created = client.post("/api/v1/investment/analyses", json=payload)
    assert created.status_code == 200
    analysis_id = created.json()["analysis_id"]
    status = _wait_for_job(client, analysis_id)
    assert status["status"] == "completed", status
    result = client.get(f"/api/v1/investment/analyses/{analysis_id}/result").json()
    assert result["completed_hours"] == 6
    assert result["technical_metrics"]["baseline"]["completed_steps"] == 6
    assert result["technical_metrics"]["proposal"]["completed_steps"] == 6
    assert result["technical_metrics"]["proposal"]["total_load_served_kwh"] > 0
    assert result["tenant_summary"]
    _assert_zip_checksums(Path(result["evidence_zip_path"]))


def _wait_for_job(client: TestClient, analysis_id: str) -> dict:
    for _ in range(90):
        status = client.get(f"/api/v1/investment/analyses/{analysis_id}").json()
        if status["status"] in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(1)
    raise AssertionError("investment job did not finish")


def _assert_zip_checksums(relative_path: Path) -> None:
    zip_path = Path.cwd() / relative_path
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        for name, expected in manifest["checksums"].items():
            actual = hashlib.sha256(archive.read(name)).hexdigest()
            assert actual == expected


def _candidate() -> CandidateInfrastructure:
    return CandidateInfrastructure(
        pv_capacity_kw=3000.0,
        battery_energy_capacity_kwh=3500.0,
        battery_power_kw=1200.0,
        minimum_soc_fraction=0.1,
        initial_soc_fraction=0.5,
        dppa_available_kw=1500.0,
        dppa_price_vnd_per_kwh=1750.0,
        dppa_availability_multiplier=1.0,
        renewable_target_fraction=0.55,
        transformer_capacity_kw=5200.0,
        terminal_inventory_valuation_vnd_per_kwh=2000.0,
    )


def _financial() -> FinancialAssumptions:
    return FinancialAssumptions(
        pv_capex_vnd_per_kwp=1000.0,
        bess_energy_capex_vnd_per_kwh=1000.0,
        bess_power_capex_vnd_per_kw=1000.0,
        fixed_implementation_cost_vnd=0.0,
        annual_pv_om_fraction=0.0,
        annual_bess_om_fraction=0.0,
        project_life_years=10,
        annual_operating_days=300,
        discount_rate=0.1,
        assumptions_version="test",
    )
