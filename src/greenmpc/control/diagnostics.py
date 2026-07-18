"""MPC diagnostic helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from greenmpc.control.types import MPCPlanResult


def plan_summary(plan: MPCPlanResult) -> dict[str, Any]:
    """Return a compact reviewable summary for scripts and verification."""

    return {
        "plan_id": plan.plan_id,
        "mode": plan.controller_mode.value,
        "solver_status": plan.solver_diagnostics.solver_status,
        "fallback_used": plan.solver_diagnostics.fallback_used,
        "objective": asdict(plan.objective_breakdown),
        "active_constraints": list(plan.constraint_diagnostics.active_constraint_codes),
        "renewable_shortfall_by_tenant_kwh": plan.constraint_diagnostics.renewable_shortfall_by_tenant_kwh,
        "first_action_valid": bool(plan.valid_for_execution),
        "max_transformer_utilization": float(plan.park_plan["transformer_utilization_fraction"].max()) if not plan.park_plan.empty else None,
    }


def write_plan_outputs(plan: MPCPlanResult, output_directory: str | Path, prefix: str = "") -> dict[str, Path]:
    target = Path(output_directory)
    target.mkdir(parents=True, exist_ok=True)
    stem = f"{prefix}_" if prefix else ""
    tenant_path = target / f"{stem}tenant_plan.csv"
    park_path = target / f"{stem}park_plan.csv"
    summary_path = target / f"{stem}summary.json"
    action_path = target / f"{stem}first_action.json"
    plan.tenant_plan.to_csv(tenant_path, index=False)
    plan.park_plan.to_csv(park_path, index=False)
    summary_path.write_text(json.dumps(_jsonable(plan_summary(plan)), indent=2), encoding="utf-8")
    if plan.first_action is not None:
        action_path.write_text(json.dumps(plan.first_action.to_dict(), indent=2), encoding="utf-8")
    return {"tenant_plan": tenant_path, "park_plan": park_path, "summary": summary_path, "first_action": action_path}


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
