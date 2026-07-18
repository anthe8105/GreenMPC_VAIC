#!/usr/bin/env python
"""Run Stage 6 closed-loop controller benchmarks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from greenmpc.evaluation.runner import PROJECT_ROOT, run_benchmark
from greenmpc.evaluation.scenarios import load_evaluation_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Run the configured 24-hour quick benchmark.")
    parser.add_argument("--scenario", choices=["normal", "cloudy", "production_shift", "combined_stress"])
    parser.add_argument("--hours", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--profile", action="store_true", help="Print live per-step timing for bottleneck diagnosis.")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    cfg = load_evaluation_config(PROJECT_ROOT / "configs/evaluation.yaml")
    output_dir = PROJECT_ROOT / cfg.output_directory
    manifest = output_dir / "benchmark_manifest.json"
    if args.status:
        print(json.dumps({"output_directory": str(output_dir), "manifest_exists": manifest.exists(), "manifest": json.loads(manifest.read_text()) if manifest.exists() else None}, indent=2))
        return 0
    summary = run_benchmark(quick=args.quick, hours=args.hours, scenario_filter=args.scenario, force=args.force, profile=args.profile)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
