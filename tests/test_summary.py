"""Tests for SummaryBuilder and build_summary."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from glitch.collectors.manifest import CollectorEntry, Manifest
from glitch.collectors.summary import SummaryBuilder, build_summary


def _make_manifest() -> Manifest:
    return Manifest(
        glitch_version="0.1.0",
        collected_at=datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc),
        collectors={
            "juju": CollectorEntry(status="ok", extra={"model": "my-model"}),
            "kubernetes": CollectorEntry(status="skipped", reason="CLI not found"),
            "lxd": CollectorEntry(status="error", reason="something broke"),
        },
    )


class TestSummaryBuilder:
    def test_add_section_renders_h2_heading(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_section("Environment", "Host: myhost")
        rendered = builder.render()
        assert "## Environment" in rendered
        assert "Host: myhost" in rendered

    def test_add_section_content(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_section("Top", "value")
        assert builder.render().count("##") == 1

    def test_add_table_renders_gfm_table(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_table(
            "Info",
            ["Field", "Value"],
            [["Hostname", "myhost"], ["Date", "2025-04-01"]],
        )
        rendered = builder.render()
        assert "| Field | Value |" in rendered
        assert "| --- | --- |" in rendered
        assert "| Hostname | myhost |" in rendered
        assert "| Date | 2025-04-01 |" in rendered

    def test_add_table_three_columns(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_table("Grid", ["A", "B", "C"], [["1", "2", "3"]])
        rendered = builder.render()
        assert "| A | B | C |" in rendered
        assert "| --- | --- | --- |" in rendered

    def test_add_code_block_renders_fenced_block(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_code_block("print('hello')", language="python")
        rendered = builder.render()
        assert "```python" in rendered
        assert "print('hello')" in rendered
        assert "```" in rendered

    def test_add_code_block_no_language(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_code_block("plain text")
        rendered = builder.render()
        assert "```" in rendered
        assert "plain text" in rendered

    def test_render_concatenates_sections(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_section("Section A", "a")
        builder.add_section("Section B", "b")
        rendered = builder.render()
        assert rendered.index("Section A") < rendered.index("Section B")

    def test_render_empty_builder(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        assert builder.render() == ""

    def test_write_to_file(self, tmp_path: Path) -> None:
        builder = SummaryBuilder(_make_manifest(), tmp_path)
        builder.add_section("Hello", "world")
        output = tmp_path / "out.md"
        builder.write(output)
        assert output.is_file()
        assert "## Hello" in output.read_text()
        assert "world" in output.read_text()

    def test_multiple_method_calls(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_section("One", "1")
        builder.add_section("Two", "2")
        builder.add_code_block("data")
        rendered = builder.render()
        assert "## One" in rendered
        assert "## Two" in rendered
        assert "data" in rendered

    def test_sections_and_table_together(self) -> None:
        builder = SummaryBuilder(_make_manifest(), Path("."))
        builder.add_section("Alpha", "start")
        builder.add_table("Metrics", ["Key"], [["val"]])
        builder.add_section("Beta", "end")
        builder.add_code_block("code", "json")
        rendered = builder.render()
        assert rendered.index("Alpha") < rendered.index("val")
        assert rendered.index("val") < rendered.index("Beta")
        assert rendered.index("Beta") < rendered.index("code")


class TestBuildSummary:
    def test_generates_complete_document(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        out = build_summary(manifest, tmp_path)

        assert "## Collection Summary" in out
        assert "### Collector Status" in out
        assert "| Collector | Status | Reason |" in out
        assert "juju" in out
        assert "ok" in out
        assert "kubernetes" in out
        assert "skipped" in out
        assert "lxd" in out
        assert "error" in out

    def test_renders_manifest_fields(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        out = build_summary(manifest, tmp_path)

        assert "0.1.0" in out
        assert "2026" in out

    def test_empty_manifest(self, tmp_path: Path) -> None:
        manifest = Manifest(
            glitch_version="0.0.0",
            collected_at=datetime.now(timezone.utc),
            collectors={},
        )
        out = build_summary(manifest, tmp_path)

        assert "## Collection Summary" in out
        assert "### Collector Status" in out

    def test_reads_juju_status_for_summary(self, tmp_path: Path) -> None:
        juju_dir = tmp_path / "juju"
        juju_dir.mkdir()
        (juju_dir / "status.json").write_text(
            json.dumps({"model": "test-model", "applications": {"app1": {}, "app2": {}}})
        )

        manifest = _make_manifest()
        out = build_summary(manifest, tmp_path)
        assert "test-model" in out
        assert "2" in out

    def test_reads_k8s_events_for_summary(self, tmp_path: Path) -> None:
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        (k8s_dir / "events.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "type": "Warning",
                            "reason": "FailedScheduling",
                            "message": "0/3 nodes available",
                            "metadata": {"namespace": "default"},
                            "involvedObject": {"kind": "Pod", "name": "bad-pod"},
                        }
                    ]
                }
            )
        )

        manifest = _make_manifest()
        out = build_summary(manifest, tmp_path)
        assert "FailedScheduling" in out
        assert "bad-pod" in out

    def test_reads_junit_xml_for_summary(self, tmp_path: Path) -> None:
        ta_dir = tmp_path / "test-artifacts"
        ta_dir.mkdir()
        suite = ET.Element("testsuite", {"tests": "5", "failures": "2", "errors": "1", "skipped": "1"})
        tree = ET.ElementTree(suite)
        tree.write(str(ta_dir / "report.xml"))

        manifest = _make_manifest()
        out = build_summary(manifest, tmp_path)
        assert "Test Results" in out
