from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd
import yaml

from greenmpc.config import load_config
from greenmpc.data.dataset_builder import PROJECT_ROOT, load_dataset_build_config
from greenmpc.data.processed_validation import (
    SIMULATION_FORBIDDEN_COLUMNS,
    validate_event_catalog,
    validate_park_hourly,
    validate_selected_profiles,
    validate_tenant_hourly,
)


def _run(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    ok, detail = _run([sys.executable, "scripts/verify_stage0.py"])
    checks.append(("Stage 0 verification", ok, detail.splitlines()[0] if detail else ""))
    ok, detail = _run([sys.executable, "scripts/verify_stage1.py"])
    checks.append(("Stage 1 verification", ok, detail.splitlines()[0] if detail else ""))
    try:
        cfg = load_dataset_build_config(PROJECT_ROOT / "configs/dataset_build.yaml")
        demo = load_config(PROJECT_ROOT / "configs/demo.yaml")
        checks.append(("dataset-build configuration loads", True, "loaded"))
    except Exception as exc:
        print(f"FAIL config: {exc}")
        return 1

    paths = {name: PROJECT_ROOT / value for name, value in cfg.outputs.__dict__.items()}
    lock_path = PROJECT_ROOT / "configs/selected_profiles.yaml"
    checks.append(("selected-profile lock exists", lock_path.exists(), str(lock_path)))
    if lock_path.exists():
        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
        selected_clients = [row["source_client_id"] for row in lock["selected_profiles"].values()]
        checks.append(("five unique source clients", len(set(selected_clients)) == 5, str(selected_clients)))
        archetypes = {row["archetype"] for row in lock["selected_profiles"].values()}
        checks.append(("archetype mapping complete", len(archetypes) == 5, str(sorted(archetypes))))

    for key in ["tenant_hourly_path", "park_hourly_path", "event_catalog_path", "steel_reference_path", "dataset_manifest_path", "data_quality_report_path", "processed_lineage_path", "overview_artifact_path"]:
        checks.append((f"{key} exists", paths[key].exists(), str(paths[key])))

    try:
        tenant = pd.read_csv(paths["tenant_hourly_path"])
        park = pd.read_csv(paths["park_hourly_path"])
        events = pd.read_csv(paths["event_catalog_path"])
        selected = pd.read_csv(paths["selected_profiles_path"])
        validate_selected_profiles(selected, [tenant.tenant_id for tenant in demo.tenants])
        validate_tenant_hourly(tenant, demo, cfg)
        validate_park_hourly(park, tenant, cfg)
        validate_event_catalog(events, tenant, [tenant.tenant_id for tenant in demo.tenants])
        checks.extend([
            ("tenant-hourly validation", True, str(len(tenant))),
            ("park-hourly validation", True, str(len(park))),
            ("event validation", True, str(len(events))),
            ("park load equals tenant sum", True, "validated"),
            ("PV within capacity", park["pv_available_kw"].le(cfg.pv.installed_capacity_kw * cfg.pv.maximum_output_fraction + 1e-6).all(), "capacity cap"),
            ("timestamps include local and UTC offsets", tenant["timestamp_local"].str.contains("+07:00", regex=False).all() and tenant["timestamp_utc"].str.contains("+00:00", regex=False).all(), "timezone-aware strings"),
            ("no actual-VRG flags", not tenant["load_is_actual_vrg_data"].any(), "false"),
            ("no measured-PV flags", not tenant["pv_is_measured"].any(), "false"),
            ("tariff category unselected", not park["tariff_category_selected"].any(), "false"),
            ("DPPA assumptions explicit", park["dppa_availability_is_assumption"].all() and park["dppa_price_is_assumption"].all(), "true"),
            ("events not applied to baseline", not events["applied_to_baseline_dataset"].any(), "false"),
            ("no controller/simulation fields", not SIMULATION_FORBIDDEN_COLUMNS.intersection(tenant.columns).union(SIMULATION_FORBIDDEN_COLUMNS.intersection(park.columns)), "none"),
        ])
    except Exception as exc:
        checks.append(("processed validation", False, str(exc)))

    try:
        manifest = json.loads(paths["dataset_manifest_path"].read_text(encoding="utf-8"))
        checks.append(("processed files fingerprinted", bool(manifest.get("output_fingerprints")), "manifest output_fingerprints"))
    except Exception as exc:
        checks.append(("processed files fingerprinted", False, str(exc)))

    print("check | result | detail")
    print("----- | ------ | ------")
    failed = False
    for name, passed, detail in checks:
        print(f"{name} | {'PASS' if passed else 'FAIL'} | {detail}")
        failed = failed or not passed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
