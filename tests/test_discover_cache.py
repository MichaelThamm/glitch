"""Tests for the local JSON-file cache layer (ADR 0002)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from glitch.discover.cache import (
    Cache,
    key_commit,
    key_jobs,
    key_run,
    key_runs,
    key_workflows,
    ttl_for_commit,
    ttl_for_jobs,
    ttl_for_run,
    ttl_for_runs_list,
    ttl_for_workflows,
)


# --- Helpers ----------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_envelope(
    path: Path,
    *,
    kind: str,
    data: object,
    ttl_seconds: int | None,
    fetched_at: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "fetched_at": fetched_at,
                "ttl_seconds": ttl_seconds,
                "kind": kind,
                "data": data,
            }
        ),
        encoding="utf-8",
    )


# --- Round-trip & basic miss paths ------------------------------------------


def test_put_then_get_roundtrip_immutable(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    payload = {"id": 42, "status": "completed"}
    cache.put("run_o_r_42.json", "run", payload, ttl_seconds=None)
    assert cache.get("run_o_r_42.json", "run") == payload


def test_wrong_kind_returns_none(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    cache.put("run_o_r_1.json", "run", {"id": 1}, ttl_seconds=None)
    assert cache.get("run_o_r_1.json", "jobs") is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    assert cache.get("run_o_r_nope.json", "run") is None


# --- TTL behaviour ----------------------------------------------------------


def test_expired_entry_is_miss(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    stale = _iso(datetime.now(UTC) - timedelta(hours=2))
    _write_envelope(
        tmp_path / "run_o_r_7.json",
        kind="run",
        data={"id": 7},
        ttl_seconds=3600,
        fetched_at=stale,
    )
    assert cache.get("run_o_r_7.json", "run") is None


def test_fresh_entry_within_ttl_is_hit(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    recent = _iso(datetime.now(UTC) - timedelta(minutes=30))
    _write_envelope(
        tmp_path / "run_o_r_8.json",
        kind="run",
        data={"id": 8},
        ttl_seconds=3600,
        fetched_at=recent,
    )
    assert cache.get("run_o_r_8.json", "run") == {"id": 8}


def test_immutable_never_expires(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    ancient = _iso(datetime.now(UTC) - timedelta(days=3650))
    _write_envelope(
        tmp_path / "commit_o_r_deadbeef.json",
        kind="commit",
        data={"sha": "deadbeef"},
        ttl_seconds=None,
        fetched_at=ancient,
    )
    assert cache.get("commit_o_r_deadbeef.json", "commit") == {"sha": "deadbeef"}


# --- Atomic write -----------------------------------------------------------


def test_put_leaves_no_tmp_file(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    cache.put("run_o_r_9.json", "run", {"id": 9}, ttl_seconds=None)
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == []
    assert (tmp_path / "run_o_r_9.json").exists()


def test_put_failure_preserves_original_and_cleans_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = Cache(tmp_path)
    cache.put("run_o_r_10.json", "run", {"id": 10, "v": 1}, ttl_seconds=None)
    original = (tmp_path / "run_o_r_10.json").read_text(encoding="utf-8")

    def boom(*_a: object, **_kw: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="simulated replace failure"):
        cache.put("run_o_r_10.json", "run", {"id": 10, "v": 2}, ttl_seconds=None)

    # Original final file is intact; the .tmp may linger because os.replace failed.
    assert (tmp_path / "run_o_r_10.json").read_text(encoding="utf-8") == original


# --- Corrupt entry ----------------------------------------------------------


def test_corrupt_json_returns_none(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    (tmp_path / "run_o_r_bad.json").write_bytes(b"{not valid json")
    assert cache.get("run_o_r_bad.json", "run") is None


def test_envelope_not_a_dict_returns_none(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    (tmp_path / "run_o_r_list.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert cache.get("run_o_r_list.json", "run") is None


def test_unparseable_fetched_at_returns_none(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    _write_envelope(
        tmp_path / "run_o_r_bogus.json",
        kind="run",
        data={"id": 11},
        ttl_seconds=3600,
        fetched_at="not-a-date",
    )
    assert cache.get("run_o_r_bogus.json", "run") is None


def test_missing_fetched_at_returns_none(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    (tmp_path / "run_o_r_x.json").write_text(
        json.dumps({"ttl_seconds": 3600, "kind": "run", "data": {"id": 12}}),
        encoding="utf-8",
    )
    assert cache.get("run_o_r_x.json", "run") is None


# --- Filename helpers -------------------------------------------------------


def test_key_run() -> None:
    assert key_run("o", "r", 123) == "run_o_r_123.json"


def test_key_jobs() -> None:
    assert key_jobs("o", "r", 123) == "jobs_o_r_123.json"


def test_key_commit() -> None:
    assert key_commit("o", "r", "deadbeef") == "commit_o_r_deadbeef.json"


def test_key_runs() -> None:
    assert (
        key_runs("o", "r", "main", "2026-05-13T00:00:00Z")
        == "runs_o_r_main_2026-05-13T00:00:00Z.json"
    )


# --- TTL helpers ------------------------------------------------------------


def test_ttl_for_completed_run_is_none() -> None:
    assert ttl_for_run({"status": "completed"}) is None


def test_ttl_for_in_progress_run_is_one_hour() -> None:
    assert ttl_for_run({"status": "in_progress"}) == 3600


def test_ttl_for_jobs_all_completed_is_none() -> None:
    payload = {"jobs": [{"status": "completed"}, {"status": "completed"}]}
    assert ttl_for_jobs(payload) is None


def test_ttl_for_jobs_mixed_is_one_hour() -> None:
    payload = {"jobs": [{"status": "completed"}, {"status": "in_progress"}]}
    assert ttl_for_jobs(payload) == 3600


def test_ttl_for_jobs_empty_list_is_one_hour() -> None:
    # Empty jobs list is treated as in-progress (GitHub hasn't materialised yet).
    assert ttl_for_jobs({"jobs": []}) == 3600


def test_ttl_for_commit_is_none() -> None:
    assert ttl_for_commit() is None


def test_ttl_for_runs_list_is_300() -> None:
    assert ttl_for_runs_list() == 300


# --- ADR 0010: Workflow filter cache helpers --------------------------------


def test_key_workflows() -> None:
    assert key_workflows("o", "r") == "workflows_o_r.json"


def test_key_runs_with_workflow_id_has_suffix() -> None:
    assert (
        key_runs("o", "r", "main", "2026-05-13T00:00:00Z", workflow_id=42)
        == "runs_o_r_main_2026-05-13T00:00:00Z_w42.json"
    )


def test_key_runs_without_workflow_id_unchanged() -> None:
    # Explicit None — same shape as the pre-ADR-0010 key.
    assert (
        key_runs("o", "r", "main", "2026-05-13T00:00:00Z", workflow_id=None)
        == "runs_o_r_main_2026-05-13T00:00:00Z.json"
    )


def test_ttl_for_workflows_is_3600() -> None:
    assert ttl_for_workflows() == 3600
