"""Chunked UCI load reading and hourly aggregation."""

from __future__ import annotations

import io
import logging
import sys
import zipfile
from pathlib import Path
from typing import Iterator

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

LOGGER = logging.getLogger(__name__)


def iter_source_year_chunks(zip_path: Path, cfg: object) -> Iterator[pd.DataFrame]:
    """Yield parsed chunks for the configured year directly from the ZIP member."""
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(cfg.uci_load.primary_archive_member) as raw:
            text = io.TextIOWrapper(raw, encoding=cfg.uci_load.encoding)
            for chunk in pd.read_csv(
                text,
                sep=cfg.uci_load.delimiter,
                decimal=cfg.uci_load.decimal_separator,
                chunksize=cfg.uci_load.chunk_size_rows,
            ):
                first = chunk.columns[0]
                chunk = chunk.rename(columns={first: "source_timestamp"})
                chunk["source_timestamp"] = pd.to_datetime(chunk["source_timestamp"], errors="coerce")
                yield chunk[chunk["source_timestamp"].dt.year == cfg.build.source_year]


def load_hourly_profiles(zip_path: Path, cfg: object, selected_columns: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Load configured source year and aggregate 15-minute profile values to hourly kW."""
    chunks = []
    rows_seen = rows_kept = invalid_ts = nonnumeric = missing = 0
    for chunk in iter_source_year_chunks(zip_path, cfg):
        rows_seen += len(chunk)
        invalid_ts += int(chunk["source_timestamp"].isna().sum())
        if selected_columns is not None:
            keep = ["source_timestamp", *selected_columns]
            chunk = chunk[[column for column in keep if column in chunk.columns]]
        client_cols = [column for column in chunk.columns if column != "source_timestamp"]
        for column in client_cols:
            before = chunk[column].isna().sum()
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")
            nonnumeric += int(chunk[column].isna().sum() - before)
        missing += int(chunk[client_cols].isna().sum().sum())
        rows_kept += len(chunk)
        chunks.append(chunk)
    if not chunks:
        raise ValueError("no UCI source-year rows were read")
    data = pd.concat(chunks, ignore_index=True).dropna(subset=["source_timestamp"])
    data["source_hour"] = data["source_timestamp"].dt.floor("h")
    client_cols = [column for column in data.columns if column.startswith("MT_")]
    hourly = data.groupby("source_hour")[client_cols].mean()
    full_index = pd.date_range(f"{cfg.build.source_year}-01-01 00:00:00", f"{cfg.build.source_year}-12-31 23:00:00", freq="1h")
    hourly = hourly.reindex(full_index)
    hourly.index = pd.DatetimeIndex(hourly.index).tz_localize(cfg.build.output_timezone)
    report = {
        "rows_inspected": int(rows_seen),
        "source_year_rows": int(rows_kept),
        "source_client_count": len(client_cols),
        "invalid_timestamp_count": int(invalid_ts),
        "nonnumeric_value_count": int(nonnumeric),
        "missing_value_count": int(missing),
        "duplicate_local_timestamps": int(data["source_timestamp"].duplicated().sum()),
        "missing_local_hours": int(hourly.isna().all(axis=1).sum()),
        "ambiguous_fall_back_timestamps": 0,
        "nonexistent_spring_forward_timestamps": 0,
        "local_23_hour_days": 0,
        "local_25_hour_days": 0,
        "rows_that_cannot_be_localized": int(invalid_ts),
        "selected_resolution_policy": "quarter-hour values aggregated by hour; duplicate local hours averaged; calendar-preserving transfer to Vietnam local time",
        "approximate_peak_memory_mb": None,
    }
    return hourly, report


def load_selected_client_columns(zip_path: Path, cfg: object, client_ids: list[str]) -> pd.DataFrame:
    """Load only selected client columns for the configured source year."""
    hourly, _ = load_hourly_profiles(zip_path, cfg, client_ids)
    return hourly[client_ids]
