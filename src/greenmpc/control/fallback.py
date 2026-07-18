"""Explicit current-step fallback action support."""

from __future__ import annotations

from dataclasses import replace

from greenmpc.config import GreenMPCConfig
from greenmpc.control.exceptions import MPCFallbackError
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.park import IndustrialParkSimulator
from greenmpc.simulation.reference_action import build_reference_action


def build_safe_fallback_action(simulator: IndustrialParkSimulator, config: GreenMPCConfig, reason: str) -> ParkAction:
    """Build a current-step-only non-optimized fallback action."""

    state = simulator.get_state()
    effective = simulator.get_effective_exogenous()
    state = replace(state, exogenous=effective)
    try:
        action = build_reference_action(state, config, action_id=f"FALLBACK-{state.step_index:06d}")
    except Exception as exc:  # pragma: no cover - defensive path
        raise MPCFallbackError(f"fallback action is infeasible: {exc}") from exc
    action = action.copy_with(
        controller_name="safe_reference_fallback",
        controller_mode="current_step_only_not_greenmpc_performance",
        notes="Fallback uses current effective exogenous values only; it is not Stage 6 baseline performance.",
        metadata={**action.metadata, "fallback_used": True, "fallback_reason": reason, "uses_forecast": False, "uses_optimization": False},
    )
    validation = simulator.validate_action(action)
    if not validation.valid:
        raise MPCFallbackError(f"fallback action failed simulator validation: {validation.violations[0].message}")
    return action
