#!/usr/bin/env python
"""Train Stage 4 load and solar forecasters."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from greenmpc.forecasting.training import status, train_forecasters


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/demo.yaml")
    parser.add_argument("--forecast-config", default="configs/forecasting.yaml")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--task", choices=["load", "solar", "all"], default="all")
    parser.add_argument("--horizon", type=int)
    parser.add_argument("--quantile", type=float)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        info = status(PROJECT_ROOT / args.forecast_config)
        print(f"expected_model_slots: {info['expected_model_slots']}")
        print(f"existing_model_slots: {info['existing_model_slots']}")
        return 0
    result = train_forecasters(
        config_path=PROJECT_ROOT / args.config,
        forecast_config_path=PROJECT_ROOT / args.forecast_config,
        task=args.task,
        force=args.force,
        quick=args.quick,
        horizon=args.horizon,
        quantile=args.quantile,
    )
    manifest = result["manifest"]
    print(f"status: {result['status']}")
    print(f"model_count: {manifest.get('model_count')}")
    print(f"training_runtime_seconds: {manifest.get('training_runtime_seconds')}")
    print(f"load_training_seconds: {manifest.get('load_training_seconds')}")
    print(f"solar_training_seconds: {manifest.get('solar_training_seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
