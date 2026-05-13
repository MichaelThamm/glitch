"""Plain JSON-file cache for the discovery client.

Per ADR 0002: one file per entry under ``<cache_dir>/``, written atomically via
``*.tmp`` + ``os.replace``. Entries are wrapped in an envelope carrying their
own ``fetched_at`` timestamp and ``ttl_seconds``, so cache metadata travels
with the payload rather than being inferred from filesystem state.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

CacheKind = Literal["run", "jobs", "commit", "runs", "workflows"]

# TTL constants (seconds).
_TTL_IN_PROGRESS = 3600  # 1 hour for in-flight runs/jobs.
_TTL_RUNS_LIST = 300  # 5 minutes for run-list pages.
_TTL_WORKFLOWS = 3600  # 1 hour for the workflow listing (ADR 0010).


# --- Envelope ---------------------------------------------------------------


@dataclass
class CacheEnvelope:
    """On-disk wrapper around a cached API payload.

    Attributes:
        fetched_at: ISO 8601 UTC timestamp of the write, e.g. ``2026-05-13T10:00:00Z``.
        ttl_seconds: TTL in seconds; ``None`` means the entry never expires.
        kind: Discriminator naming the payload shape.
        data: The raw API response, exactly as the client received it.
    """

    fetched_at: str
    ttl_seconds: int | None
    kind: CacheKind
    data: Any


def _now_iso() -> str:
    """Return current UTC time formatted as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp, tolerating the trailing ``Z``."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


# --- Filename helpers -------------------------------------------------------


def key_run(owner: str, repo: str, run_id: int | str) -> str:
    """Filename for a single run's metadata."""
    return f"run_{owner}_{repo}_{run_id}.json"


def key_jobs(owner: str, repo: str, run_id: int | str) -> str:
    """Filename for a run's jobs payload."""
    return f"jobs_{owner}_{repo}_{run_id}.json"


def key_commit(owner: str, repo: str, sha: str) -> str:
    """Filename for a commit's metadata. Commits are immutable."""
    return f"commit_{owner}_{repo}_{sha}.json"


def key_runs(
    owner: str,
    repo: str,
    branch: str,
    since_iso: str,
    workflow_id: int | str | None = None,
) -> str:
    """Filename for a run-list page scoped to a branch and ``since`` window.

    When ``workflow_id`` is supplied (ADR 0010), the workflow-scoped variant of
    the endpoint is in use; the key gains a ``_w{workflow_id}`` suffix so the
    flat-endpoint cache and the per-workflow caches never collide.
    """
    base = f"runs_{owner}_{repo}_{branch}_{since_iso}"
    if workflow_id is not None:
        base = f"{base}_w{workflow_id}"
    return f"{base}.json"


def key_workflows(owner: str, repo: str) -> str:
    """Filename for the repo's workflow listing (ADR 0010)."""
    return f"workflows_{owner}_{repo}.json"


# --- TTL policy -------------------------------------------------------------


def ttl_for_run(run: dict[str, Any]) -> int | None:
    """Completed runs are immutable; in-flight runs expire after one hour."""
    return None if run.get("status") == "completed" else _TTL_IN_PROGRESS


def ttl_for_jobs(jobs_payload: dict[str, Any]) -> int | None:
    """Immutable only if every job in the payload reports ``completed``.

    Accepts the raw GitHub shape ``{"jobs": [...], "total_count": N}``.
    """
    jobs = jobs_payload.get("jobs", [])
    if not jobs:
        return _TTL_IN_PROGRESS
    if all(job.get("status") == "completed" for job in jobs):
        return None
    return _TTL_IN_PROGRESS


def ttl_for_runs_list() -> int:
    """Run-list pages always cache for 5 minutes."""
    return _TTL_RUNS_LIST


def ttl_for_workflows() -> int:
    """Workflow listings cache for one hour (ADR 0010)."""
    return _TTL_WORKFLOWS


def ttl_for_commit() -> None:
    """Commits are immutable."""
    return None


# --- Cache ------------------------------------------------------------------


class Cache:
    """Read-through JSON-file cache rooted at ``cache_dir``.

    The cache is intentionally trivial: ``get`` reads-and-validates, ``put``
    writes atomically. Eviction is out of scope for Phase 1 (see ADR 0002).
    """

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)

    # -- Public API ----------------------------------------------------------

    def get(self, filename: str, kind: str) -> Any | None:
        """Return the cached payload if fresh, else ``None``.

        Returns ``None`` on miss, expiry, wrong ``kind``, or malformed envelope —
        a corrupt entry must never poison the caller; the next ``put`` overwrites it.
        """
        path = self._path_for(filename)
        if not path.exists():
            return None

        try:
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        if not isinstance(raw, dict):
            return None
        if raw.get("kind") != kind:
            return None

        ttl = raw.get("ttl_seconds")
        fetched_at = raw.get("fetched_at")
        if not isinstance(fetched_at, str):
            return None

        if ttl is not None:
            try:
                fetched_dt = _parse_iso(fetched_at)
            except ValueError:
                return None
            age = (datetime.now(UTC) - fetched_dt).total_seconds()
            if age > ttl:
                return None

        return raw.get("data")

    def put(
        self,
        filename: str,
        kind: CacheKind,
        data: Any,
        ttl_seconds: int | None,
    ) -> None:
        """Atomically write an envelope for ``data`` to ``<cache_dir>/{filename}``."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        envelope = CacheEnvelope(
            fetched_at=_now_iso(),
            ttl_seconds=ttl_seconds,
            kind=kind,
            data=data,
        )
        final_path = self._path_for(filename)
        tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(asdict(envelope), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, final_path)

    # -- Internals -----------------------------------------------------------

    def _path_for(self, filename: str) -> Path:
        return self.cache_dir / filename


__all__ = [
    "Cache",
    "CacheEnvelope",
    "CacheKind",
    "key_commit",
    "key_jobs",
    "key_run",
    "key_runs",
    "key_workflows",
    "ttl_for_commit",
    "ttl_for_jobs",
    "ttl_for_run",
    "ttl_for_runs_list",
    "ttl_for_workflows",
]
