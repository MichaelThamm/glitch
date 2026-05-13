"""Domain models for Phase 1 discovery.

Per ADR 0003: every internal shape is a ``@dataclass(slots=True, frozen=True)``.
Parsing from raw GitHub JSON is centralised here via ``from_api`` classmethods,
so the rest of the package only ever sees typed instances. ``datetime`` values
are always timezone-aware UTC inside the program; ISO-8601 strings (Z-suffix)
are reserved for the wire/cache format.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

# --- Datetime helpers -------------------------------------------------------


def _parse_dt(s: str) -> datetime:
    """Parse a GitHub ISO 8601 timestamp into a timezone-aware UTC datetime.

    GitHub returns ``YYYY-MM-DDTHH:MM:SSZ``; ``datetime.fromisoformat`` accepts
    a ``+00:00`` offset on every supported Python version, so we normalise the
    trailing ``Z`` before delegating.
    """
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_dt_optional(s: str | None) -> datetime | None:
    """Parse an optional GitHub timestamp; ``None`` passes through unchanged."""
    if s is None:
        return None
    return _parse_dt(s)


def _isoformat(dt: datetime) -> str:
    """Render a timezone-aware UTC ``datetime`` as ``...Z``-suffix ISO 8601."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- Raw API shapes ---------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Run:
    """A GitHub Actions workflow run.

    Source: ``GET /repos/{owner}/{repo}/actions/runs`` list items.
    """

    id: int
    name: str
    head_sha: str
    head_branch: str | None
    status: str
    conclusion: str | None
    created_at: datetime
    updated_at: datetime
    run_attempt: int

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> Self:
        return cls(
            id=payload["id"],
            name=payload["name"],
            head_sha=payload["head_sha"],
            head_branch=payload.get("head_branch"),
            status=payload["status"],
            conclusion=payload.get("conclusion"),
            created_at=_parse_dt(payload["created_at"]),
            updated_at=_parse_dt(payload["updated_at"]),
            run_attempt=payload["run_attempt"],
        )


@dataclass(slots=True, frozen=True)
class Job:
    """A single job within a workflow run.

    Source: ``GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs``.
    """

    id: int
    run_id: int
    name: str
    status: str
    conclusion: str | None
    started_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> Self:
        return cls(
            id=payload["id"],
            run_id=payload["run_id"],
            name=payload["name"],
            status=payload["status"],
            conclusion=payload.get("conclusion"),
            started_at=_parse_dt_optional(payload.get("started_at")),
            completed_at=_parse_dt_optional(payload.get("completed_at")),
        )


@dataclass(slots=True, frozen=True)
class Commit:
    """A commit's metadata, including the file paths it touched.

    Source: ``GET /repos/{owner}/{repo}/commits/{ref}``. ``files`` is a tuple
    (not a list) so this dataclass remains hashable under ``frozen=True``;
    GitHub omits ``files`` from some response shapes, in which case we record
    an empty tuple rather than ``None``.
    """

    sha: str
    message: str
    author_date: datetime
    files: tuple[str, ...]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> Self:
        commit = payload["commit"]
        author_date = _parse_dt(commit["author"]["date"])
        files_payload = payload.get("files") or ()
        files = tuple(entry["filename"] for entry in files_payload)
        return cls(
            sha=payload["sha"],
            message=commit["message"],
            author_date=author_date,
            files=files,
        )


# --- Internal / derived types ----------------------------------------------


@dataclass(slots=True, frozen=True)
class Heuristics:
    """Per-test heuristic scores, each independently normalised to ``[0, 1]``."""

    volatility: float
    retry_rate: float
    timing_variance: float
    change_independence: float


@dataclass(slots=True, frozen=True)
class TestScore:
    """A single test's flakiness verdict, ready for the output payload."""

    id: str
    job_name: str
    flakiness_index: float
    run_count: int
    heuristics: Heuristics
    trend: tuple[str, ...]
    last_failed_at: datetime | None


@dataclass(slots=True, frozen=True)
class InsufficientData:
    """A test that did not clear the minimum-runs threshold for scoring."""

    id: str
    run_count: int


@dataclass(slots=True, frozen=True)
class Meta:
    """Provenance for a discovery report."""

    repo: str
    branch: str
    generated_at: datetime
    lookback_days: int
    total_runs_analysed: int
    glitch_version: str


@dataclass(slots=True, frozen=True)
class DiscoveryReport:
    """The full Phase-1 output payload, serialised verbatim to JSON."""

    meta: Meta
    tests: tuple[TestScore, ...]
    insufficient_data: tuple[InsufficientData, ...]


# --- Serialisation ----------------------------------------------------------


def to_json(report: DiscoveryReport) -> str:
    """Serialise a ``DiscoveryReport`` to the canonical JSON wire format."""
    return json.dumps(
        dataclasses.asdict(report),
        default=_isoformat,
        indent=2,
    )


__all__ = [
    "Commit",
    "DiscoveryReport",
    "Heuristics",
    "InsufficientData",
    "Job",
    "Meta",
    "Run",
    "TestScore",
    "to_json",
]
