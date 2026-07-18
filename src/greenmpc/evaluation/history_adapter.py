"""Observed-history adapter for closed-loop forecasting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pandas as pd

from greenmpc.simulation.state import ExogenousState


@dataclass
class ObservedHistoryAdapter:
    """Create forecast histories with realized effective observations through origin."""

    baseline_tenant: pd.DataFrame
    baseline_park: pd.DataFrame
    tenant_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        self._tenant = self.baseline_tenant.copy(deep=True)
        self._park = self.baseline_park.copy(deep=True)
        self._tenant["timestamp_local"] = pd.to_datetime(self._tenant["timestamp_local"])
        self._park["timestamp_local"] = pd.to_datetime(self._park["timestamp_local"])
        self._realized: dict[pd.Timestamp, ExogenousState] = {}

    def record_observation(self, exogenous: ExogenousState) -> None:
        self._realized[pd.Timestamp(exogenous.timestamp_local)] = exogenous

    def histories_through(self, origin: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        origin = pd.Timestamp(origin)
        tenant = self._tenant.copy(deep=True)
        park = self._park.copy(deep=True)
        for timestamp, exogenous in self._realized.items():
            if timestamp > origin:
                raise ValueError("observed history contains a future timestamp")
            for tenant_id in self.tenant_ids:
                mask = (tenant["timestamp_local"] == timestamp) & (tenant["tenant_id"] == tenant_id)
                tenant.loc[mask, "load_kw"] = float(exogenous.effective_tenant_load_kw[tenant_id])
                tenant.loc[mask, "load_kwh"] = float(exogenous.effective_tenant_load_kw[tenant_id])
            park_mask = park["timestamp_local"] == timestamp
            park.loc[park_mask, "pv_available_kw"] = float(exogenous.effective_pv_available_kw)
            park.loc[park_mask, "pv_available_kwh"] = float(exogenous.effective_pv_available_kw)
            park.loc[park_mask, "park_load_kw"] = sum(exogenous.effective_tenant_load_kw.values())
            park.loc[park_mask, "park_load_kwh"] = sum(exogenous.effective_tenant_load_kw.values())
            park.loc[park_mask, "dppa_available_kw"] = float(exogenous.dppa_available_kw)
        audit = {
            "forecast_origin": origin.isoformat(),
            "realized_replacement_count": len([ts for ts in self._realized if ts <= origin]),
            "max_realized_timestamp": max((ts.isoformat() for ts in self._realized if ts <= origin), default=None),
            "future_observations_used": any(ts > origin for ts in self._realized),
            "all_five_tenants_aligned": bool(tenant.groupby("timestamp_local")["tenant_id"].nunique().min() == len(self.tenant_ids)),
            "policy": "realized effective observations through current origin only; Stage 4 feature manifest forbids future actual feature columns",
        }
        return tenant, park, audit

    def fingerprint(self, origin: pd.Timestamp) -> str:
        relevant = {
            ts.isoformat(): {
                "pv": ex.effective_pv_available_kw,
                "dppa": ex.dppa_available_kw,
                "load": dict(ex.effective_tenant_load_kw),
            }
            for ts, ex in sorted(self._realized.items())
            if ts <= pd.Timestamp(origin)
        }
        return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode("utf-8")).hexdigest()
