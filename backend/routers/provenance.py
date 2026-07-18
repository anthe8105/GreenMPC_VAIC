"""Data trust and provenance routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.dependencies import get_resources
from backend.schemas import ProvenanceResponse
from backend.services import provenance_data
from greenmpc.ui.state import ControlRoomResources

router = APIRouter(prefix="/api/v1", tags=["provenance"])


@router.get("/provenance", response_model=ProvenanceResponse)
def provenance(resources: ControlRoomResources = Depends(get_resources)) -> ProvenanceResponse:
    return ProvenanceResponse(data=provenance_data(resources))
