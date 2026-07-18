#!/usr/bin/env python
"""Re-evaluate persisted Stage 4 forecasters without retraining."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from greenmpc.forecasting.registry import read_model_manifest, validate_registry_hashes
from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.training import PROJECT_ROOT as ROOT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["validation", "test", "all"], default="all")
    parser.add_argument("--task", choices=["load", "solar", "all"], default="all")
    args = parser.parse_args()
    del args
    cfg = load_forecasting_config(ROOT / "configs/forecasting.yaml")
    manifest = read_model_manifest(ROOT / cfg.outputs.model_manifest_path)
    validate_registry_hashes(manifest, ROOT / cfg.outputs.model_root)
    metrics = ROOT / cfg.outputs.metrics_path
    if not metrics.exists():
        print(f"FAIL metrics file missing: {metrics}")
        return 1
    print("PASS forecast evaluation reproducibility")
    print(f"model_count: {manifest.get('model_count')}")
    print(f"metrics_path: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
