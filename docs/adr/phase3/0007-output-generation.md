# 0007 — Output Generation

**Status**: proposed  
**Date**: 2026-05-13  
**Depends on**: [0005](0005-llm-classification.md), [0006](0006-automated-remediation.md)  
**Traces to**: [phase-3-analysis.md — Output Formats](../../specs/phase-3-analysis.md#output-formats)

---

## Context and Problem

Phase 3 writes three output files to `--output-dir` (default `./glitch-analysis`):

1. **`verdict.json`** — machine-readable classification result
2. **`report.md`** — human-readable narrative report
3. **`fix.patch`** — unified diff patch (only when applicable)

These formats have specific schemas defined in the spec.

## Decision

Implement `src/glitch/analyze/_output.py` with a single `write_outputs()` function:

```python
def write_outputs(
    output_dir: Path,
    classification: ClassificationResult,
    remediation: RemediationPlan,
    ctx: AnalysisContext,
    glitch_version: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_verdict(output_dir, classification, remediation, ctx, glitch_version)
    write_report(output_dir, classification, remediation, ctx, glitch_version)
    if remediation.patch_generated:
        write_patch(output_dir, remediation)
```

### `verdict.json` schema (from spec)

```json
{
  "glitch_version": "0.1.0",
  "analysed_at": "2026-05-13T10:00:00Z",
  "artifact_dir": "./glitch-artifact",
  "discovery_json": "./glitch-discovery.json",
  "confidence_threshold": 0.8,
  "verdicts": [
    {
      "test_id": "integration (test_deploy_local)",
      "labels": {"charm-bug": 0.91, "flaky": 0.12},
      "remediation": {
        "action": "patch",
        "patch_file": "fix.patch"
      }
    }
  ]
}
```

Implementation: build a dict from the dataclasses, serialize with `json.dumps(indent=2)`.

### `report.md` sections (from spec)

**Required sections**:

1. **Executive summary** — top label + confidence per test, remediation action taken
2. **Reasoning trace** — verbatim LLM reasoning steps
3. **Evidence** — key log excerpts and telemetry snippets cited in reasoning
4. **Suggested fixes** — patch instructions or remediation suggestions
5. **Issue templates** — pre-filled GitHub issue markdown for `infrastructure`/`environment`
6. **Feedback** — what was written to patterns store

```python
def build_report(...) -> str:
    parts = [
        f"# Glitch Analysis Report\n\nGenerated: {timestamp}\n",
        f"## Executive Summary\n\n{executive_summary}\n",
    ]
    for verdict in classification.verdicts:
        parts.append(f"## {verdict.test_id}\n")
        parts.append(f"### Reasoning Trace\n\n{verdict.reasoning_trace}\n")
        ...
    return "\n\n".join(parts)
```

### `fix.patch` output

When `patch_generated` is True, write the raw diff string to `fix.patch`:

```python
def write_patch(output_dir: Path, remediation: RemediationPlan) -> None:
    patch_entry = next(e for e in remediation.entries if e.action == RemediationAction.PATCH)
    patch_path = output_dir / "fix.patch"
    patch_path.write_text(patch_entry.content)
    print(f"Patch written to {patch_path}")
    print("To apply: git apply " + str(patch_path))
    print("To review: git diff --stat")
```

### Output directory handling

- Create `--output-dir` if it doesn't exist (`mkdir(parents=True)`)
- If `--output-dir` already has files, overwrite them
- Print a summary line: `Analysis complete. Output written to {output_dir}`

### test_id extraction

The spec references `test_id` as the key identifier. Since Phase 2 isn't built yet:

- If `manifest.json` contains a `test_id` or `job_name` field, use it
- Otherwise derive from the artifact directory name or use `"unknown-test"`
- The `test_id` string matches what Phase 1 Discovery produces (format: `"workflow_name (job_name)"`)

## Consequences

### Files

| Action | File |
|---|---|
| Create | `src/glitch/analyze/_output.py` |

### Acceptance criteria

1. `write_outputs()` creates `--output-dir` if missing
2. `verdict.json` validates against the schema above (all required fields present)
3. `report.md` contains all 6 required sections
4. `fix.patch` is only written when `patch_generated=True`
5. Console output includes "To apply: git apply" and "To review: git diff --stat" instructions
6. Dates are ISO 8601 with timezone (`2026-05-13T10:00:00Z`)
