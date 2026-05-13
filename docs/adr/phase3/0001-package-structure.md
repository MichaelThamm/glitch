# 0001 — Phase 3 Package Structure

**Status**: proposed  
**Date**: 2026-05-13  
**Traces to**: [VISION.md — Phase 3](../../VISION.md), [phase-3-analysis.md](../../specs/phase-3-analysis.md)

---

## Context and Problem

The current `src/glitch/analyze.py` is a single-file stub (lines 1-52) that raises `NotImplementedError`. Phase 3 requires significant logic: Copilot SDK integration, LLM classification, remediation, output generation, and a patterns store. A single file will become unwieldy.

The theow project uses an internal `_gateway/` package pattern with private modules (`_copilot.py`, `_base.py`) and a factory `__init__.py`. Glitch should follow this pattern but simpler — less abstraction, more direct implementation.

`github-copilot-sdk` (>=0.1.30) must be added as a **required** dependency to `pyproject.toml`.

## Decision

Convert `src/glitch/analyze.py` into a package at `src/glitch/analyze/` with the following layout:

```
src/glitch/analyze/
├── __init__.py          # Re-exports run() to maintain CLI contract
├── _run.py              # Main orchestration entry point
├── _copilot.py          # CopilotClient wrapper (persistent loop, session lifecycle)
├── _auth.py             # Auth resolution (GITHUB_TOKEN → gh auth token)
├── _loader.py           # Artifact bundle loading (manifest.json, collector outputs)
├── _classify.py         # LLM classification prompt + response parsing
├── _remediate.py        # Patch generation, suggestion templates
├── _output.py           # Write verdict.json, report.md, fix.patch
└── _patterns.py         # Known-patterns store read/write
```

### Why this structure

1. **`__init__.py`** — preserves the existing `run()` function signature. `cli.py` imports `from glitch.analyze import run` — that import path must not break.
2. **`_run.py`** — orchestrates the full pipeline. Each step calls into a dedicated module.
3. **Private modules** (`_` prefix) — follows theow convention. Consumers import only through `__init__.py`.
4. **One concern per module** — agents cannot break other concerns while working on their ADR.

## Consequences

### Files to create

| File | From |
|---|---|
| `src/glitch/analyze/__init__.py` | Repurpose existing `analyze.py` content |
| `src/glitch/analyze/_run.py` | New |
| `src/glitch/analyze/_copilot.py` | New |
| `src/glitch/analyze/_auth.py` | New |
| `src/glitch/analyze/_loader.py` | New |
| `src/glitch/analyze/_classify.py` | New |
| `src/glitch/analyze/_remediate.py` | New |
| `src/glitch/analyze/_output.py` | New |
| `src/glitch/analyze/_patterns.py` | New |

### Files to delete

| File | Reason |
|---|---|
| `src/glitch/analyze.py` | Replaced by package |

### Files to modify

| File | Change |
|---|---|
| `pyproject.toml` | Add `github-copilot-sdk>=0.1.30` to `[project] dependencies` |
| `tests/test_cli.py` | Import path unchanged (`from glitch.analyze import run`), so no change needed IF `__init__.py` re-exports correctly |

### Acceptance criteria

1. `glitch analyze --help` still works and shows the same 5 options
2. Running `glitch analyze --artifact-dir /tmp` errors with a clear message (no longer a `NotImplementedError` from a stub return)
3. `python -m glitch analyze --help` works identically
4. Existing smoke tests in `tests/test_cli.py` pass unchanged
