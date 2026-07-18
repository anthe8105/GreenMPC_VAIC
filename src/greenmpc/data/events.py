"""Synthetic event catalog generation, separate from baseline data."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


def build_event_catalog(index: pd.DatetimeIndex, tenant_ids: list[str], cfg: object) -> pd.DataFrame:
    if not cfg.create_catalog:
        return pd.DataFrame()
    days = sorted(set(pd.Series(index).dt.date))
    picks = [days[len(days)//4], days[len(days)//3], days[len(days)//2], days[(2*len(days))//3]]
    events = [
        ("EVT_CLOUD_001", "cloud_event", "Daytime cloud event", picks[0], 11, None, 1.0, 1 - cfg.cloud_event_reduction_fraction, 1.0, cfg.cloud_event_duration_hours),
        ("EVT_SHIFT_001", "production_shift_event", "Tenant production shift", picks[1], 8, tenant_ids[0], cfg.production_shift_multiplier, 1.0, 1.0, cfg.production_shift_duration_hours),
        ("EVT_HIGH_001", "high_load_event", "High-load stress event", picks[2], 9, None, cfg.high_load_multiplier, 1.0, 1.0, cfg.high_load_duration_hours),
        ("EVT_COMBINED_001", "combined_stress_event", "Combined peak stress event", picks[3], 17, tenant_ids[1], cfg.high_load_multiplier, 1 - cfg.cloud_event_reduction_fraction, 1.0, cfg.combined_stress_duration_hours),
    ]
    rows = []
    tz = index.tz
    for event_id, etype, name, day, hour, tenant, lm, pm, dm, duration in events:
        start = pd.Timestamp(day, tz=tz) + pd.Timedelta(hours=hour)
        rows.append({
            "event_id": event_id,
            "event_type": etype,
            "event_name": name,
            "start_timestamp_local": str(start),
            "end_timestamp_local": str(start + pd.Timedelta(hours=duration)),
            "duration_hours": duration,
            "affected_tenant_id": tenant,
            "load_multiplier": lm,
            "pv_multiplier": pm,
            "dppa_multiplier": dm,
            "description": "Synthetic demo event catalog entry; not applied to baseline dataset.",
            "event_is_synthetic": True,
            "applied_to_baseline_dataset": False,
            "intended_demo_use": "later simulator runtime injection",
        })
    return pd.DataFrame(rows)
