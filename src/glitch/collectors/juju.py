"""Collect telemetry from a Juju model."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from glitch.collectors.base import Collector, CollectorResult, register, run_tool

logger = logging.getLogger(__name__)


@register
class JujuCollector(Collector):
    """Collect Juju status, debug-logs, and per-unit details.

    Args:
        model: Optional Juju model name (passed to ``-m``).  Defaults to the
            currently-active model.
    """

    name = "juju"
    priority = 10

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model

    def detect(self) -> bool:
        return shutil.which("juju") is not None

    def collect(self, output_dir: Path) -> CollectorResult:
        base = output_dir / "juju"
        base.mkdir(parents=True, exist_ok=True)

        juju_args = ["juju"]
        if self.model:
            juju_args.extend(["-m", self.model])

        artifacts: list[Path] = []

        _collect_status(juju_args, base, artifacts)
        _collect_debug_log(juju_args, base, artifacts)
        _collect_units(juju_args, base, artifacts)

        return CollectorResult(status="ok", artifacts=artifacts)


def _collect_status(
    juju_args: list[str], base: Path, artifacts: list[Path]
) -> None:
    """Fetch ``juju status --format json`` and discover units/containers."""
    try:
        result = run_tool([*juju_args, "status", "--format", "json"])
        if result.returncode != 0:
            logger.warning("juju status failed: %s", result.stderr[:200])
            return
        data = json.loads(result.stdout)
        path = base / "status.json"
        path.write_text(json.dumps(data, indent=2))
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("juju status timed out")
    except json.JSONDecodeError as exc:
        logger.warning("juju status returned invalid JSON: %s", exc)
    except Exception:
        logger.exception("Unexpected error collecting juju status")


def _collect_debug_log(
    juju_args: list[str], base: Path, artifacts: list[Path]
) -> None:
    try:
        result = run_tool([*juju_args, "debug-log", "--limit", "0"], timeout=120)
        if result.returncode != 0:
            logger.warning("juju debug-log failed: %s", result.stderr[:200])
            return
        path = base / "debug-log.txt"
        path.write_text(result.stdout)
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("juju debug-log timed out after 120s")
    except Exception:
        logger.exception("Unexpected error collecting juju debug-log")


def _discover_containers(status_data: dict) -> list[tuple[str, str]]:
    """Return (unit_name, container_name) pairs from status JSON."""
    pairs: list[tuple[str, str]] = []
    for app_name, app in status_data.get("applications", {}).items():
        for unit_name in app.get("units", {}):
            containers = app.get("units", {}).get(unit_name, {}).get("containers", {})
            for container_name in containers:
                pairs.append((unit_name, container_name))
    return pairs


def _collect_units(
    juju_args: list[str], base: Path, artifacts: list[Path]
) -> None:
    """Collect ``juju show-unit`` for every unit and ``pebble logs`` for every container."""

    try:
        result = run_tool([*juju_args, "status", "--format", "json"])
        if result.returncode != 0:
            return
        status_data = json.loads(result.stdout)
    except Exception:
        logger.exception("Cannot enumerate units; skipping unit collection")
        return

    containers = _discover_containers(status_data)
    seen_units: set[str] = set()

    for unit_name, container_name in containers:
        if unit_name not in seen_units:
            seen_units.add(unit_name)
            _collect_show_unit(juju_args, base, artifacts, unit_name)
        _collect_pebble_logs(juju_args, base, artifacts, unit_name, container_name)


def _collect_show_unit(
    juju_args: list[str], base: Path, artifacts: list[Path], unit: str
) -> None:
    units_dir = base / "units"
    units_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_tool([*juju_args, "show-unit", unit, "--format", "json"], timeout=30)
        if result.returncode != 0:
            logger.warning("juju show-unit %s failed: %s", unit, result.stderr[:200])
            return
        path = units_dir / f"{unit}.json"
        path.write_text(json.dumps(json.loads(result.stdout), indent=2))
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("juju show-unit %s timed out", unit)
    except json.JSONDecodeError as exc:
        logger.warning("juju show-unit %s returned invalid JSON: %s", unit, exc)
    except Exception:
        logger.exception("Unexpected error collecting show-unit for %s", unit)


def _collect_pebble_logs(
    juju_args: list[str],
    base: Path,
    artifacts: list[Path],
    unit: str,
    container: str,
) -> None:
    pebble_dir = base / "pebble"
    pebble_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_tool(
            [*juju_args, "exec", "--unit", unit, "--", "pebble", "logs"],
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("pebble logs for %s/%s failed: %s", unit, container, result.stderr[:200])
            return
        path = pebble_dir / f"{unit}-{container}.txt"
        path.write_text(result.stdout)
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("pebble logs for %s/%s timed out", unit, container)
    except Exception:
        logger.exception("Unexpected error collecting pebble logs for %s/%s", unit, container)