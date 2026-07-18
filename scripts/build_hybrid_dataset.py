from __future__ import annotations

import argparse
import json

from greenmpc.data.dataset_builder import build_hybrid_dataset, build_status
from greenmpc.logging_utils import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Stage 2 hybrid industrial-park dataset.")
    parser.add_argument("--config", default="configs/demo.yaml")
    parser.add_argument("--source-config", default="configs/data_sources.yaml")
    parser.add_argument("--build-config", default="configs/dataset_build.yaml")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--reselect-profiles", action="store_true")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--status", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    if args.status:
        print(json.dumps(build_status(), indent=2, sort_keys=True))
        return 0
    result = build_hybrid_dataset(
        demo_config_path=args.config,
        source_config_path=args.source_config,
        build_config_path=args.build_config,
        force=args.force,
        quick=args.quick,
        reselect_profiles=args.reselect_profiles,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    manifest = result["manifest"]
    print("PASS hybrid dataset build")
    print(f"dataset_version: {manifest['dataset_version']}")
    print(f"hourly_timestamps: {manifest['total_hourly_timestamps']}")
    print(f"complete_local_days: {manifest['total_complete_local_days']}")
    print("selected_profiles:")
    for row in manifest["tenant_summary"]:
        print(f"  {row['tenant_id']}: {row['source_client_id']} ({row['archetype']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
