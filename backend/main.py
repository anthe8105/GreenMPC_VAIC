"""FastAPI entry point for the GreenMPC React command center."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import benchmark, control, health, investment, provenance, session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend/dist"


def create_app() -> FastAPI:
    app = FastAPI(title="GreenMPC Command Center API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(session.router)
    app.include_router(control.router)
    app.include_router(benchmark.router)
    app.include_router(investment.router)
    app.include_router(provenance.router)

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception):
        logging.getLogger(__name__).exception("unhandled API error")
        return JSONResponse(status_code=500, content={"detail": {"code": "INTERNAL_ERROR", "message": str(exc)}})

    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        logging.getLogger(__name__).info("Mounting SPA from %s", FRONTEND_DIST)
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(_: str = ""):
            return FileResponse(index_html)
    else:
        logging.getLogger(__name__).warning(
            "frontend/dist not found at %s - SPA/root routes NOT mounted (built frontend is missing)",
            FRONTEND_DIST,
        )

    return app


app = create_app()
