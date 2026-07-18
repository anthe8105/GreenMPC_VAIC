"""Processed dataset lineage and fingerprints."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_lineage() -> dict:
    return {
        "load_kw": {"source": "UCI ElectricityLoadDiagrams", "transformation": ["quarter-hour to hourly aggregation", "calendar-preserving transfer", "p95 scaling"], "classification": ["measured shape", "rescaled", "scenario-labeled"], "actual_vrg_data": False},
        "temperature_c": {"source": "NASA POWER T2M", "transformation": ["UTC to Asia/Ho_Chi_Minh", "boundary-day filtering"], "classification": ["satellite/model-based"], "on_site_sensor": False},
        "pv_available_kw": {"source": "NASA POWER ALLSKY_SFC_SW_DWN", "transformation": ["unit-aware PV derivation", "performance-ratio adjustment", "capacity clipping"], "classification": ["derived"], "measured_inverter_output": False},
        "grid_price_vnd_per_kwh": {"source": ["configs/demo.yaml", "tariff-reference metadata"], "classification": ["demo operational reference"], "official_category_selected": False},
        "dppa_price_vnd_per_kwh": {"source": "configs/demo.yaml", "classification": ["contract scenario assumption"]},
        "scenario_events": {"source": "configs/dataset_build.yaml", "classification": ["synthetic scenario assumption"], "applied_to_baseline_dataset": False},
    }
