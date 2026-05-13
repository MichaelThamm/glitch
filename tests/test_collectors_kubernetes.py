"""Tests for KubernetesCollector."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from glitch.collectors.kubernetes import KubernetesCollector, filter_failed_pods

FIXTURES = Path(__file__).parent / "fixtures" / "k8s"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def make_mock_run(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> MagicMock:
    mock_result = MagicMock()
    mock_result.returncode = returncode
    mock_result.stdout = stdout
    mock_result.stderr = stderr
    return MagicMock(return_value=mock_result)


def _make_status_mock(pods_json: str, events_json: str) -> MagicMock:
    call_index = 0

    def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal call_index
        call_index += 1
        if "pods" in str(args):
            return make_mock_run(stdout=pods_json)(*args, **kwargs)
        elif "events" in str(args):
            return make_mock_run(stdout=events_json)(*args, **kwargs)
        return make_mock_run(stdout="{}")(*args, **kwargs)

    return MagicMock(side_effect=side_effect)


class TestDetect:
    def test_detect_true_when_kubectl_on_path(self) -> None:
        with patch(
            "glitch.collectors.kubernetes.shutil.which", return_value="/usr/bin/kubectl"
        ):
            collector = KubernetesCollector()
            assert collector.detect() is True

    def test_detect_false_when_kubectl_not_found(self) -> None:
        with patch("glitch.collectors.kubernetes.shutil.which", return_value=None):
            collector = KubernetesCollector()
            assert collector.detect() is False


class TestPodFiltering:
    def test_running_zero_restarts_excluded(self) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        failed = filter_failed_pods(pods)
        names = [p["metadata"]["name"] for p in failed]
        assert "good-pod" not in names

    def test_running_with_restarts_included(self) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        failed = filter_failed_pods(pods)
        names = [p["metadata"]["name"] for p in failed]
        assert "crashy-pod" in names

    def test_non_running_phase_included(self) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        failed = filter_failed_pods(pods)
        names = [p["metadata"]["name"] for p in failed]
        assert "error-pod" in names
        assert "crashloop-pod" in names

    def test_all_failed_pods_count(self) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        failed = filter_failed_pods(pods)
        assert len(failed) == 3

    def test_empty_pods_list(self) -> None:
        failed = filter_failed_pods({"items": []})
        assert failed == []

    def test_pods_missing_status_field(self) -> None:
        pods = {"items": [{"metadata": {"name": "no-status"}}]}
        failed = filter_failed_pods(pods)
        assert len(failed) == 1


class TestCommandConstruction:
    def test_default_no_namespace(self, tmp_path: Path) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        events = json.loads(_load_fixture("events.json"))
        mock_run = _make_status_mock(json.dumps(pods), json.dumps(events))

        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            collector.collect(tmp_path)

        for call in mock_run.call_args_list:
            args = call[0][0]
            if "get" in args and ("pods" in str(args) or "events" in str(args)):
                assert "-n" not in args

    def test_namespace_flag_added(self, tmp_path: Path) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        events = json.loads(_load_fixture("events.json"))
        mock_run = MagicMock()

        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if "pods" in str(args):
                return make_mock_run(stdout=json.dumps(pods))(*args, **kwargs)
            return make_mock_run(stdout=json.dumps(events))(*args, **kwargs)

        mock_run.side_effect = side_effect

        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector(namespace="my-ns")
            collector.collect(tmp_path)

        for call in mock_run.call_args_list:
            args = call[0][0]
            if "get" in args and ("pods" in str(args) or "events" in str(args)):
                assert "-n" in args
                assert "my-ns" in args

    def test_kubectl_command_includes_get_pods(self, tmp_path: Path) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        events = json.loads(_load_fixture("events.json"))
        mock_run = _make_status_mock(json.dumps(pods), json.dumps(events))

        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            collector.collect(tmp_path)

        pod_calls = [
            call for call in mock_run.call_args_list if "get" in str(call) and "pods" in str(call)
        ]
        assert len(pod_calls) == 1

    def test_kubectl_command_includes_get_events(self, tmp_path: Path) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        events = json.loads(_load_fixture("events.json"))
        mock_run = _make_status_mock(json.dumps(pods), json.dumps(events))

        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            collector.collect(tmp_path)

        event_calls = [
            call
            for call in mock_run.call_args_list
            if "get" in str(call) and "events" in str(call)
        ]
        assert len(event_calls) == 1


class TestOutputFiles:
    def test_collect_writes_pods_json(self, tmp_path: Path) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        events = json.loads(_load_fixture("events.json"))
        mock_run = _make_status_mock(json.dumps(pods), json.dumps(events))

        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            result = collector.collect(tmp_path)

        assert result.status == "ok"
        events_path = tmp_path / "k8s" / "events.json"
        assert events_path.is_file()

    def test_collect_writes_pod_describe(self, tmp_path: Path) -> None:
        pods = json.loads(_load_fixture("pods.json"))
        events = json.loads(_load_fixture("events.json"))
        mock_run = _make_status_mock(json.dumps(pods), json.dumps(events))

        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            collector.collect(tmp_path)

        describe_path = tmp_path / "k8s" / "pods" / "crashy-pod-describe.txt"
        assert describe_path.is_file()