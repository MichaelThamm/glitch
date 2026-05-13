"""Error handling and isolation tests across collectors."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from glitch.collectors.juju import JujuCollector
from glitch.collectors.kubernetes import KubernetesCollector
from glitch.collectors.lxd import LXDCollector
from glitch.collectors.ceph import CephCollector

FIXTURES = Path(__file__).parent / "fixtures"


def make_mock_run(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> MagicMock:
    mock_result = MagicMock()
    mock_result.returncode = returncode
    mock_result.stdout = stdout
    mock_result.stderr = stderr
    return MagicMock(return_value=mock_result)


class TestTimeoutHandling:
    def test_juju_timeout_returns_ok(self, tmp_path: Path) -> None:
        mock_run = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="juju", timeout=30)
        )
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_kubernetes_timeout_returns_ok(self, tmp_path: Path) -> None:
        mock_run = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="kubectl", timeout=30)
        )
        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_lxd_timeout_returns_ok(self, tmp_path: Path) -> None:
        mock_run = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="lxc", timeout=30)
        )
        with patch("glitch.collectors.lxd.subprocess.run", mock_run):
            collector = LXDCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_ceph_timeout_returns_ok(self, tmp_path: Path) -> None:
        mock_run = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="ceph", timeout=30)
        )
        with patch("glitch.collectors.ceph.subprocess.run", mock_run):
            collector = CephCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"


class TestNonZeroExitCode:
    def test_juju_nonzero_skip_artifact(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stderr="connection error", returncode=1)
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"
        assert not (tmp_path / "juju" / "status.json").exists()

    def test_kubernetes_nonzero_skip_artifact(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stderr="connection refused", returncode=1)
        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"
        assert not (tmp_path / "kubernetes" / "pods.json").exists()

    def test_lxd_nonzero_skip_artifact(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stderr="not found", returncode=1)
        with patch("glitch.collectors.lxd.subprocess.run", mock_run):
            collector = LXDCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_ceph_nonzero_skip_artifact(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stderr="permission denied", returncode=1)
        with patch("glitch.collectors.ceph.subprocess.run", mock_run):
            collector = CephCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"


class TestMalformedJSON:
    def test_juju_malformed_json_graceful(self, tmp_path: Path) -> None:
        malformed = (FIXTURES / "malformed" / "bad.json").read_text()
        call_count = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_mock_run(stdout=malformed, returncode=0)(*args, **kwargs)
            return make_mock_run(
                stdout=json.dumps({"model": {}, "applications": {}})
            )(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_kubernetes_malformed_json_graceful(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stdout="not json", returncode=0)
        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_lxd_malformed_json_graceful(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stdout="not json", returncode=0)
        with patch("glitch.collectors.lxd.subprocess.run", mock_run):
            collector = LXDCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_ceph_malformed_json_graceful(self, tmp_path: Path) -> None:
        call_count = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_mock_run(stdout="not json", returncode=0)(*args, **kwargs)
            return make_mock_run(stdout="not json either")(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)
        with patch("glitch.collectors.ceph.subprocess.run", mock_run):
            collector = CephCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"


class TestMissingFieldsInOutput:
    def test_juju_status_missing_applications_field(self, tmp_path: Path) -> None:
        status = {"model": {"name": "bare"}}
        mock_run = make_mock_run(stdout=json.dumps(status))
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_juju_status_missing_units_field(self, tmp_path: Path) -> None:
        status = {
            "model": {"name": "test"},
            "applications": {"app": {"charm": "app"}},
        }
        mock_run = make_mock_run(stdout=json.dumps(status))
        with patch("glitch.collectors.juju.subprocess.run", mock_run):
            collector = JujuCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_kubernetes_pods_missing_items_field(self, tmp_path: Path) -> None:
        call_count = 0

        def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_count
            call_count += 1
            if "pods" in str(args):
                return make_mock_run(stdout=json.dumps({"not_items": []}))(*args, **kwargs)
            return make_mock_run(stdout=json.dumps({"items": []}))(*args, **kwargs)

        mock_run = MagicMock(side_effect=side_effect)
        with patch("glitch.collectors.kubernetes.subprocess.run", mock_run):
            collector = KubernetesCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"

    def test_lxd_list_returns_object_not_list(self, tmp_path: Path) -> None:
        mock_run = make_mock_run(stdout=json.dumps({"error": "not a list"}))
        with patch("glitch.collectors.lxd.subprocess.run", mock_run):
            collector = LXDCollector()
            result = collector.collect(tmp_path)
        assert result.status == "ok"