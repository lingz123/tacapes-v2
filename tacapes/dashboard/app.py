"""FastAPI app for the tacapes history dashboard.

Routes:
  GET  /                       history page (Jinja, deleted in Phase 6)
  GET  /healthz                DB ping
  GET  /api/*                  JSON API for the React SPA (Phase 2)
  GET  /missions/new           new-mission form              (Task 4.2)
  POST /missions               enqueue a mission             (Task 4.3)
  GET  /missions/{id}          detail page                   (Task 3.5)
  GET  /missions/{id}/status   HTMX poll fragment            (Task 4.4)
  POST /missions/{id}/delete   delete a mission              (Task 5.4)
  POST /prices/refresh         invalidate the 15-min cache   (Task 3.6)

SPA lifecycle (see docs/superpowers/plans/2026-05-31-dashboard-redesign.md):
- Phases 1-5: Jinja UI lives at /, React app served via `vite dev` on :5173.
  If a production build exists at web/dist/, FastAPI also serves it as a
  catch-all on unmatched routes — so visiting an SPA-only path like /app
  hits the React shell.
- Phase 6: Jinja routes deleted; SPA becomes the only frontend.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import filters as _filters

_DIR = Path(__file__).parent
_WEB_DIST = _DIR / "web" / "dist"
_TEMPLATES = Jinja2Templates(directory=str(_DIR / "templates"))
_filters.register(_TEMPLATES.env)


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

    # Jinja routes. Phase 6 removes this.
    from . import routes
    routes.register(app)

    # JSON API. Registered before the SPA fallback so /api/* never falls
    # through to index.html.
    from .api import routes as api_routes
    api_routes.register(app)

    # SPA fallback. Only active when `pnpm build` has produced web/dist/.
    # Until Phase 6 these only catch unmatched paths (e.g. /app, /missions
    # routes the React Router knows about that Jinja doesn't); after Phase 6
    # this becomes the sole frontend handler.
    if _WEB_DIST.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_WEB_DIST / "assets")),
            name="spa-assets",
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> Any:
            # /api/* never reaches here — those routes register first.
            # Same-named static files (favicon, etc.) are served from dist root.
            candidate = _WEB_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(_WEB_DIST / "index.html")

    return app
