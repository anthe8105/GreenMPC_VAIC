from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PACKAGE_ROOT = PROJECT_ROOT / "src" / "greenmpc"


REQUIRED_DIRECTORIES = [
    "configs",
    "data/raw",
    "data/processed",
    "data/outputs",
    "models",
    "artifacts",
    "docs",
    "scripts",
    "src/greenmpc",
    "tests",
]


def main() -> int:
    try:
        import greenmpc
        from greenmpc.config import load_config

        config = load_config(PROJECT_ROOT / "configs" / "demo.yaml")
        package_file = Path(greenmpc.__file__).resolve()
        expected_init = (SRC_PACKAGE_ROOT / "__init__.py").resolve()
        checks = {
            "package import": package_file == expected_init,
            "no root-level greenmpc package": not (PROJECT_ROOT / "greenmpc").exists(),
            "python version": (3, 11) <= sys.version_info[:2] < (3, 13),
            "tenant count": len(config.tenants) == 5,
            "solver": config.mpc.solver == "HIGHS",
            "certificate claims disabled": (
                not config.reporting.official_certificate_claim_allowed
            ),
            "required directories": all(
                (PROJECT_ROOT / directory).is_dir() for directory in REQUIRED_DIRECTORIES
            ),
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            print(f"FAIL Stage 0 verification: {', '.join(failed)}")
            return 1

        print("PASS Stage 0 verification")
        print(f"package version: {greenmpc.__version__}")
        print(f"package file: {package_file}")
        print(f"python version: {sys.version.split()[0]}")
        print(f"configured tenants: {len(config.tenants)}")
        print(f"solver: {config.mpc.solver}")
        return 0
    except Exception as exc:
        print(f"FAIL Stage 0 verification: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
