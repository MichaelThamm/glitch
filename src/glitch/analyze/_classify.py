"""LLM classification prompt construction and response parsing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._copilot import CopilotSession
    from ._loader import AnalysisContext

SYSTEM_PROMPT = """You are a CI failure analyst for Juju charm development.
Classify the failure using this taxonomy:

- flaky: Non-deterministic; timing or environment sensitivity
- charm-bug: Defect in charm logic or configuration
- test-bug: Defect in the test itself (bad assertion, wrong assumption)
- infrastructure: CI runner, Kubernetes, Ceph, or LXD-level issue
- environment: Transient external dependency (network, registry, upstream package)
- unknown: Insufficient signal to classify

For each label, provide a confidence score in [0, 1].
A failure may carry multiple labels with independent scores.

First, write a step-by-step reasoning trace analyzing the evidence.
Then, output a JSON object with "test_id", "reasoning_trace", and "labels":
{
  "test_id": "...",
  "reasoning_trace": "Step 1: ...",
  "labels": {"charm-bug": 0.91, "flaky": 0.12}
}

Only include labels with confidence >= 0.1. Always include at least one label."""


@dataclass
class ClassificationVerdict:
    test_id: str
    labels: dict[str, float]
    reasoning_trace: str


@dataclass
class ClassificationResult:
    verdicts: list[ClassificationVerdict]
    model_used: str | None


def _build_discovery_context(discovery: dict) -> str:
    flakiness = discovery.get("flakiness_index", "N/A")
    heuristics = discovery.get("heuristic_breakdown", {})
    lines = [
        "## Flakiness Context (from Phase 1 Discovery)\n",
        f"Flakiness index: {flakiness}",
        "Heuristic breakdown:",
    ]
    for key, val in heuristics.items():
        lines.append(f"  - {key}: {val}")
    lines.append(
        "\nA high flakiness index (> 0.5) increases the prior probability of "
        "a 'flaky' label.\n"
        "High change_independence (> 0.7) further supports 'flaky' or suggests "
        "'environment'.\n"
    )
    return "\n".join(lines)


def _build_prompt(ctx: AnalysisContext) -> str:
    from ._loader import read_collector_content

    parts = [SYSTEM_PROMPT]

    if ctx.discovery:
        parts.append(_build_discovery_context(ctx.discovery))

    collector_content = read_collector_content(ctx)
    if collector_content:
        parts.append("## Telemetry Evidence\n")
        for name, text in collector_content.items():
            parts.append(f"### {name}\n```\n{text}\n```\n")

    test_id = ctx.manifest.get("test_id") or ctx.manifest.get(
        "job_name"
    ) or "unknown-test"
    parts.append(
        f"## Classification Task\n\nTest ID: {test_id}\n\n"
        "Follow the instructions: first reason step-by-step, then output JSON."
    )

    return "\n\n".join(parts)


def _extract_json(raw: str) -> str:
    """Extract JSON object from LLM response, handling fenced and nested braces."""
    fenced = re.search(
        r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL
    )
    content = fenced.group(1) if fenced else raw

    if content.strip().startswith("{") or content.strip().startswith("["):
        return content.strip()

    search = re.search(r"\{.*\}", content, re.DOTALL)
    if search:
        candidate = search.group(0)
        depth = 0
        start = None
        for i, ch in enumerate(candidate):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    return candidate[start:i + 1]

    raise ValueError(f"No JSON object found in response: {raw[:200]}")


def parse_classification(raw: str) -> ClassificationVerdict:
    json_str = _extract_json(raw)
    data = json.loads(json_str)
    return ClassificationVerdict(
        test_id=data.get("test_id", "unknown-test"),
        labels=data.get("labels", {"unknown": 1.0}),
        reasoning_trace=data.get("reasoning_trace", ""),
    )


def classify(
    ctx: AnalysisContext, session: CopilotSession
) -> ClassificationResult:
    prompt = _build_prompt(ctx)

    raw = None
    for attempt in range(2):
        raw = session.classify(prompt)
        try:
            verdict = parse_classification(raw)
            return ClassificationResult(
                verdicts=[verdict],
                model_used=None,
            )
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 0:
                prompt = (
                    f"{prompt}\n\nYour previous response was not valid JSON. "
                    f"Error: {e}\nPlease output ONLY a valid JSON object."
                )
            else:
                return ClassificationResult(
                    verdicts=[
                        ClassificationVerdict(
                            test_id=ctx.manifest.get("test_id")
                            or ctx.manifest.get("job_name")
                            or "unknown-test",
                            labels={"unknown": 1.0},
                            reasoning_trace=f"Malformed LLM response after retry. "
                            f"Raw: {raw[:500] if raw else 'None'}",
                        )
                    ],
                    model_used=None,
                )

    return ClassificationResult(
        verdicts=[
            ClassificationVerdict(
                test_id=ctx.manifest.get("test_id")
                or ctx.manifest.get("job_name")
                or "unknown-test",
                labels={"unknown": 1.0},
                reasoning_trace="No response from LLM.",
            )
        ],
        model_used=None,
    )
