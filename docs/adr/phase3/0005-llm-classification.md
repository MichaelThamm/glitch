# 0005 — LLM Classification

**Status**: proposed  
**Date**: 2026-05-13  
**Depends on**: [0002](0002-copilot-sdk-integration.md), [0004](0004-artifact-loading.md)  
**Traces to**: [phase-3-analysis.md — Classification](../../specs/phase-3-analysis.md#classification)

---

## Context and Problem

Phase 3 must classify CI failures into the 6-label taxonomy (`flaky`, `charm-bug`, `test-bug`, `infrastructure`, `environment`, `unknown`) with independent confidence scores [0, 1]. The LLM must produce a reasoning trace before committing to classification. The raw LLM output must be parsed into structured `Verdict` objects.

When `--discovery-json` is provided, the flakiness index and heuristic breakdown for the failing test are prepended to the LLM context. A high flakiness index raises the prior for `flaky`; high `change_independence` raises it further.

## Decision

Implement `src/glitch/analyze/_classify.py` with:

1. **`ClassificationVerdict` dataclass** — holds test_id, labels dict, reasoning trace
2. **`classify()` function** — builds prompt, sends to Copilot, parses response
3. **Prompt template** — structured to enforce taxonomy, reasoning trace, and structured output
4. **Response parser** — extracts labels + confidence from LLM text, handles malformed output

### Data model

```python
from dataclasses import dataclass, field

@dataclass
class ClassificationVerdict:
    test_id: str
    labels: dict[str, float]               # e.g. {"charm-bug": 0.91, "flaky": 0.12}
    reasoning_trace: str                    # verbatim LLM reasoning steps

@dataclass
class ClassificationResult:
    verdicts: list[ClassificationVerdict]
    model_used: str | None
```

### Prompt construction

The prompt has these sections, in order:

1. **System preamble** — role definition, taxonomy reference, output format instructions
2. **Phase 1 context** (if `--discovery-json` provided) — flakiness score, heuristic breakdown
3. **Telemetry evidence** — concatenated collector outputs from artifact bundle
4. **Classification task** — explicit instruction to produce reasoning trace then labels

Key prompt constraints:
- Output must be parseable JSON following a known schema
- The LLM is forced to reason step-by-step before producing labels
- Labels with confidence < 0.1 may be omitted from output

```python
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
```

### Response parsing

Parse the JSON block from LLM response. Handle:
- Response wrapped in ```json ... ``` fences
- Pure JSON body
- Malformed JSON → retry once; on second failure classify as `unknown` with error noted

```python
import json
import re

def parse_classification(raw: str) -> ClassificationVerdict:
    # Extract JSON block from markdown fences if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    json_str = match.group(1) if match else raw
    data = json.loads(json_str)
    return ClassificationVerdict(
        test_id=data["test_id"],
        labels=data["labels"],
        reasoning_trace=data["reasoning_trace"],
    )
```

### Phase 1 enrichment

When discovery data is present, inject into prompt:

```
## Flakiness Context (from Phase 1 Discovery)

Flakiness index: 0.73
Heuristic breakdown:
  - pass_fail_volatility: 0.82
  - retry_rate: 0.65
  - timing_variance: 0.41
  - change_independence: 0.91
  - recency_multiplier: 1.2

A high flakiness index (> 0.5) increases the prior probability of a 'flaky' label.
High change_independence (> 0.7) further supports 'flaky' or suggests 'environment'.
```

## Consequences

### Files

| Action | File |
|---|---|
| Create | `src/glitch/analyze/_classify.py` |

### Acceptance criteria

1. `classify(ctx, session)` returns `ClassificationResult` with at least one verdict
2. `parse_classification(valid_json_string)` returns correct `ClassificationVerdict`
3. `parse_classification("```json\n{...}\n```")` strips fences and parses correctly
4. Malformed LLM response triggers one retry; on second failure returns `unknown` label
5. Prompt includes Phase 1 context when `ctx.discovery` is not None
