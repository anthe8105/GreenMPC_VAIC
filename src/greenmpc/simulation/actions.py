"""Action schema accepted by the digital-twin simulator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any


def _float_dict(values: dict[str, Any]) -> dict[str, float]:
    return {str(key): float(value) for key, value in values.items()}


@dataclass(frozen=True)
class ParkAction:
    """Externally generated one-step park action.

    The action contains allocations only. It does not infer dispatch or choose
    fallback supply.
    """

    action_id: str
    timestamp_local: datetime
    controller_name: str
    controller_mode: str
    created_at_utc: datetime
    pv_to_tenant_kw: dict[str, float]
    battery_to_tenant_kw: dict[str, float]
    dppa_to_tenant_kw: dict[str, float]
    grid_to_tenant_kw: dict[str, float]
    pv_to_battery_kw: float = 0.0
    dppa_to_battery_kw: float = 0.0
    pv_curtailment_kw: float = 0.0
    forecast_origin: str | None = None
    planning_horizon_hours: int | None = None
    source_plan_id: str | None = None
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pv_to_tenant_kw", _float_dict(self.pv_to_tenant_kw))
        object.__setattr__(self, "battery_to_tenant_kw", _float_dict(self.battery_to_tenant_kw))
        object.__setattr__(self, "dppa_to_tenant_kw", _float_dict(self.dppa_to_tenant_kw))
        object.__setattr__(self, "grid_to_tenant_kw", _float_dict(self.grid_to_tenant_kw))

    @property
    def total_pv_to_tenants_kw(self) -> float:
        return sum(self.pv_to_tenant_kw.values())

    @property
    def total_battery_to_tenants_kw(self) -> float:
        return sum(self.battery_to_tenant_kw.values())

    @property
    def total_dppa_to_tenants_kw(self) -> float:
        return sum(self.dppa_to_tenant_kw.values())

    @property
    def total_grid_to_tenants_kw(self) -> float:
        return sum(self.grid_to_tenant_kw.values())

    @property
    def total_battery_charge_kw(self) -> float:
        return self.pv_to_battery_kw + self.dppa_to_battery_kw

    @property
    def total_battery_discharge_kw(self) -> float:
        return self.total_battery_to_tenants_kw

    @property
    def total_external_import_kw(self) -> float:
        return self.total_grid_to_tenants_kw + self.total_dppa_to_tenants_kw + self.dppa_to_battery_kw

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParkAction":
        values = dict(data)
        for key in ("timestamp_local", "created_at_utc"):
            if isinstance(values.get(key), str):
                values[key] = datetime.fromisoformat(values[key])
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp_local"] = self.timestamp_local.isoformat()
        data["created_at_utc"] = self.created_at_utc.isoformat()
        return data

    def copy_with(self, **changes: Any) -> "ParkAction":
        return replace(self, **changes)


def empty_action(
    *,
    action_id: str,
    timestamp_local: datetime,
    tenant_ids: list[str],
    controller_name: str = "reference_feasible_action",
    controller_mode: str = "simulator_verification",
) -> ParkAction:
    zeros = {tenant_id: 0.0 for tenant_id in tenant_ids}
    return ParkAction(
        action_id=action_id,
        timestamp_local=timestamp_local,
        controller_name=controller_name,
        controller_mode=controller_mode,
        created_at_utc=datetime.now(timezone.utc),
        pv_to_tenant_kw=zeros.copy(),
        battery_to_tenant_kw=zeros.copy(),
        dppa_to_tenant_kw=zeros.copy(),
        grid_to_tenant_kw=zeros.copy(),
    )
