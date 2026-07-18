"""Read-only Stage 6 benchmark routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.dependencies import get_resources
from backend.schemas import BenchmarkResponse
from backend.services import benchmark_rows
from greenmpc.ui.state import ControlRoomResources

router = APIRouter(prefix="/api/v1", tags=["benchmark"])


@router.get("/benchmark", response_model=BenchmarkResponse)
def benchmark(
    valuation_price_vnd_per_kwh: float = Query(1100.0, enum=[1100.0, 1500.0, 2000.0, 2500.0]),
    resources: ControlRoomResources = Depends(get_resources),
) -> BenchmarkResponse:
    return BenchmarkResponse(
        valuation_price_vnd_per_kwh=valuation_price_vnd_per_kwh,
        rows=benchmark_rows(resources, valuation_price_vnd_per_kwh),
        explanation="Read-only Stage 6 realized metrics. Terminal inventory adjustment is recalculated from stored histories only.",
    )
