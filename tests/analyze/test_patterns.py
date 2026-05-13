"""Tests for known-patterns store persistence and upsert."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from glitch.analyze._patterns import PatternEntry, PatternsStore, _patterns_path


def _make_entry(
    repo: str = "test-repo",
    test_id: str = "test-foo",
    summary: str = "Summary.",
    resolution: str = "Resolved.",
) -> PatternEntry:
    return PatternEntry(
        id="entry-1",
        recorded_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        repo=repo,
        test_id=test_id,
        labels={"flaky": 0.9},
        summary=summary,
        resolution=resolution,
    )


class TestPatternEntry:
    def test_patternentry_required_fields(self) -> None:
        entry = _make_entry()
        d = entry.__dict__ if hasattr(entry, "__dict__") else {}
        required = {"id", "recorded_at", "repo", "test_id", "labels", "summary", "resolution"}
        for field in required:
            assert field in d, f"Missing field: {field}"


class TestPatternsStoreRead:
    def test_read_empty_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        store = PatternsStore()
        assert store.read() == []


class TestPatternsStoreAppend:
    def test_append_and_read(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        store = PatternsStore()

        e1 = _make_entry(repo="repo-a", test_id="test-1")
        store.append([e1])

        results = store.read()
        assert len(results) == 1
        assert results[0]["repo"] == "repo-a"
        assert results[0]["test_id"] == "test-1"

    def test_upsert_dedup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        store = PatternsStore()

        e1 = _make_entry(repo="repo-a", test_id="test-1", summary="first")
        e2 = _make_entry(repo="repo-a", test_id="test-1", summary="second")

        store.append([e1])
        store.append([e2])

        results = store.read()
        assert len(results) == 1
        assert results[0]["summary"] == "second"

    def test_upsert_new_entry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        store = PatternsStore()

        e1 = _make_entry(repo="repo-a", test_id="test-1")
        e2 = _make_entry(repo="repo-a", test_id="test-2")

        store.append([e1])
        store.append([e2])

        results = store.read()
        assert len(results) == 2


class TestPatternsPath:
    def test_xdg_data_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        path = _patterns_path()
        expected_dir = tmp_path / "glitch"
        assert expected_dir.is_dir()
        assert path == expected_dir / "patterns.json"
