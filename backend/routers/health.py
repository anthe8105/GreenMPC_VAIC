"""Health routes."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health() -> dict[str, str | bool]:
    return {"status": "ok", "offline": True, "service": "greenmpc-command-center"}
