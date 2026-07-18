"""Investment Scenario Lab analysis engine.

This module is an adapter over the approved simulator, forecasting, rule-based,
and MPC controller layers. It does not mutate global configuration, Stage 6
benchmark outputs, or trained forecasting artifacts.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import zipfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.config import BatteryConfig, DPPAConfig, GreenMPCConfig, GridConfig, SolarConfig, TenantConfig
from greenmpc.control import GreenMPCController, MPCMode
from greenmpc.evaluation.history_adapter import ObservedHistoryAdapter
from greenmpc.evaluation.metrics import controller_metrics, terminal_inventory_adjustment
from greenmpc.evaluation.rule_based import build_rule_based_action
from greenmpc.evaluation.scenarios import build_scenarios
from greenmpc.forecasting.training import current_fingerprints
from greenmpc.simulation.park import IndustrialParkSimulator, _prepare_park_frame
from greenmpc.simulation.state import BatteryState


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_SOFTWARE_VERSION = "stage8_investment_v1"


@dataclass(frozen=True)
class CandidateInfrastructure:
    pv_capacity_kw: float
    battery_energy_capacity_kwh: float
    battery_power_kw: float
    minimum_soc_fraction: float
    initial_soc_fraction: float
    dppa_available_kw: float
    dppa_price_vnd_per_kwh: float
    dppa_availability_multiplier: float
    renewable_target_fraction: float
    transformer_capacity_kw: float
    terminal_inventory_valuation_vnd_per_kwh: float


@dataclass(frozen=True)
class FinancialAssumptions:
    pv_capex_vnd_per_kwp: float
    bess_energy_capex_vnd_per_kwh: float
    bess_power_capex_vnd_per_kw: float
    fixed_implementation_cost_vnd: float
    annual_pv_om_fraction: float
    annual_bess_om_fraction: float
    project_life_years: int
    annual_operating_days: int
    discount_rate: float
    assumptions_version: str


@dataclass(frozen=True)
class InvestmentAnalysisRequest:
    scenario_id: str
    controller_id: str
    duration_hours: int
    candidate: CandidateInfrastructure
    financial: FinancialAssumptions
    request_id: str
    start_timestamp: str | None = None


ProgressCallback = Callable[[str, int, int], None]


def baseline_infrastructure(config: GreenMPCConfig, valuation_price: float = 2000.0) -> CandidateInfrastructure:
    """Return immutable baseline infrastructure values from approved config."""

    return CandidateInfrastructure(
        pv_capacity_kw=float(config.solar.installed_capacity_kw),
        battery_energy_capacity_kwh=float(config.battery.energy_capacity_kwh),
        battery_power_kw=float(config.battery.max_discharge_power_kw),
        minimum_soc_fraction=float(config.battery.minimum_soc_fraction),
        initial_soc_fraction=float(config.battery.initial_soc_fraction),
        dppa_available_kw=float(config.dppa.available_capacity_kw),
        dppa_price_vnd_per_kwh=float(config.dppa.base_price_vnd_per_kwh),
        dppa_availability_multiplier=1.0,
        renewable_target_fraction=float(max(tenant.renewable_target_fraction for tenant in config.tenants)),
        transformer_capacity_kw=float(config.grid.transformer_capacity_kw),
        terminal_inventory_valuation_vnd_per_kwh=float(valuation_price),
    )


def validate_candidate(candidate: CandidateInfrastructure) -> None:
    """Reject invalid physical or financial candidate inputs before simulation."""

    positive = {
        "pv_capacity_kw": candidate.pv_capacity_kw,
        "battery_energy_capacity_kwh": candidate.battery_energy_capacity_kwh,
        "battery_power_kw": candidate.battery_power_kw,
        "dppa_available_kw": candidate.dppa_available_kw,
        "transformer_capacity_kw": candidate.transformer_capacity_kw,
        "terminal_inventory_valuation_vnd_per_kwh": candidate.terminal_inventory_valuation_vnd_per_kwh,
    }
    for field, value in positive.items():
        if float(value) <= 0:
            raise ValueError(f"{field} must be positive")
    if candidate.dppa_price_vnd_per_kwh < 0:
        raise ValueError("dppa_price_vnd_per_kwh must be nonnegative")
    if not 0 <= candidate.minimum_soc_fraction < 1:
        raise ValueError("minimum_soc_fraction must be between zero and one")
    if not candidate.minimum_soc_fraction <= candidate.initial_soc_fraction <= 0.95:
        raise ValueError("initial_soc_fraction must be at least minimum_soc_fraction and no more than 0.95")
    if not 0 <= candidate.dppa_availability_multiplier <= 2.0:
        raise ValueError("dppa_availability_multiplier must be between 0 and 2")
    if not 0 <= candidate.renewable_target_fraction <= 1:
        raise ValueError("renewable_target_fraction must be between 0 and 1")


def cache_identity(resources: Any, request: InvestmentAnalysisRequest) -> dict[str, Any]:
    """Build exact identity for Stage 8 result reuse."""

    payload = {
        "software_version": ANALYSIS_SOFTWARE_VERSION,
        "dataset_fingerprints": current_fingerprints(),
        "model_registry_fingerprint": _object_hash(resources.model_manifest),
        "controller_version": "stage5_greenmpc_v1",
        "simulator_version": "stage3_digital_twin",
        "scenario": request.scenario_id,
        "controller": request.controller_id,
        "start_timestamp": request.start_timestamp or resources.evaluation_config.start_timestamp,
        "duration": request.duration_hours,
        "candidate": asdict(request.candidate),
        "financial_assumption_version": request.financial.assumptions_version,
        "financial": asdict(request.financial),
    }
    return {**payload, "cache_fingerprint": _object_hash(payload)}


def run_investment_analysis(
    resources: Any,
    request: InvestmentAnalysisRequest,
    *,
    output_root: Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run baseline and proposal closed-loop analyses and persist evidence."""

    validate_candidate(request.candidate)
    if request.duration_hours not in {6, 24, 72}:
        raise ValueError("duration_hours must be 6, 24, or 72")
    if request.controller_id not in {"rule_based", "deterministic_mpc", "greenmpc_conservative"}:
        raise ValueError("controller_id is unsupported")
    if request.scenario_id not in resources.evaluation_config.scenarios:
        raise ValueError("scenario_id is unsupported")

    started = time.perf_counter()
    output_root = output_root or PROJECT_ROOT / "data/outputs/stage8_investment"
    output_root.mkdir(parents=True, exist_ok=True)
    cache = cache_identity(resources, request)
    analysis_id = f"inv_{cache['cache_fingerprint'][:16]}"
    analysis_dir = output_root / analysis_id
    manifest_path = analysis_dir / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("completed_successfully") and existing.get("cache_fingerprint") == cache["cache_fingerprint"]:
            return {**existing, "loaded_from_cache": True}

    if progress:
        progress("Validating configuration", 0, request.duration_hours * 2)
    baseline_candidate = baseline_infrastructure(
        resources.project_config,
        request.candidate.terminal_inventory_valuation_vnd_per_kwh,
    )
    start_timestamp = request.start_timestamp or resources.evaluation_config.start_timestamp

    if progress:
        progress("Running baseline digital twin", 0, request.duration_hours * 2)
    baseline = _run_case(resources, request, baseline_candidate, "baseline", start_timestamp, progress, 0)
    if progress:
        progress("Running proposal digital twin", request.duration_hours, request.duration_hours * 2)
    proposal = _run_case(resources, request, request.candidate, "proposal", start_timestamp, progress, request.duration_hours)

    if progress:
        progress("Calculating financial metrics", request.duration_hours * 2, request.duration_hours * 2)
    financial = _financial_metrics(baseline_candidate, request.candidate, baseline["technical_metrics"], proposal["technical_metrics"], request.financial, request.duration_hours)
    technical_comparison = _comparison_rows(baseline["technical_metrics"], proposal["technical_metrics"])
    tenant_summary = _tenant_summary(baseline["tenant_ledger"], proposal["tenant_ledger"])
    evidence_zip = _write_evidence_package(
        analysis_dir,
        analysis_id,
        request,
        baseline_candidate,
        baseline,
        proposal,
        technical_comparison,
        financial,
        tenant_summary,
        cache,
        resources,
    )
    result = {
        "analysis_id": analysis_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario_id": request.scenario_id,
        "controller_id": request.controller_id,
        "duration_hours": request.duration_hours,
        "completed_successfully": True,
        "completed_hours": request.duration_hours,
        "baseline_configuration": asdict(baseline_candidate),
        "proposal_configuration": asdict(request.candidate),
        "technical_metrics": {"baseline": baseline["technical_metrics"], "proposal": proposal["technical_metrics"], "comparison": technical_comparison},
        "financial_metrics": financial,
        "tenant_summary": tenant_summary,
        "evidence_zip_path": str(evidence_zip.relative_to(PROJECT_ROOT)),
        "cache_fingerprint": cache["cache_fingerprint"],
        "loaded_from_cache": False,
        "runtime_seconds": time.perf_counter() - started,
        "assumptions": [
            "Capacity-scaling approximation using the same weather resource profile.",
            "Financial values are editable demonstration assumptions, not supplier quotations or investment advice.",
            "Tenant evidence is scenario-based and not an official renewable certificate or legal DPPA settlement.",
        ],
    }
    result["result_checksum"] = _object_hash(result)
    _atomic_write_json(manifest_path, result)
    return result


def scale_park_for_candidate(park: pd.DataFrame, baseline_capacity_kw: float, candidate: CandidateInfrastructure) -> pd.DataFrame:
    """Scale PV capacity and candidate DPPA/transformer fields without mutating input."""

    frame = park.copy(deep=True)
    ratio = float(candidate.pv_capacity_kw) / float(baseline_capacity_kw)
    cap = float(candidate.pv_capacity_kw)
    for col in ("pv_available_kw", "pv_available_kwh"):
        frame[col] = (frame[col].astype(float) * ratio).clip(lower=0.0, upper=cap)
    if "installed_pv_capacity_kw" in frame.columns:
        frame["installed_pv_capacity_kw"] = cap
    if "pv_clipped_to_capacity" in frame.columns:
        frame["pv_clipped_to_capacity"] = frame["pv_available_kw"] >= cap - 1e-6
    frame["dppa_available_kw"] = float(candidate.dppa_available_kw) * float(candidate.dppa_availability_multiplier)
    frame["dppa_price_vnd_per_kwh"] = float(candidate.dppa_price_vnd_per_kwh)
    frame["transformer_capacity_kw"] = float(candidate.transformer_capacity_kw)
    return frame


def _run_case(
    resources: Any,
    request: InvestmentAnalysisRequest,
    candidate: CandidateInfrastructure,
    label: str,
    start_timestamp: str,
    progress: ProgressCallback | None,
    completed_offset: int,
) -> dict[str, Any]:
    run_config = _config_with_candidate(resources.project_config, candidate)
    park = scale_park_for_candidate(resources.park_hourly, resources.project_config.solar.installed_capacity_kw, candidate)
    sim = _candidate_simulator(resources, run_config, park, start_timestamp, request.scenario_id)
    controller = GreenMPCController(run_config, resources.mpc_config)
    adapter = ObservedHistoryAdapter(resources.tenant_hourly, park, tuple(sim.tenant_ids))
    runtime = {"forecast_time_seconds": 0.0, "planning_time_seconds": 0.0, "validation_time_seconds": 0.0, "step_time_seconds": 0.0, "fallback_reasons": []}
    fallback_count = 0

    for step in range(request.duration_hours):
        origin = pd.Timestamp(sim.get_state().timestamp_local)
        effective = sim.get_effective_exogenous()
        adapter.record_observation(effective)
        tenant_hist, park_hist, audit = adapter.histories_through(origin)
        if audit.get("future_observations_used"):
            raise RuntimeError("investment analysis attempted to use future observations")
        t0 = time.perf_counter()
        load_forecast, solar_forecast = resources.forecast_service.forecast_all(tenant_hist, park_hist, origin, 6)
        runtime["forecast_time_seconds"] += time.perf_counter() - t0
        p0 = time.perf_counter()
        if request.controller_id == "rule_based":
            action = build_rule_based_action(sim.get_state(), run_config, action_id=f"INV-RB-{label}-{step:03d}")
        else:
            mode = MPCMode.EXPECTED if request.controller_id == "deterministic_mpc" else MPCMode.CONSERVATIVE
            plan = controller.plan_with_fallback(sim.clone(), load_forecast, solar_forecast, mode)
            action = plan.first_action
            if plan.solver_diagnostics.fallback_used:
                fallback_count += 1
                runtime["fallback_reasons"].append(plan.fallback_reason or "unknown")
        runtime["planning_time_seconds"] += time.perf_counter() - p0
        v0 = time.perf_counter()
        validation = sim.validate_action(action)
        runtime["validation_time_seconds"] += time.perf_counter() - v0
        if not validation.valid:
            raise RuntimeError(f"{label} invalid action at {origin}: {validation.violations[0].message}")
        s0 = time.perf_counter()
        sim.step(action)
        runtime["step_time_seconds"] += time.perf_counter() - s0
        if progress:
            progress(f"Running {label} digital twin", completed_offset + step + 1, request.duration_hours * 2)

    metrics = controller_metrics(sim, request.scenario_id, f"{request.controller_id}_{label}", fallback_count, 0, runtime)
    metrics["requested_hours"] = request.duration_hours
    metrics["completed_hours"] = metrics["completed_steps"]
    metrics.update(_extra_technical_metrics(sim, candidate))
    adjusted = terminal_inventory_adjustment(
        initial_battery_energy_kwh=float(sim.get_park_energy_history()["battery_energy_before_kwh"].iloc[0]),
        final_battery_energy_kwh=float(sim.get_park_energy_history()["battery_energy_after_kwh"].iloc[-1]),
        raw_operating_cost_vnd=float(metrics["total_realized_operating_cost_proxy_vnd"]),
        valuation_price_vnd_per_kwh=float(candidate.terminal_inventory_valuation_vnd_per_kwh),
    )
    metrics.update(adjusted)
    return {
        "simulator": sim,
        "technical_metrics": _jsonable(metrics),
        "tenant_ledger": _tenant_ledger(sim, request, label),
        "park_history": sim.get_park_energy_history(),
    }


def _candidate_simulator(resources: Any, config: GreenMPCConfig, park: pd.DataFrame, start_timestamp: str, scenario_id: str) -> IndustrialParkSimulator:
    sim = IndustrialParkSimulator(config, resources.tenant_hourly, resources.park_hourly, resources.event_catalog, start_timestamp, dataset_manifest=resources.dataset_manifest)
    sim._park_hourly = _prepare_park_frame(park)
    sim.reset(start_timestamp)
    scenarios = build_scenarios(resources.evaluation_config, start_timestamp)
    for event in scenarios[scenario_id].events:
        sim.inject_event(event)
    return sim


def _config_with_candidate(config: GreenMPCConfig, candidate: CandidateInfrastructure) -> GreenMPCConfig:
    tenants = [
        replace(tenant, renewable_target_fraction=float(candidate.renewable_target_fraction))
        for tenant in config.tenants
    ]
    return replace(
        config,
        tenants=tenants,
        solar=replace(config.solar, installed_capacity_kw=float(candidate.pv_capacity_kw)),
        battery=replace(
            config.battery,
            energy_capacity_kwh=float(candidate.battery_energy_capacity_kwh),
            max_charge_power_kw=float(candidate.battery_power_kw),
            max_discharge_power_kw=float(candidate.battery_power_kw),
            minimum_soc_fraction=float(candidate.minimum_soc_fraction),
            initial_soc_fraction=float(candidate.initial_soc_fraction),
        ),
        dppa=replace(config.dppa, available_capacity_kw=float(candidate.dppa_available_kw), base_price_vnd_per_kwh=float(candidate.dppa_price_vnd_per_kwh)),
        grid=replace(config.grid, transformer_capacity_kw=float(candidate.transformer_capacity_kw)),
    )


def _extra_technical_metrics(sim: IndustrialParkSimulator, candidate: CandidateInfrastructure) -> dict[str, float]:
    park = sim.get_park_energy_history()
    cumulative = sim.get_state().cumulative
    pv_generation = float(park["total_pv_to_tenants_kwh"].sum() + park["pv_to_battery_kwh"].sum() + park["pv_curtailment_kwh"].sum()) if not park.empty else 0.0
    charge = float(park["pv_to_battery_kwh"].sum() + park["dppa_to_battery_kwh"].sum()) if not park.empty else 0.0
    cycles = 0.0 if candidate.battery_energy_capacity_kwh <= 0 else cumulative.battery_throughput_kwh / (2.0 * candidate.battery_energy_capacity_kwh)
    return {
        "total_pv_generation_kwh": pv_generation,
        "direct_pv_utilization_kwh": cumulative.direct_pv_energy_kwh,
        "battery_charge_kwh": charge,
        "battery_discharge_kwh": cumulative.battery_discharge_energy_kwh,
        "equivalent_battery_cycles": cycles,
        "curtailed_renewable_energy_kwh": cumulative.pv_curtailed_energy_kwh,
    }


def _tenant_ledger(sim: IndustrialParkSimulator, request: InvestmentAnalysisRequest, case_label: str) -> pd.DataFrame:
    tenant = sim.get_tenant_energy_history().copy(deep=True)
    tenant["scenario"] = request.scenario_id
    tenant["controller"] = request.controller_id
    tenant["case"] = case_label
    tenant["analysis_window_hours"] = request.duration_hours
    tenant["target_shortfall_kwh"] = (tenant["renewable_target_fraction"] * tenant["effective_load_kwh"] - tenant["total_renewable_delivery_kwh"]).clip(lower=0.0)
    return tenant.rename(
        columns={
            "effective_load_kwh": "load_served_kwh",
            "rooftop_pv_kwh": "direct_pv_kwh",
            "dppa_kwh": "direct_dppa_kwh",
            "grid_kwh": "grid_energy_kwh",
        }
    )


def _tenant_summary(baseline_ledger: pd.DataFrame, proposal_ledger: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, frame in (("baseline", baseline_ledger), ("proposal", proposal_ledger)):
        grouped = frame.groupby("tenant_id", sort=True)
        for tenant_id, group in grouped:
            load = float(group["load_served_kwh"].sum())
            renewable = float(group["total_renewable_delivery_kwh"].sum())
            target = float(group["renewable_target_fraction"].iloc[0])
            rows.append(
                {
                    "case": label,
                    "tenant_id": tenant_id,
                    "load_served_kwh": load,
                    "direct_pv_kwh": float(group["direct_pv_kwh"].sum()),
                    "dppa_kwh": float(group["direct_dppa_kwh"].sum()),
                    "renewable_battery_kwh": float(group["renewable_battery_delivery_kwh"].sum()),
                    "grid_energy_kwh": float(group["grid_energy_kwh"].sum()),
                    "renewable_energy_kwh": renewable,
                    "renewable_share": 0.0 if load <= 0 else renewable / load,
                    "renewable_target": target,
                    "shortfall_kwh": max(0.0, target * load - renewable),
                }
            )
    return rows


def _financial_metrics(
    baseline: CandidateInfrastructure,
    candidate: CandidateInfrastructure,
    baseline_metrics: dict[str, Any],
    proposal_metrics: dict[str, Any],
    financial: FinancialAssumptions,
    hours: int,
) -> dict[str, float | str | None]:
    baseline_capex = _asset_capex(baseline, financial)
    candidate_capex = _asset_capex(candidate, financial)
    incremental_capex = candidate_capex - baseline_capex
    period_savings = float(baseline_metrics["inventory_adjusted_operating_cost_vnd"]) - float(proposal_metrics["inventory_adjusted_operating_cost_vnd"])
    annual_hours = float(financial.annual_operating_days) * 24.0
    annualized_savings = period_savings * annual_hours / float(hours)
    baseline_om = _annual_om(baseline, financial)
    candidate_om = _annual_om(candidate, financial)
    incremental_om = candidate_om - baseline_om
    net_annual_savings = annualized_savings - incremental_om
    payback = incremental_capex / net_annual_savings if incremental_capex > 0 and net_annual_savings > 0 else None
    return {
        "baseline_asset_capex_vnd": baseline_capex,
        "candidate_asset_capex_vnd": candidate_capex,
        "incremental_capex_vnd": incremental_capex,
        "period_operating_savings_vnd": period_savings,
        "annualized_operating_savings_vnd": annualized_savings,
        "incremental_annual_om_vnd": incremental_om,
        "net_annual_savings_vnd": net_annual_savings,
        "simple_payback_years": payback,
        "payback_status": "calculated" if payback is not None else "no payback under current assumptions",
        "annualization_note": "Linear extrapolation from the selected representative analysis window.",
    }


def _asset_capex(candidate: CandidateInfrastructure, financial: FinancialAssumptions) -> float:
    return (
        candidate.pv_capacity_kw * financial.pv_capex_vnd_per_kwp
        + candidate.battery_energy_capacity_kwh * financial.bess_energy_capex_vnd_per_kwh
        + candidate.battery_power_kw * financial.bess_power_capex_vnd_per_kw
        + financial.fixed_implementation_cost_vnd
    )


def _annual_om(candidate: CandidateInfrastructure, financial: FinancialAssumptions) -> float:
    pv_asset = candidate.pv_capacity_kw * financial.pv_capex_vnd_per_kwp
    battery_asset = candidate.battery_energy_capacity_kwh * financial.bess_energy_capex_vnd_per_kwh + candidate.battery_power_kw * financial.bess_power_capex_vnd_per_kw
    return pv_asset * financial.annual_pv_om_fraction + battery_asset * financial.annual_bess_om_fraction


def _comparison_rows(baseline: dict[str, Any], proposal: dict[str, Any]) -> dict[str, float]:
    fields = [
        "total_realized_operating_cost_proxy_vnd",
        "inventory_adjusted_operating_cost_vnd",
        "park_renewable_share",
        "peak_grid_import_kw",
        "peak_external_import_kw",
        "renewable_shortfall_total_kwh",
        "pv_curtailment_kwh",
        "battery_throughput_kwh",
        "final_soc",
    ]
    return {f"{field}_change": float(proposal.get(field, 0.0)) - float(baseline.get(field, 0.0)) for field in fields}


def _write_evidence_package(
    analysis_dir: Path,
    analysis_id: str,
    request: InvestmentAnalysisRequest,
    baseline_config: CandidateInfrastructure,
    baseline: dict[str, Any],
    proposal: dict[str, Any],
    technical_comparison: dict[str, Any],
    financial: dict[str, Any],
    tenant_summary: list[dict[str, Any]],
    cache: dict[str, Any],
    resources: Any,
) -> Path:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {}
    files["analysis_summary.json"] = _json_bytes(
        {
            "analysis_id": analysis_id,
            "scenario": request.scenario_id,
            "controller": request.controller_id,
            "duration_hours": request.duration_hours,
            "disclosures": _disclosures(),
        }
    )
    files["baseline_configuration.json"] = _json_bytes(asdict(baseline_config))
    files["proposal_configuration.json"] = _json_bytes(asdict(request.candidate))
    files["technical_metrics.csv"] = _csv_bytes(pd.DataFrame([{"case": "baseline", **baseline["technical_metrics"]}, {"case": "proposal", **proposal["technical_metrics"], **technical_comparison}]))
    files["financial_assumptions.json"] = _json_bytes(asdict(request.financial))
    files["financial_metrics.csv"] = _csv_bytes(pd.DataFrame([financial]))
    tenant_hourly = pd.concat([baseline["tenant_ledger"], proposal["tenant_ledger"]], ignore_index=True)
    files["tenant_hourly_ledger.csv"] = _csv_bytes(tenant_hourly)
    files["tenant_summary.csv"] = _csv_bytes(pd.DataFrame(tenant_summary))
    files["provenance.json"] = _json_bytes(
        {
            "dataset_version": resources.dataset_manifest.get("dataset_version"),
            "dataset_fingerprints": current_fingerprints(),
            "model_version": resources.model_manifest.get("model_version"),
            "pv_formula_version": resources.processed_lineage.get("pv_formula_version") or "simple_capacity_factor_v2",
            "disclosures": _disclosures(),
        }
    )
    checksums = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    manifest = {
        "analysis_id": analysis_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cache_fingerprint": cache["cache_fingerprint"],
        "completed_successfully": True,
        "checksums": checksums,
        "excluded": ["raw public datasets", "model binaries", "local absolute paths", "Stage 6 detailed histories"],
    }
    files["manifest.json"] = _json_bytes(manifest)
    zip_path = analysis_dir / f"greenmpc_investment_{analysis_id}.zip"
    tmp = zip_path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    tmp.replace(zip_path)
    return zip_path


def _disclosures() -> list[str]:
    return [
        "Scenario-based demonstration using public/rescaled data.",
        "PV is derived from public irradiance data and is not measured inverter output.",
        "Financial assumptions are illustrative and editable.",
        "This package is not an official renewable-energy certificate.",
        "This package is not legal DPPA settlement evidence.",
        "This package does not claim actual VRG operational data.",
    ]


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(_jsonable(payload), indent=2, sort_keys=True).encode("utf-8")


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    return value


def _object_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(_jsonable(payload), sort_keys=True).encode("utf-8")).hexdigest()
