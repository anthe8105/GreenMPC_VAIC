#!/usr/bin/env python
"""Verify Stage 3 digital-twin simulator acceptance checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from greenmpc.config import load_config
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.exceptions import InvalidActionError
from greenmpc.simulation.park import IndustrialParkSimulator
from greenmpc.simulation.reference_action import build_reference_action


MODULES = [
    "exceptions.py",
    "state.py",
    "actions.py",
    "events.py",
    "validation.py",
    "accounting.py",
    "park.py",
    "history.py",
    "reference_action.py",
]


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for script in ("verify_stage0.py", "verify_stage1.py", "verify_stage2.py"):
        result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / script)], cwd=PROJECT_ROOT, text=True, capture_output=True)
        checks.append((script, result.returncode == 0, result.stdout.splitlines()[0] if result.stdout else result.stderr[:120]))

    sim_dir = PROJECT_ROOT / "src/greenmpc/simulation"
    checks.append(("required simulation modules exist", all((sim_dir / module).exists() for module in MODULES), ", ".join(MODULES)))
    config = load_config(PROJECT_ROOT / "configs/demo.yaml")
    checks.append(("updated configuration loads", True, config.accounting.renewable_battery_inventory_method))

    try:
        sim = IndustrialParkSimulator.from_processed_files()
        state = sim.get_state()
        checks.append(("processed data initializes simulator", True, state.timestamp_local.isoformat()))
        checks.append(("five tenants present", len(state.exogenous.effective_tenant_load_kw) == 5, str(list(state.exogenous.effective_tenant_load_kw))))
        checks.append(("initial battery state valid", state.battery.minimum_energy_kwh <= state.battery.energy_kwh <= state.battery.maximum_energy_kwh, f"{state.battery.energy_kwh:.3f} kWh"))
        checks.append(("initial renewable inventory valid", 0 <= state.battery.renewable_energy_kwh <= state.battery.energy_kwh, f"{state.battery.renewable_energy_kwh:.3f} kWh"))
        action = build_reference_action(state, sim.config)
        validation = sim.validate_action(action)
        checks.append(("reference action passes validation", validation.valid, str([v.code for v in validation.violations])))
        result = sim.step(action)
        checks.append(("one valid step executes", True, result.next_state.timestamp_local.isoformat()))
        checks.append(("state advances one hour", (result.next_state.timestamp_local - state.timestamp_local).total_seconds() == 3600, "one-hour step"))
        battery_expected = validation.calculated_values["battery_next_energy_kwh"]
        checks.append(("battery transition reconciles", abs(result.next_state.battery.energy_kwh - battery_expected) < 1e-6, f"{result.next_state.battery.energy_kwh:.6f}"))
        tenant_total = sum(record.effective_load_kwh for record in result.tenant_energy_records)
        checks.append(("tenant energy records reconcile", abs(tenant_total - result.park_energy_record.total_effective_load_kwh) < 1e-6, f"{tenant_total:.6f}"))
        checks.append(("park energy record reconciles", abs(result.park_energy_record.total_effective_load_kwh - sum(result.effective_exogenous_state.effective_tenant_load_kw.values())) < 1e-6, "load sum"))
        checks.append(("external import includes DPPA", abs(action.total_external_import_kw - (action.total_grid_to_tenants_kw + action.total_dppa_to_tenants_kw + action.dppa_to_battery_kw)) < 1e-9, f"{action.total_external_import_kw:.6f}"))
        bad = action.copy_with(grid_to_tenant_kw={**action.grid_to_tenant_kw, list(action.grid_to_tenant_kw)[0]: action.grid_to_tenant_kw[list(action.grid_to_tenant_kw)[0]] + 999999.0})
        before = sim.get_state()
        try:
            sim.step(bad)
            rejected = False
        except InvalidActionError:
            rejected = True
        after = sim.get_state()
        checks.append(("intentionally invalid action rejected", rejected, "InvalidActionError"))
        checks.append(("state unchanged after invalid action", before.timestamp_local == after.timestamp_local and before.battery.energy_kwh == after.battery.energy_kwh, before.timestamp_local.isoformat()))
        event_sim = IndustrialParkSimulator.from_processed_files()
        cloud = next(event for event in event_sim._catalog_events.values() if event.event_type == "cloud_event")
        event_sim.reset(cloud.start_timestamp_local)
        base = event_sim.get_baseline_exogenous().baseline_pv_available_kw
        event_sim.activate_catalog_event(cloud.event_id)
        effective = event_sim.get_effective_exogenous().effective_pv_available_kw
        checks.append(("cloud event changes effective PV", effective < base, f"{base:.3f}->{effective:.3f}"))
        checks.append(("baseline data remains unchanged", event_sim.get_baseline_exogenous().baseline_pv_available_kw == base, f"{base:.3f}"))
        cloned = event_sim.clone()
        cloned.clear_runtime_events()
        checks.append(("clone is independent", cloned.get_effective_exogenous().effective_pv_available_kw != event_sim.get_effective_exogenous().effective_pv_available_kw, "runtime events copied independently"))
        event_sim.reset(cloud.start_timestamp_local)
        checks.append(("reset is deterministic", event_sim.get_state().timestamp_local == cloud.start_timestamp_local, cloud.start_timestamp_local.isoformat()))
    except Exception as exc:
        checks.append(("simulator runtime checks", False, repr(exc)))

    smoke = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts/run_digital_twin_smoke.py")], cwd=PROJECT_ROOT, text=True, capture_output=True)
    checks.append(("24-hour smoke run completes", smoke.returncode == 0, smoke.stdout.splitlines()[0] if smoke.stdout else smoke.stderr[:120]))
    checks.append(("history exports work", (PROJECT_ROOT / "data/outputs/stage3_smoke/states.csv").exists(), "data/outputs/stage3_smoke"))
    checks.append(("digital_twin_smoke.html exists", (PROJECT_ROOT / "artifacts/digital_twin_smoke.html").exists(), "artifacts/digital_twin_smoke.html"))

    text = "\n".join(path.read_text(encoding="utf-8") for path in sim_dir.glob("*.py"))
    lowered = text.lower()
    checks.append(("no CVXPY import in simulation modules", "cvxpy" not in lowered, "simulation package"))
    checks.append(("no Streamlit import in simulation modules", "streamlit" not in lowered, "simulation package"))
    checks.append(("no forecasting model code introduced", "sklearn" not in lowered and "fit(" not in lowered, "simulation package"))
    checks.append(("no MPC code introduced", "cvxpy" not in lowered and "solver" not in lowered, "simulation package"))

    print("check | result | detail")
    print("----- | ------ | ------")
    failed = False
    for name, ok, detail in checks:
        print(f"{name} | {'PASS' if ok else 'FAIL'} | {detail}")
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
