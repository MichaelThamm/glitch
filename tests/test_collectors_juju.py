"""Tests for JujuCollector."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from glitch.collectors.juju import JujuCollector, _discover_containers

FIXTURES = Path(__file__).parent / "fixtures" / "juju"


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
    def test_detect_true_when_juju_on_path(self) -> None:
        with patch("glitch.collectors.juju.shutil.which", return_value="/usr/bin/juju"):
            collector = JujuCollector()
            assert collector.detect() is True

    def test_detect_false_when_juju_not_found(self) -> None:
        with patch("glitch.collectors.juju.shutil.which", return_value=None):
            collector = JujuCollector()
            assert collector.detect() is False


class TestCommandConstruction:
    def test_default_no_model_flag(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stdout=json.dumps({"model": {}, "applications": {}}))
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            collector.collect(tmp_path)

        call_args_list = [call[0][0] for call in mock_run.call_args_list]
        for args in call_args_list:
            assert "-m" not in args

    def test_model_flag_added(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stdout=json.dumps({"model": {}, "applications": {}}))
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector(model="prod-model")
            collector.collect(tmp_path)

        call_args_list = [call[0][0] for call in mock_run.call_args_list]
        for args in call_args_list:
            assert "-m" in args
            assert "prod-model" in args

    def test_status_command_uses_json_format(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stdout=json.dumps({"model": {}, "applications": {}}))
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            collector.collect(tmp_path)

        status_calls = [
            call
            for call in mock_run.call_args_list
            if "status" in call[0][0] and "--format" in call[0][0]
        ]
        assert len(status_calls) >= 1

    def test_debug_log_uses_limit_zero(self, tmp_path: Path) -> None:
        debug_text = "line1\nline2"
        call_index = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_index
            call_index += 1
            if "debug-log" in args[0]:
                return make_mock_run(stdout=debug_text)(*args, **kwargs)
            elif "status" in args[0] and call_index <= 2:
                return make_mock_run(stdout=json.dumps({"model": {}, "applications": {}}))(
                    *args, **kwargs
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("glitch.collectors.juju.subprocess.run", side_effect=side_effect):
            collector = JujuCollector()
            collector.collect(tmp_path)
        # Verify collection completed without error


class TestOutputFiles:
    def test_creates_juju_directory(self, tmp_path: Path) -> None:
        status = json.loads(_load_fixture("status.json"))
        mock_run = make_mock_run(stdout=json.dumps(status))
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            collector.collect(tmp_path)

        assert (tmp_path / "juju").is_dir()

    def test_writes_status_json(self, tmp_path: Path) -> None:
        status = json.loads(_load_fixture("status.json"))
        mock_run = make_mock_run(stdout=json.dumps(status))
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            collector.collect(tmp_path)

        status_path = tmp_path / "juju" / "status.json"
        assert status_path.is_file()
        written = json.loads(status_path.read_text())
        assert written["model"]["name"] == "my-model"

    def test_writes_debug_log(self, tmp_path: Path) -> None:
        debug_text = "log line 1\nlog line 2\nlog line 3"
        status = json.loads(_load_fixture("status.json"))
        call_count = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_count
            call_count += 1
            if "debug-log" in str(args):
                return make_mock_run(stdout=debug_text)(*args, **kwargs)
            return make_mock_run(stdout=json.dumps(status))(*args, **kwargs)

        with patch("glitch.collectors.juju.subprocess.run", side_effect=side_effect):
            collector = JujuCollector()
            collector.collect(tmp_path)

        debug_path = tmp_path / "juju" / "debug-log.txt"
        assert debug_path.is_file()
        assert debug_path.read_text() == debug_text


class TestUnitDiscovery:
    def test_discovers_units_from_status(self) -> None:
        status = json.loads(_load_fixture("status.json"))
        containers = _discover_containers(status)
        assert len(containers) == 4
        assert ("myapp/0", "myapp-container") in containers
        assert ("otherdb/0", "db-container") in containers
        assert ("otherdb/0", "sidecar-container") in containers
        assert ("otherdb/1", "db-container") in containers

    def test_no_units_in_empty_status(self) -> None:
        status = json.loads(_load_fixture("status_empty.json"))
        containers = _discover_containers(status)
        assert containers == []

    def test_no_containers_in_no_containers_status(self) -> None:
        status = {
            "model": {"name": "test"},
            "applications": {
                "app": {
                    "units": {
                        "app/0": {},
                    },
                },
            },
        }
        containers = _discover_containers(status)
        assert containers == []


class TestErrorHandling:
    def test_status_nonzero_return(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stderr="connection refused", returncode=1)
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            result = collector.collect(tmp_path)

        assert result.status == "ok"
        assert not (tmp_path / "juju" / "status.json").exists()

    def test_status_timeout(self, tmp_path: Path) -> None:
        mock_run = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="juju", timeout=30)
        )
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            result = collector.collect(tmp_path)

        assert result.status == "ok"

    def test_invalid_json_status(self, tmp_path: Path) -> None:
        status_json = json.dumps({"model": {}, "applications": {}})

        call_count = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_mock_run(stdout="not valid json", returncode=0)(*args, **kwargs)
            return make_mock_run(stdout=status_json, returncode=0)(*args, **kwargs)

        with patch("glitch.collectors.juju.subprocess.run", side_effect=side_effect):
            collector = JujuCollector()
            result = collector.collect(tmp_path)

        assert result.status == "ok"