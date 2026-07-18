"""Deterministic profile selection and lock-file handling."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd
import yaml


def archetype_scores(metrics: pd.DataFrame) -> pd.DataFrame:
    scored = metrics.copy()
    for column in [
        "load_factor_mean_over_p95", "coefficient_of_variation", "overnight_baseload_ratio",
        "weekend_reduction_fraction", "p99_to_median_ratio", "business_hour_concentration",
        "daytime_to_nighttime_ratio", "hourly_ramp_p95", "two_shift_score", "evening_mean",
    ]:
        scored[f"z_{column}"] = _norm(scored[column])
    scored["continuous_high_baseload"] = scored["z_load_factor_mean_over_p95"] + scored["z_overnight_baseload_ratio"] - scored["z_coefficient_of_variation"] - scored["z_weekend_reduction_fraction"]
    scored["daytime_concentrated"] = scored["z_business_hour_concentration"] + scored["z_daytime_to_nighttime_ratio"] + scored["z_weekend_reduction_fraction"]
    scored["variable_shift_driven"] = scored["z_coefficient_of_variation"] + scored["z_hourly_ramp_p95"] + scored["z_weekend_reduction_fraction"]
    scored["two_shift_stable"] = scored["z_two_shift_score"] + scored["z_load_factor_mean_over_p95"] - 0.5 * scored["z_coefficient_of_variation"]
    scored["spiky_overtime"] = scored["z_p99_to_median_ratio"] + scored["z_evening_mean"] + scored["z_hourly_ramp_p95"]
    return scored


def select_profiles(metrics: pd.DataFrame, hourly: pd.DataFrame, cfg: object, source_fingerprint: str, force: bool = False, reselect: bool = False) -> pd.DataFrame:
    lock_path = Path("configs/selected_profiles.yaml")
    if lock_path.exists() and not reselect:
        locked = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
        rows = []
        scored = archetype_scores(metrics)
        for tenant in cfg.tenant_mapping:
            item = locked["selected_profiles"][tenant.tenant_id]
            metric = scored[scored["source_client_id"] == item["source_client_id"]].iloc[0]
            rows.append(_selection_row(tenant, item["source_client_id"], metric, rank=1, corr=0, warning="lock file reused"))
        return pd.DataFrame(rows)
    scored = archetype_scores(metrics)
    eligible = scored[scored["eligible"]].copy()
    selected = []
    used: set[str] = set()
    for tenant in sorted(cfg.tenant_mapping, key=lambda x: x.selection_priority):
        ranked = eligible.sort_values([tenant.archetype, "source_client_id"], ascending=[False, True])
        choice = None
        fallback_warning = ""
        rank = 0
        for _, row in ranked.iterrows():
            rank += 1
            cid = row["source_client_id"]
            if cid in used:
                continue
            corr = _max_corr(cid, [r["source_client_id"] for r in selected], hourly)
            if corr <= cfg.uci_load.maximum_allowed_pairwise_correlation:
                choice = (row, corr, rank)
                break
        if choice is None:
            candidates = [row for _, row in ranked.iterrows() if row["source_client_id"] not in used]
            if not candidates:
                raise ValueError("not enough eligible profiles for unique tenant selection")
            best = min(candidates, key=lambda row: _max_corr(row["source_client_id"], [r["source_client_id"] for r in selected], hourly))
            choice = (best, _max_corr(best["source_client_id"], [r["source_client_id"] for r in selected], hourly), 999)
            fallback_warning = "correlation threshold fallback: least-correlated valid candidate selected"
        metric, corr, rank = choice
        used.add(metric["source_client_id"])
        selected.append(_selection_row(tenant, metric["source_client_id"], metric, rank, corr, fallback_warning))
    return pd.DataFrame(selected)


def write_profile_lock(path: Path, selected: pd.DataFrame, cfg: object, source_fingerprint: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "selection_version": 1,
        "source_dataset_fingerprint": source_fingerprint,
        "source_year": cfg.build.source_year,
        "random_seed": cfg.build.random_seed,
        "profile_selection_date": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "generated_by_script": "scripts/build_hybrid_dataset.py",
        "manual_override": False,
        "selected_profiles": {
            row["tenant_id"]: {
                "source_client_id": row["source_client_id"],
                "archetype": row["archetype"],
                "source_metrics": {"archetype_score": float(row["archetype_score"])},
                "target_scaling_value": float(row["target_p95_load_kw"]),
            }
            for row in selected.to_dict("records")
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _selection_row(tenant: object, cid: str, metric: pd.Series, rank: int, corr: float, warning: str) -> dict:
    source_p95 = float(metric["p95"])
    factor = tenant.target_p95_load_kw / source_p95
    return {
        "tenant_id": tenant.tenant_id,
        "archetype": tenant.archetype,
        "source_client_id": cid,
        "source_dataset": "UCI ElectricityLoadDiagrams20112014",
        "archetype_score": float(metric[tenant.archetype]),
        "rank_within_archetype": int(rank),
        "pairwise_correlation_max": float(corr),
        "selection_reason": f"highest deterministic {tenant.archetype} score; {warning}".strip("; "),
        "scenario_label_only": True,
        "is_actual_industry_identity": False,
        "is_actual_vrg_tenant": False,
        "target_p95_load_kw": float(tenant.target_p95_load_kw),
        "source_profile_p95_load_kw": source_p95,
        "scaling_factor": float(factor),
        "source_mean_load_kw": float(metric["mean_load"]),
        "source_max_load_kw": float(metric["maximum"]),
    }


def _norm(s: pd.Series) -> pd.Series:
    span = s.max() - s.min()
    return (s - s.min()) / span if span else s * 0


def _max_corr(cid: str, selected: list[str], hourly: pd.DataFrame) -> float:
    if not selected:
        return 0.0
    base = _shape(hourly[cid])
    values = []
    for other in selected:
        corr = base.corr(_shape(hourly[other]))
        values.append(abs(float(corr)) if pd.notna(corr) else 1.0)
    return max(values)


def _shape(s: pd.Series) -> pd.Series:
    s = s.fillna(0)
    std = s.std()
    return (s - s.mean()) / std if std else s * 0
