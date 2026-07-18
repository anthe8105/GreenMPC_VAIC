"""Testable data preparation for the Streamlit Control Room."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.evaluation.metrics import rank_inventory_adjusted_costs, terminal_inventory_adjusted_costs_from_histories
from greenmpc.ui.state import ControlRoomResources, LiveControlSession, PROJECT_ROOT


def current_kpis(session: LiveControlSession) -> dict[str, float | str]:
    """Build the current operational KPI card values."""

    state = session.simulator.get_state()
    ex = session.simulator.get_effective_exogenous()
    cumulative = state.cumulative
    total_load = sum(ex.effective_tenant_load_kw.values())
    external_import = cumulative.peak_external_import_kw
    park_history = session.simulator.get_park_energy_history()
    latest_external = 0.0 if park_history.empty else float(park_history.iloc[-1]["external_import_kwh"])
    latest_grid = 0.0 if park_history.empty else float(park_history.iloc[-1]["total_grid_to_tenants_kwh"])
    latest_dppa = 0.0 if park_history.empty else float(park_history.iloc[-1]["total_dppa_to_tenants_kwh"] + park_history.iloc[-1]["dppa_to_battery_kwh"])
    renewable_share = 0.0 if cumulative.total_load_energy_kwh <= 0 else cumulative.renewable_energy_to_tenants_kwh / cumulative.total_load_energy_kwh
    return {
        "timestamp_local": state.timestamp_local.isoformat(),
        "park_load_kw": total_load,
        "pv_available_kw": ex.effective_pv_available_kw,
        "battery_soc_fraction": state.battery.soc_fraction,
        "grid_import_kw": latest_grid,
        "dppa_import_kw": latest_dppa,
        "external_import_kw": latest_external,
        "grid_import_kw_last_peak": cumulative.peak_grid_import_kw,
        "external_import_kw_last_peak": external_import,
        "transformer_utilization_fraction": 0.0 if ex.transformer_capacity_kw <= 0 else latest_external / ex.transformer_capacity_kw,
        "renewable_share_fraction": renewable_share,
        "operating_cost_vnd": cumulative.total_operating_cost_vnd,
        "total_load_energy_kwh": cumulative.total_load_energy_kwh,
        "renewable_energy_to_tenants_kwh": cumulative.renewable_energy_to_tenants_kwh,
        "tariff_period": ex.tariff_period,
        "dppa_available_kw": ex.dppa_available_kw,
        "renewable_shortfall_kwh": sum(
            max(0.0, session.simulator.tenant_targets[tenant] * state.cumulative_load_by_tenant_kwh[tenant] - state.cumulative_renewable_by_tenant_kwh[tenant])
            for tenant in session.simulator.tenant_ids
        ),
    }


def primary_kpi_cards(session: LiveControlSession) -> list[dict[str, str]]:
    """Return four prominent command-center KPI card definitions."""

    kpis = current_kpis(session)
    return [
        {"label": "Renewable share", "value": f"{kpis['renewable_share_fraction']:.1%}", "detail": "realized cumulative"},
        {"label": "Operating cost", "value": f"{kpis['operating_cost_vnd']/1_000_000:,.2f}M VND", "detail": "realized proxy"},
        {"label": "Battery SOC", "value": f"{kpis['battery_soc_fraction']:.1%}", "detail": "current inventory"},
        {"label": "Transformer utilization", "value": f"{kpis['transformer_utilization_fraction']:.1%}", "detail": "latest external import"},
    ]


def secondary_kpi_cards(session: LiveControlSession) -> list[dict[str, str]]:
    """Return compact secondary command-center KPI card definitions."""

    kpis = current_kpis(session)
    return [
        {"label": "Park load", "value": f"{kpis['park_load_kw']:,.0f} kW"},
        {"label": "PV available", "value": f"{kpis['pv_available_kw']:,.0f} kW"},
        {"label": "Grid import", "value": f"{kpis['grid_import_kw']:,.0f} kW"},
        {"label": "DPPA import", "value": f"{kpis['dppa_import_kw']:,.0f} kW"},
        {"label": "External import", "value": f"{kpis['external_import_kw']:,.0f} kW"},
        {"label": "Renewable shortfall", "value": f"{kpis['renewable_shortfall_kwh']:,.0f} kWh"},
    ]


def current_energy_flow(session: LiveControlSession) -> pd.DataFrame:
    """Return current or latest-executed source-flow rows for plotting."""

    park = session.simulator.get_park_energy_history()
    if park.empty:
        ex = session.simulator.get_effective_exogenous()
        return pd.DataFrame(
            [
                {"source": "Load", "sink": "tenants", "kw": sum(ex.effective_tenant_load_kw.values())},
                {"source": "PV available", "sink": "onsite", "kw": ex.effective_pv_available_kw},
                {"source": "DPPA available", "sink": "external", "kw": ex.dppa_available_kw},
            ]
        )
    last = park.iloc[-1]
    return pd.DataFrame(
        [
            {"source": "PV", "sink": "tenants", "kw": float(last["total_pv_to_tenants_kwh"])},
            {"source": "Battery", "sink": "tenants", "kw": float(last["total_battery_to_tenants_kwh"])},
            {"source": "DPPA", "sink": "tenants", "kw": float(last["total_dppa_to_tenants_kwh"])},
            {"source": "Grid", "sink": "tenants", "kw": float(last["total_grid_to_tenants_kwh"])},
            {"source": "PV", "sink": "battery", "kw": float(last["pv_to_battery_kwh"])},
            {"source": "PV", "sink": "curtailment", "kw": float(last["pv_curtailment_kwh"])},
        ]
    )


def energy_topology(session: LiveControlSession) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return command-center topology nodes and source-to-sink edge flows."""

    tenant_ids = list(session.simulator.tenant_ids)
    nodes = pd.DataFrame(
        [{"node": node, "kind": kind} for node, kind in [
            ("Rooftop PV", "source"),
            ("DPPA", "source"),
            ("Grid", "source"),
            ("BESS", "storage"),
            ("Park bus", "bus"),
            ("Curtailment", "sink"),
            *[(tenant, "tenant") for tenant in tenant_ids],
        ]]
    )
    action = session.latest_action
    park = session.simulator.get_park_energy_history()
    edges: list[dict[str, Any]] = []
    if action is not None:
        for tenant in tenant_ids:
            edges.extend(
                [
                    _edge("Rooftop PV", tenant, action.pv_to_tenant_kw[tenant], "pv"),
                    _edge("DPPA", tenant, action.dppa_to_tenant_kw[tenant], "dppa"),
                    _edge("Grid", tenant, action.grid_to_tenant_kw[tenant], "grid"),
                    _edge("BESS", tenant, action.battery_to_tenant_kw[tenant], "battery"),
                ]
            )
        edges.extend(
            [
                _edge("Rooftop PV", "BESS", action.pv_to_battery_kw, "pv"),
                _edge("DPPA", "BESS", action.dppa_to_battery_kw, "dppa"),
                _edge("Rooftop PV", "Curtailment", action.pv_curtailment_kw, "curtailment"),
            ]
        )
    elif not park.empty:
        last = park.iloc[-1]
        tenant_energy = session.simulator.get_tenant_energy_history()
        latest_ts = tenant_energy["timestamp_local"].iloc[-1] if not tenant_energy.empty else None
        latest_tenant = tenant_energy[tenant_energy["timestamp_local"] == latest_ts] if latest_ts is not None else pd.DataFrame()
        for _, row in latest_tenant.iterrows():
            tenant = row["tenant_id"]
            edges.extend(
                [
                    _edge("Rooftop PV", tenant, float(row["rooftop_pv_kwh"]), "pv"),
                    _edge("DPPA", tenant, float(row["dppa_kwh"]), "dppa"),
                    _edge("Grid", tenant, float(row["grid_kwh"]), "grid"),
                    _edge("BESS", tenant, float(row["battery_delivery_kwh"]), "battery"),
                ]
            )
        edges.extend(
            [
                _edge("Rooftop PV", "BESS", float(last["pv_to_battery_kwh"]), "pv"),
                _edge("DPPA", "BESS", float(last["dppa_to_battery_kwh"]), "dppa"),
                _edge("Rooftop PV", "Curtailment", float(last["pv_curtailment_kwh"]), "curtailment"),
            ]
        )
    else:
        edges.extend(_edge(source, target, 0.0, style) for source, target, style in _default_edges(tenant_ids))
    edge_frame = pd.DataFrame(edges)
    if not edge_frame.empty:
        max_kw = max(float(edge_frame["kw"].max()), 1.0)
        edge_frame["active"] = edge_frame["kw"] > 1e-6
        edge_frame["width"] = edge_frame["kw"].apply(lambda value: 1.0 + 7.0 * float(value) / max_kw)
    return nodes, edge_frame


def forecast_frames(session: LiveControlSession) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return load and solar forecast frames for charts."""

    load = session.latest_load_forecast.to_dataframe() if session.latest_load_forecast else pd.DataFrame()
    solar = session.latest_solar_forecast.to_dataframe() if session.latest_solar_forecast else pd.DataFrame()
    return load, solar


def aggregate_forecast_frame(session: LiveControlSession) -> pd.DataFrame:
    """Build total-load and solar forecast frame with current observed values."""

    load, solar = forecast_frames(session)
    if load.empty or solar.empty:
        return pd.DataFrame()
    load_group = load.groupby(["timestamp_local", "horizon_hours"], as_index=False)[["p10_kw", "p50_kw", "p90_kw"]].sum()
    load_group["series"] = "Total load"
    solar_group = solar[["timestamp_local", "horizon_hours", "p10_kw", "p50_kw", "p90_kw"]].copy()
    solar_group["series"] = "Solar PV"
    current = current_kpis(session)
    combined = pd.concat([load_group, solar_group], ignore_index=True)
    combined["current_observed_kw"] = combined["series"].map({"Total load": current["park_load_kw"], "Solar PV": current["pv_available_kw"]})
    return combined


def plan_frames(session: LiveControlSession) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return normalized tenant and park plan frames."""

    plan = session.latest_plan
    if plan is None:
        return pd.DataFrame(), pd.DataFrame()
    return plan.tenant_plan.copy(deep=True), plan.park_plan.copy(deep=True)


def rolling_history_frame(session: LiveControlSession) -> pd.DataFrame:
    """Return the most recent live execution history rows."""

    return pd.DataFrame(session.rolling_history[-24:])


def tenant_summary(session: LiveControlSession, tenant_id: str) -> dict[str, float | str | bool]:
    """Build tenant-level current and cumulative summary values."""

    state = session.simulator.get_state()
    ex = session.simulator.get_effective_exogenous()
    load = ex.effective_tenant_load_kw[tenant_id]
    cumulative_load = state.cumulative_load_by_tenant_kwh[tenant_id]
    renewable = state.cumulative_renewable_by_tenant_kwh[tenant_id]
    target = session.simulator.tenant_targets[tenant_id]
    shortfall = max(0.0, target * cumulative_load - renewable)
    share = 0.0 if cumulative_load <= 0 else renewable / cumulative_load
    return {
        "tenant_id": tenant_id,
        "current_load_kw": load,
        "cumulative_load_kwh": cumulative_load,
        "cumulative_renewable_kwh": renewable,
        "renewable_share_fraction": share,
        "renewable_target_fraction": target,
        "realized_shortfall_kwh": shortfall,
        "target_achieved": shortfall <= 1e-6,
        "grid_delivery_kwh": state.cumulative_grid_by_tenant_kwh[tenant_id],
        "direct_pv_kwh": state.cumulative_pv_by_tenant_kwh[tenant_id],
        "dppa_kwh": state.cumulative_dppa_by_tenant_kwh[tenant_id],
        "battery_delivery_kwh": state.cumulative_battery_by_tenant_kwh[tenant_id],
    }


def solver_diagnostics(session: LiveControlSession) -> dict[str, Any]:
    """Return solver and validation diagnostics for display."""

    plan = session.latest_plan
    validation = session.latest_validation
    if plan is None:
        return {
            "controller": session.controller_id,
            "solver_status": "not applicable",
            "fallback_used": session.fallback_visible,
            "fallback_reason": session.fallback_reason,
            "validation_valid": bool(getattr(validation, "valid", False)) if validation else False,
        }
    return {
        "controller": session.controller_id,
        "solver_status": plan.solver_diagnostics.solver_status,
        "solver_name": plan.solver_diagnostics.solver_name,
        "solve_time_seconds": plan.solver_diagnostics.solve_time_seconds,
        "direction_repair_applied": plan.solver_diagnostics.direction_repair_applied,
        "fallback_used": plan.solver_diagnostics.fallback_used,
        "fallback_reason": plan.fallback_reason,
        "validation_valid": bool(getattr(validation, "valid", False)) if validation else False,
        "active_constraints": ", ".join(plan.constraint_diagnostics.active_constraint_codes),
        "warnings": "; ".join(plan.warnings),
    }


def recommended_action_card(session: LiveControlSession) -> dict[str, str | float | bool | None]:
    """Summarize the latest recommended or executed action."""

    action = session.latest_action
    if action is None:
        return {
            "plan_timestamp": session.plan_timestamp,
            "controller": session.controller_id,
            "solver_status": "not ready",
            "validation_result": "not validated",
            "fallback_state": session.fallback_visible,
        }
    total_pv = sum(action.pv_to_tenant_kw.values())
    total_dppa = sum(action.dppa_to_tenant_kw.values()) + action.dppa_to_battery_kw
    total_grid = sum(action.grid_to_tenant_kw.values())
    total_battery = sum(action.battery_to_tenant_kw.values())
    total_charge = action.pv_to_battery_kw + action.dppa_to_battery_kw
    ex = session.simulator.get_effective_exogenous()
    external = total_grid + total_dppa
    validation = session.latest_validation
    return {
        "plan_timestamp": session.plan_timestamp,
        "controller": session.controller_id,
        "solver_status": solver_diagnostics(session).get("solver_status"),
        "grid_import_kw": total_grid,
        "dppa_allocation_kw": total_dppa,
        "pv_allocation_kw": total_pv,
        "battery_discharge_kw": total_battery,
        "battery_charge_kw": total_charge,
        "curtailment_kw": action.pv_curtailment_kw,
        "transformer_utilization_fraction": 0.0 if ex.transformer_capacity_kw <= 0 else external / ex.transformer_capacity_kw,
        "validation_result": "valid" if validation is not None and validation.valid else "invalid",
        "fallback_state": session.fallback_visible,
        "fallback_reason": session.fallback_reason,
    }


def alert_cards(session: LiveControlSession) -> list[dict[str, str]]:
    """Derive visible operational alerts from real state and plan status."""

    alerts: list[dict[str, str]] = []
    kpis = current_kpis(session)
    if float(kpis["transformer_utilization_fraction"]) >= 0.85:
        alerts.append({"severity": "warning", "message": "High transformer utilization"})
    if float(kpis["battery_soc_fraction"]) <= 0.15:
        alerts.append({"severity": "warning", "message": "Low battery SOC"})
    if float(kpis["renewable_shortfall_kwh"]) > 0:
        alerts.append({"severity": "info", "message": "Renewable target shortfall remains"})
    aggregate = aggregate_forecast_frame(session)
    if not aggregate.empty:
        spread = (aggregate["p90_kw"] - aggregate["p10_kw"]).max()
        center = max(float(aggregate["p50_kw"].mean()), 1.0)
        if float(spread) / center > 0.35:
            alerts.append({"severity": "info", "message": "High forecast uncertainty"})
    if session.fallback_visible:
        alerts.append({"severity": "error", "message": f"Fallback active: {session.fallback_reason or 'current-step fallback'}"})
    if session.last_error:
        alerts.append({"severity": "error", "message": session.last_error})
    if session.plan_is_stale and session.latest_action is not None:
        alerts.append({"severity": "warning", "message": "Plan is stale and cannot execute"})
    return alerts


def objective_breakdown(session: LiveControlSession) -> pd.DataFrame:
    """Separate actual operating-cost proxy from control penalties."""

    plan = session.latest_plan
    if plan is None:
        return pd.DataFrame()
    obj = asdict(plan.objective_breakdown)
    rows = [
        ("grid_energy_cost_vnd", "operating_cost_proxy"),
        ("dppa_energy_cost_vnd", "operating_cost_proxy"),
        ("battery_degradation_proxy_cost_vnd", "operating_cost_proxy"),
        ("operating_cost_proxy_vnd", "operating_cost_proxy_total"),
        ("grid_peak_penalty_vnd", "control_penalty"),
        ("pv_curtailment_penalty_vnd", "control_penalty"),
        ("renewable_shortfall_penalty_vnd", "control_penalty"),
        ("terminal_reserve_penalty_vnd", "control_penalty"),
        ("total_control_objective", "objective_total"),
    ]
    return pd.DataFrame([{"component": key, "category": category, "value_vnd": float(obj[key])} for key, category in rows])


def benchmark_view(resources: ControlRoomResources, valuation_price_vnd_per_kwh: float) -> pd.DataFrame:
    """Return read-only benchmark metrics with recalculated inventory-adjusted cost."""

    metrics = resources.benchmark_metrics.copy(deep=True)
    if metrics.empty:
        return metrics
    scenarios = tuple(metrics["scenario_id"].drop_duplicates())
    controllers = tuple(metrics["controller_id"].drop_duplicates())
    # Committed inventory-adjusted costs are split across two files: the base
    # valuation lives in terminal_inventory_costs while the alternate valuation
    # prices live in terminal_inventory_sensitivity. Combine them so every price
    # offered by the API resolves from committed data before falling back to the
    # (optional, not shipped) per-scenario history CSVs.
    committed = [
        df for df in (resources.terminal_inventory_costs, resources.terminal_inventory_sensitivity)
        if not df.empty
    ]
    adjusted = pd.concat(committed, ignore_index=True) if committed else pd.DataFrame()
    if not adjusted.empty and "valuation_price_vnd_per_kwh" in adjusted.columns:
        adjusted = adjusted[adjusted["valuation_price_vnd_per_kwh"].round(6) == round(float(valuation_price_vnd_per_kwh), 6)]
    if adjusted.empty:
        adjusted = terminal_inventory_adjusted_costs_from_histories(
            PROJECT_ROOT / resources.evaluation_config.output_directory,
            valuation_price_vnd_per_kwh,
            scenarios,
            controllers,
        )
    adjusted = rank_inventory_adjusted_costs(adjusted)
    merged = metrics.merge(
        adjusted[
            [
                "scenario_id",
                "controller_id",
                "terminal_inventory_adjustment_vnd",
                "inventory_adjusted_operating_cost_vnd",
                "inventory_adjusted_rank",
            ]
        ],
        on=["scenario_id", "controller_id"],
        how="left",
    )
    return merged


def provenance_summary(resources: ControlRoomResources, scenario_id: str) -> dict[str, Any]:
    """Build compact provenance and assumption display data without local paths."""

    manifest = resources.dataset_manifest
    model = resources.model_manifest
    fingerprints = manifest.get("output_fingerprints", manifest.get("fingerprints", {}))
    return {
        "dataset_version": manifest.get("dataset_version", "unknown"),
        "model_version": model.get("model_version", "unknown"),
        "controller_version": resources.mpc_config.general.controller_name,
        "scenario_id": scenario_id,
        "pv_formula_version": _find_lineage_value(resources.processed_lineage, "pv_available_kw", "pv_formula_version"),
        "tenant_dataset_fingerprint": model.get("tenant_dataset_fingerprint", fingerprints.get("tenant_hourly.csv", "unknown")),
        "park_dataset_fingerprint": model.get("park_dataset_fingerprint", fingerprints.get("park_hourly.csv", "unknown")),
        "disclosures": [
            "The industrial-park dataset combines measured public load-profile shapes with Vietnam weather data and transparent scenario assumptions.",
            "PV availability is physically derived from NASA POWER irradiance and is not measured inverter output.",
            "Tariff category, DPPA volume, DPPA price, tenant industry labels, and stress events are scenario assumptions.",
            "No actual VRG operational data or official renewable certificate claim is used.",
        ],
    }


def action_preview(session: LiveControlSession) -> pd.DataFrame:
    """Flatten the latest first action for review before execution."""

    action = session.latest_action
    if action is None:
        return pd.DataFrame()
    rows = []
    for tenant_id in action.pv_to_tenant_kw:
        rows.append(
            {
                "tenant_id": tenant_id,
                "pv_kw": action.pv_to_tenant_kw[tenant_id],
                "battery_kw": action.battery_to_tenant_kw[tenant_id],
                "dppa_kw": action.dppa_to_tenant_kw[tenant_id],
                "grid_kw": action.grid_to_tenant_kw[tenant_id],
            }
        )
    rows.append(
        {
            "tenant_id": "park",
            "pv_kw": action.pv_to_battery_kw,
            "battery_kw": 0.0,
            "dppa_kw": action.dppa_to_battery_kw,
            "grid_kw": 0.0,
            "notes": f"curtailment_kw={action.pv_curtailment_kw:.3f}",
        }
    )
    return pd.DataFrame(rows)


def ui_status(session: LiveControlSession, countdown_seconds: float | None = None) -> dict[str, str]:
    """Return compact live-loop status strings."""

    return {
        "status": session.latest_status,
        "operation_mode": session.operation_mode,
        "countdown": "paused" if countdown_seconds is None else f"{countdown_seconds:.0f}s",
        "completed_hours": f"{session.simulated_hours_completed}",
        "maximum_hours": f"{session.maximum_simulated_hours}",
        "forecast_latency": f"{session.timings.get('forecast_seconds', 0.0):.2f}s",
        "planning_latency": f"{session.timings.get('planning_seconds', 0.0):.2f}s",
    }


def _edge(source: str, target: str, kw: float, style: str) -> dict[str, Any]:
    return {"source": source, "target": target, "kw": max(0.0, float(kw)), "style": style}


def _default_edges(tenant_ids: list[str]) -> list[tuple[str, str, str]]:
    edges = []
    for tenant in tenant_ids:
        edges.extend([
            ("Rooftop PV", tenant, "pv"),
            ("DPPA", tenant, "dppa"),
            ("Grid", tenant, "grid"),
            ("BESS", tenant, "battery"),
        ])
    edges.extend([
        ("Rooftop PV", "BESS", "pv"),
        ("DPPA", "BESS", "dppa"),
        ("Rooftop PV", "Curtailment", "curtailment"),
    ])
    return edges


def _find_lineage_value(lineage: dict[str, Any], key: str, nested_key: str) -> str:
    raw = lineage.get(key, {})
    if isinstance(raw, dict):
        if nested_key in raw:
            return str(raw[nested_key])
        text = json.dumps(raw)
        if "simple_capacity_factor_v2" in text:
            return "simple_capacity_factor_v2"
    return "simple_capacity_factor_v2"
