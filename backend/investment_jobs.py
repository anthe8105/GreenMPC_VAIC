"""Bounded in-memory investment-analysis job manager."""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from greenmpc.investment.analysis import CandidateInfrastructure, FinancialAssumptions, InvestmentAnalysisRequest, cache_identity, run_investment_analysis
from greenmpc.investment.config import InvestmentConfig, load_investment_config
from greenmpc.ui.state import PROJECT_ROOT, ControlRoomResources


@dataclass
class InvestmentJob:
    analysis_id: str
    request: InvestmentAnalysisRequest
    status: str = "queued"
    progress_percentage: float = 0.0
    current_phase: str = "Queued"
    completed_hours: int = 0
    requested_hours: int = 0
    created_at_monotonic: float = field(default_factory=time.perf_counter)
    started_at_monotonic: float | None = None
    finished_at_monotonic: float | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    cancel_requested: bool = False

    def to_status(self) -> dict[str, Any]:
        elapsed = (self.finished_at_monotonic or time.perf_counter()) - (self.started_at_monotonic or self.created_at_monotonic)
        eta = None
        if self.status == "running" and self.progress_percentage > 0:
            eta = elapsed * (100.0 - self.progress_percentage) / self.progress_percentage
        return {
            "analysis_id": self.analysis_id,
            "status": self.status,
            "progress_percentage": self.progress_percentage,
            "current_phase": self.current_phase,
            "completed_hours": self.completed_hours,
            "requested_hours": self.requested_hours,
            "elapsed_seconds": elapsed,
            "eta_seconds": eta,
            "error": self.error,
            "loaded_from_cache": bool((self.result or {}).get("loaded_from_cache")),
        }


class InvestmentJobManager:
    def __init__(self, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="greenmpc-investment")
        self._jobs: dict[str, InvestmentJob] = {}
        self._lock = threading.Lock()

    def submit(self, resources: ControlRoomResources, request: InvestmentAnalysisRequest, cfg: InvestmentConfig) -> InvestmentJob:
        identity = cache_identity(resources, request)
        analysis_id = f"inv_{identity['cache_fingerprint'][:16]}"
        with self._lock:
            existing = self._jobs.get(analysis_id)
            if existing and existing.status in {"queued", "running", "completed"}:
                return existing
            job = InvestmentJob(analysis_id=analysis_id, request=request, requested_hours=int(request.duration_hours))
            self._jobs[analysis_id] = job
        self._executor.submit(self._run, resources, cfg, job)
        return job

    def get(self, analysis_id: str) -> InvestmentJob:
        with self._lock:
            if analysis_id not in self._jobs:
                path = PROJECT_ROOT / "data/outputs/stage8_investment" / analysis_id / "manifest.json"
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    request = _request_from_manifest(data)
                    job = InvestmentJob(analysis_id=analysis_id, request=request, status="completed", progress_percentage=100.0, current_phase="Loaded persisted result", completed_hours=data.get("completed_hours", 0), requested_hours=data.get("duration_hours", 0), result=data)
                    self._jobs[analysis_id] = job
                else:
                    raise KeyError(analysis_id)
            return self._jobs[analysis_id]

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = [job.to_status() for job in self._jobs.values()]
        root = PROJECT_ROOT / "data/outputs/stage8_investment"
        if root.exists():
            known = {row["analysis_id"] for row in rows}
            for manifest in root.glob("inv_*/manifest.json"):
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if data.get("analysis_id") not in known and data.get("completed_successfully"):
                    rows.append(
                        {
                            "analysis_id": data["analysis_id"],
                            "status": "completed",
                            "progress_percentage": 100.0,
                            "current_phase": "Persisted result",
                            "completed_hours": data.get("completed_hours"),
                            "requested_hours": data.get("duration_hours"),
                            "elapsed_seconds": data.get("runtime_seconds"),
                            "eta_seconds": None,
                            "error": None,
                            "loaded_from_cache": True,
                        }
                    )
        return sorted(rows, key=lambda row: str(row["analysis_id"]))

    def cancel(self, analysis_id: str) -> InvestmentJob:
        job = self.get(analysis_id)
        job.cancel_requested = True
        if job.status == "queued":
            job.status = "cancelled"
            job.current_phase = "Cancelled"
            job.finished_at_monotonic = time.perf_counter()
        return job

    def _run(self, resources: ControlRoomResources, cfg: InvestmentConfig, job: InvestmentJob) -> None:
        job.status = "running"
        job.started_at_monotonic = time.perf_counter()

        def progress(phase: str, completed: int, total: int) -> None:
            if job.cancel_requested:
                raise RuntimeError("analysis cancelled")
            job.current_phase = phase
            job.completed_hours = min(int(completed), job.requested_hours)
            job.progress_percentage = 0.0 if total <= 0 else min(99.0, 100.0 * float(completed) / float(total))

        try:
            result = run_investment_analysis(resources, job.request, output_root=PROJECT_ROOT / cfg.outputs.output_directory, progress=progress)
            job.result = result
            job.status = "completed"
            job.progress_percentage = 100.0
            job.completed_hours = int(result["completed_hours"])
            job.current_phase = "Completed"
        except Exception as exc:
            # This runs on a background worker thread, so the FastAPI global
            # exception handler never sees it — log the traceback here or the
            # failure is invisible in the server logs.
            logging.getLogger(__name__).exception("investment analysis %s failed", job.analysis_id)
            job.error = str(exc)
            job.status = "cancelled" if job.cancel_requested else "failed"
            job.current_phase = "Cancelled" if job.cancel_requested else "Failed"
        finally:
            job.finished_at_monotonic = time.perf_counter()


def investment_defaults(resources: ControlRoomResources, cfg: InvestmentConfig) -> dict[str, Any]:
    from greenmpc.investment.analysis import baseline_infrastructure

    baseline = baseline_infrastructure(resources.project_config, cfg.defaults.terminal_inventory_valuation_vnd_per_kwh)
    financial = FinancialAssumptions(
        pv_capex_vnd_per_kwp=cfg.financial.pv_capex_vnd_per_kwp,
        bess_energy_capex_vnd_per_kwh=cfg.financial.bess_energy_capex_vnd_per_kwh,
        bess_power_capex_vnd_per_kw=cfg.financial.bess_power_capex_vnd_per_kw,
        fixed_implementation_cost_vnd=cfg.financial.fixed_implementation_cost_vnd,
        annual_pv_om_fraction=cfg.financial.annual_pv_om_fraction,
        annual_bess_om_fraction=cfg.financial.annual_bess_om_fraction,
        project_life_years=cfg.financial.project_life_years,
        annual_operating_days=cfg.financial.annual_operating_days,
        discount_rate=cfg.financial.discount_rate,
        assumptions_version=cfg.financial.assumptions_version,
    )
    proposal = CandidateInfrastructure(
        pv_capacity_kw=baseline.pv_capacity_kw * 1.2,
        battery_energy_capacity_kwh=baseline.battery_energy_capacity_kwh * 1.25,
        battery_power_kw=baseline.battery_power_kw * 1.2,
        minimum_soc_fraction=baseline.minimum_soc_fraction,
        initial_soc_fraction=baseline.initial_soc_fraction,
        dppa_available_kw=baseline.dppa_available_kw,
        dppa_price_vnd_per_kwh=baseline.dppa_price_vnd_per_kwh,
        dppa_availability_multiplier=1.0,
        renewable_target_fraction=baseline.renewable_target_fraction,
        transformer_capacity_kw=baseline.transformer_capacity_kw,
        terminal_inventory_valuation_vnd_per_kwh=baseline.terminal_inventory_valuation_vnd_per_kwh,
    )
    return {
        "baseline": asdict(baseline),
        "proposal": asdict(proposal),
        "financial": asdict(financial),
        "defaults": asdict(cfg.defaults),
        "durations": asdict(cfg.durations),
        "valuation_prices": cfg.financial.terminal_battery_valuation_prices_vnd_per_kwh,
        "disclosure": "Editable demonstration assumptions — not supplier quotations or investment advice.",
    }


def request_from_payload(payload: dict[str, Any]) -> InvestmentAnalysisRequest:
    return InvestmentAnalysisRequest(
        scenario_id=str(payload["scenario_id"]),
        controller_id=str(payload["controller_id"]),
        duration_hours=int(payload["duration_hours"]),
        candidate=CandidateInfrastructure(**payload["candidate"]),
        financial=FinancialAssumptions(**payload["financial"]),
        request_id=str(payload["request_id"]),
        start_timestamp=payload.get("start_timestamp"),
    )


def _request_from_manifest(data: dict[str, Any]) -> InvestmentAnalysisRequest:
    return InvestmentAnalysisRequest(
        scenario_id=str(data.get("scenario_id", "normal")),
        controller_id=str(data.get("controller_id", "deterministic_mpc")),
        duration_hours=int(data.get("duration_hours", 6)),
        candidate=CandidateInfrastructure(**data["proposal_configuration"]),
        financial=FinancialAssumptions(
            pv_capex_vnd_per_kwp=0,
            bess_energy_capex_vnd_per_kwh=0,
            bess_power_capex_vnd_per_kw=0,
            fixed_implementation_cost_vnd=0,
            annual_pv_om_fraction=0,
            annual_bess_om_fraction=0,
            project_life_years=1,
            annual_operating_days=1,
            discount_rate=0,
            assumptions_version="persisted",
        ),
        request_id="persisted",
    )


INVESTMENT_CONFIG = load_investment_config(PROJECT_ROOT / "configs/investment.yaml")
INVESTMENT_JOBS = InvestmentJobManager(max_workers=1)
