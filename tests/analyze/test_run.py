from __future__ import annotations

from pathlib import Path

import pytest

from glitch.analyze._run import run


class TestIntegrationRun:
    def test_full_pipeline_charm_bug(
        self, valid_manifest: Path, temp_output_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        monkeypatch.setenv("XDG_DATA_HOME", str(temp_output_dir))

        imported_module = __import__(
            "glitch.analyze._copilot",
            fromlist=["CopilotSession"],
        )
        original_classify = imported_module.CopilotSession.classify
        imported_module.CopilotSession.classify = lambda self, prompt: (
            '{"test_id": "test-foo", "labels": {"charm-bug": 0.91}, "reasoning_trace": "Step 1: x"}'
        )

        try:
            run(
                artifact_dir=valid_manifest,
                output_dir=temp_output_dir,
                confidence_threshold=0.8,
            )
        finally:
            imported_module.CopilotSession.classify = original_classify

        verdict_file = temp_output_dir / "verdict.json"
        report_file = temp_output_dir / "report.md"
        patch_file = temp_output_dir / "fix.patch"
        assert verdict_file.is_file()
        assert report_file.is_file()
        assert patch_file.is_file()
        assert "charm-bug" in verdict_file.read_text()
        assert "charm-bug" in report_file.read_text()

    def test_full_pipeline_flaky_no_patch(
        self, valid_manifest: Path, temp_output_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        monkeypatch.setenv("XDG_DATA_HOME", str(temp_output_dir))

        imported_module = __import__(
            "glitch.analyze._copilot",
            fromlist=["CopilotSession"],
        )
        original_classify = imported_module.CopilotSession.classify
        imported_module.CopilotSession.classify = lambda self, prompt: (
            '{"test_id": "test-foo", "labels": {"flaky": 0.95}, "reasoning_trace": "Step 1: x"}'
        )

        try:
            run(
                artifact_dir=valid_manifest,
                output_dir=temp_output_dir,
                confidence_threshold=0.8,
            )
        finally:
            imported_module.CopilotSession.classify = original_classify

        patch_file = temp_output_dir / "fix.patch"
        assert not patch_file.is_file()

    def test_full_pipeline_patterns_store(
        self, valid_manifest: Path, temp_output_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        monkeypatch.setenv("XDG_DATA_HOME", str(temp_output_dir))

        imported_module = __import__(
            "glitch.analyze._copilot",
            fromlist=["CopilotSession"],
        )
        original_classify = imported_module.CopilotSession.classify
        imported_module.CopilotSession.classify = lambda self, prompt: (
            '{"test_id": "test-foo", "labels": {"charm-bug": 0.91}, "reasoning_trace": "Step 1: x"}'
        )

        try:
            run(
                artifact_dir=valid_manifest,
                output_dir=temp_output_dir,
                confidence_threshold=0.8,
            )
        finally:
            imported_module.CopilotSession.classify = original_classify

        patterns_path = Path(temp_output_dir) / "glitch" / "patterns.json"
        assert patterns_path.is_file()

    def test_full_pipeline_with_discovery(
        self, valid_manifest: Path, temp_output_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        monkeypatch.setenv("XDG_DATA_HOME", str(temp_output_dir))

        discovery = valid_manifest / "discovery.json"
        discovery.write_text('{"flakiness_index": 0.78}')

        imported_module = __import__(
            "glitch.analyze._copilot",
            fromlist=["CopilotSession"],
        )
        original_classify = imported_module.CopilotSession.classify
        imported_module.CopilotSession.classify = lambda self, prompt: (
            '{"test_id": "test-foo", "labels": {"infrastructure": 0.7}, "reasoning_trace": "Step 1: x"}'
        )

        try:
            run(
                artifact_dir=valid_manifest,
                discovery_json=discovery,
                output_dir=temp_output_dir,
                confidence_threshold=0.8,
            )
        finally:
            imported_module.CopilotSession.classify = original_classify

        verdict_file = temp_output_dir / "verdict.json"
        report_file = temp_output_dir / "report.md"
        assert verdict_file.is_file()
        assert report_file.is_file()
        assert "infrastructure" in verdict_file.read_text()
