"""
Background job runner for the dashboard (design §7.1).

A refresh costs $2-8 and minutes; a thesis run costs $30-60 and longer —
buttons can't block an HTTP request. `JobRunner` is backed by a
`ThreadPoolExecutor(max_workers=1)`: ONE worker on purpose. The whole
rate-limiting story (sequential graph, shared InMemoryRateLimiter) means
concurrent jobs would burst Anthropic's input-token caps, so extra jobs
queue rather than run in parallel.

Each job's status is mirrored to ~/.tacapes/jobs/<job_id>.json so the
dashboard (and a curious operator) can see it without shared memory.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal

from ..config import tacapes_home
from ..schemas import Strict

# A job body: takes a `progress(msg)` callback, returns a short result_ref.
JobFn = Callable[[Callable[[str], None]], str]


def jobs_dir() -> Path:
    return tacapes_home() / "jobs"


class Job(Strict):
    """One unit of background work, mirrored to ~/.tacapes/jobs/<id>.json."""

    id: str
    kind: Literal["refresh", "thesis", "mission"]
    target: str                       # ticker (refresh) | statement (thesis)
    status: Literal["queued", "running", "done", "failed"] = "queued"
    progress_msg: str = ""
    cost_usd: float = 0.0
    result_ref: str | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobRunner:
    """Single-worker job queue. Thread-safe; mirrors every state change to
    disk. `drain_completed()` lets the /jobs route fire `HX-Trigger:
    fundChanged` exactly once per finished job."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="tacapes-job"
        )
        self._jobs: dict[str, Job] = {}
        self._newly_done: set[str] = set()
        self._lock = threading.Lock()

    # --- public API ---

    def submit(self, *, kind: str, target: str, fn: JobFn) -> Job:
        """Enqueue a job. Returns the queued Job immediately; `fn` runs on the
        single background worker (queued behind any in-flight job)."""
        from uuid import uuid4  # noqa: PLC0415

        job = Job(
            id=str(uuid4()),
            kind=kind,  # type: ignore[arg-type]
            target=target,
            created_at=datetime.now(UTC),
        )
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        self._executor.submit(self._run, job.id, fn)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(
                self._jobs.values(), key=lambda j: j.created_at, reverse=True
            )

    def drain_completed(self) -> set[str]:
        """Return + clear the ids of jobs that finished since the last call —
        the /jobs route uses this to fire `fundChanged` once per completion."""
        with self._lock:
            done = self._newly_done
            self._newly_done = set()
            return done

    # --- internals ---

    def _run(self, job_id: str, fn: JobFn) -> None:
        from ..cost import _TRACKER  # noqa: PLC0415

        before = _TRACKER.snapshot().total_usd()
        self._update(job_id, status="running", started_at=datetime.now(UTC),
                     progress_msg="started")
        try:
            result_ref = fn(lambda msg: self._update(job_id, progress_msg=msg))
            self._update(
                job_id, status="done", result_ref=str(result_ref),
                finished_at=datetime.now(UTC),
                cost_usd=round(_TRACKER.snapshot().total_usd() - before, 4),
            )
        except Exception as e:  # noqa: BLE001 — a failed job must not kill the worker
            self._update(
                job_id, status="failed", error=f"{type(e).__name__}: {e}"[:300],
                finished_at=datetime.now(UTC),
                cost_usd=round(_TRACKER.snapshot().total_usd() - before, 4),
            )
        with self._lock:
            self._newly_done.add(job_id)

    def _update(self, job_id: str, **fields: object) -> None:
        with self._lock:
            job = self._jobs[job_id].model_copy(update=fields)
            self._jobs[job_id] = job
        self._persist(job)

    def _persist(self, job: Job) -> None:
        d = jobs_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{job.id}.json").write_text(
            job.model_dump_json(indent=2), encoding="utf-8"
        )


__all__ = ["Job", "JobRunner", "JobFn", "jobs_dir"]
