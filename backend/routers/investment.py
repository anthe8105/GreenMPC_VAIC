"""Investment Scenario Lab API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.dependencies import get_resources
from backend.investment_jobs import INVESTMENT_CONFIG, INVESTMENT_JOBS, investment_defaults, request_from_payload
from greenmpc.ui.state import PROJECT_ROOT, ControlRoomResources

router = APIRouter(prefix="/api/v1/investment", tags=["investment"])


@router.get("/defaults")
def defaults(resources: ControlRoomResources = Depends(get_resources)) -> dict[str, Any]:
    return investment_defaults(resources, INVESTMENT_CONFIG)


@router.post("/analyses")
def create_analysis(payload: dict[str, Any], resources: ControlRoomResources = Depends(get_resources)) -> dict[str, Any]:
    try:
        request = request_from_payload(payload)
        job = INVESTMENT_JOBS.submit(resources, request, INVESTMENT_CONFIG)
        return {**job.to_status(), "estimated_work_units": request.duration_hours * 2}
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_INVESTMENT_REQUEST", "message": str(exc)}) from exc


@router.get("/analyses")
def list_analyses() -> dict[str, Any]:
    return {"analyses": INVESTMENT_JOBS.list()}


@router.get("/analyses/{analysis_id}")
def analysis_status(analysis_id: str) -> dict[str, Any]:
    try:
        return INVESTMENT_JOBS.get(analysis_id).to_status()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "ANALYSIS_NOT_FOUND", "message": analysis_id}) from exc


@router.get("/analyses/{analysis_id}/result")
def analysis_result(analysis_id: str) -> dict[str, Any]:
    try:
        job = INVESTMENT_JOBS.get(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "ANALYSIS_NOT_FOUND", "message": analysis_id}) from exc
    if job.status != "completed" or not job.result:
        raise HTTPException(status_code=409, detail={"code": "ANALYSIS_NOT_COMPLETE", "message": job.status})
    return job.result


@router.post("/analyses/{analysis_id}/cancel")
def cancel_analysis(analysis_id: str) -> dict[str, Any]:
    try:
        return INVESTMENT_JOBS.cancel(analysis_id).to_status()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "ANALYSIS_NOT_FOUND", "message": analysis_id}) from exc


@router.get("/analyses/{analysis_id}/export")
def export_analysis(analysis_id: str) -> FileResponse:
    try:
        job = INVESTMENT_JOBS.get(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "ANALYSIS_NOT_FOUND", "message": analysis_id}) from exc
    if job.status != "completed" or not job.result:
        raise HTTPException(status_code=409, detail={"code": "ANALYSIS_NOT_COMPLETE", "message": job.status})
    evidence_zip_path = job.result.get("evidence_zip_path")
    if not evidence_zip_path:
        raise HTTPException(status_code=404, detail={"code": "EXPORT_NOT_FOUND", "message": "evidence package was not persisted"})
    path = PROJECT_ROOT / evidence_zip_path
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "EXPORT_NOT_FOUND", "message": str(path.name)})
    return FileResponse(path, media_type="application/zip", filename=path.name)
