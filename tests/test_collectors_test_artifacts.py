"""Tests for TestArtifactsCollector."""

from __future__ import annotations

from pathlib import Path

from glitch.collectors.test_artifacts import TestArtifactsCollector


class TestDetect:
    def test_detect_true_when_dir_exists(self, tmp_path: Path) -> None:
        collector = TestArtifactsCollector(source_dir=tmp_path)
        assert collector.detect() is True

    def test_detect_false_when_none(self) -> None:
        collector = TestArtifactsCollector(source_dir=None)
        assert collector.detect() is False

    def test_detect_false_when_dir_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        collector = TestArtifactsCollector(source_dir=missing)
        assert collector.detect() is False

    def test_detect_false_when_path_is_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("hello")
        collector = TestArtifactsCollector(source_dir=file_path)
        assert collector.detect() is False


class TestCollect:
    def test_copies_directory_contents(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "results.xml").write_text("<testsuite/>")
        (src_dir / "report.html").write_text("<html/>")

        dest_dir = tmp_path / "output"

        collector = TestArtifactsCollector(source_dir=src_dir)
        result = collector.collect(dest_dir)

        assert result.status == "ok"
        assert (dest_dir / "test-artifacts" / "results.xml").is_file()
        assert (dest_dir / "test-artifacts" / "report.html").is_file()

    def test_copies_nested_directories(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        nested = src_dir / "coverage"
        nested.mkdir()
        (nested / "index.html").write_text("<html/>")

        dest_dir = tmp_path / "output"

        collector = TestArtifactsCollector(source_dir=src_dir)
        result = collector.collect(dest_dir)

        assert result.status == "ok"
        assert (dest_dir / "test-artifacts" / "coverage" / "index.html").is_file()

    def test_skips_when_dir_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing"
        dest_dir = tmp_path / "output"

        collector = TestArtifactsCollector(source_dir=missing)
        result = collector.collect(dest_dir)

        assert result.status == "skipped"
        assert "not found" in (result.reason or "")

    def test_skips_when_dir_is_none(self, tmp_path: Path) -> None:
        dest_dir = tmp_path / "output"

        collector = TestArtifactsCollector(source_dir=None)
        result = collector.collect(dest_dir)

        assert result.status == "skipped"

    def test_artifact_tracking_lists_copied_files(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.xml").write_text("<testsuite/>")
        (src_dir / "output.log").write_text("log data")

        dest_dir = tmp_path / "output"

        collector = TestArtifactsCollector(source_dir=src_dir)
        result = collector.collect(dest_dir)

        assert len(result.artifacts) == 2

    def test_empty_source_directory(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "empty_src"
        src_dir.mkdir()
        dest_dir = tmp_path / "output"

        collector = TestArtifactsCollector(source_dir=src_dir)
        result = collector.collect(dest_dir)

        assert result.status == "ok"
        assert len(result.artifacts) == 0