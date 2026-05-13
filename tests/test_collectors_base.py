"""Tests for collector base: CollectorResult, register, get_collectors, run_tool."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from glitch.collectors.base import (
    Collector,
    CollectorResult,
    _registry,
    get_collectors,
    register,
    run_tool,
)


class _TestCollector(Collector):
    name = "test-collector"
    priority = 99

    def detect(self) -> bool:
        return True

    def collect(self, output_dir: Path) -> CollectorResult:
        return CollectorResult(status="ok")


class _TestCollectorLow(Collector):
    name = "low-prio"
    priority = 10

    def detect(self) -> bool:
        return True

    def collect(self, output_dir: Path) -> CollectorResult:
        return CollectorResult(status="ok")


class _TestCollectorHigh(Collector):
    name = "high-prio"
    priority = 80

    def detect(self) -> bool:
        return True

    def collect(self, output_dir: Path) -> CollectorResult:
        return CollectorResult(status="ok")


class TestCollectorResult:
    def test_default_values(self) -> None:
        result = CollectorResult(status="ok")
        assert result.status == "ok"
        assert result.reason is None
        assert result.artifacts == []
        assert result.extra == {}

    def test_ok_with_artifacts(self) -> None:
        artifacts = [Path("juju/status.json"), Path("k8s/pods.json")]
        result = CollectorResult(status="ok", artifacts=artifacts)
        assert result.artifacts == artifacts

    def test_skipped_with_reason(self) -> None:
        result = CollectorResult(status="skipped", reason="tool not found")
        assert result.status == "skipped"
        assert result.reason == "tool not found"

    def test_error_with_reason(self) -> None:
        result = CollectorResult(status="error", reason="timeout")
        assert result.status == "error"
        assert result.reason == "timeout"

    def test_extra_metadata(self) -> None:
        result = CollectorResult(status="ok", extra={"units": 3})
        assert result.extra == {"units": 3}


class TestRegister:
    def test_register_adds_to_registry(self) -> None:
        @register
        class MyCollector(Collector):
            name = "my-registered"
            priority = 15

            def detect(self) -> bool:
                return True

            def collect(self, output_dir: Path) -> CollectorResult:
                return CollectorResult(status="ok")

        assert "my-registered" in _registry
        assert _registry["my-registered"] is MyCollector

    def test_register_returns_class(self) -> None:
        @register
        class MyCollector(Collector):
            name = "returns-self"
            priority = 15

            def detect(self) -> bool:
                return True

            def collect(self, output_dir: Path) -> CollectorResult:
                return CollectorResult(status="ok")

        assert isinstance(MyCollector, type)


class TestGetCollectors:
    def test_returns_sorted_by_priority(self) -> None:
        @register
        class A(Collector):
            name = "collector-a"
            priority = 100

            def detect(self) -> bool:
                return True

            def collect(self, output_dir: Path) -> CollectorResult:
                return CollectorResult(status="ok")

        @register
        class B(Collector):
            name = "collector-b"
            priority = 1

            def detect(self) -> bool:
                return True

            def collect(self, output_dir: Path) -> CollectorResult:
                return CollectorResult(status="ok")

        @register
        class C(Collector):
            name = "collector-c"
            priority = 50

            def detect(self) -> bool:
                return True

            def collect(self, output_dir: Path) -> CollectorResult:
                return CollectorResult(status="ok")

        result = get_collectors()
        priorities = [c.priority for c in result]
        assert priorities == sorted(priorities)
        assert priorities[0] == 1


class TestRunTool:
    def make_mock_run(
        self, stdout: str = "", stderr: str = "", returncode: int = 0
    ) -> MagicMock:
        mock_result = MagicMock()
        mock_result.returncode = returncode
        mock_result.stdout = stdout
        mock_result.stderr = stderr
        return MagicMock(return_value=mock_result)

    def test_passes_correct_args(self) -> None:
        mock_run = self.make_mock_run(stdout="output")
        with patch("glitch.collectors.base.subprocess.run", mock_run):
            run_tool(["echo", "hello"])
        mock_run.assert_called_once_with(
            ["echo", "hello"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_respects_timeout_parameter(self) -> None:
        mock_run = self.make_mock_run(stdout="output")
        with patch("glitch.collectors.base.subprocess.run", mock_run):
            run_tool(["slow-cmd"], timeout=60)
        mock_run.assert_called_once_with(
            ["slow-cmd"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_returns_completed_process(self) -> None:
        mock_run = self.make_mock_run(stdout="hello world", returncode=0)
        with patch("glitch.collectors.base.subprocess.run", mock_run):
            result = run_tool(["echo", "hello"])
        assert result.returncode == 0
        assert result.stdout == "hello world"

    def test_does_not_raise_on_nonzero(self) -> None:
        mock_run = self.make_mock_run(stdout="", stderr="error", returncode=1)
        with patch("glitch.collectors.base.subprocess.run", mock_run):
            result = run_tool(["failing-cmd"])
        assert result.returncode == 1
        assert result.stderr == "error"

    def test_timeout_propagates(self) -> None:
        mock_run = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="slow", timeout=30)
        )
        with patch("glitch.collectors.base.subprocess.run", mock_run), pytest.raises(
            subprocess.TimeoutExpired
        ):
            run_tool(["slow"])