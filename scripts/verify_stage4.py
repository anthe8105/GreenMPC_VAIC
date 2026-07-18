#!/usr/bin/env python
"""Verify Stage 4 forecasting acceptance checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.features import audit_feature_manifest
from greenmpc.forecasting.inference import ForecastService
from greenmpc.forecasting.registry import load_model, model_path, read_model_manifest, validate_registry_hashes
from greenmpc.forecasting.training import current_fingerprints


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    for script in ("verify_stage0.py", "verify_stage1.py", "verify_stage2.py", "verify_stage3.py"):
        result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / script)], cwd=PROJECT_ROOT, text=True, capture_output=True)
        checks.append((script, result.returncode == 0, result.stdout.splitlines()[0] if result.stdout else result.stderr[:120]))
    cfg = load_forecasting_config(PROJECT_ROOT / "configs/forecasting.yaml")
    checks.append(("forecasting configuration loads", True, "configs/forecasting.yaml"))
    manifest_path = PROJECT_ROOT / cfg.outputs.model_manifest_path
    split_path = PROJECT_ROOT / cfg.outputs.split_manifest_path
    feature_path = PROJECT_ROOT / cfg.outputs.feature_manifest_path
    metrics_path = PROJECT_ROOT / cfg.outputs.metrics_path
    checks.append(("split manifest exists", split_path.exists(), str(split_path)))
    checks.append(("feature manifest exists", feature_path.exists(), str(feature_path)))
    checks.append(("model manifest exists", manifest_path.exists(), str(manifest_path)))
    manifest = read_model_manifest(manifest_path)
    checks.append(("dataset fingerprints match", manifest.get("fingerprints") == current_fingerprints(), "current fingerprints"))
    fingerprint_keys = set(manifest.get("fingerprints", {}))
    checks.append(("selected-profile fingerprint keys are explicit", "selected_profiles" not in fingerprint_keys and {"selected_tenant_profiles_csv_sha256", "selected_profiles_lock_yaml_sha256"}.issubset(fingerprint_keys), str(sorted(fingerprint_keys))))
    load_models = [m for m in manifest.get("models", []) if m["task"] == "load"]
    solar_models = [m for m in manifest.get("models", []) if m["task"] == "solar"]
    checks.append(("18 load quantile models exist", len(load_models) == 18, str(len(load_models))))
    checks.append(("18 solar quantile models exist", len(solar_models) == 18, str(len(solar_models))))
    try:
        validate_registry_hashes(manifest, PROJECT_ROOT / cfg.outputs.model_root)
        for task in ("load", "solar"):
            for h in cfg.general.forecast_horizons_hours:
                for q in cfg.general.quantiles:
                    load_model(model_path(PROJECT_ROOT / cfg.outputs.model_root, task, h, q))
        checks.append(("all model artifacts load and hashes match", True, "36 artifacts"))
    except Exception as exc:
        checks.append(("all model artifacts load and hashes match", False, repr(exc)))
    feature_manifest = __import__("json").loads(feature_path.read_text(encoding="utf-8"))
    try:
        audit_feature_manifest(feature_manifest["load"])
        audit_feature_manifest(feature_manifest["solar"])
        checks.append(("feature leakage audit passes", True, "load and solar"))
    except Exception as exc:
        checks.append(("feature leakage audit passes", False, repr(exc)))
    load_features = feature_manifest["load"]["feature_columns"]
    solar_features = feature_manifest["solar"]["feature_columns"]
    checks.append(("future actual weather absent", not any("future" in c or c.startswith("target_temperature") for c in load_features + solar_features), "feature names"))
    service = ForecastService.from_registry()
    tenant = pd.read_csv(PROJECT_ROOT / "data/processed/tenant_hourly.csv")
    park = pd.read_csv(PROJECT_ROOT / "data/processed/park_hourly.csv")
    split = __import__("json").loads(split_path.read_text(encoding="utf-8"))
    origin = pd.Timestamp(split["test_target_start"]) - pd.Timedelta(hours=1)
    load_forecast, solar_forecast = service.forecast_all(tenant, park, origin, 6)
    checks.append(("six-hour load inference succeeds", len(load_forecast.predictions) == 30, str(len(load_forecast.predictions))))
    checks.append(("six-hour solar inference succeeds", len(solar_forecast.predictions) == 6, str(len(solar_forecast.predictions))))
    checks.append(("five tenants returned", load_forecast.predictions["tenant_id"].nunique() == 5, "tenant count"))
    checks.append(("quantiles ordered", ((load_forecast.predictions["p10_kw"] <= load_forecast.predictions["p50_kw"]) & (load_forecast.predictions["p50_kw"] <= load_forecast.predictions["p90_kw"])).all(), "load"))
    cap = float(park["installed_pv_capacity_kw"].iloc[0])
    checks.append(("solar respects physical limits", (solar_forecast.predictions[["p10_kw", "p50_kw", "p90_kw"]] <= cap + 1e-6).all().all(), f"cap={cap}"))
    checks.append(("nighttime solar zero", (solar_forecast.predictions.loc[solar_forecast.predictions["forced_nighttime_zero"], ["p10_kw", "p50_kw", "p90_kw"]] == 0).all().all(), "forced rows"))
    metrics = pd.read_csv(metrics_path)
    checks.append(("metrics file exists", metrics_path.exists(), str(metrics_path)))
    checks.append(("baseline metrics exist", metrics["model_name"].str.startswith("baseline_").any(), "baseline rows"))
    checks.append(("interval metrics exist", metrics["metric_name"].eq("empirical_coverage").any(), "coverage rows"))
    audit_paths = [
        "data/outputs/baseline_audit/solar_previous_day.csv",
        "data/outputs/baseline_audit/solar_previous_week.csv",
        "data/outputs/baseline_audit/solar_audit_summary.json",
        "data/outputs/baseline_audit/load_audit_summary.csv",
        "data/outputs/baseline_audit/root_cause.md",
        "data/outputs/baseline_audit/forecast_latency_audit.json",
        "data/outputs/forecast_latency_audit.json",
    ]
    for path in audit_paths:
        checks.append((f"{path} exists", (PROJECT_ROOT / path).exists(), path))
    try:
        audit = __import__("json").loads((PROJECT_ROOT / "data/outputs/baseline_audit/solar_audit_summary.json").read_text(encoding="utf-8"))
        day_rows = pd.read_csv(PROJECT_ROOT / "data/outputs/baseline_audit/solar_previous_day.csv")
        week_rows = pd.read_csv(PROJECT_ROOT / "data/outputs/baseline_audit/solar_previous_week.csv")
        checks.append(("solar audit stores lag source timestamps", {"baseline_source_timestamp", "target_timestamp"}.issubset(day_rows.columns), "solar audit columns"))
        checks.append(("solar previous-day source differs from target", (pd.to_datetime(day_rows["baseline_source_timestamp"]) != pd.to_datetime(day_rows["target_timestamp"])).all(), "minus 24h"))
        checks.append(("solar previous-week source differs from target", (pd.to_datetime(week_rows["baseline_source_timestamp"]) != pd.to_datetime(week_rows["target_timestamp"])).all(), "minus 168h"))
        checks.append(("PV integrity audit completed", "pv_integrity" in audit and audit["pv_integrity"]["unique_solar_resource_values"] > 1, "raw solar variation"))
        checks.append(("latency audit deterministic", bool(audit["latency"]["deterministic_predictions"]) and not bool(audit["latency"]["models_reloaded_per_call"]), "cache and determinism"))
    except Exception as exc:
        checks.append(("baseline audit outputs are readable", False, repr(exc)))
    for path in [
        "data/outputs/stage4_example/load_forecast.csv",
        "data/outputs/stage4_example/solar_forecast.csv",
        "artifacts/forecast_example.html",
        "artifacts/forecast_load_examples.html",
        "artifacts/forecast_solar_examples.html",
        "artifacts/forecast_baseline_comparison.html",
        "artifacts/forecast_interval_coverage.html",
        "artifacts/forecast_error_by_horizon.html",
    ]:
        checks.append((f"{path} exists", (PROJECT_ROOT / path).exists(), path))
    sim_text = "\n".join(path.read_text(encoding="utf-8").lower() for path in (PROJECT_ROOT / "src/greenmpc/simulation").glob("*.py"))
    forecast_text = "\n".join(path.read_text(encoding="utf-8").lower() for path in (PROJECT_ROOT / "src/greenmpc/forecasting").glob("*.py"))
    checks.append(("no forecasting code inside simulator", "greenmpc.forecasting" not in sim_text, "simulation package"))
    checks.append(("no CVXPY or MPC implementation", "cvxpy" not in forecast_text and "cvxpy." not in forecast_text and "control." not in forecast_text, "forecasting package"))
    print("check | result | detail")
    print("----- | ------ | ------")
    failed = False
    for name, ok, detail in checks:
        print(f"{name} | {'PASS' if ok else 'FAIL'} | {detail}")
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
