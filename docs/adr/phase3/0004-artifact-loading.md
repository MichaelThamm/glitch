# 0004 — Artifact Loading

**Status**: proposed  
**Date**: 2026-05-13  
**Depends on**: [0001](0001-package-structure.md)  
**Traces to**: [phase-3-analysis.md — Inputs](../../specs/phase-3-analysis.md#inputs)

---

## Context and Problem

Phase 3 must read the Phase 2 artifact bundle provided via `--artifact-dir`. The bundle contains a `manifest.json` and per-collector subdirectories (`juju/`, `k8s/`, `lxd/`, `ceph/`, `test-artifacts/`). Phase 2 is not yet implemented, so the schema must be loose — fail gracefully on missing or unexpected content rather than requiring a rigid schema.

Phase 3 also optionally reads Phase 1 JSON via `--discovery-json` to enrich classification.

## Decision

Implement `src/glitch/analyze/_loader.py` with a single `load_context()` function that returns a dataclass:

```python
@dataclass
class AnalysisContext:
    artifact_dir: Path
    manifest: dict[str, Any]                    # parsed manifest.json
    collector_paths: dict[str, Path | None]      # collector dir path or None if missing
    discovery: dict[str, Any] | None             # parsed Phase 1 JSON or None
```

### Loading logic

```python
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

COLLECTORS = ("juju", "k8s", "lxd", "ceph", "test-artifacts")

def load_context(
    artifact_dir: Path,
    discovery_json: Path | None = None,
) -> AnalysisContext:
    # 1. Validate manifest.json exists
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"No manifest.json found in {artifact_dir}. "
            f"This does not look like a Phase 2 artifact bundle."
        )

    # 2. Parse manifest.json (no schema validation — keep it loose)
    manifest = json.loads(manifest_path.read_text())

    # 3. Resolve collector paths (None if missing)
    collector_paths: dict[str, Path | None] = {}
    for name in COLLECTORS:
        path = artifact_dir / name
        collector_paths[name] = path if path.is_dir() else None

    # 4. Load optional Phase 1 JSON
    discovery: dict[str, Any] | None = None
    if discovery_json:
        if not discovery_json.is_file():
            # Warn but continue (per spec error handling)
            import sys
            print(f"Warning: --discovery-json not found at {discovery_json}", file=sys.stderr)
        else:
            discovery = json.loads(discovery_json.read_text())

    return AnalysisContext(
        artifact_dir=artifact_dir,
        manifest=manifest,
        collector_paths=collector_paths,
        discovery=discovery,
    )
```

### File reading helper

Collector output is plain text, log files, or JSON. Provide a helper to read collector content for LLM context assembly:

```python
def read_collector_content(ctx: AnalysisContext) -> dict[str, str]:
    """Return collector_name → concatenated text content for all present collectors."""
    ...
```

## Consequences

### Files

| Action | File |
|---|---|
| Create | `src/glitch/analyze/_loader.py` |

### Acceptance criteria

1. `load_context(valid_dir)` with a `manifest.json` succeeds and returns `AnalysisContext` with `manifest` populated
2. `load_context(missing_dir)` raises `FileNotFoundError` with a clear message mentioning "Phase 2 artifact bundle"
3. Missing collector directories result in `None` in `collector_paths` — no error raised
4. Missing `--discovery-json` prints a warning to stderr, continues with `discovery=None`
5. `manifest.json` that is not valid JSON raises a clear `json.JSONDecodeError`
