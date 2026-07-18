"""NASA POWER raw weather processing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


def process_nasa_power(path: Path, cfg: object) -> tuple[pd.DataFrame, dict]:
    """Parse NASA CSV, preserve UTC/local timestamps, and flag missing data."""
    text = path.read_text(encoding="utf-8", errors="replace")
    units = _parse_units(text)
    start = next(i for i, line in enumerate(text.splitlines()) if line.startswith("YEAR,"))
    df = pd.read_csv(path, skiprows=start)
    for parameter in cfg.weather.requested_parameters:
        if parameter not in df.columns:
            raise ValueError(f"NASA parameter missing: {parameter}")
    ts = pd.to_datetime(dict(year=df.YEAR, month=df.MO, day=df.DY, hour=df.HR), utc=True)
    out = pd.DataFrame({"timestamp_utc": ts, "timestamp_local": ts.dt.tz_convert(cfg.weather.output_timezone)})
    missing_counts = {}
    imputed_counts = {}
    for parameter in cfg.weather.requested_parameters:
        series = pd.to_numeric(df[parameter], errors="coerce")
        series = series.mask(series.isin(cfg.weather.missing_value_sentinels))
        missing_counts[parameter] = int(series.isna().sum())
        flag = series.isna()
        if cfg.weather.interpolation_enabled:
            filled = series.interpolate(limit=cfg.weather.maximum_short_gap_hours_for_interpolation, limit_direction="both")
        else:
            filled = series
        imputed_counts[parameter] = int(flag.sum() - filled.isna().sum())
        out[parameter] = filled
        out[f"{parameter}_imputed"] = flag & filled.notna()
    out = out.drop_duplicates("timestamp_utc").sort_values("timestamp_utc")
    if cfg.weather.drop_incomplete_boundary_days:
        counts = out.groupby(out["timestamp_local"].dt.date).size()
        complete_days = set(counts[counts == 24].index)
        before = len(out)
        out = out[out["timestamp_local"].dt.date.isin(complete_days)]
        removed = before - len(out)
    else:
        removed = 0
    out = out.rename(columns={"T2M": "temperature_c", "RH2M": "relative_humidity_pct", "PRECTOTCORR": "precipitation", "WS10M": "wind_speed"})
    out["weather_quality_flag"] = "ok"
    meta = {
        "raw_timestamp_count": int(len(df)),
        "complete_local_days": int(out["timestamp_local"].dt.date.nunique()),
        "removed_boundary_timestamps": int(removed),
        "missing_count_per_parameter": missing_counts,
        "imputed_count_per_parameter": imputed_counts,
        "unknown_unit_incidents": [],
        "units": units,
    }
    out.attrs["units"] = units
    return out, meta


def _parse_units(text: str) -> dict[str, str]:
    units: dict[str, str] = {}
    for line in text.splitlines()[:80]:
        stripped = line.strip()
        for key in ("ALLSKY_SFC_SW_DWN", "T2M", "RH2M", "PRECTOTCORR", "WS10M"):
            if stripped.startswith(key):
                start = stripped.rfind("(")
                end = stripped.rfind(")")
                if start == -1 or end == -1 or end <= start:
                    raise ValueError(f"could not parse NASA unit for {key}: {line}")
                units[key] = stripped[start + 1:end].strip()
    required = {"ALLSKY_SFC_SW_DWN", "T2M", "RH2M", "PRECTOTCORR", "WS10M"}
    missing = required - set(units)
    if missing:
        raise ValueError(f"NASA unit metadata missing for: {sorted(missing)}")
    return units
