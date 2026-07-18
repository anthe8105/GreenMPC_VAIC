#!/usr/bin/env python
"""Fast packaging check for clone-time GreenMPC runtime assets.

This verifier intentionally does not run simulations, forecasts, model
training, benchmarks, or historical stage verifiers. It only proves that the
files needed by the web command center are present and repository-relative.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


REQUIRED_FILES = [
    "configs/demo.yaml",
    "configs/forecasting.yaml",
    "configs/mpc.yaml",
    "configs/evaluation.yaml",
    "configs/investment.yaml",
    "configs/selected_profiles.yaml",
    "data/processed/tenant_hourly.csv",
    "data/processed/park_hourly.csv",
    "data/processed/scenario_events.csv",
    "data/processed/selected_tenant_profiles.csv",
    "data/processed/dataset_manifest.json",
    "data/processed/data_quality_report.json",
    "data/provenance/processed_lineage.json",
    "data/provenance/raw_schema_report.json",
    "data/provenance/acquisitions.json",
    "models/forecasting/model_manifest.json",
    "data/outputs/stage6_benchmark/benchmark_manifest.json",
    "data/outputs/stage6_benchmark/benchmark_summary.json",
    "data/outputs/stage6_benchmark/controller_scenario_metrics.csv",
    "data/outputs/stage6_benchmark/paired_controller_comparison.csv",
    "data/outputs/stage6_benchmark/forecast_diagnostics.csv",
    "data/outputs/stage6_benchmark/runtime_metrics.csv",
    "data/outputs/stage6_audit/terminal_inventory_adjusted_costs.csv",
    "data/outputs/stage6_audit/terminal_inventory_sensitivity.csv",
    "data/outputs/stage6_audit/terminal_inventory_rankings.csv",
    "data/outputs/stage6_audit/terminal_inventory_adjustment_summary.json",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/vite.config.ts",
    "frontend/src/main.tsx",
    "frontend/src/App.tsx",
    "backend/main.py",
    "scripts/run_command_center.py",
]

RUNTIME_SOURCE_GLOBS = [
    "backend/**/*.py",
    "src/greenmpc/**/*.py",
    "scripts/run_command_center.py",
    "frontend/src/**/*",
    "configs/*.yaml",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_check_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", path],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def git_is_versionable(path: str) -> bool:
    """Return True when the path is tracked, staged, or not ignored."""

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if tracked.returncode == 0:
        return True
    return not git_check_ignored(path)


def check_required_files() -> Check:
    missing = [p for p in REQUIRED_FILES if not (ROOT / p).exists()]
    ignored = [p for p in REQUIRED_FILES if (ROOT / p).exists() and not git_is_versionable(p)]
    problems = []
    if missing:
        problems.append(f"missing={missing}")
    if ignored:
        problems.append(f"ignored={ignored}")
    if problems:
        return Check("required runtime files", False, "; ".join(problems))
    return Check("required runtime files", True, f"{len(REQUIRED_FILES)} files present and versionable")


def check_model_registry() -> Check:
    manifest_path = ROOT / "models/forecasting/model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    models = manifest.get("models", [])
    missing = []
    bad_hash = []
    for model in models:
        rel = Path("models/forecasting") / model["relative_path"]
        path = ROOT / rel
        if not path.exists():
            missing.append(str(rel))
            continue
        expected = model.get("artifact_sha256")
        if expected and sha256(path) != expected:
            bad_hash.append(str(rel))
    joblibs = sorted((ROOT / "models/forecasting").glob("**/*.joblib"))
    count_ok = len(models) == 36 and int(manifest.get("model_count", -1)) == 36 and len(joblibs) == 36
    if missing or bad_hash or not count_ok:
        return Check(
            "forecasting model artifacts",
            False,
            f"manifest_models={len(models)} joblibs={len(joblibs)} missing={missing[:5]} bad_hash={bad_hash[:5]}",
        )
    return Check("forecasting model artifacts", True, "36 manifest entries and 36 joblib artifacts verified")


def check_dataset_model_fingerprints() -> Check:
    dataset = json.loads((ROOT / "data/processed/dataset_manifest.json").read_text(encoding="utf-8"))
    model = json.loads((ROOT / "models/forecasting/model_manifest.json").read_text(encoding="utf-8"))
    model_fp = model.get("fingerprints", {})
    expected = {
        "tenant_hourly_csv_sha256": sha256(ROOT / "data/processed/tenant_hourly.csv"),
        "park_hourly_csv_sha256": sha256(ROOT / "data/processed/park_hourly.csv"),
        "selected_tenant_profiles_csv_sha256": sha256(ROOT / "data/processed/selected_tenant_profiles.csv"),
        "selected_profiles_lock_yaml_sha256": sha256(ROOT / "configs/selected_profiles.yaml"),
        "forecasting_config_yaml_sha256": sha256(ROOT / "configs/forecasting.yaml"),
    }
    mismatches = {k: {"manifest": model_fp.get(k), "actual": v} for k, v in expected.items() if model_fp.get(k) != v}
    dataset_outputs = dataset.get("output_fingerprints", {})
    dataset_mismatches = {
        "tenant_hourly_path": dataset_outputs.get("tenant_hourly_path") != expected["tenant_hourly_csv_sha256"],
        "park_hourly_path": dataset_outputs.get("park_hourly_path") != expected["park_hourly_csv_sha256"],
        "selected_profiles_path": dataset_outputs.get("selected_profiles_path") != expected["selected_tenant_profiles_csv_sha256"],
    }
    failed_dataset = [k for k, failed in dataset_mismatches.items() if failed]
    if mismatches or failed_dataset:
        return Check("dataset/model fingerprints", False, f"model={mismatches} dataset={failed_dataset}")
    return Check("dataset/model fingerprints", True, "processed data, selected profiles, and model registry match")


def check_stage6_manifest() -> Check:
    manifest = json.loads((ROOT / "data/outputs/stage6_benchmark/benchmark_manifest.json").read_text(encoding="utf-8"))
    requested = manifest.get("requested_hours")
    completed = manifest.get("completed_hours")
    ok = bool(manifest.get("completed_successfully")) and requested == completed == 72
    partial_markers = [
        "data/outputs/stage6_benchmark/.partial",
        "data/outputs/stage6_benchmark/PARTIAL",
        "data/outputs/stage6_benchmark/partial_manifest.json",
    ]
    present_markers = [p for p in partial_markers if (ROOT / p).exists()]
    if not ok or present_markers:
        return Check("Stage 6 compact evidence", False, f"requested={requested} completed={completed} partial_markers={present_markers}")
    return Check("Stage 6 compact evidence", True, "completed 72-hour manifest and compact summary files present")


def check_runtime_paths() -> Check:
    offenders: list[str] = []
    for pattern in RUNTIME_SOURCE_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file() and "node_modules" not in path.parts and "dist" not in path.parts:
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if "/Users/" in text or "/home/" in text or "C:\\Users\\" in text:
                    offenders.append(str(path.relative_to(ROOT)))
    if offenders:
        return Check("repository-relative runtime paths", False, ", ".join(sorted(offenders)[:20]))
    return Check("repository-relative runtime paths", True, "runtime source/config has no local absolute paths")


def check_imports() -> Check:
    try:
        importlib.import_module("backend.main")
        importlib.import_module("scripts.run_command_center")
    except Exception as exc:  # noqa: BLE001 - packaging diagnostic should report exact import failure.
        return Check("FastAPI and launcher imports", False, repr(exc))
    return Check("FastAPI and launcher imports", True, "backend.main and run_command_center import successfully")


def main() -> int:
    checks = [
        check_required_files(),
        check_model_registry(),
        check_dataset_model_fingerprints(),
        check_stage6_manifest(),
        check_runtime_paths(),
        check_imports(),
    ]
    width = max(len(check.name) for check in checks)
    print("Runtime Asset Verification")
    print("=" * 72)
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{check.name:<{width}}  {status:<4}  {check.detail}")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
