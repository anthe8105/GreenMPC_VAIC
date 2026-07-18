"""Public GreenMPC controller API."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from greenmpc.config import GreenMPCConfig, load_config
from greenmpc.control.config import GreenMPCControlConfig, load_mpc_config
from greenmpc.control.exceptions import (
    MPCFallbackError,
    MPCPostprocessingError,
    MPCSolverError,
    UnsupportedRenewableInventoryForLinearMPCError,
)
from greenmpc.control.fallback import build_safe_fallback_action
from greenmpc.control.input_builder import build_mpc_planning_input
from greenmpc.control.postprocessing import extract_plan_result
from greenmpc.control.solver import solve_mpc_lp
from greenmpc.control.types import (
    MPCConstraintDiagnostics,
    MPCMode,
    MPCObjectiveBreakdown,
    MPCPlanningInput,
    MPCPlanResult,
    MPCSolverDiagnostics,
)
from greenmpc.forecasting.inference import ParkSolarForecast, TenantLoadForecast
from greenmpc.simulation.park import IndustrialParkSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class GreenMPCController:
    """Transparent continuous-LP MPC controller.

    The controller plans and validates a first action. It never calls
    simulator.step() and does not mutate simulator state.
    """

    def __init__(self, project_config: GreenMPCConfig, mpc_config: GreenMPCControlConfig) -> None:
        self.project_config = project_config
        self.mpc_config = mpc_config
        _validate_linear_renewable_assumptions(project_config)

    @classmethod
    def from_config(
        cls,
        project_config_path: str | Path = PROJECT_ROOT / "configs/demo.yaml",
        mpc_config_path: str | Path = PROJECT_ROOT / "configs/mpc.yaml",
    ) -> "GreenMPCController":
        return cls(load_config(project_config_path), load_mpc_config(mpc_config_path))

    def build_input(
        self,
        simulator: IndustrialParkSimulator,
        load_forecast: TenantLoadForecast,
        solar_forecast: ParkSolarForecast,
        mode: MPCMode | str,
        audit_output_path: str | Path | None = None,
    ) -> MPCPlanningInput:
        resolved_mode = MPCMode(mode)
        return build_mpc_planning_input(
            simulator=simulator,
            load_forecast=load_forecast,
            solar_forecast=solar_forecast,
            mode=resolved_mode,
            project_config=self.project_config,
            mpc_config=self.mpc_config,
            audit_output_path=audit_output_path,
        )

    def solve(self, planning_input: MPCPlanningInput, simulator: IndustrialParkSimulator | None = None) -> MPCPlanResult:
        formulation, solver_diagnostics = solve_mpc_lp(planning_input, self.mpc_config)
        return extract_plan_result(
            formulation=formulation,
            planning=planning_input,
            cfg=self.mpc_config,
            simulator=simulator,
            solver_diagnostics=solver_diagnostics,
            direction_repair_applied=solver_diagnostics.direction_repair_applied,
        )

    def plan(
        self,
        simulator: IndustrialParkSimulator,
        load_forecast: TenantLoadForecast,
        solar_forecast: ParkSolarForecast,
        mode: MPCMode | str,
    ) -> MPCPlanResult:
        planning = self.build_input(simulator, load_forecast, solar_forecast, mode)
        return self.solve(planning, simulator)

    def plan_with_fallback(
        self,
        simulator: IndustrialParkSimulator,
        load_forecast: TenantLoadForecast,
        solar_forecast: ParkSolarForecast,
        mode: MPCMode | str,
    ) -> MPCPlanResult:
        try:
            return self.plan(simulator, load_forecast, solar_forecast, mode)
        except (MPCSolverError, MPCPostprocessingError) as exc:
            if not self.mpc_config.fallback.enabled:
                raise
            action = build_safe_fallback_action(simulator, self.project_config, str(exc))
            planning = self.build_input(simulator, load_forecast, solar_forecast, mode)
            validation = simulator.validate_action(action)
            diag = MPCSolverDiagnostics("HIGHS", "fallback_after_failure", None, None, None, 0, False, True, (str(exc),))
            return MPCPlanResult(
                plan_id=f"FALLBACK-{pd.Timestamp.utcnow().strftime('%Y%m%d%H%M%S')}",
                controller_name=self.mpc_config.general.controller_name,
                controller_mode=MPCMode(mode),
                created_at_utc=datetime.now(timezone.utc),
                planning_input=planning,
                objective_breakdown=MPCObjectiveBreakdown(0, 0, 0, 0, 0, 0, 0, 0, 0),
                solver_diagnostics=diag,
                constraint_diagnostics=MPCConstraintDiagnostics(0, 0, 0, 0, 0, 0, tuple(), tuple(), {}, 0),
                tenant_plan=pd.DataFrame(),
                park_plan=pd.DataFrame(),
                first_action=action,
                valid_for_execution=validation.valid,
                simulator_validation_result=validation,
                fallback_action=action,
                fallback_reason=str(exc),
                warnings=(str(exc),),
                metadata={"fallback_used": True, "fallback_is_evaluation_baseline": False},
            )


def _validate_linear_renewable_assumptions(config: GreenMPCConfig) -> None:
    if abs(config.battery.initial_renewable_fraction - 1.0) > 1e-9:
        raise UnsupportedRenewableInventoryForLinearMPCError("linear MPC renewable battery assumption requires initial_renewable_fraction=1.0")
    if not config.accounting.count_rooftop_pv_as_renewable:
        raise UnsupportedRenewableInventoryForLinearMPCError("linear MPC requires rooftop PV to count as renewable")
    if not config.dppa.renewable_eligible or not config.accounting.count_dppa_as_renewable:
        raise UnsupportedRenewableInventoryForLinearMPCError("linear MPC requires renewable-eligible DPPA")
    if config.battery.allow_simultaneous_charge_discharge:
        raise UnsupportedRenewableInventoryForLinearMPCError("linear MPC MVP assumes no meaningful simultaneous charge/discharge after repair")
