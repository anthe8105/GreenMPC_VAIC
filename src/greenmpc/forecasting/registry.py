"""Forecast model registry persistence and compatibility checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib

from greenmpc.forecasting.artifacts import file_sha256, write_json
from greenmpc.forecasting.exceptions import ModelCompatibilityError, ModelRegistryError


EXPECTED_MODEL_COUNT = 36


def quantile_label(q: float) -> str:
    return f"quantile_{int(round(q * 1000)):03d}.joblib"


def model_path(root: str | Path, task: str, horizon: int, quantile: float) -> Path:
    return Path(root) / task / f"horizon_{horizon:02d}" / quantile_label(quantile)


def save_model(path: str | Path, pipeline: Any) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, target)
    return file_sha256(target)


def load_model(path: str | Path) -> Any:
    if not Path(path).exists():
        raise ModelRegistryError(f"missing model artifact: {path}")
    return joblib.load(path)


def write_model_manifest(path: str | Path, manifest: dict) -> None:
    write_json(path, manifest)


def read_model_manifest(path: str | Path) -> dict:
    if not Path(path).exists():
        raise ModelRegistryError(f"model manifest does not exist: {path}")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_registry_hashes(manifest: dict, root: str | Path) -> None:
    for model in manifest.get("models", []):
        path = Path(root) / model["relative_path"]
        digest = file_sha256(path)
        if digest != model["artifact_sha256"]:
            raise ModelRegistryError(f"artifact hash mismatch for {path}")


def validate_compatibility(manifest: dict, fingerprints: dict, reject_mismatch: bool = True) -> None:
    expected = manifest.get("fingerprints", {})
    mismatches = {
        key: (expected.get(key), fingerprints.get(key))
        for key in expected
        if fingerprints.get(key) != expected.get(key)
    }
    if mismatches and reject_mismatch:
        raise ModelCompatibilityError(f"model/data fingerprint mismatch: {mismatches}")
