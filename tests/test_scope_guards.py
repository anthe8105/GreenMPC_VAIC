from __future__ import annotations

import ast
from pathlib import Path

from greenmpc.config import load_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "demo.yaml"
CONTROLLED_EXTENSIONS = {
    ".md",
    ".py",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
}
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".streamlit",
}


def _project_files() -> list[Path]:
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in CONTROLLED_EXTENSIONS:
            files.append(path)
    return files


def _terms_outside_energy_scope() -> list[str]:
    return [
        "waste" + "water",
        "aeration" + " control",
        "recirculation" + " pumps",
        "chemical" + " dosing",
        "effluent" + " quality",
        "waste" + "water load shock",
        "discharge" + "-water limits",
    ]


def test_frozen_scope_settings() -> None:
    config = load_config(CONFIG_PATH)

    assert config.mpc.solver == "HIGHS"
    assert not config.reporting.official_certificate_claim_allowed
    assert len(config.tenants) == 5
    assert config.forecasting.horizons_hours == [1, 2, 3, 4, 5, 6]
    assert {0.1, 0.5, 0.9}.issubset(set(config.forecasting.quantiles))


def test_out_of_scope_terms_do_not_appear() -> None:
    terms = _terms_outside_energy_scope()
    offenders: list[str] = []
    for path in _project_files():
        text = path.read_text(encoding="utf-8").lower()
        for term in terms:
            if term in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

    assert offenders == []


def test_no_prohibited_dependencies_in_requirements() -> None:
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    prohibited = [
        "gurobi",
        "gurobipy",
        "cplex",
        "tensorflow",
        "torch",
        "pytorch",
        "fastapi",
        "react",
    ]

    for dependency in prohibited:
        assert dependency not in requirements


def test_gurobipy_is_not_imported() -> None:
    offenders: list[str] = []
    for path in _project_files():
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "gurobi" + "py":
                        offenders.append(str(path.relative_to(PROJECT_ROOT)))
            elif isinstance(node, ast.ImportFrom) and node.module == "gurobi" + "py":
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []
