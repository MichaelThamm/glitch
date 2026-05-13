"""Build a human-readable Markdown summary of collected data."""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from glitch.collectors.manifest import Manifest

logger = logging.getLogger(__name__)


class SummaryBuilder:
    """Helper that accumulates sections into a Markdown document."""

    def __init__(self, manifest: Manifest, output_dir: Path) -> None:
        self._manifest = manifest
        self._output_dir = output_dir
        self._lines: list[str] = []

    def add_section(self, heading: str, content: str) -> None:
        self._lines.append(f"## {heading}")
        self._lines.append("")
        self._lines.append(content.rstrip())
        self._lines.append("")

    def add_table(self, heading: str, headers: list[str], rows: list[list[str]]) -> None:
        self._lines.append(f"### {heading}")
        self._lines.append("")
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join("---" for _ in headers) + " |"
        self._lines.append(header_line)
        self._lines.append(sep_line)
        for row in rows:
            self._lines.append("| " + " | ".join(str(c) for c in row) + " |")
        self._lines.append("")

    def add_code_block(self, content: str, language: str = "") -> None:
        self._lines.append(f"```{language}")
        self._lines.append(content.rstrip())
        self._lines.append("```")
        self._lines.append("")

    def render(self) -> str:
        return "\n".join(self._lines)

    def write(self, path: Path) -> None:
        path.write_text(self.render())


def build_summary(manifest: Manifest, output_dir: Path) -> str:
    """Construct summary.md from the manifest and collected data files.

    Args:
        manifest: The collection manifest.
        output_dir: Root directory where collector subdirectories live.

    Returns:
        The rendered Markdown string.
    """
    builder = SummaryBuilder(manifest, output_dir)

    builder.add_section(
        "Collection Summary",
        f"**Glitch version:** {manifest.glitch_version}\n\n"
        f"**Collected at:** {manifest.collected_at.isoformat()}",
    )

    _build_collector_status_table(builder, manifest)
    _build_juju_summary(builder, output_dir)
    _build_k8s_summary(builder, output_dir)
    _build_lxd_summary(builder, output_dir)
    _build_ceph_summary(builder, output_dir)
    _build_test_artifacts_summary(builder, output_dir)

    return builder.render()


def _build_collector_status_table(builder: SummaryBuilder, manifest: Manifest) -> None:
    headers = ["Collector", "Status", "Reason"]
    rows: list[list[str]] = []
    for name, entry in manifest.collectors.items():
        rows.append([name, entry.status, entry.reason or ""])
    builder.add_table("Collector Status", headers, rows)


def _build_juju_summary(builder: SummaryBuilder, output_dir: Path) -> None:
    status_path = output_dir / "juju" / "status.json"
    debug_log_path = output_dir / "juju" / "debug-log.txt"

    if status_path.is_file():
        try:
            data = json.loads(status_path.read_text())
            model = data.get("model", "")
            apps = data.get("applications", {})
            lines = [f"**Model:** {model}", f"**Applications:** {len(apps)}"]
            builder.add_section("Juju Status", "\n".join(lines))
        except Exception:
            logger.exception("Failed to parse juju status.json for summary")

    if debug_log_path.is_file():
        try:
            raw = debug_log_path.read_text().splitlines()
            filtered = [line for line in raw if "ERROR" in line or "WARNING" in line]
            snippet = "\n".join(filtered[-50:])
            if snippet:
                builder.add_section("Juju Debug Log (last 50 ERROR/WARNING lines)", "")
                builder.add_code_block(snippet, language="text")
        except Exception:
            logger.exception("Failed to read juju debug-log for summary")


def _build_k8s_summary(builder: SummaryBuilder, output_dir: Path) -> None:
    events_path = output_dir / "k8s" / "events.json"
    if not events_path.is_file():
        return

    try:
        data = json.loads(events_path.read_text())
        warning_events: list[dict] = []
        for item in data.get("items", []):
            if item.get("type") == "Warning":
                warning_events.append(item)

        if warning_events:
            headers = ["Namespace", "Object", "Reason", "Message"]
            rows: list[list[str]] = []
            for ev in warning_events[-20:]:
                involved = ev.get("involvedObject", {})
                rows.append([
                    ev.get("metadata", {}).get("namespace", ""),
                    f"{involved.get('kind', '')}/{involved.get('name', '')}",
                    ev.get("reason", ""),
                    (ev.get("message", "") or "")[:120],
                ])
            builder.add_table("Kubernetes Warning Events (last 20)", headers, rows)
    except Exception:
        logger.exception("Failed to parse k8s events for summary")


def _build_lxd_summary(builder: SummaryBuilder, output_dir: Path) -> None:
    list_path = output_dir / "lxd" / "list.json"
    if not list_path.is_file():
        return

    try:
        data = json.loads(list_path.read_text())
        if isinstance(data, list):
            builder.add_section("LXD Instances", f"**Count:** {len(data)}")
    except Exception:
        logger.exception("Failed to parse lxd list for summary")


def _build_ceph_summary(builder: SummaryBuilder, output_dir: Path) -> None:
    status_path = output_dir / "ceph" / "status.json"
    if not status_path.is_file():
        return

    try:
        data = json.loads(status_path.read_text())
        health_info = data.get("health", {})
        overall = health_info.get("status", "unknown")
        builder.add_section("Ceph Status", f"**Overall health:** {overall}")
    except Exception:
        logger.exception("Failed to parse ceph status for summary")


def _build_test_artifacts_summary(builder: SummaryBuilder, output_dir: Path) -> None:
    test_artifacts_dir = output_dir / "test-artifacts"
    if not test_artifacts_dir.is_dir():
        return

    junit_files = list(test_artifacts_dir.rglob("*.xml"))
    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0

    for xml_file in junit_files:
        try:
            tree = ET.parse(str(xml_file))
            root = tree.getroot()
            if root.tag == "testsuites":
                suites = root.findall("testsuite")
            elif root.tag == "testsuite":
                suites = [root]
            else:
                suites = []

            for suite in suites:
                total_tests += int(suite.get("tests", 0))
                total_failures += int(suite.get("failures", 0))
                total_errors += int(suite.get("errors", 0))
                total_skipped += int(suite.get("skipped", 0))
        except ET.ParseError:
            continue
        except Exception:
            logger.exception("Failed to parse JUnit XML: %s", xml_file)

    if total_tests > 0:
        rows = [
            ["Total tests", str(total_tests)],
            ["Failures", str(total_failures)],
            ["Errors", str(total_errors)],
            ["Skipped", str(total_skipped)],
        ]
        builder.add_table("Test Results", ["Metric", "Count"], rows)
    else:
        builder.add_section(
            "Test Artifacts",
            "Copied from `test-artifacts/` (no parseable JUnit XML found)",
        )