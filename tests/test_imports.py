from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PACKAGE_ROOT = PROJECT_ROOT / "src" / "greenmpc"


def test_import_greenmpc() -> None:
    module = importlib.import_module("greenmpc")

    assert module.__version__ == "0.1.0"
    assert Path(module.__file__).resolve() == (SRC_PACKAGE_ROOT / "__init__.py").resolve()


def test_no_repository_root_greenmpc_package() -> None:
    assert not (PROJECT_ROOT / "greenmpc").exists()


def test_editable_install_package_import_location() -> None:
    module = importlib.import_module("greenmpc")
    package_path = Path(module.__file__).resolve()

    assert package_path.is_relative_to(SRC_PACKAGE_ROOT.resolve())


def test_import_configuration_module() -> None:
    module = importlib.import_module("greenmpc.config")

    assert hasattr(module, "load_config")


def test_package_directories_import_successfully() -> None:
    packages = [
        "greenmpc.data",
        "greenmpc.forecasting",
        "greenmpc.simulation",
        "greenmpc.control",
        "greenmpc.evaluation",
        "greenmpc.reporting",
        "greenmpc.ui",
    ]

    for package in packages:
        importlib.import_module(package)


def test_python_metadata_supports_311_and_312() -> None:
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["requires-python"] == ">=3.11,<3.13"
    assert (3, 11) <= sys.version_info[:2] < (3, 13)
