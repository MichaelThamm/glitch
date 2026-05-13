"""Tests for output writing: verdict.json, report.md, fix.patch."""

from __future__ import annotations

import json
from pathlib import Path


from glitch.analyze._classify import ClassificationResult, ClassificationVerdict
from glitch.analyze._loader import AnalysisContext
from glitch.analyze._output import write_outputs, write_verdict, write_report
from glitch.analyze._remediate import (
    RemediationAction,
    RemediationEntry,
    RemediationPlan,
)


def _make_ctx(artifact_dir: Path) -> AnalysisContext:
    return AnalysisContext(
        artifact_dir=artifact_dir,
        manifest={"test_id": "test-foo"},
        collector_paths={},
        discovery=None,
    )


def _make_verdict(
    test_id: str = "test-foo",
    labels: dict[str, float] | None = None,
    reasoning_trace: str = "step 1",
) -> ClassificationVerdict:
    return ClassificationVerdict(
        test_id=test_id,
        labels=labels or {"charm-bug": 0.91, "flaky": 0.12},
        reasoning_trace=reasoning_trace,
    )


def _make_classification(
    verdicts: list[ClassificationVerdict] | None = None,
) -> ClassificationResult:
    return ClassificationResult(
        verdicts=verdicts or [_make_verdict()],
        model_used=None,
    )


class TestWriteVerdict:
    def test_write_verdict_creates_file(self, temp_output_dir: Path) -> None:
        classification = _make_classification()
        remediation = RemediationPlan(entries=[], patch_generated=False)
        ctx = _make_ctx(Path("/fake/artifacts"))

        write_verdict(temp_output_dir, classification, remediation, ctx, "1.0.0", 0.8)

        verdict_path = temp_output_dir / "verdict.json"
        assert verdict_path.is_file()
        data = json.loads(verdict_path.read_text())
        assert isinstance(data, dict)

    def test_write_verdict_schema(self, temp_output_dir: Path) -> None:
        classification = _make_classification()
        remediation = RemediationPlan(entries=[], patch_generated=False)
        ctx = _make_ctx(Path("/fake/artifacts"))

        write_verdict(temp_output_dir, classification, remediation, ctx, "1.0.0", 0.8)

        data = json.loads((temp_output_dir / "verdict.json").read_text())
        for key in ("glitch_version", "analysed_at", "verdicts"):
            assert key in data, f"Missing key: {key}"

    def test_write_verdict_remediation_action(self, temp_output_dir: Path) -> None:
        verdict = _make_verdict(test_id="test-foo", labels={"charm-bug": 0.91})
        classification = _make_classification([verdict])
        entry = RemediationEntry(
            test_id="test-foo",
            label="charm-bug",
            confidence=0.91,
            action=RemediationAction.PATCH,
            content="diff content",
        )
        remediation = RemediationPlan(entries=[entry], patch_generated=True)
        ctx = _make_ctx(Path("/fake/artifacts"))

        write_verdict(temp_output_dir, classification, remediation, ctx, "1.0.0", 0.8)

        data = json.loads((temp_output_dir / "verdict.json").read_text())
        v = data["verdicts"][0]
        assert v["remediation"]["action"] == "patch"
        assert v["remediation"]["patch_file"] == "fix.patch"


class TestWriteReport:
    def test_write_report_creates_file(self, temp_output_dir: Path) -> None:
        classification = _make_classification()
        remediation = RemediationPlan(entries=[], patch_generated=False)
        ctx = _make_ctx(Path("/fake/artifacts"))

        write_report(temp_output_dir, classification, remediation, ctx, "1.0.0")

        report_path = temp_output_dir / "report.md"
        assert report_path.is_file()

    def test_write_report_has_sections(self, temp_output_dir: Path) -> None:
        classification = _make_classification()
        remediation = RemediationPlan(entries=[], patch_generated=False)
        ctx = _make_ctx(Path("/fake/artifacts"))

        write_report(temp_output_dir, classification, remediation, ctx, "1.0.0")

        content = (temp_output_dir / "report.md").read_text()
        assert "Glitch Analysis Report" in content
        assert "Executive Summary" in content
        assert "Suggested Fixes" in content


class TestWriteOutputs:
    def test_write_outputs_creates_dir(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "new-output"
        classification = _make_classification()
        remediation = RemediationPlan(entries=[], patch_generated=False)
        ctx = _make_ctx(Path("/fake/artifacts"))

        assert not output_dir.exists()

        write_outputs(output_dir, classification, remediation, ctx, "1.0.0", 0.8)

        assert output_dir.is_dir()
        assert (output_dir / "verdict.json").is_file()
        assert (output_dir / "report.md").is_file()

    def test_write_outputs_with_patch(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "with-patch"
        verdict = _make_verdict(test_id="test-foo", labels={"charm-bug": 0.91})
        classification = _make_classification([verdict])
        entry = RemediationEntry(
            test_id="test-foo",
            label="charm-bug",
            confidence=0.91,
            action=RemediationAction.PATCH,
            content="--- a/file\n+++ b/file\n@@ -1 +1 @@\n- old\n+ new\n",
        )
        remediation = RemediationPlan(entries=[entry], patch_generated=True)
        ctx = _make_ctx(Path("/fake/artifacts"))

        write_outputs(output_dir, classification, remediation, ctx, "1.0.0", 0.8)

        patch_path = output_dir / "fix.patch"
        assert patch_path.is_file()
        assert "--- a/file" in patch_path.read_text()
