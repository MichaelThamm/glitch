"""Tests for LXDCollector."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from glitch.collectors.lxd import LXDCollector

FIXTURES = Path(__file__).parent / "fixtures" / "lxd"


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
    def test_detect_true_when_lxc_on_path(self) -> None:
        with patch(
            "glitch.collectors.lxd.shutil.which", return_value="/usr/bin/lxc"
        ):
            collector = LXDCollector()
            assert collector.detect() is True

    def test_detect_false_when_lxc_not_found(self) -> None:
        with patch("glitch.collectors.lxd.shutil.which", return_value=None):
            collector = LXDCollector()
            assert collector.detect() is False


class TestInstanceEnumeration:
    def test_lists_instances_from_json(self, tmp_path: Path) -> None:
        instances = json.loads(_load_fixture("list.json"))
        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if args[0] == ["lxc", "list", "--format", "json"] and call_index == 1:
                return make_mock_run(stdout=json.dumps(instances))(*args, **kwargs)
            return make_mock_run(stdout="info output")(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)

        with patch("glitch.collectors.lxd.subprocess.run", mock_run):
            collector = LXDCollector()
            result = collector.collect(tmp_path)

        assert result.status == "ok"
        list_path = tmp_path / "lxd" / "list.json"
        assert list_path.is_file()

    def test_fetches_info_per_instance(self, tmp_path: Path) -> None:
        instances = json.loads(_load_fixture("list.json"))
        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if call_index == 1:
                return make_mock_run(stdout=json.dumps(instances))(*args, **kwargs)
            return make_mock_run(stdout="info for instance")(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)

        with patch("glitch.collectors.lxd.subprocess.run", mock_run):
            collector = LXDCollector()
            collector.collect(tmp_path)

        info_calls = [
            call for call in mock_run.call_args_list if "info" in str(call[0][0])
        ]
        assert len(info_calls) == 2

        for instance in instances:
            info_path = tmp_path / "lxd" / "instances" / f"{instance['name']}.txt"
            assert info_path.is_file()

    def test_lxc_list_command_format(self, tmp_path: Path) -> None:
        instances = json.loads(_load_fixture("list.json"))
        mock_run = make_mock_run(stdout=json.dumps(instances))

        with patch("glitch.collectors.lxd.subprocess.run", mock_run):
            collector = LXDCollector()
            collector.collect(tmp_path)

        list_calls = [
            call
            for call in mock_run.call_args_list
            if "lxc" in str(call) and "list" in str(call)
        ]
        assert len(list_calls) == 1
        args = list_calls[0][0][0]
        assert "lxc" in args
        assert "list" in args
        assert "--format" in args
        assert "json" in args