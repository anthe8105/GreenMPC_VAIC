"""Inference API for persisted Stage 4 forecasters."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.forecasting.config import ForecastingConfig, load_forecasting_config
from greenmpc.forecasting.exceptions import ForecastDataError
from greenmpc.forecasting.features import build_load_features, build_solar_features
from greenmpc.forecasting.metrics import reconcile_quantiles
from greenmpc.forecasting.registry import load_model, model_path, read_model_manifest, validate_compatibility
from greenmpc.forecasting.training import PROJECT_ROOT, current_fingerprints


@dataclass(frozen=True)
class ForecastMetadata:
    forecast_id: str
    task: str
    forecast_origin_local: str
    forecast_origin_utc: str
    horizon_hours: int
    model_version: str
    dataset_version: str
    generated_at_utc: str
    quantile_reconciliation_applied: bool
    data_quality_flags: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class TenantLoadForecast:
    metadata: ForecastMetadata
    predictions: pd.DataFrame

    def to_dataframe(self) -> pd.DataFrame:
        return self.predictions.copy(deep=True)

    def to_dict(self) -> dict[str, Any]:
        return {"metadata": asdict(self.metadata), "predictions": self.predictions.to_dict("records")}

    def validate(self) -> None:
        if self.predictions["tenant_id"].nunique() != 5:
            raise ForecastDataError("tenant load forecast must include five tenants")
        _validate_quantiles(self.predictions)


@dataclass(frozen=True)
class ParkSolarForecast:
    metadata: ForecastMetadata
    predictions: pd.DataFrame

    def to_dataframe(self) -> pd.DataFrame:
        return self.predictions.copy(deep=True)

    def to_dict(self) -> dict[str, Any]:
        return {"metadata": asdict(self.metadata), "predictions": self.predictions.to_dict("records")}

    def validate(self) -> None:
        _validate_quantiles(self.predictions)
        if (self.predictions[["p10_kw", "p50_kw", "p90_kw"]] < 0).any().any():
            raise ForecastDataError("solar forecast contains negative values")


class ForecastService:
    def __init__(self, cfg: ForecastingConfig, manifest: dict, model_root: Path) -> None:
        self.cfg = cfg
        self.manifest = manifest
        self.model_root = model_root
        self._model_cache: dict[tuple[str, int, float], object] = {}
        self._load_feature_cache: dict[tuple[int, int, str, str, str, str], pd.DataFrame] = {}
        self._solar_feature_cache: dict[tuple[int, str, str], pd.DataFrame] = {}
        validate_compatibility(manifest, current_fingerprints(), cfg.general.reject_dataset_fingerprint_mismatch)

    @classmethod
    def from_registry(cls, forecast_config_path: str | Path = PROJECT_ROOT / "configs/forecasting.yaml") -> "ForecastService":
        cfg = load_forecasting_config(forecast_config_path)
        manifest = read_model_manifest(PROJECT_ROOT / cfg.outputs.model_manifest_path)
        return cls(cfg, manifest, PROJECT_ROOT / cfg.outputs.model_root)

    def forecast_tenant_load(self, tenant_history: pd.DataFrame, park_history: pd.DataFrame, forecast_origin: pd.Timestamp, horizon_hours: int = 6) -> TenantLoadForecast:
        rows = self._origin_load_rows(tenant_history.copy(deep=True), park_history.copy(deep=True), forecast_origin, horizon_hours)
        predictions = self._predict_rows("load", rows, "target_load_kw", horizon_hours)
        metadata = _metadata("load", forecast_origin, horizon_hours, self.manifest, predictions["quantile_corrected"].any())
        result = TenantLoadForecast(metadata, predictions)
        result.validate()
        return result

    def forecast_park_solar(self, park_history: pd.DataFrame, forecast_origin: pd.Timestamp, horizon_hours: int = 6) -> ParkSolarForecast:
        rows = self._origin_solar_rows(park_history.copy(deep=True), forecast_origin, horizon_hours)
        predictions = self._predict_rows("solar", rows, "target_pv_available_kw", horizon_hours)
        metadata = _metadata("solar", forecast_origin, horizon_hours, self.manifest, predictions["quantile_corrected"].any())
        result = ParkSolarForecast(metadata, predictions)
        result.validate()
        return result

    def forecast_all(self, tenant_history: pd.DataFrame, park_history: pd.DataFrame, forecast_origin: pd.Timestamp, horizon_hours: int = 6) -> tuple[TenantLoadForecast, ParkSolarForecast]:
        return (
            self.forecast_tenant_load(tenant_history, park_history, forecast_origin, horizon_hours),
            self.forecast_park_solar(park_history, forecast_origin, horizon_hours),
        )

    def _origin_load_rows(self, tenant: pd.DataFrame, park: pd.DataFrame, origin: pd.Timestamp, horizon_hours: int) -> pd.DataFrame:
        if horizon_hours < 1 or horizon_hours > 6:
            raise ForecastDataError("horizon_hours must be between 1 and 6")
        origin = pd.Timestamp(origin)
        tenant["timestamp_local"] = pd.to_datetime(tenant["timestamp_local"])
        park["timestamp_local"] = pd.to_datetime(park["timestamp_local"])
        tenant_cut = tenant.copy()
        park_cut = park.copy()
        if origin not in set(tenant_cut["timestamp_local"]):
            raise ForecastDataError("forecast origin must exist in tenant history")
        if tenant_cut["tenant_id"].nunique() != 5:
            raise ForecastDataError("all five tenants must have sufficient history")
        built = self._cached_load_features(tenant_cut, park_cut)
        rows = built[built["forecast_origin_local"] == origin]
        rows = rows[rows["horizon_hours"] <= horizon_hours]
        if rows["horizon_hours"].nunique() != horizon_hours or len(rows) != horizon_hours * 5:
            raise ForecastDataError("insufficient history for requested load horizon")
        return rows

    def _origin_solar_rows(self, park: pd.DataFrame, origin: pd.Timestamp, horizon_hours: int) -> pd.DataFrame:
        if horizon_hours < 1 or horizon_hours > 6:
            raise ForecastDataError("horizon_hours must be between 1 and 6")
        origin = pd.Timestamp(origin)
        park["timestamp_local"] = pd.to_datetime(park["timestamp_local"])
        park_cut = park.copy()
        if origin not in set(park_cut["timestamp_local"]):
            raise ForecastDataError("forecast origin must exist in park history")
        built = self._cached_solar_features(park_cut)
        rows = built[(built["forecast_origin_local"] == origin) & (built["horizon_hours"] <= horizon_hours)]
        if rows["horizon_hours"].nunique() != horizon_hours:
            raise ForecastDataError("insufficient history for requested solar horizon")
        return rows

    def _predict_rows(self, task: str, rows: pd.DataFrame, target_col: str, horizon_hours: int) -> pd.DataFrame:
        output = rows[["forecast_origin_local", "forecast_origin_utc", "target_timestamp_local", "target_timestamp_utc", "horizon_hours"] + (["tenant_id"] if task == "load" else [])].copy()
        if task == "solar":
            output["target_is_daylight"] = rows["target_is_daylight"].to_numpy()
            output["installed_pv_capacity_kw"] = rows["installed_pv_capacity_kw"].to_numpy()
        model_ids = {}
        feature_cols = next(model["feature_names"] for model in self.manifest["models"] if model["task"] == task)
        for q, col in [(0.1, "raw_p10_kw"), (0.5, "raw_p50_kw"), (0.9, "raw_p90_kw")]:
            preds = []
            for h in range(1, horizon_hours + 1):
                model = self._load_cached_model(task, h, q)
                h_rows = rows[rows["horizon_hours"] == h]
                preds.append(pd.Series(model.predict(h_rows[feature_cols]), index=h_rows.index))
                model_ids[f"h{h}_q{q}"] = f"{task}_h{h:02d}_q{int(q * 100):02d}"
            output[col] = pd.concat(preds).sort_index()
        output["model_ids"] = json.dumps(model_ids, sort_keys=True)
        capacity = float(rows["installed_pv_capacity_kw"].max()) if task == "solar" else None
        output = reconcile_quantiles(output, task, capacity)
        output = output.rename(columns={"forecast_origin_local": "origin_local", "forecast_origin_utc": "origin_utc", "target_timestamp_local": "timestamp_local", "target_timestamp_utc": "timestamp_utc"})
        return output

    def _load_cached_model(self, task: str, horizon: int, quantile: float):
        key = (task, horizon, float(quantile))
        if key not in self._model_cache:
            self._model_cache[key] = load_model(model_path(self.model_root, task, horizon, quantile))
        return self._model_cache[key]

    def _cached_load_features(self, tenant: pd.DataFrame, park: pd.DataFrame) -> pd.DataFrame:
        key = _load_cache_key(tenant, park)
        if key not in self._load_feature_cache:
            self._load_feature_cache[key] = build_load_features(tenant, park, self.cfg).frame
        return self._load_feature_cache[key]

    def _cached_solar_features(self, park: pd.DataFrame) -> pd.DataFrame:
        key = _park_cache_key(park)
        if key not in self._solar_feature_cache:
            self._solar_feature_cache[key] = build_solar_features(park, self.cfg).frame
        return self._solar_feature_cache[key]


def _metadata(task: str, origin: pd.Timestamp, horizon: int, manifest: dict, corrected: bool) -> ForecastMetadata:
    return ForecastMetadata(
        forecast_id=f"{task}-{pd.Timestamp(origin).isoformat()}-{horizon}",
        task=task,
        forecast_origin_local=pd.Timestamp(origin).isoformat(),
        forecast_origin_utc=pd.Timestamp(origin).tz_convert("UTC").isoformat() if pd.Timestamp(origin).tzinfo else "",
        horizon_hours=horizon,
        model_version=manifest["model_version"],
        dataset_version=manifest["dataset_version"],
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        quantile_reconciliation_applied=bool(corrected),
        data_quality_flags=["OK"],
        warnings=[],
    )


def _validate_quantiles(df: pd.DataFrame) -> None:
    if not ((df["p10_kw"] <= df["p50_kw"]) & (df["p50_kw"] <= df["p90_kw"])).all():
        raise ForecastDataError("forecast quantiles are not ordered")


def _load_cache_key(tenant: pd.DataFrame, park: pd.DataFrame) -> tuple[int, int, str, str, str, str]:
    tenant_ts = pd.to_datetime(tenant["timestamp_local"])
    park_ts = pd.to_datetime(park["timestamp_local"])
    return (
        len(tenant),
        len(park),
        str(tenant_ts.min()),
        str(tenant_ts.max()),
        str(park_ts.min()),
        str(park_ts.max()),
    )


def _park_cache_key(park: pd.DataFrame) -> tuple[int, str, str]:
    park_ts = pd.to_datetime(park["timestamp_local"])
    return (
        len(park),
        str(park_ts.min()),
        str(park_ts.max()),
    )
