"""Serve the React/FastAPI GreenMPC command center from one local URL."""

from __future__ import annotations

import sys
import os
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    if not (FRONTEND_DIST / "index.html").exists():
        print("Compiled frontend assets are missing. Run: cd frontend && npm install && npm run build", file=sys.stderr)
        return 2
    os.chdir(PROJECT_ROOT)
    print("GreenMPC Command Center: http://127.0.0.1:8000")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
