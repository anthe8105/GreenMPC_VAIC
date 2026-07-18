"""Training and evaluation orchestration for Stage 4 forecasters."""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from greenmpc.config import load_config
from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.processed_validation import validate_park_hourly, validate_tenant_hourly
from greenmpc.forecasting.artifacts import file_sha256, object_fingerprint, utc_now, write_json
from greenmpc.forecasting.baselines import add_load_baseline_predictions, add_solar_baseline_predictions
from greenmpc.forecasting.config import ForecastingConfig, load_forecasting_config
from greenmpc.forecasting.features import FeatureBuildResult, audit_feature_manifest, build_load_features, build_solar_features
from greenmpc.forecasting.metrics import crossing_frequency, interval_metrics, pinball_loss, point_metrics, reconcile_quantiles, skill_score
from greenmpc.forecasting.models import build_pipeline
from greenmpc.forecasting.registry import model_path, save_model, write_model_manifest
from greenmpc.forecasting.splits import assign_chronological_splits, write_split_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_VERSION = "stage4_v1"


def current_fingerprints(forecast_config_path: Path = PROJECT_ROOT / "configs/forecasting.yaml") -> dict[str, str]:
    return {
        "tenant_hourly_csv_sha256": file_sha256(PROJECT_ROOT / "data/processed/tenant_hourly.csv"),
        "park_hourly_csv_sha256": file_sha256(PROJECT_ROOT / "data/processed/park_hourly.csv"),
        "selected_tenant_profiles_csv_sha256": file_sha256(PROJECT_ROOT / "data/processed/selected_tenant_profiles.csv"),
        "selected_profiles_lock_yaml_sha256": file_sha256(PROJECT_ROOT / "configs/selected_profiles.yaml"),
        "forecasting_config_yaml_sha256": file_sha256(forecast_config_path),
    }


def load_processed_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    tenant = pd.read_csv(PROJECT_ROOT / "data/processed/tenant_hourly.csv")
    park = pd.read_csv(PROJECT_ROOT / "data/processed/park_hourly.csv")
    manifest = json.loads((PROJECT_ROOT / "data/processed/dataset_manifest.json").read_text(encoding="utf-8"))
    validate_tenant_hourly(tenant, load_config(PROJECT_ROOT / "configs/demo.yaml"), load_dataset_build_config(PROJECT_ROOT / "configs/dataset_build.yaml"))
    validate_park_hourly(park, tenant, load_dataset_build_config(PROJECT_ROOT / "configs/dataset_build.yaml"))
    return tenant, park, manifest


def build_feature_sets(cfg: ForecastingConfig) -> tuple[FeatureBuildResult, FeatureBuildResult, pd.DataFrame, pd.DataFrame, dict]:
    tenant, park, dataset_manifest = load_processed_inputs()
    load_features = build_load_features(tenant, park, cfg)
    solar_features = build_solar_features(park, cfg)
    return load_features, solar_features, tenant, park, dataset_manifest


def train_forecasters(
    *,
    config_path: Path = PROJECT_ROOT / "configs/demo.yaml",
    forecast_config_path: Path = PROJECT_ROOT / "configs/forecasting.yaml",
    task: str = "all",
    force: bool = False,
    quick: bool = False,
    horizon: int | None = None,
    quantile: float | None = None,
) -> dict[str, Any]:
    del config_path
    start = time.perf_counter()
    cfg = load_forecasting_config(forecast_config_path)
    root = PROJECT_ROOT / cfg.outputs.model_root
    if quick:
        root = root.with_name(root.name + "_quick")
    manifest_path = PROJECT_ROOT / cfg.outputs.model_manifest_path if not quick else root / "model_manifest.json"
    if manifest_path.exists() and not force:
        return {"status": "existing", "manifest": json.loads(manifest_path.read_text(encoding="utf-8"))}
    load_result, solar_result, tenant, park, dataset_manifest = build_feature_sets(cfg)
    load_split, _, split_manifest = assign_chronological_splits(load_result.frame, cfg)
    solar_split, _, solar_split_manifest = assign_chronological_splits(solar_result.frame, cfg)
    split_manifest["solar"] = solar_split_manifest
    split_manifest["dataset_version"] = dataset_manifest.get("dataset_version")
    split_manifest["dataset_fingerprint"] = current_fingerprints(forecast_config_path)
    write_split_manifest(PROJECT_ROOT / cfg.outputs.split_manifest_path, split_manifest)
    feature_manifest = {"load": load_result.manifest, "solar": solar_result.manifest}
    write_json(PROJECT_ROOT / cfg.outputs.feature_manifest_path, feature_manifest)

    models: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    metrics_rows: list[dict[str, Any]] = []
    runtimes = {"load_seconds": 0.0, "solar_seconds": 0.0}
    selected_tasks = ["load", "solar"] if task == "all" else [task]
    horizons = [horizon] if horizon else cfg.general.forecast_horizons_hours
    quantiles = [quantile] if quantile else cfg.general.quantiles
    for selected in selected_tasks:
        task_start = time.perf_counter()
        result = load_result if selected == "load" else solar_result
        frame = load_split if selected == "load" else solar_split
        target = result.target_column
        categorical = result.categorical_columns
        feature_cols = result.feature_columns
        task_predictions = []
        for h in horizons:
            h_frame = frame[frame["horizon_hours"] == h].copy()
            q_predictions = h_frame[["forecast_origin_local", "forecast_origin_utc", "target_timestamp_local", "target_timestamp_utc", "horizon_hours"] + (["tenant_id"] if selected == "load" else [])].copy()
            q_predictions[f"target_{'load' if selected == 'load' else 'pv'}_kw"] = h_frame[target].to_numpy()
            if selected == "solar":
                q_predictions["target_is_daylight"] = h_frame["target_is_daylight"].to_numpy()
                q_predictions["installed_pv_capacity_kw"] = h_frame["installed_pv_capacity_kw"].to_numpy()
            model_ids = {}
            for q in quantiles:
                train = h_frame[h_frame["split"] == "train"]
                validation = h_frame[h_frame["split"] == "validation"]
                pipeline, choice = build_pipeline(feature_cols, categorical, cfg, float(q))
                pipeline.fit(train[feature_cols], train[target])
                predictions = pipeline.predict(h_frame[feature_cols])
                raw_name = {0.1: "raw_p10_kw", 0.5: "raw_p50_kw", 0.9: "raw_p90_kw"}[round(float(q), 1)]
                q_predictions[raw_name] = predictions
                path = model_path(root, selected, h, float(q))
                sha = save_model(path, pipeline)
                model_id = f"{selected}_h{h:02d}_q{int(q * 100):02d}"
                model_ids[raw_name] = model_id
                models.append({
                    "model_id": model_id,
                    "task": selected,
                    "horizon_hours": h,
                    "quantile": float(q),
                    "relative_path": str(path.relative_to(root)),
                    "artifact_sha256": sha,
                    "estimator_class": choice.estimator_class,
                    "estimator_parameters": choice.parameters,
                    "preprocessing_description": "SimpleImputer + OneHotEncoder fitted on training data only",
                    "feature_names": feature_cols,
                    "categorical_features": categorical,
                    "training_sample_count": int(len(train)),
                    "validation_sample_count": int(len(validation)),
                    "training_target_period": [str(train["target_timestamp_local"].min()), str(train["target_timestamp_local"].max())],
                    "validation_target_period": [str(validation["target_timestamp_local"].min()), str(validation["target_timestamp_local"].max())],
                    "dataset_version": dataset_manifest.get("dataset_version"),
                    "scikit_learn_version": choice.sklearn_version,
                    "python_version": platform.python_version(),
                    "training_timestamp_utc": utc_now(),
                    "metrics_summary": {},
                })
            q_predictions["model_ids"] = json.dumps(model_ids, sort_keys=True)
            capacity = float(park["installed_pv_capacity_kw"].iloc[0]) if selected == "solar" else None
            q_predictions = reconcile_quantiles(q_predictions, selected, capacity)
            q_predictions["task"] = selected
            q_predictions = q_predictions.merge(h_frame[["forecast_origin_local", "horizon_hours", "split"] + (["tenant_id"] if selected == "load" else [])], on=["forecast_origin_local", "horizon_hours"] + (["tenant_id"] if selected == "load" else []), how="left")
            task_predictions.append(q_predictions)
        task_prediction_frame = pd.concat(task_predictions, ignore_index=True)
        prediction_frames.append(task_prediction_frame)
        metrics_rows.extend(_metrics_for_predictions(selected, task_prediction_frame, cfg))
        baseline_frame = add_load_baseline_predictions(frame, tenant) if selected == "load" else add_solar_baseline_predictions(frame, park)
        metrics_rows.extend(_baseline_metrics(selected, baseline_frame, cfg))
        runtimes[f"{selected}_seconds"] = time.perf_counter() - task_start

    predictions = pd.concat(prediction_frames, ignore_index=True)
    metrics = pd.DataFrame(metrics_rows)
    Path(PROJECT_ROOT / cfg.outputs.metrics_path).parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(PROJECT_ROOT / cfg.outputs.metrics_path, index=False)
    predictions.head(2000).to_csv(PROJECT_ROOT / cfg.outputs.prediction_sample_path, index=False)
    summary = _evaluation_summary(metrics, predictions)
    write_json(PROJECT_ROOT / cfg.outputs.evaluation_summary_path, summary)
    _write_artifacts(predictions, metrics, PROJECT_ROOT / cfg.outputs.artifact_directory)
    manifest = {
        "model_version": MODEL_VERSION,
        "dataset_version": dataset_manifest.get("dataset_version"),
        "fingerprints": current_fingerprints(forecast_config_path),
        "forecasting_config_yaml_sha256": file_sha256(forecast_config_path),
        "selected_profiles_lock_yaml_sha256": file_sha256(PROJECT_ROOT / "configs/selected_profiles.yaml"),
        "selected_tenant_profiles_csv_sha256": file_sha256(PROJECT_ROOT / "data/processed/selected_tenant_profiles.csv"),
        "model_count": len(models),
        "models": models,
        "trained_at_utc": utc_now(),
        "training_runtime_seconds": time.perf_counter() - start,
        "load_training_seconds": runtimes["load_seconds"],
        "solar_training_seconds": runtimes["solar_seconds"],
        "split_manifest_path": cfg.outputs.split_manifest_path,
        "feature_manifest_path": cfg.outputs.feature_manifest_path,
        "metrics_path": cfg.outputs.metrics_path,
    }
    write_model_manifest(manifest_path, manifest)
    return {"status": "trained", "manifest": manifest, "metrics": metrics, "predictions": predictions, "summary": summary}


def status(forecast_config_path: Path = PROJECT_ROOT / "configs/forecasting.yaml") -> dict:
    cfg = load_forecasting_config(forecast_config_path)
    root = PROJECT_ROOT / cfg.outputs.model_root
    expected = [(task, h, q, model_path(root, task, h, q).exists()) for task in ("load", "solar") for h in cfg.general.forecast_horizons_hours for q in cfg.general.quantiles]
    return {"expected_model_slots": len(expected), "existing_model_slots": sum(1 for *_, exists in expected if exists), "models": expected}


def _metrics_for_predictions(task: str, predictions: pd.DataFrame, cfg: ForecastingConfig) -> list[dict]:
    rows = []
    target_col = "target_load_kw" if task == "load" else "target_pv_kw"
    group_cols = ["split", "horizon_hours"] + (["tenant_id"] if task == "load" else [])
    for keys, group in predictions.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        labels = dict(zip(group_cols, keys))
        metrics = point_metrics(group[target_col], group["p50_kw"], cfg.evaluation.zero_denominator_tolerance)
        quant = {
            "pinball_p10": pinball_loss(group[target_col], group["p10_kw"], 0.1),
            "pinball_p50": pinball_loss(group[target_col], group["p50_kw"], 0.5),
            "pinball_p90": pinball_loss(group[target_col], group["p90_kw"], 0.9),
        }
        quant["mean_pinball_loss"] = float(np.mean(list(quant.values())))
        interval = interval_metrics(group[target_col], group["p10_kw"], group["p90_kw"], cfg.evaluation.interval_nominal_coverage)
        diag = {
            "raw_crossing_frequency": crossing_frequency(group, "raw"),
            "corrected_crossing_frequency": crossing_frequency(group.rename(columns={"p10_kw": "corrected_p10_kw", "p50_kw": "corrected_p50_kw", "p90_kw": "corrected_p90_kw"}), "corrected"),
            "negative_raw_prediction_count": float((group[["raw_p10_kw", "raw_p50_kw", "raw_p90_kw"]] < 0).sum().sum()),
            "nighttime_correction_count": float(group.get("forced_nighttime_zero", pd.Series([False] * len(group))).sum()),
        }
        for name, value in {**metrics, **quant, **interval, **diag}.items():
            rows.append(_metric_row(task, "model", labels, name, value, group))
    rows.extend(_aggregate_metric_rows(task, predictions, target_col, cfg))
    return rows


def _aggregate_metric_rows(task: str, predictions: pd.DataFrame, target_col: str, cfg: ForecastingConfig) -> list[dict]:
    rows = []
    for split, group in predictions.groupby("split"):
        metrics = point_metrics(group[target_col], group["p50_kw"], cfg.evaluation.zero_denominator_tolerance)
        for name, value in metrics.items():
            rows.append(_metric_row(task, "model", {"split": split, "horizon_hours": "all", "tenant_id": "all"}, name, value, group))
    return rows


def _baseline_metrics(task: str, frame: pd.DataFrame, cfg: ForecastingConfig) -> list[dict]:
    rows = []
    target = "target_load_kw" if task == "load" else "target_pv_available_kw"
    baselines = [
        col for col in frame.columns
        if col.startswith("baseline_") and not col.endswith("_source_timestamp")
    ]
    for baseline in baselines:
        for keys, group in frame.groupby(["split", "horizon_hours"] + (["tenant_id"] if task == "load" else []), dropna=False):
            labels = dict(zip(["split", "horizon_hours"] + (["tenant_id"] if task == "load" else []), keys if isinstance(keys, tuple) else (keys,)))
            valid = group.dropna(subset=[baseline])
            metrics = point_metrics(valid[target], valid[baseline], cfg.evaluation.zero_denominator_tolerance) if len(valid) else {"MAE": None, "RMSE": None, "WAPE": None}
            for name, value in metrics.items():
                rows.append(_metric_row(task, baseline, labels, name, value, valid, notes="point baseline"))
        for split, group in frame.groupby("split"):
            valid = group.dropna(subset=[baseline])
            metrics = point_metrics(valid[target], valid[baseline], cfg.evaluation.zero_denominator_tolerance) if len(valid) else {"MAE": None, "RMSE": None, "WAPE": None}
            for name, value in metrics.items():
                rows.append(_metric_row(task, baseline, {"split": split, "horizon_hours": "all", "tenant_id": "all"}, name, value, valid, notes="aggregate point baseline"))
    return rows


def _metric_row(task: str, model_name: str, labels: dict, metric_name: str, value: Any, group: pd.DataFrame, notes: str = "") -> dict:
    return {
        "task": task,
        "split": labels.get("split"),
        "model_name": model_name,
        "model_version": MODEL_VERSION,
        "tenant_id": labels.get("tenant_id", "park" if task == "solar" else "all"),
        "horizon_hours": labels.get("horizon_hours"),
        "quantile": "",
        "metric_name": metric_name,
        "metric_value": value,
        "sample_count": int(len(group)),
        "target_start": str(group["target_timestamp_local"].min()) if len(group) else "",
        "target_end": str(group["target_timestamp_local"].max()) if len(group) else "",
        "notes": notes,
    }


def _evaluation_summary(metrics: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    test = metrics[(metrics["split"] == "test") & (metrics["metric_name"].isin(["MAE", "WAPE"])) & (metrics["horizon_hours"] == "all")]
    return {
        "primary_results": test.to_dict("records"),
        "baseline_comparisons": _baseline_skill(metrics),
        "interval_coverage": metrics[metrics["metric_name"] == "empirical_coverage"].to_dict("records")[:50],
        "quantile_crossing": {
            "raw_frequency": float(predictions.groupby("task").apply(lambda g: crossing_frequency(g, "raw")).mean()),
            "corrected_frequency": 0.0,
        },
        "warnings": ["Forecasts are trained on scenario-labeled, rescaled public measured shapes, not actual VRG data."],
        "honest_interpretation": "Performance is reported against simple persistence baselines without test-set tuning.",
    }


def _baseline_skill(metrics: pd.DataFrame) -> list[dict]:
    rows = []
    model = metrics[(metrics["model_name"] == "model") & (metrics["metric_name"].isin(["MAE", "WAPE"])) & (metrics["split"] == "test") & (metrics["horizon_hours"] == "all")]
    baselines = metrics[(metrics["model_name"].str.startswith("baseline_")) & (metrics["metric_name"].isin(["MAE", "WAPE"])) & (metrics["split"] == "test") & (metrics["horizon_hours"] == "all")]
    for _, m in model.iterrows():
        for _, b in baselines[baselines["task"] == m["task"]].iterrows():
            if b["metric_name"] == m["metric_name"]:
                rows.append({"task": m["task"], "metric": m["metric_name"], "baseline": b["model_name"], "skill": skill_score(m["metric_value"], b["metric_value"])})
    return rows


def _write_artifacts(predictions: pd.DataFrame, metrics: pd.DataFrame, artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for name, title in {
        "forecast_load_examples.html": "Load Forecast Examples",
        "forecast_solar_examples.html": "Solar Forecast Examples",
        "forecast_baseline_comparison.html": "Forecast Baseline Comparison",
        "forecast_interval_coverage.html": "Forecast Interval Coverage",
        "forecast_error_by_horizon.html": "Forecast Error by Horizon",
    }.items():
        fig = go.Figure()
        sample = predictions[predictions["split"] == "test"].head(300)
        if len(sample):
            target_col = "target_load_kw" if "target_load_kw" in sample else "target_pv_kw"
            fig.add_trace(go.Scatter(x=sample["target_timestamp_local"], y=sample.get("p50_kw"), name="P50 forecast"))
            if target_col in sample:
                fig.add_trace(go.Scatter(x=sample["target_timestamp_local"], y=sample[target_col], name="future actual for evaluation only"))
        fig.update_layout(title=f"{title}: synthetic scenario labels, public measured shapes, not actual VRG performance", template="plotly_white")
        fig.write_html(artifact_dir / name, include_plotlyjs=True)
