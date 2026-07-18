"""CVXPY/HIGHS solver wrapper for GreenMPC."""

from __future__ import annotations

import time

import cvxpy as cp
import numpy as np

from greenmpc.control.config import GreenMPCControlConfig
from greenmpc.control.exceptions import MPCInfeasibleError, MPCSolverError
from greenmpc.control.formulation import MPCFormulation, assert_continuous_lp, build_mpc_problem
from greenmpc.control.types import MPCPlanningInput, MPCSolverDiagnostics


ACCEPTED_STATUSES = {"optimal"}


def highs_available() -> bool:
    return "HIGHS" in cp.installed_solvers()


def solve_mpc_lp(planning: MPCPlanningInput, cfg: GreenMPCControlConfig) -> tuple[MPCFormulation, MPCSolverDiagnostics]:
    if not highs_available():
        raise MPCSolverError("HIGHS is not installed in cvxpy.installed_solvers()")
    formulation = build_mpc_problem(planning, cfg)
    assert_continuous_lp(formulation)
    formulation, diagnostics = _solve_once(formulation, cfg, resolve_count=0, repair=False)
    conflicts = _simultaneous_conflicts(formulation, cfg)
    if conflicts and cfg.battery.direction_fixing_repair_enabled:
        fixed_charge_zero: set[int] = set()
        fixed_discharge_zero: set[int] = set()
        charge = np.asarray(formulation.expressions["battery_charge_kw"].value, dtype=float)
        discharge = np.asarray(formulation.expressions["battery_discharge_kw"].value, dtype=float)
        for interval in conflicts:
            if charge[interval] >= discharge[interval]:
                fixed_discharge_zero.add(interval)
            else:
                fixed_charge_zero.add(interval)
        formulation = build_mpc_problem(planning, cfg, fixed_charge_zero=fixed_charge_zero, fixed_discharge_zero=fixed_discharge_zero)
        assert_continuous_lp(formulation)
        formulation, diagnostics = _solve_once(formulation, cfg, resolve_count=1, repair=True)
        conflicts = _simultaneous_conflicts(formulation, cfg)
        if conflicts:
            raise MPCSolverError(f"direction-fixing repair did not remove simultaneous operation: {conflicts}")
    return formulation, diagnostics


def _solve_once(formulation: MPCFormulation, cfg: GreenMPCControlConfig, resolve_count: int, repair: bool) -> tuple[MPCFormulation, MPCSolverDiagnostics]:
    start = time.perf_counter()
    try:
        formulation.problem.solve(solver="HIGHS", verbose=cfg.solver.verbose, warm_start=cfg.solver.warm_start)
    except Exception as exc:  # pragma: no cover - exercised by integration failure paths
        raise MPCSolverError(f"HIGHS solve failed: {exc}") from exc
    elapsed = time.perf_counter() - start
    status = str(formulation.problem.status)
    if status in {"infeasible", "infeasible_inaccurate"}:
        raise MPCInfeasibleError("MPC problem is infeasible")
    if status in {"unbounded", "unbounded_inaccurate"}:
        raise MPCSolverError("MPC problem is unbounded")
    if status not in ACCEPTED_STATUSES:
        raise MPCSolverError(f"MPC solver returned unsupported status: {status}")
    stats = formulation.problem.solver_stats
    diagnostics = MPCSolverDiagnostics(
        solver_name="HIGHS",
        solver_status=status,
        solve_time_seconds=float(stats.solve_time) if stats.solve_time is not None else elapsed,
        setup_time_seconds=float(stats.setup_time) if stats.setup_time is not None else None,
        iteration_count=int(stats.num_iters) if stats.num_iters is not None else None,
        resolve_count=resolve_count,
        direction_repair_applied=repair,
        fallback_used=False,
        warnings=tuple(),
    )
    return formulation, diagnostics


def _simultaneous_conflicts(formulation: MPCFormulation, cfg: GreenMPCControlConfig) -> tuple[int, ...]:
    charge = np.asarray(formulation.expressions["battery_charge_kw"].value, dtype=float)
    discharge = np.asarray(formulation.expressions["battery_discharge_kw"].value, dtype=float)
    tol = cfg.battery.simultaneous_power_tolerance_kw
    return tuple(int(i) for i, (c, d) in enumerate(zip(charge, discharge)) if c > tol and d > tol)
