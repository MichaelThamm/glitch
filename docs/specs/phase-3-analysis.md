# Spec: Phase 3 — Analysis

**Status**: Draft  
**Phase**: 3 of 3  
**Traces to**: [VISION.md — Phase 3: Analysis](../../VISION.md)

---

## Purpose

Analysis classifies CI failures by root cause with confidence scores and attempts automated remediation where confidence is sufficient. It is the only phase that uses an LLM. It works identically in-runner (immediately after a CI failure) and offline (developer runs it locally against a downloaded artifact bundle).

For shared CLI concerns (installation, packaging, global flags), see [glitch-cli.md](glitch-cli.md).

---

## CLI Interface

```
glitch analyze [OPTIONS]

Options:
  --artifact-dir         Path to the Phase 2 artifact bundle directory (required)
  --discovery-json       Path to Phase 1 JSON output to enrich classification confidence (optional)
  --confidence-threshold Float in [0, 1]; remediation is attempted above this value (default: 0.8)
  --output-dir           Directory to write verdict and report (default: ./glitch-analysis)
  --model                Copilot model to use (default: determined by Copilot SDK)
```

### Typical CI usage

```yaml
- name: Analyse failure
  if: failure()
  run: |
    glitch analyze \
      --artifact-dir ./glitch-artifact \
      --discovery-json ./glitch-discovery.json
```

### Typical offline usage

```bash
# Developer downloads artifact from GitHub Actions, then:
glitch analyze --artifact-dir ~/Downloads/glitch-artifact --discovery-json ./glitch-discovery.json
```

---

## LLM Integration

Phase 3 uses the **GitHub Copilot SDK** (`copilot-sdk` on PyPI) for all LLM calls.

### Authentication

Resolved in order:

1. `GITHUB_TOKEN` environment variable — passed to `SubprocessConfig`
2. `gh auth token` — used as a fallback via the GitHub CLI credential

### Session lifecycle

A single Copilot session is created per `glitch analyze` invocation. All classification and remediation calls share the session, preserving context across the reasoning steps.

```python
from copilot import CopilotClient
from copilot.session import PermissionHandler

async with CopilotClient() as client:
    async with await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
    ) as session:
        # classification and remediation calls
```

---

## Inputs

| Input | Flag | Required |
|---|---|---|
| Phase 2 artifact bundle | `--artifact-dir` | Yes |
| Phase 1 flakiness JSON | `--discovery-json` | No — enriches confidence when present |

Phase 3 reads `manifest.json` from the artifact bundle root to locate collector outputs. It does not download artifacts from GitHub; the caller is responsible for providing a local path.

---

## Classification

### Taxonomy

Each failure receives one or more labels with independent confidence scores in `[0, 1]`:

| Label | Meaning |
|---|---|
| `flaky` | Non-deterministic; likely timing or environment sensitivity |
| `charm-bug` | Defect in the charm's logic or configuration |
| `test-bug` | Defect in the test itself (bad assertion, wrong assumption) |
| `infrastructure` | CI runner, Kubernetes, Ceph, or LXD-level issue |
| `environment` | Transient external dependency (network, registry, upstream package) |
| `unknown` | Insufficient signal to classify with confidence |

A failure may carry multiple labels (e.g. `flaky: 0.7, test-bug: 0.4`).

### Phase 1 enrichment

When `--discovery-json` is provided, the flakiness index and heuristic breakdown for the failing test are prepended to the LLM context. A high flakiness index raises the prior for a `flaky` label; a high `change_independence` score raises it further.

### Reasoning trace

The LLM is prompted to produce a step-by-step reasoning trace before committing to a classification. The trace is captured verbatim and included in `report.md`.

---

## Automated Remediation

Remediation is only attempted when a label's confidence score exceeds `--confidence-threshold` (default: `0.8`).

| Label | Remediation action |
|---|---|
| `charm-bug` (≥ threshold) | LLM generates a unified diff; written to `glitch-analysis/fix.patch` |
| `test-bug` (≥ threshold) | LLM generates a unified diff; written to `glitch-analysis/fix.patch` |
| `charm-bug` / `test-bug` (< threshold) | Fix suggested in `report.md` but no patch written |
| `flaky` | Retry policy, ordering guard, or isolation change suggested in `report.md` |
| `infrastructure` | Pre-filled GitHub issue template written to `report.md` |
| `environment` | Pre-filled GitHub issue template written to `report.md` |
| `unknown` | No remediation; narrative explains what signal is missing |

### Patch generation

The LLM is prompted to produce a **unified diff** (`diff -u` format). `glitch analyze` writes it to `fix.patch` and prints instructions for the developer to review and apply:

```
Patch written to glitch-analysis/fix.patch
To apply: git apply glitch-analysis/fix.patch
To review: git diff --stat
```

`glitch analyze` does not commit, branch, or push. Human review and approval are required before any change lands.

---

## Known-Patterns Store

After each analysis, resolved patterns are appended to `~/.local/share/glitch/patterns.json`. Phase 1 reads this file on its next run to adjust heuristic scores for known failure signatures.

### Schema

```json
{
  "patterns": [
    {
      "id": "uuid",
      "recorded_at": "2026-05-13T10:00:00Z",
      "repo": "canonical/my-charm",
      "test_id": "integration (test_deploy_local)",
      "labels": { "charm-bug": 0.91 },
      "summary": "Hook failed due to missing relation data on first install",
      "resolution": "patch"
    }
  ]
}
```

---

## Output Formats

All outputs are written to `--output-dir` (default: `./glitch-analysis/`).

### `verdict.json`

Machine-readable classification result. Consumed by Phase 1 to update the known-patterns store and by downstream tooling.

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
      "labels": {
        "charm-bug": 0.91,
        "flaky": 0.12
      },
      "remediation": {
        "action": "patch",
        "patch_file": "fix.patch"
      }
    }
  ]
}
```

### `report.md`

Human and LLM-readable narrative. Contents:

- **Executive summary**: top label and confidence per test, remediation action taken
- **Reasoning trace**: verbatim LLM reasoning steps leading to classification
- **Evidence**: key log excerpts and telemetry snippets cited in the reasoning
- **Charm-bug cases**: Mermaid hook-sequence diagram illustrating the failure path
- **Suggested fixes**: patch instructions or remediation suggestions below threshold
- **Issue templates**: pre-filled GitHub issue markdown for `infrastructure` / `environment` cases
- **Feedback**: what was written to the known-patterns store

### `fix.patch`

Written only when a `charm-bug` or `test-bug` classification exceeds `--confidence-threshold`. Standard unified diff format, applicable with `git apply`.

---

## Error Handling

| Condition | Behaviour |
|---|---|
| `--artifact-dir` missing or no `manifest.json` | Exit code 1 with clear message |
| Copilot auth fails | Exit code 1 with instructions for `GITHUB_TOKEN` or `gh auth login` |
| `--discovery-json` not found | Warn to stderr, continue without Phase 1 enrichment |
| LLM returns malformed output | Retry once; on second failure classify as `unknown` with error noted in report |
| Patch fails to generate | Record in `verdict.json`; include suggested fix as prose in `report.md` |

---

## Out of Scope (Phase 3 v1)

- Automatic GitHub issue filing (pre-filled template in `report.md` instead)
- Automatic branch creation or PR opening
- Re-running tests after patch application
- Multi-failure batch analysis in a single invocation
- Non-Copilot LLM providers

---

## Relationship to Other Phases

- **Phase 1** (Discovery): `verdict.json` is written to the known-patterns store, which Phase 1 reads on its next run to improve flakiness heuristics. Phase 1 JSON output optionally enriches classification confidence via `--discovery-json`.
- **Phase 2** (Collection): the artifact bundle produced by `glitch collect` is the primary input to `glitch analyze` via `--artifact-dir`.
