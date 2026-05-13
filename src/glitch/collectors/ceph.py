"""Collect telemetry from a Ceph cluster."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from glitch.collectors.base import Collector, CollectorResult, register, run_tool

logger = logging.getLogger(__name__)


@register
class CephCollector(Collector):
    """Collect Ceph cluster status and health detail."""

    name = "ceph"
    priority = 40

    def detect(self) -> bool:
        return shutil.which("ceph") is not None

    def collect(self, output_dir: Path) -> CollectorResult:
        base = output_dir / "ceph"
        base.mkdir(parents=True, exist_ok=True)

        artifacts: list[Path] = []

        _collect_ceph_status(base, artifacts)
        _collect_ceph_health_detail(base, artifacts)

        return CollectorResult(status="ok", artifacts=artifacts)


def _collect_ceph_status(base: Path, artifacts: list[Path]) -> None:
    try:
        result = run_tool(["ceph", "status", "--format", "json"], timeout=30)
        if result.returncode != 0:
            logger.warning("ceph status failed: %s", result.stderr[:200])
            return
        data = json.loads(result.stdout)
        path = base / "status.json"
        path.write_text(json.dumps(data, indent=2))
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("ceph status timed out")
    except json.JSONDecodeError as exc:
        logger.warning("ceph status returned invalid JSON: %s", exc)
    except Exception:
        logger.exception("Unexpected error collecting ceph status")


def _collect_ceph_health_detail(base: Path, artifacts: list[Path]) -> None:
    try:
        result = run_tool(["ceph", "health", "detail", "--format", "json"], timeout=30)
        if result.returncode != 0:
            logger.warning("ceph health detail failed: %s", result.stderr[:200])
            return
        data = json.loads(result.stdout)
        path = base / "health-detail.json"
        path.write_text(json.dumps(data, indent=2))
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("ceph health detail timed out")
    except json.JSONDecodeError as exc:
        logger.warning("ceph health detail returned invalid JSON: %s", exc)
    except Exception:
        logger.exception("Unexpected error collecting ceph health detail")