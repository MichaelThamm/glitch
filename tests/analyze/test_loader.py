"""Tests for artifact bundle loading."""
from __future__ import annotations

from pathlib import Path

import pytest

from glitch.analyze._loader import (
    COLLECTORS,
    AnalysisContext,
    load_context,
    read_collector_content,
)


class TestLoadContext:
    def test_load_context_valid(self, valid_manifest: Path) -> None:
        ctx = load_context(valid_manifest)
        assert isinstance(ctx, AnalysisContext)
        assert ctx.artifact_dir == valid_manifest
        assert ctx.manifest == {
            "collectors": {"juju": "ok"},
            "test_id": "test-foo",
            "repository": "test-repo",
        }

    def test_load_context_missing_manifest(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "no-manifest"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="No manifest.json"):
            load_context(empty_dir)

    def test_load_context_bad_json(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "bad-manifest"
        bad_dir.mkdir()
        (bad_dir / "manifest.json").write_text("{invalid")
        with pytest.raises(Exception):
            load_context(bad_dir)

    def test_load_context_with_discovery_json(
        self, valid_manifest: Path
    ) -> None:
        discovery = valid_manifest / "discovery.json"
        discovery.write_text('{"key": "value"}')
        ctx = load_context(valid_manifest, discovery_json=discovery)
        assert ctx.discovery == {"key": "value"}

    def test_load_context_discovery_not_found(
        self, valid_manifest: Path
    ) -> None:
        nonexistent = valid_manifest / "nope.json"
        ctx = load_context(valid_manifest, discovery_json=nonexistent)
        assert ctx.discovery is None

    def test_load_context_collector_paths(
        self, valid_manifest: Path
    ) -> None:
        for name in COLLECTORS:
            (valid_manifest / name).mkdir(exist_ok=True)
        ctx = load_context(valid_manifest)
        for name in COLLECTORS:
            assert isinstance(ctx.collector_paths[name], Path)
        missing_dir = valid_manifest.parent / "missing-collectors"
        missing_dir.mkdir()
        (missing_dir / "manifest.json").write_text(
            '{"collectors": {}, "test_id": "test-foo", "repository": "test-repo"}'
        )
        missing_ctx = load_context(missing_dir)
        for name in COLLECTORS:
            assert missing_ctx.collector_paths[name] is None

    def test_read_collector_content(
        self, valid_manifest: Path, tmp_path: Path
    ) -> None:
        ctx = load_context(valid_manifest)
        assert read_collector_content(ctx) == {}

        juju_dir = valid_manifest / "juju"
        juju_dir.mkdir()
        (juju_dir / "a.log").write_text("content-a")
        (juju_dir / "b.log").write_text("content-b")

        ctx = load_context(valid_manifest)
        result = read_collector_content(ctx)
        assert "juju" in result
        assert result["juju"] == "content-a\n\ncontent-b"
