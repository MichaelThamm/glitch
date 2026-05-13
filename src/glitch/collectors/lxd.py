"""Collect telemetry from LXD instances."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from glitch.collectors.base import Collector, CollectorResult, register, run_tool

logger = logging.getLogger(__name__)


@register
class LXDCollector(Collector):
    """Collect the LXD instance list and per-instance info."""

    name = "lxd"
    priority = 30

    def detect(self) -> bool:
        return shutil.which("lxc") is not None

    def collect(self, output_dir: Path) -> CollectorResult:
        base = output_dir / "lxd"
        base.mkdir(parents=True, exist_ok=True)

        artifacts: list[Path] = []

        instances = _collect_list(base, artifacts)
        for instance_name in instances:
            _collect_instance_info(base, artifacts, instance_name)

        return CollectorResult(status="ok", artifacts=artifacts)


def _collect_list(base: Path, artifacts: list[Path]) -> list[str]:
    try:
        result = run_tool(["lxc", "list", "--format", "json"], timeout=30)
        if result.returncode != 0:
            logger.warning("lxc list failed: %s", result.stderr[:200])
            return []
        data = json.loads(result.stdout)
        path = base / "list.json"
        path.write_text(json.dumps(data, indent=2))
        artifacts.append(path)

        instance_names: list[str] = []
        for entry in data:
            if isinstance(entry, dict) and "name" in entry:
                instance_names.append(entry["name"])
        return instance_names
    except subprocess.TimeoutExpired:
        logger.warning("lxc list timed out")
        return []
    except json.JSONDecodeError as exc:
        logger.warning("lxc list returned invalid JSON: %s", exc)
        return []
    except Exception:
        logger.exception("Unexpected error collecting lxc list")
        return []


def _collect_instance_info(
    base: Path, artifacts: list[Path], instance: str
) -> None:
    instances_dir = base / "instances"
    instances_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_tool(["lxc", "info", instance], timeout=30)
        if result.returncode != 0:
            logger.warning("lxc info %s failed: %s", instance, result.stderr[:200])
            return
        path = instances_dir / f"{instance}.txt"
        path.write_text(result.stdout)
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("lxc info %s timed out", instance)
    except Exception:
        logger.exception("Unexpected error collecting lxc info for %s", instance)