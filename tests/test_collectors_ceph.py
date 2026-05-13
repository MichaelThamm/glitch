"""Tests for CephCollector."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from glitch.collectors.ceph import CephCollector

FIXTURES = Path(__file__).parent / "fixtures" / "ceph"


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


class TestDetect:
    def test_detect_true_when_ceph_on_path(self) -> None:
        with patch(
            "glitch.collectors.ceph.shutil.which", return_value="/usr/bin/ceph"
        ):
            collector = CephCollector()
            assert collector.detect() is True

    def test_detect_false_when_ceph_not_found(self) -> None:
        with patch("glitch.collectors.ceph.shutil.which", return_value=None):
            collector = CephCollector()
            assert collector.detect() is False


class TestTwoCommandCollection:
    def test_runs_status_and_health_detail(self, tmp_path: Path) -> None:
        status_data = json.loads(_load_fixture("status.json"))
        health_data = json.loads(_load_fixture("health-detail.json"))
        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if "status" in str(args) and call_index == 1:
                return make_mock_run(stdout=json.dumps(status_data))(*args, **kwargs)
            return make_mock_run(stdout=json.dumps(health_data))(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)

        with patch("glitch.collectors.ceph.subprocess.run", mock_run):
            collector = CephCollector()
            collector.collect(tmp_path)

        assert mock_run.call_count == 2

        status_calls = [
            call
            for call in mock_run.call_args_list
            if "status" in str(call) and "health" not in str(call)
        ]
        health_calls = [
            call
            for call in mock_run.call_args_list
            if "health" in str(call) and "detail" in str(call)
        ]
        assert len(status_calls) == 1
        assert len(health_calls) == 1

    def test_status_command_format(self, tmp_path: Path) -> None:
        status_data = json.loads(_load_fixture("status.json"))
        health_data = json.loads(_load_fixture("health-detail.json"))

        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if call_index == 1:
                return make_mock_run(stdout=json.dumps(status_data))(*args, **kwargs)
            return make_mock_run(stdout=json.dumps(health_data))(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)

        with patch("glitch.collectors.ceph.subprocess.run", mock_run):
            collector = CephCollector()
            collector.collect(tmp_path)

        status_call_args = mock_run.call_args_list[0][0][0]
        assert "ceph" in status_call_args
        assert "status" in status_call_args
        assert "--format" in status_call_args
        assert "json" in status_call_args

    def test_health_detail_command_format(self, tmp_path: Path) -> None:
        status_data = json.loads(_load_fixture("status.json"))
        health_data = json.loads(_load_fixture("health-detail.json"))

        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if call_index == 1:
                return make_mock_run(stdout=json.dumps(status_data))(*args, **kwargs)
            return make_mock_run(stdout=json.dumps(health_data))(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)

        with patch("glitch.collectors.ceph.subprocess.run", mock_run):
            collector = CephCollector()
            collector.collect(tmp_path)

        health_call_args = mock_run.call_args_list[1][0][0]
        assert "ceph" in health_call_args
        assert "health" in health_call_args
        assert "detail" in health_call_args


class TestOutputFiles:
    def test_writes_status_json(self, tmp_path: Path) -> None:
        status_data = json.loads(_load_fixture("status.json"))
        health_data = json.loads(_load_fixture("health-detail.json"))

        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if call_index == 1:
                return make_mock_run(stdout=json.dumps(status_data))(*args, **kwargs)
            return make_mock_run(stdout=json.dumps(health_data))(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)

        with patch("glitch.collectors.ceph.subprocess.run", mock_run):
            collector = CephCollector()
            result = collector.collect(tmp_path)

        assert result.status == "ok"
        status_path = tmp_path / "ceph" / "status.json"
        assert status_path.is_file()
        written = json.loads(status_path.read_text())
        assert written["fsid"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_writes_health_detail_json(self, tmp_path: Path) -> None:
        status_data = json.loads(_load_fixture("status.json"))
        health_data = json.loads(_load_fixture("health-detail.json"))

        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if call_index == 1:
                return make_mock_run(stdout=json.dumps(status_data))(*args, **kwargs)
            return make_mock_run(stdout=json.dumps(health_data))(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)

        with patch("glitch.collectors.ceph.subprocess.run", mock_run):
            collector = CephCollector()
            collector.collect(tmp_path)

        health_path = tmp_path / "ceph" / "health-detail.json"
        assert health_path.is_file()
        written = json.loads(health_path.read_text())
        assert "health" in written