"""Write verdict.json, report.md, and fix.patch to output directory."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._classify import ClassificationResult
    from ._loader import AnalysisContext
    from ._remediate import RemediationPlan


def write_outputs(
    output_dir: Path,
    classification: ClassificationResult,
    remediation: RemediationPlan,
    ctx: AnalysisContext,
    glitch_version: str,
    confidence_threshold: float,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_verdict(output_dir, classification, remediation, ctx, glitch_version, confidence_threshold)
    write_report(output_dir, classification, remediation, ctx, glitch_version)
    if remediation.patch_generated:
        write_patch(output_dir, remediation)


def write_verdict(
    output_dir: Path,
    classification: ClassificationResult,
    remediation: RemediationPlan,
    ctx: AnalysisContext,
    glitch_version: str,
    confidence_threshold: float,
) -> None:
    from ._remediate import RemediationAction

    verdict_list = []
    for verdict in classification.verdicts:
        rem_action = "none"
        patch_file = None
        for entry in remediation.entries:
            if entry.test_id == verdict.test_id and entry.action == RemediationAction.PATCH:
                rem_action = "patch"
                patch_file = "fix.patch"
                break
            elif entry.test_id == verdict.test_id:
                rem_action = entry.action.name.lower()
                break

        v = {
            "test_id": verdict.test_id,
            "labels": verdict.labels,
            "remediation": {
                "action": rem_action,
            },
        }
        if patch_file:
            v["remediation"]["patch_file"] = patch_file
        verdict_list.append(v)

    data = {
        "glitch_version": glitch_version,
        "analysed_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "artifact_dir": str(ctx.artifact_dir),
        "discovery_json": str(ctx.discovery.get("_path", ""))
        if ctx.discovery
        else "",
        "confidence_threshold": confidence_threshold,
        "verdicts": verdict_list,
    }

    path = output_dir / "verdict.json"
    path.write_text(json.dumps(data, indent=2))


def write_report(
    output_dir: Path,
    classification: ClassificationResult,
    remediation: RemediationPlan,
    ctx: AnalysisContext,
    glitch_version: str,
) -> None:
    from ._remediate import RemediationAction

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parts = [
        "# Glitch Analysis Report\n\n",
        f"**Glitch version**: {glitch_version}\n\n",
        f"**Generated**: {timestamp}\n\n",
        f"**Artifact directory**: {ctx.artifact_dir}\n\n",
]

    parts.append("## Executive Summary\n\n")
    for verdict in classification.verdicts:
        top_label = max(verdict.labels.items(), key=lambda x: x[1])
        actions = [
            f"- {e.label} ({e.confidence:.2f}): {e.action.name.lower()}\n"
            for e in remediation.entries
            if e.test_id == verdict.test_id
        ]
        parts.append(
            f"**{verdict.test_id}**: {top_label[0]} ({top_label[1]:.2f})\n"
        )
        parts.extend(actions)
        parts.append("\n")

    for verdict in classification.verdicts:
        parts.append(f"## {verdict.test_id}\n\n")

        parts.append("### Reasoning Trace\n\n")
        parts.append(verdict.reasoning_trace)
        parts.append("\n\n")

        parts.append("### Evidence\n\n")
        parts.append("(Telemetry from artifact bundle)\n\n")

    parts.append("## Suggested Fixes\n\n")
    for entry in remediation.entries:
        if entry.action in (RemediationAction.PATCH, RemediationAction.SUGGESTION):
            parts.append(f"### {entry.test_id} — {entry.label}\n\n")
            if entry.action == RemediationAction.PATCH:
                parts.append(f"**Patch generated** (confidence: {entry.confidence:.2f})\n")
                parts.append("Apply with: `git apply glitch-analysis/fix.patch`\n\n")
            else:
                parts.append(f"**Suggestion** (confidence: {entry.confidence:.2f}, below threshold)\n\n")
                parts.append(entry.content)
                parts.append("\n\n")

    parts.append("## Issue Templates\n\n")
    for entry in remediation.entries:
        if entry.action == RemediationAction.ISSUE_TEMPLATE:
            parts.append(entry.content)
            parts.append("\n\n")

    for entry in remediation.entries:
        if entry.action == RemediationAction.NARRATIVE:
            parts.append(entry.content)
            parts.append("\n\n")

    parts.append("## Feedback\n\n")
    parts.append(
        "Resolved patterns have been written to the known-patterns store.\n"
    )

    path = output_dir / "report.md"
    path.write_text("".join(parts))


def write_patch(
    output_dir: Path, remediation: RemediationPlan
) -> None:
    from ._remediate import RemediationAction

    patch_entry = next(
        e for e in remediation.entries if e.action == RemediationAction.PATCH
    )
    patch_path = output_dir / "fix.patch"
    patch_path.write_text(patch_entry.content)
    print(f"Patch written to {patch_path}")
    print("To apply: git apply glitch-analysis/fix.patch")
    print("To review: git diff --stat")
