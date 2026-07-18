"""Session routes for the web command center."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_resources
from backend.schemas import SessionCreateRequest, SessionResetRequest, SessionResponse
from backend.services import create_live_session, reset_session_in_place, serialize_state
from backend.session_store import STORE
from greenmpc.ui.state import ControlRoomResources

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
def create_session(payload: SessionCreateRequest, resources: ControlRoomResources = Depends(get_resources)) -> SessionResponse:
    live = create_live_session(resources, payload.scenario_id, payload.controller_id, payload.start_timestamp)
    stored = STORE.create(live)
    return SessionResponse(session_id=stored.session_id, run_id=stored.live.run_identifier, state=serialize_state(stored))


@router.post("/{session_id}/reset", response_model=SessionResponse)
def reset_session(session_id: str, payload: SessionResetRequest, resources: ControlRoomResources = Depends(get_resources)) -> SessionResponse:
    try:
        stored = STORE.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": str(exc)}) from exc
    with stored.lock:
        reset_session_in_place(stored, resources, payload.scenario_id, payload.controller_id, payload.start_timestamp)
        return SessionResponse(session_id=session_id, run_id=stored.live.run_identifier, state=serialize_state(stored))


@router.get("/{session_id}/state")
def state(session_id: str) -> dict:
    try:
        stored = STORE.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": str(exc)}) from exc
    with stored.lock:
        return {"session_id": session_id, "run_id": stored.live.run_identifier, "state": serialize_state(stored)}
