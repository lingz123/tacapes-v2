"""FastAPI app for the tacapes dashboard.

Routes:
  GET  /healthz                   DB ping
  GET  /api/*                     JSON API for the React SPA
  GET  /assets/*                  built JS/CSS chunks served from web/dist/assets
  GET  /{anything}                SPA fallback: serves the matching file out
                                  of web/dist if it exists, otherwise index.html
                                  so React Router can take over

The Jinja+HTMX UI that used to live here was deleted in the dashboard-redesign
Phase 6 cutover; see
docs/superpowers/specs/2026-05-31-dashboard-redesign-design.md.

The SPA fallback only mounts when `pnpm build` has produced `web/dist/`.
Dev mode runs `vite dev` on :5173 separately, with /api proxied through
to this app on :8732 — `dist/` is absent there and the catch-all routes
are simply not registered.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_DIR = Path(__file__).parent
_WEB_DIST = _DIR / "web" / "dist"


def create_app(*, job_runner: Any | None = None) -> FastAPI:
    """Build the dashboard app. Pass `job_runner` to inject a fake in tests."""
    from .jobs import JobRunner

    app = FastAPI(title="tacapes dashboard")
    app.state.job_runner = job_runner if job_runner is not None else JobRunner()

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

    # JSON API. Registered before the SPA fallback so /api/* never falls
    # through to index.html.
    from .api import routes as api_routes
    api_routes.register(app)

    # SPA fallback. Only active when `pnpm build` has produced web/dist/.
    # In dev (`vite dev` on :5173), this branch stays inert and FastAPI
    # serves only /healthz + /api/*.
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
