"""
FastAPI app for the local dashboard (design §7.2).

No build step, no JS framework — Jinja templates plus a vendored HTMX-subset
shim under static/. `create_app` takes an optional `job_runner` so tests can
swap in a synchronous fake (no threads, no network).

Routes
  GET  /                       full dashboard page
  POST /refresh/{ticker}       enqueue a refresh job
  POST /thesis                 enqueue a thesis job from the new-thesis form
  POST /proposal/{id}/apply    apply a proposal → refreshed book fragment
  POST /proposal/{id}/discard  discard a pending proposal → book fragment
  GET  /jobs                   HTMX poll fragment; fires HX-Trigger: fundChanged
  GET  /memo/{ticker}          memo detail (drivers/risks/breakers/valuation)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_DIR = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_DIR / "templates"))


def _book_context() -> dict[str, Any]:
    """Fund + the single pending proposal — the data behind the `#book` div."""
    from ..fund import fund_exists, load_fund
    from ..proposals import list_proposals

    fund = load_fund() if fund_exists() else None
    pending = next(
        (p for p in list_proposals() if p.status == "pending"), None
    )
    return {"fund": fund, "proposal": pending}


def _load_memo(ticker: str) -> Any:
    """The latest InvestmentMemo for a holding, via its stored memo_ref."""
    from ..config import tacapes_home
    from ..fund import fund_exists, get_holding, load_fund
    from ..schemas import InvestmentMemo

    if not fund_exists():
        return None
    holding = get_holding(load_fund(), ticker)
    if holding is None:
        return None
    path = tacapes_home() / holding.memo_ref
    if not path.exists():
        return None
    return InvestmentMemo.model_validate_json(path.read_text(encoding="utf-8"))


def create_app(*, job_runner: Any | None = None) -> FastAPI:
    """Build the dashboard app. Pass `job_runner` to inject a fake in tests."""
    from .jobs import JobRunner

    app = FastAPI(title="tacapes dashboard")
    app.state.job_runner = job_runner if job_runner is not None else JobRunner()
    app.mount(
        "/static", StaticFiles(directory=str(_DIR / "static")), name="static"
    )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Any:
        ctx = _book_context()
        ctx["jobs"] = request.app.state.job_runner.list_jobs()
        return _TEMPLATES.TemplateResponse(request, "index.html", ctx)

    @app.post("/refresh/{ticker}", response_class=HTMLResponse)
    def refresh(request: Request, ticker: str) -> Any:
        from .runners import make_refresh_job

        runner = request.app.state.job_runner
        runner.submit(
            kind="refresh",
            target=ticker.upper(),
            fn=make_refresh_job(ticker.upper()),
        )
        return _TEMPLATES.TemplateResponse(
            request, "_jobs.html", {"jobs": runner.list_jobs()}
        )

    @app.post("/thesis", response_class=HTMLResponse)
    def thesis(
        request: Request,
        statement: str = Form(...),
        budget: float = Form(20000.0),
        max_positions: int = Form(5),
    ) -> Any:
        from .runners import make_thesis_job

        runner = request.app.state.job_runner
        runner.submit(
            kind="thesis",
            target=statement[:80],
            fn=make_thesis_job(statement, budget, max_positions),
        )
        return _TEMPLATES.TemplateResponse(
            request, "_jobs.html", {"jobs": runner.list_jobs()}
        )

    @app.post("/proposal/{proposal_id}/apply", response_class=HTMLResponse)
    def proposal_apply(request: Request, proposal_id: str) -> Any:
        from ..proposals import apply_proposal

        try:
            apply_proposal(proposal_id)
        except (ValueError, FileNotFoundError):
            pass  # already applied/discarded/gone — fall through to re-render
        return _TEMPLATES.TemplateResponse(request, "_book.html", _book_context())

    @app.post("/proposal/{proposal_id}/discard", response_class=HTMLResponse)
    def proposal_discard(request: Request, proposal_id: str) -> Any:
        from ..proposals import discard_proposal

        try:
            discard_proposal(proposal_id)
        except (ValueError, FileNotFoundError):
            pass
        return _TEMPLATES.TemplateResponse(request, "_book.html", _book_context())

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs(request: Request) -> Any:
        runner = request.app.state.job_runner
        resp = _TEMPLATES.TemplateResponse(
            request, "_jobs.html", {"jobs": runner.list_jobs()}
        )
        # A job flipped to done/failed since the last poll → tell the book to
        # re-fetch itself (design §7.2).
        if runner.drain_completed():
            resp.headers["HX-Trigger"] = "fundChanged"
        return resp

    @app.get("/memo/{ticker}", response_class=HTMLResponse)
    def memo(request: Request, ticker: str) -> Any:
        return _TEMPLATES.TemplateResponse(
            request,
            "_memo.html",
            {"ticker": ticker.upper(), "memo": _load_memo(ticker.upper())},
        )

    return app
