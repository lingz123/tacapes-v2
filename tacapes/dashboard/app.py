"""FastAPI app for the tacapes history dashboard.

Routes:
  GET  /                       history page
  GET  /healthz                DB ping
  GET  /missions/new           new-mission form              (Task 4.2)
  POST /missions               enqueue a mission             (Task 4.3)
  GET  /missions/{id}          detail page                   (Task 3.5)
  GET  /missions/{id}/status   HTMX poll fragment            (Task 4.4)
  POST /missions/{id}/delete   delete a mission              (Task 5.4)
  POST /prices/refresh         invalidate the 15-min cache   (Task 3.6)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_DIR = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_DIR / "templates"))


def create_app(*, job_runner: Any | None = None) -> FastAPI:
    """Build the dashboard app. Pass `job_runner` to inject a fake in tests."""
    from .jobs import JobRunner

    app = FastAPI(title="tacapes history dashboard")
    app.state.job_runner = job_runner if job_runner is not None else JobRunner()
    app.state.templates = _TEMPLATES
    app.mount(
        "/static", StaticFiles(directory=str(_DIR / "static")), name="static"
    )

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        from sqlalchemy import text
        from .db import get_engine
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return JSONResponse({"ok": True})
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=503)

    # Routes registered here in later tasks (3.4, 3.5, 3.6, 4.2-4.4, 5.4).
    from . import routes
    routes.register(app)

    return app
