"""
Phase 4 tests — the local dashboard.

Route smoke tests use FastAPI's `TestClient` with a synchronous fake
JobRunner (design §11) so they neither spawn threads nor hit the network —
`submit` records a job without running its (LLM-bound) body. The real
`JobRunner` is exercised separately with a trivial in-process job.

Covered: every route in §7.2 renders, refresh/thesis enqueue jobs, apply/
discard mutate the book, `/jobs` fires `HX-Trigger: fundChanged` exactly once
per completion, the memo route renders, and the JobRunner mirrors job state
to disk + reports completions.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from tacapes.dashboard.app import create_app
from tacapes.dashboard.jobs import Job, JobRunner, jobs_dir
from tacapes.fund import load_fund
from tacapes.proposals import load_proposal

from tests.test_fund import run_cold_start
from tests.test_proposals import run_incremental


# ---------------------------------------------------------------------------
# a synchronous fake JobRunner — records jobs, never runs their bodies
# ---------------------------------------------------------------------------

class FakeJobRunner:
    def __init__(self) -> None:
        self._jobs: list[Job] = []
        self._completed: set[str] = set()

    def submit(self, *, kind: str, target: str, fn) -> Job:  # noqa: ARG002
        job = Job(
            id=str(uuid4()), kind=kind, target=target, status="queued",
            created_at=datetime.now(UTC),
        )
        self._jobs.append(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return next((j for j in self._jobs if j.id == job_id), None)

    def list_jobs(self) -> list[Job]:
        return list(reversed(self._jobs))

    def drain_completed(self) -> set[str]:
        done, self._completed = self._completed, set()
        return done

    def mark_done(self, job_id: str) -> None:
        """Test helper — flip a job to done and queue it for announcement."""
        self._jobs = [
            j.model_copy(update={"status": "done"}) if j.id == job_id else j
            for j in self._jobs
        ]
        self._completed.add(job_id)


def _client(monkeypatch, tmp_path) -> tuple[TestClient, FakeJobRunner]:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    fake = FakeJobRunner()
    return TestClient(create_app(job_runner=fake)), fake


# ---------------------------------------------------------------------------
# GET /  — the dashboard page
# ---------------------------------------------------------------------------

def test_index_renders_without_a_fund(tmp_path, monkeypatch) -> None:
    client, _fake = _client(monkeypatch, tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "tacapes" in resp.text
    assert "No fund yet" in resp.text
    assert 'src="/static/htmx.min.js"' in resp.text


def test_index_renders_the_book(tmp_path, monkeypatch) -> None:
    run_cold_start(tmp_path, monkeypatch)  # sets TACAPES_HOME, writes fund.json
    client = TestClient(create_app(job_runner=FakeJobRunner()))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "NUSC" in resp.text and "CEG" in resp.text
    assert 'id="book"' in resp.text


def test_static_htmx_is_served(tmp_path, monkeypatch) -> None:
    client, _fake = _client(monkeypatch, tmp_path)
    resp = client.get("/static/htmx.min.js")
    assert resp.status_code == 200
    assert "HTMX-subset" in resp.text


# ---------------------------------------------------------------------------
# POST /refresh, /thesis  — enqueue jobs
# ---------------------------------------------------------------------------

def test_post_refresh_enqueues_a_refresh_job(tmp_path, monkeypatch) -> None:
    client, fake = _client(monkeypatch, tmp_path)
    resp = client.post("/refresh/nusc")
    assert resp.status_code == 200
    assert len(fake._jobs) == 1
    assert fake._jobs[0].kind == "refresh"
    assert fake._jobs[0].target == "NUSC"      # uppercased by the route
    assert "NUSC" in resp.text                 # the _jobs fragment shows it


def test_post_thesis_enqueues_a_thesis_job(tmp_path, monkeypatch) -> None:
    client, fake = _client(monkeypatch, tmp_path)
    resp = client.post("/thesis", data={
        "statement": "Buy advanced reactor names for the AI power decade",
        "budget": 25000,
        "max_positions": 4,
    })
    assert resp.status_code == 200
    assert len(fake._jobs) == 1
    assert fake._jobs[0].kind == "thesis"


# ---------------------------------------------------------------------------
# GET /jobs  — poll fragment + HX-Trigger
# ---------------------------------------------------------------------------

def test_jobs_fragment_fires_fundchanged_once_per_completion(tmp_path, monkeypatch) -> None:
    client, fake = _client(monkeypatch, tmp_path)
    job = fake.submit(kind="refresh", target="NUSC", fn=lambda p: "x")

    # nothing completed yet → no trigger
    assert "HX-Trigger" not in client.get("/jobs").headers

    # a job finishes → the next /jobs poll fires fundChanged, exactly once
    fake.mark_done(job.id)
    first = client.get("/jobs")
    assert first.headers.get("HX-Trigger") == "fundChanged"
    second = client.get("/jobs")
    assert "HX-Trigger" not in second.headers


# ---------------------------------------------------------------------------
# POST /proposal/{id}/apply + /discard
# ---------------------------------------------------------------------------

def test_proposal_apply_route_commits_to_the_fund(tmp_path, monkeypatch) -> None:
    _m1, _fund_before, proposal = run_incremental(tmp_path, monkeypatch)
    client = TestClient(create_app(job_runner=FakeJobRunner()))

    resp = client.post(f"/proposal/{proposal.id}/apply")
    assert resp.status_code == 200
    assert 'id="book"' in resp.text                         # returns the book fragment
    assert load_proposal(proposal.id).status == "applied"
    assert {h.ticker for h in load_fund().holdings} >= {"NUSC", "CEG", "OKLO", "SMR"}


def test_proposal_discard_route(tmp_path, monkeypatch) -> None:
    _m1, _fund_before, proposal = run_incremental(tmp_path, monkeypatch)
    client = TestClient(create_app(job_runner=FakeJobRunner()))

    resp = client.post(f"/proposal/{proposal.id}/discard")
    assert resp.status_code == 200
    assert load_proposal(proposal.id).status == "discarded"
    # the fund is untouched by a discard
    assert {h.ticker for h in load_fund().holdings} == {"NUSC", "CEG"}


# ---------------------------------------------------------------------------
# GET /memo/{ticker}
# ---------------------------------------------------------------------------

def test_memo_route_renders_detail(tmp_path, monkeypatch) -> None:
    run_cold_start(tmp_path, monkeypatch)
    client = TestClient(create_app(job_runner=FakeJobRunner()))

    resp = client.get("/memo/NUSC")
    assert resp.status_code == 200
    assert "NUSC" in resp.text
    assert "conviction" in resp.text
    assert "Thesis breakers" in resp.text

    missing = client.get("/memo/NOPE")
    assert missing.status_code == 200
    assert "no memo found" in missing.text


# ---------------------------------------------------------------------------
# the real JobRunner
# ---------------------------------------------------------------------------

def test_jobrunner_runs_job_and_mirrors_to_disk(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    runner = JobRunner()
    seen: list[str] = []

    def body(progress):
        progress("step one")
        progress("step two")
        return "trivial-result"

    job = runner.submit(kind="refresh", target="NUSC", fn=body)
    runner._executor.shutdown(wait=True)  # block until the worker is done

    final = runner.get(job.id)
    assert final.status == "done"
    assert final.result_ref == "trivial-result"
    assert final.progress_msg == "step two"
    assert final.started_at is not None and final.finished_at is not None

    # mirrored to ~/.tacapes/jobs/<id>.json and re-validates as a Job
    disk = jobs_dir() / f"{job.id}.json"
    assert disk.exists()
    assert Job.model_validate_json(disk.read_text()).status == "done"

    # the completion is reported exactly once
    assert runner.drain_completed() == {job.id}
    assert runner.drain_completed() == set()
    _ = seen


def test_jobrunner_marks_failed_job(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TACAPES_HOME", str(tmp_path))
    runner = JobRunner()

    def body(progress):  # noqa: ARG001
        raise RuntimeError("boom")

    job = runner.submit(kind="refresh", target="X", fn=body)
    runner._executor.shutdown(wait=True)

    final = runner.get(job.id)
    assert final.status == "failed"
    assert "RuntimeError: boom" in final.error
    assert final.finished_at is not None
