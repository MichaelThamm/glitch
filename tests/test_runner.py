"""Tests for run_collectors orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from glitch.collectors.base import CollectorResult, _registry
from glitch.collectors.runner import run_collectors


class TestRunCollectors:
    def _make_collector_cls(self, cls_name, *, detect=True, collect_ok=True):
        class MockCollector:
            priority = 10

            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def detect(self):
                return detect

            def collect(self, output_dir):
                if not collect_ok:
                    return CollectorResult(status="error", reason="collect failed")
                return CollectorResult(status="ok", artifacts=[output_dir / "test.txt"])

        MockCollector.name = cls_name
        return MockCollector

    def test_instantiates_collectors_with_kwargs(self, tmp_path: Path) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockCls = self._make_collector_cls("juju")
            instance = None
            captured_kwargs: dict[str, object] = {}

            def capture_init(self, **kwargs):  # noqa: ANN001, ANN002
                nonlocal instance, captured_kwargs
                instance = self
                captured_kwargs = kwargs

            MockCls.__init__ = capture_init
            _registry["juju"] = MockCls

            with patch("glitch.collectors.runner.build_summary", return_value=""):
                run_collectors(tmp_path, model="test-model")
        finally:
            _registry.clear()
            _registry.update(orig_registry)

        assert instance is not None
        assert captured_kwargs.get("model") == "test-model"

    def test_produces_manifest_json(self, tmp_path: Path) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockCls = self._make_collector_cls("juju")
            _registry["juju"] = MockCls

            with patch("glitch.collectors.runner.build_summary", return_value=""):
                run_collectors(tmp_path)
        finally:
            _registry.clear()
            _registry.update(orig_registry)

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.is_file()
        data = json.loads(manifest_path.read_text())
        assert "glitch_version" in data
        assert "collected_at" in data
        assert "collectors" in data
        assert "juju" in data["collectors"]
        assert data["collectors"]["juju"]["status"] == "ok"

    def test_produces_summary_md(self, tmp_path: Path) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockCls = self._make_collector_cls("juju")
            _registry["juju"] = MockCls

            run_collectors(tmp_path)
        finally:
            _registry.clear()
            _registry.update(orig_registry)

        summary_path = tmp_path / "summary.md"
        assert summary_path.is_file()

    def test_all_collectors_skipped_raises_exit(self, tmp_path: Path) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockCls = self._make_collector_cls("juju", detect=False)
            _registry["juju"] = MockCls

            with pytest.raises(typer.Exit) as exc_info:
                with patch("glitch.collectors.runner.build_summary", return_value=""):
                    run_collectors(tmp_path)
            assert exc_info.value.exit_code == 1
        finally:
            _registry.clear()
            _registry.update(orig_registry)

    def test_at_least_one_ok_succeeds(self, tmp_path: Path) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockA = self._make_collector_cls("juju", detect=False)
            MockB = self._make_collector_cls("kubernetes")
            _registry["juju"] = MockA
            _registry["kubernetes"] = MockB

            with patch("glitch.collectors.runner.build_summary", return_value=""):
                run_collectors(tmp_path)
            manifest = json.loads((tmp_path / "manifest.json").read_text())
            assert manifest["collectors"]["juju"]["status"] == "skipped"
            assert manifest["collectors"]["kubernetes"]["status"] == "ok"
        finally:
            _registry.clear()
            _registry.update(orig_registry)

    def test_error_isolation_one_collector_fails_others_continue(
        self, tmp_path: Path
    ) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockError = self._make_collector_cls("juju", collect_ok=False)
            MockGood = self._make_collector_cls("kubernetes")
            _registry["juju"] = MockError
            _registry["kubernetes"] = MockGood

            with patch("glitch.collectors.runner.build_summary", return_value=""):
                run_collectors(tmp_path)

            manifest = json.loads((tmp_path / "manifest.json").read_text())
            assert manifest["collectors"]["juju"]["status"] == "error"
            assert manifest["collectors"]["kubernetes"]["status"] == "ok"
        finally:
            _registry.clear()
            _registry.update(orig_registry)

    def test_detect_exception_handled(self, tmp_path: Path) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockBorked = self._make_collector_cls("juju")
            MockBorked.detect = MagicMock(side_effect=RuntimeError("detect crash"))
            MockGood = self._make_collector_cls("kubernetes")
            _registry["juju"] = MockBorked
            _registry["kubernetes"] = MockGood

            with patch("glitch.collectors.runner.build_summary", return_value=""):
                run_collectors(tmp_path)

            manifest = json.loads((tmp_path / "manifest.json").read_text())
            assert manifest["collectors"]["juju"]["status"] == "error"
            assert "crashed" in manifest["collectors"]["juju"]["reason"]
            assert manifest["collectors"]["kubernetes"]["status"] == "ok"
        finally:
            _registry.clear()
            _registry.update(orig_registry)

    def test_collect_exception_handled(self, tmp_path: Path) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockBorked = self._make_collector_cls("juju")
            MockBorked.collect = MagicMock(
                side_effect=RuntimeError("collect crash")
            )
            MockGood = self._make_collector_cls("kubernetes")
            _registry["juju"] = MockBorked
            _registry["kubernetes"] = MockGood

            with patch("glitch.collectors.runner.build_summary", return_value=""):
                run_collectors(tmp_path)

            manifest = json.loads((tmp_path / "manifest.json").read_text())
            assert manifest["collectors"]["juju"]["status"] == "error"
            assert manifest["collectors"]["kubernetes"]["status"] == "ok"
        finally:
            _registry.clear()
            _registry.update(orig_registry)

    def test_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "nested" / "output"
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            MockCls = self._make_collector_cls("juju")
            _registry["juju"] = MockCls

            with patch("glitch.collectors.runner.build_summary", return_value=""):
                run_collectors(output_dir)
            assert output_dir.is_dir()
        finally:
            _registry.clear()
            _registry.update(orig_registry)

    def test_no_collectors_registered_raises_exit(self, tmp_path: Path) -> None:
        orig_registry = dict(_registry)
        _registry.clear()
        try:
            with pytest.raises(typer.Exit) as exc_info:
                run_collectors(tmp_path)
            assert exc_info.value.exit_code == 1
        finally:
            _registry.clear()
            _registry.update(orig_registry)