"""Tests for `glitch.discover.models` — ADR 0003.

Covers `from_api` parsing for the three raw GitHub shapes, the frozen-dataclass
invariant, the datetime helpers, and the end-to-end `to_json` serialisation.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from glitch.discover.models import (
    Commit,
    DiscoveryReport,
    Heuristics,
    InsufficientData,
    Job,
    Meta,
    Run,
)
from glitch.discover.models import TestScore as _TestScore  # avoid pytest "Test*" collection
from glitch.discover.models import (
    _isoformat,
    _parse_dt,
    _parse_dt_optional,
    to_json,
)


# --- Fixtures ---------------------------------------------------------------


def _run_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 123456789,
        "name": "CI",
        "head_sha": "deadbeefcafebabe0000111122223333deadbeef",
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-05-13T10:00:00Z",
        "updated_at": "2026-05-13T10:15:00Z",
        "run_attempt": 1,
    }
    base.update(overrides)
    return base


def _job_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 987654321,
        "run_id": 123456789,
        "name": "integration (test_deploy_local)",
        "status": "completed",
        "conclusion": "failure",
        "started_at": "2026-05-13T10:01:00Z",
        "completed_at": "2026-05-13T10:14:00Z",
    }
    base.update(overrides)
    return base


def _commit_payload(*, files: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sha": "deadbeefcafebabe0000111122223333deadbeef",
        "commit": {
            "message": "fix: stop the flaky thing",
            "author": {"date": "2026-05-13T09:00:00Z"},
        },
    }
    if files is not None:
        payload["files"] = files
    return payload


# --- Run.from_api -----------------------------------------------------------


def test_run_from_api_parses_all_fields() -> None:
    run = Run.from_api(_run_payload())

    assert run.id == 123456789
    assert run.name == "CI"
    assert run.head_sha == "deadbeefcafebabe0000111122223333deadbeef"
    assert run.head_branch == "main"
    assert run.status == "completed"
    assert run.conclusion == "success"
    assert run.run_attempt == 1
    assert run.created_at == datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    assert run.updated_at == datetime(2026, 5, 13, 10, 15, 0, tzinfo=UTC)


def test_run_from_api_datetimes_are_tz_aware_utc() -> None:
    run = Run.from_api(_run_payload())

    assert run.created_at.tzinfo is not None
    assert run.updated_at.tzinfo is not None
    assert run.created_at.utcoffset() == UTC.utcoffset(None)
    assert run.updated_at.utcoffset() == UTC.utcoffset(None)


def test_run_from_api_optional_head_branch_and_conclusion() -> None:
    run = Run.from_api(_run_payload(head_branch=None, conclusion=None))

    assert run.head_branch is None
    assert run.conclusion is None


# --- Job.from_api -----------------------------------------------------------


def test_job_from_api_parses_all_fields() -> None:
    job = Job.from_api(_job_payload())

    assert job.id == 987654321
    assert job.run_id == 123456789
    assert job.name == "integration (test_deploy_local)"
    assert job.status == "completed"
    assert job.conclusion == "failure"
    assert job.started_at == datetime(2026, 5, 13, 10, 1, 0, tzinfo=UTC)
    assert job.completed_at == datetime(2026, 5, 13, 10, 14, 0, tzinfo=UTC)


def test_job_from_api_in_progress_completed_at_is_none() -> None:
    job = Job.from_api(_job_payload(status="in_progress", conclusion=None, completed_at=None))

    assert job.completed_at is None
    assert job.status == "in_progress"
    assert job.conclusion is None
    # An in-progress job still has a started_at; make sure that survived.
    assert job.started_at == datetime(2026, 5, 13, 10, 1, 0, tzinfo=UTC)


def test_job_from_api_missing_started_at_is_none() -> None:
    payload = _job_payload()
    del payload["started_at"]

    job = Job.from_api(payload)

    assert job.started_at is None


# --- Commit.from_api --------------------------------------------------------


def test_commit_from_api_missing_files_key_yields_empty_tuple() -> None:
    commit = Commit.from_api(_commit_payload())

    assert commit.files == ()
    assert isinstance(commit.files, tuple)


def test_commit_from_api_with_files_returns_tuple_of_filenames() -> None:
    files = [
        {"filename": "src/glitch/discover/models.py", "status": "modified"},
        {"filename": "tests/test_discover_models.py", "status": "added"},
    ]
    commit = Commit.from_api(_commit_payload(files=files))

    assert commit.files == (
        "src/glitch/discover/models.py",
        "tests/test_discover_models.py",
    )
    assert isinstance(commit.files, tuple)


def test_commit_from_api_parses_sha_message_and_author_date() -> None:
    commit = Commit.from_api(_commit_payload())

    assert commit.sha == "deadbeefcafebabe0000111122223333deadbeef"
    assert commit.message == "fix: stop the flaky thing"
    assert commit.author_date == datetime(2026, 5, 13, 9, 0, 0, tzinfo=UTC)
    assert commit.author_date.tzinfo is not None


def test_commit_from_api_null_files_becomes_empty_tuple() -> None:
    # GitHub can also send `files: null` for some commit shapes; the impl uses
    # `payload.get("files") or ()`, so null should collapse to empty as well.
    payload = _commit_payload()
    payload["files"] = None

    commit = Commit.from_api(payload)

    assert commit.files == ()


# --- Frozen-dataclass invariant --------------------------------------------


def test_run_is_frozen_assignment_raises() -> None:
    run = Run.from_api(_run_payload())

    with pytest.raises(dataclasses.FrozenInstanceError):
        run.name = "x"  # type: ignore[misc]


# --- Datetime helpers -------------------------------------------------------


def test_parse_dt_z_suffix_returns_tz_aware_utc() -> None:
    dt = _parse_dt("2026-05-13T10:00:00Z")

    assert dt == datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    assert dt.tzinfo is not None
    assert dt.utcoffset() == UTC.utcoffset(None)


def test_isoformat_round_trips_z_suffix() -> None:
    dt = _parse_dt("2026-05-13T10:00:00Z")

    assert _isoformat(dt) == "2026-05-13T10:00:00Z"


def test_parse_dt_optional_none_returns_none() -> None:
    assert _parse_dt_optional(None) is None


def test_parse_dt_optional_passes_through_real_value() -> None:
    assert _parse_dt_optional("2026-05-13T10:00:00Z") == datetime(
        2026, 5, 13, 10, 0, 0, tzinfo=UTC
    )


# --- DiscoveryReport / to_json end-to-end ----------------------------------


def _sample_report() -> DiscoveryReport:
    meta = Meta(
        repo="canonical/my-charm",
        branch="main",
        generated_at=datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC),
        lookback_days=30,
        total_runs_analysed=142,
        glitch_version="0.1.0",
    )
    test = _TestScore(
        id="integration (test_deploy_local)",
        job_name="integration (test_deploy_local)",
        flakiness_index=0.87,
        run_count=38,
        heuristics=Heuristics(
            volatility=0.91,
            retry_rate=0.82,
            timing_variance=0.71,
            change_independence=0.88,
        ),
        trend=("pass", "pass", "fail", "pass", "pass"),
        last_failed_at=datetime(2026, 5, 12, 14, 22, 0, tzinfo=UTC),
    )
    insufficient = InsufficientData(id="integration (test_new_feature)", run_count=2)
    return DiscoveryReport(
        meta=meta,
        tests=(test,),
        insufficient_data=(insufficient,),
    )


def test_report_collections_are_tuples() -> None:
    report = _sample_report()

    assert isinstance(report.tests, tuple)
    assert isinstance(report.insufficient_data, tuple)


def test_to_json_produces_valid_json_with_expected_top_level_keys() -> None:
    payload = json.loads(to_json(_sample_report()))

    assert set(payload.keys()) == {"meta", "tests", "insufficient_data"}


def test_to_json_serialises_datetimes_with_z_suffix() -> None:
    payload = json.loads(to_json(_sample_report()))

    assert payload["meta"]["generated_at"] == "2026-05-13T10:00:00Z"
    assert payload["tests"][0]["last_failed_at"] == "2026-05-12T14:22:00Z"


def test_to_json_nests_heuristics_under_each_test() -> None:
    payload = json.loads(to_json(_sample_report()))

    test = payload["tests"][0]
    assert "heuristics" in test
    assert test["heuristics"] == {
        "volatility": 0.91,
        "retry_rate": 0.82,
        "timing_variance": 0.71,
        "change_independence": 0.88,
    }


def test_to_json_preserves_meta_and_insufficient_data_fields() -> None:
    payload = json.loads(to_json(_sample_report()))

    assert payload["meta"] == {
        "repo": "canonical/my-charm",
        "branch": "main",
        "generated_at": "2026-05-13T10:00:00Z",
        "lookback_days": 30,
        "total_runs_analysed": 142,
        "glitch_version": "0.1.0",
    }
    assert payload["insufficient_data"] == [
        {"id": "integration (test_new_feature)", "run_count": 2},
    ]


def test_to_json_test_entry_matches_spec_shape() -> None:
    payload = json.loads(to_json(_sample_report()))
    test = payload["tests"][0]

    assert test["id"] == "integration (test_deploy_local)"
    assert test["job_name"] == "integration (test_deploy_local)"
    assert test["flakiness_index"] == 0.87
    assert test["run_count"] == 38
    assert test["trend"] == ["pass", "pass", "fail", "pass", "pass"]
