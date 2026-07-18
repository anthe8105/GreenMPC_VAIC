from __future__ import annotations

from scripts.run_mpc_diagnostic import build_handcrafted_input

from greenmpc.config import load_config
from greenmpc.control.config import load_mpc_config
from greenmpc.control.controller import GreenMPCController
from greenmpc.control.formulation import assert_continuous_lp, build_mpc_problem
from greenmpc.control.types import MPCMode
from greenmpc.simulation.park import IndustrialParkSimulator


def test_handcrafted_problem_is_continuous_dcp_lp():
    sim = IndustrialParkSimulator.from_processed_files(start_timestamp="2013-04-03T11:00:00+07:00")
    cfg = load_mpc_config("configs/mpc.yaml")
    planning = build_handcrafted_input(sim, MPCMode.EXPECTED)
    formulation = build_mpc_problem(planning, cfg)
    assert formulation.problem.is_dcp()
    assert_continuous_lp(formulation)
    names = {variable.name() for variable in formulation.problem.variables()}
    assert not any("grid_to_battery" in name for name in names)
    assert not any("unmet" in name for name in names)


def test_handcrafted_plan_charges_and_discharges_without_simultaneous_operation():
    sim = IndustrialParkSimulator.from_processed_files(start_timestamp="2013-04-03T11:00:00+07:00")
    controller = GreenMPCController(load_config("configs/demo.yaml"), load_mpc_config("configs/mpc.yaml"))
    plan = controller.solve(build_handcrafted_input(sim, MPCMode.EXPECTED), sim)
    assert plan.valid_for_execution
    assert plan.park_plan["battery_charge_kw"].sum() > 0
    assert plan.park_plan["battery_discharge_kw"].sum() > 0
    assert not ((plan.park_plan["battery_charge_kw"] > 1e-6) & (plan.park_plan["battery_discharge_kw"] > 1e-6)).any()
