#!/usr/bin/env python
"""Verify Stage 5 GreenMPC control-engine acceptance gates."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import cvxpy as cp
import pandas as pd

from greenmpc.config import load_config
from greenmpc.control.config import load_mpc_config
from greenmpc.control.controller import GreenMPCController
from greenmpc.control.formulation import assert_continuous_lp, build_mpc_problem
from greenmpc.control.solver import highs_available
from greenmpc.control.types import MPCMode
from greenmpc.forecasting.inference import ForecastService
from greenmpc.simulation.park import IndustrialParkSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for script in ("verify_stage0.py", "verify_stage1.py", "verify_stage2.py", "verify_stage3.py", "verify_stage4.py"):
        result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / script)], cwd=PROJECT_ROOT, capture_output=True, text=True)
        checks.append((script, result.returncode == 0, _first_line(result.stdout) or result.stderr.strip()))

    project_cfg = load_config(PROJECT_ROOT / "configs/demo.yaml")
    mpc_cfg = load_mpc_config(PROJECT_ROOT / "configs/mpc.yaml")
    checks.append(("MPC configuration loads", True, "configs/mpc.yaml"))
    checks.append(("HIGHS installed", highs_available(), str(cp.installed_solvers())))

    build_handcrafted_input = _load_diagnostic_builder()

    diagnostic_sim = IndustrialParkSimulator.from_processed_files(start_timestamp="2013-04-03T11:00:00+07:00")
    controller = GreenMPCController(project_cfg, mpc_cfg)
    diagnostic_plans = {}
    for mode in (MPCMode.EXPECTED, MPCMode.CONSERVATIVE):
        planning = build_handcrafted_input(diagnostic_sim.clone(), mode)
        formulation = build_mpc_problem(planning, mpc_cfg)
        try:
            assert_continuous_lp(formulation)
            dcp = True
            detail = "DCP continuous LP"
        except Exception as exc:
            dcp = False
            detail = str(exc)
        checks.append((f"{mode.value} problem is DCP continuous", dcp, detail))
        plan = controller.solve(planning, diagnostic_sim.clone())
        diagnostic_plans[mode.value] = plan
        checks.append((f"diagnostic {mode.value} solves", plan.solver_diagnostics.solver_status == "optimal", plan.solver_diagnostics.solver_status))
        checks.append((f"diagnostic {mode.value} first action validates", bool(plan.valid_for_execution), str(plan.valid_for_execution)))

    expected_diag = diagnostic_plans["expected"].park_plan
    checks.append(("diagnostic battery charges", expected_diag["battery_charge_kw"].sum() > 0, f"{expected_diag['battery_charge_kw'].sum():.3f} kW"))
    checks.append(("diagnostic battery later discharges", expected_diag["battery_discharge_kw"].sum() > 0, f"{expected_diag['battery_discharge_kw'].sum():.3f} kW"))
    checks.append(("no meaningful simultaneous operation remains", not ((expected_diag["battery_charge_kw"] > mpc_cfg.battery.simultaneous_power_tolerance_kw) & (expected_diag["battery_discharge_kw"] > mpc_cfg.battery.simultaneous_power_tolerance_kw)).any(), "expected plan"))

    tenant = pd.read_csv(PROJECT_ROOT / "data/processed/tenant_hourly.csv")
    park = pd.read_csv(PROJECT_ROOT / "data/processed/park_hourly.csv")
    origin = pd.Timestamp("2013-11-08T09:00:00+07:00")
    simulator = IndustrialParkSimulator.from_processed_files(start_timestamp=origin.isoformat())
    service = ForecastService.from_registry(PROJECT_ROOT / "configs/forecasting.yaml")
    load_forecast, solar_forecast = service.forecast_all(tenant, park, origin, horizon_hours=6)
    state_before = simulator.get_state()
    real_plans = {}
    for mode in (MPCMode.EXPECTED, MPCMode.CONSERVATIVE):
        planning = controller.build_input(simulator.clone(), load_forecast, solar_forecast, mode)
        checks.append((f"{mode.value} quantiles", planning.forecast_quantiles_used == {"load": mpc_cfg.modes[mode.value].load_quantile, "solar": mpc_cfg.modes[mode.value].solar_quantile}, str(planning.forecast_quantiles_used)))
        checks.append((f"{mode.value} no future actual load/PV", planning.metadata.get("no_future_actual_load_or_pv") is True, "metadata flag"))
        plan = controller.solve(planning, simulator.clone())
        real_plans[mode.value] = plan
        checks.append((f"real-data {mode.value} solves", plan.solver_diagnostics.solver_status == "optimal", plan.solver_diagnostics.solver_status))
        checks.append((f"real-data {mode.value} first action validates", bool(plan.valid_for_execution), str(plan.valid_for_execution)))
    checks.append(("simulator state unchanged after planning", simulator.get_state().timestamp_local == state_before.timestamp_local and simulator.get_state().battery.energy_kwh == state_before.battery.energy_kwh, state_before.timestamp_local.isoformat()))

    fallback_result = _fallback_check(controller, simulator, load_forecast, solar_forecast)
    checks.append(("infeasible-case fallback works", fallback_result, "fallback current-step action"))
    checks.append(("fallback clearly labeled", fallback_result, "safe_reference_fallback"))

    for path in (
        "data/outputs/stage5_diagnostic/expected_tenant_plan.csv",
        "data/outputs/stage5_diagnostic/expected_park_plan.csv",
        "data/outputs/stage5_example/expected_tenant_plan.csv",
        "data/outputs/stage5_example/conservative_park_plan.csv",
        "artifacts/mpc_diagnostic.html",
        "artifacts/mpc_example.html",
    ):
        checks.append((f"{path} exists", (PROJECT_ROOT / path).exists(), path))

    control_files = list((PROJECT_ROOT / "src/greenmpc/control").glob("*.py"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in control_files)
    checks.append(("no Streamlit import in control modules", "streamlit" not in text.lower(), "control package"))
    checks.append(("no Stage 6 closed-loop evaluation", "closed-loop benchmark" not in text.lower(), "control package"))

    print("check | result | detail")
    print("----- | ------ | ------")
    failed = False
    for name, ok, detail in checks:
        failed = failed or not ok
        print(f"{name} | {'PASS' if ok else 'FAIL'} | {detail}")
    return 1 if failed else 0


def _fallback_check(controller: GreenMPCController, simulator: IndustrialParkSimulator, load_forecast, solar_forecast) -> bool:
    original = controller.solve

    def broken(*args, **kwargs):
        from greenmpc.control.exceptions import MPCSolverError

        raise MPCSolverError("intentional verification failure")

    controller.solve = broken  # type: ignore[method-assign]
    try:
        result = controller.plan_with_fallback(simulator.clone(), load_forecast, solar_forecast, MPCMode.EXPECTED)
        return bool(result.fallback_action and result.fallback_action.controller_name == "safe_reference_fallback" and result.valid_for_execution)
    finally:
        controller.solve = original  # type: ignore[method-assign]


def _first_line(text: str) -> str:
    return next((line for line in text.splitlines() if line.strip()), "")


def _load_diagnostic_builder():
    path = PROJECT_ROOT / "scripts/run_mpc_diagnostic.py"
    spec = importlib.util.spec_from_file_location("run_mpc_diagnostic_stage5", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_handcrafted_input


if __name__ == "__main__":
    raise SystemExit(main())
