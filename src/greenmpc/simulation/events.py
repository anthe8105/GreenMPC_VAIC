"""Runtime event model for baseline-preserving simulator stress tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any

from greenmpc.config import GreenMPCConfig
from greenmpc.simulation.exceptions import EventValidationError
from greenmpc.simulation.state import ExogenousState


@dataclass(frozen=True)
class RuntimeEvent:
    event_id: str
    event_type: str
    event_name: str
    start_timestamp_local: datetime
    end_timestamp_local: datetime
    duration_hours: int
    affected_tenant_id: str | None
    load_multiplier: float
    pv_multiplier: float
    dppa_multiplier: float
    description: str
    source: str = "runtime"
    is_synthetic: bool = True
    enabled: bool = True

    @classmethod
    def from_catalog_row(cls, row: dict[str, Any]) -> "RuntimeEvent":
        affected = row.get("affected_tenant_id")
        if affected != affected or affected == "":  # NaN-safe
            affected = None
        return cls(
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            event_name=str(row["event_name"]),
            start_timestamp_local=_parse_timestamp(row["start_timestamp_local"]),
            end_timestamp_local=_parse_timestamp(row["end_timestamp_local"]),
            duration_hours=int(row["duration_hours"]),
            affected_tenant_id=affected,
            load_multiplier=float(row["load_multiplier"]),
            pv_multiplier=float(row["pv_multiplier"]),
            dppa_multiplier=float(row["dppa_multiplier"]),
            description=str(row["description"]),
            source="catalog",
            is_synthetic=bool(row.get("event_is_synthetic", True)),
            enabled=False,
        )

    def is_active(self, timestamp: datetime) -> bool:
        return self.enabled and self.start_timestamp_local <= timestamp < self.end_timestamp_local


@dataclass(frozen=True)
class EventEffectRecord:
    timestamp_local: datetime
    event_ids: tuple[str, ...]
    event_types: tuple[str, ...]
    baseline_load_by_tenant_kw: dict[str, float]
    effective_load_by_tenant_kw: dict[str, float]
    baseline_pv_kw: float
    effective_pv_kw: float
    baseline_dppa_kw: float
    effective_dppa_kw: float
    combined_load_multiplier_by_tenant: dict[str, float]
    combined_pv_multiplier: float
    combined_dppa_multiplier: float


def validate_event(event: RuntimeEvent, tenant_ids: list[str], config: GreenMPCConfig, current_timestamp: datetime | None = None) -> None:
    if event.start_timestamp_local >= event.end_timestamp_local:
        raise EventValidationError(f"{event.event_id} start must precede end")
    if current_timestamp is not None and event.start_timestamp_local < current_timestamp:
        raise EventValidationError(f"{event.event_id} starts before current simulator timestamp")
    for field in ("load_multiplier", "pv_multiplier", "dppa_multiplier"):
        value = getattr(event, field)
        if not isfinite(value) or value < 0:
            raise EventValidationError(f"{event.event_id}.{field} must be finite and nonnegative")
        if value > config.simulation.maximum_event_multiplier:
            raise EventValidationError(f"{event.event_id}.{field} exceeds configured maximum_event_multiplier")
    if event.affected_tenant_id and event.affected_tenant_id not in tenant_ids:
        raise EventValidationError(f"{event.event_id} references unknown tenant {event.affected_tenant_id}")
    actual_hours = int((event.end_timestamp_local - event.start_timestamp_local).total_seconds() // 3600)
    if actual_hours != event.duration_hours:
        raise EventValidationError(f"{event.event_id}.duration_hours does not match timestamp range")


def apply_events(
    baseline: ExogenousState,
    events: list[RuntimeEvent],
    tenant_ids: list[str],
) -> tuple[ExogenousState, EventEffectRecord | None]:
    active = sorted((event for event in events if event.is_active(baseline.timestamp_local)), key=lambda event: event.event_id)
    if not active:
        return baseline, None

    load_multipliers = {tenant_id: 1.0 for tenant_id in tenant_ids}
    pv_multiplier = 1.0
    dppa_multiplier = 1.0
    for event in active:
        if event.event_type == "cloud_event":
            pv_multiplier *= event.pv_multiplier
        elif event.event_type == "production_shift_event":
            if event.affected_tenant_id:
                load_multipliers[event.affected_tenant_id] *= event.load_multiplier
        elif event.event_type == "high_load_event":
            for tenant_id in tenant_ids:
                load_multipliers[tenant_id] *= event.load_multiplier
        elif event.event_type == "combined_stress_event":
            targets = [event.affected_tenant_id] if event.affected_tenant_id else tenant_ids
            for tenant_id in targets:
                if tenant_id:
                    load_multipliers[tenant_id] *= event.load_multiplier
            pv_multiplier *= event.pv_multiplier
            dppa_multiplier *= event.dppa_multiplier

    effective_load = {
        tenant_id: max(0.0, baseline.baseline_tenant_load_kw[tenant_id] * load_multipliers[tenant_id])
        for tenant_id in tenant_ids
    }
    effective_pv = max(0.0, baseline.baseline_pv_available_kw * pv_multiplier)
    effective_dppa = max(0.0, baseline.dppa_available_kw * dppa_multiplier)
    event_ids = tuple(event.event_id for event in active)
    event_types = tuple(event.event_type for event in active)
    effective = baseline.with_effective_values(
        effective_tenant_load_kw=effective_load,
        effective_pv_available_kw=effective_pv,
        dppa_available_kw=effective_dppa,
        active_event_ids=event_ids,
        active_event_types=event_types,
    )
    record = EventEffectRecord(
        timestamp_local=baseline.timestamp_local,
        event_ids=event_ids,
        event_types=event_types,
        baseline_load_by_tenant_kw=dict(baseline.baseline_tenant_load_kw),
        effective_load_by_tenant_kw=effective_load,
        baseline_pv_kw=baseline.baseline_pv_available_kw,
        effective_pv_kw=effective_pv,
        baseline_dppa_kw=baseline.dppa_available_kw,
        effective_dppa_kw=effective_dppa,
        combined_load_multiplier_by_tenant=load_multipliers,
        combined_pv_multiplier=pv_multiplier,
        combined_dppa_multiplier=dppa_multiplier,
    )
    return effective, record


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
