from __future__ import annotations

import argparse
import sys

from greenmpc.data.acquisition import acquire_sources, print_status_table
from greenmpc.logging_utils import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire and validate Stage 1 public raw data.")
    parser.add_argument("--all", action="store_true", help="Acquire all enabled sources.")
    parser.add_argument(
        "--source",
        action="append",
        choices=["uci-load", "uci-steel", "nasa-power", "tariff"],
        help="Acquire one source; may be supplied multiple times.",
    )
    parser.add_argument("--offline", action="store_true", help="Validate cached files without network calls.")
    parser.add_argument("--force", action="store_true", help="Reacquire even when a cache exists.")
    parser.add_argument("--status", action="store_true", help="Print source readiness without downloading.")
    parser.add_argument("--extract-large", action="store_true", help="Explicitly extract the large UCI load archive.")
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    if args.status:
        print_status_table()
        return 0
    return acquire_sources(
        source_names=args.source,
        all_sources=args.all,
        offline=args.offline,
        force=args.force,
        extract_large=args.extract_large,
    )


if __name__ == "__main__":
    raise SystemExit(main())
