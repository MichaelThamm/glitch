# 0008 — Patterns Store

**Status**: proposed  
**Date**: 2026-05-13  
**Depends on**: [0005](0005-llm-classification.md)  
**Traces to**: [phase-3-analysis.md — Known-Patterns Store](../../specs/phase-3-analysis.md#known-patterns-store)

---

## Context and Problem

After analysis completes, resolved patterns must be persisted so Phase 1 can read them on its next run to adjust heuristic scores. The store lives at `~/.local/share/glitch/patterns.json`.

Phase 3 must **both read and write** to this store:
- **Write**: append resolved patterns after each analysis
- **Read**: check existing patterns to avoid duplicates, potentially use past patterns to inform classification (future enhancement)

The schema is defined in the spec. Each entry has: `id` (UUID), `recorded_at` (ISO 8601), `repo`, `test_id`, `labels`, `summary`, `resolution`.

## Decision

Implement `src/glitch/analyze/_patterns.py` with:

1. **`PatternsStore` class** — manages read/write to the JSON file
2. **`load_patterns()`** — reads and validates the store
3. **`append_patterns()`** — appends new entries, avoids duplicates
4. **`PatternEntry` dataclass** — typed representation of a pattern

### Store location

Use `platformdirs` (already a transitive dep via `rich`/`typer`?) or implement manually:

```python
import os
from pathlib import Path

def _patterns_path() -> Path:
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    store_dir = Path(xdg_data) / "glitch"
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir / "patterns.json"
```

### Schema (per spec)

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from uuid import uuid4

@dataclass
class PatternEntry:
    id: str
    recorded_at: str
    repo: str
    test_id: str
    labels: dict[str, float]
    summary: str
    resolution: str   # "patch", "suggestion", "issue_template", "narrative"

class PatternsStore:
    def __init__(self) -> None:
        self._path = _patterns_path()

    def read(self) -> list[dict]:
        """Return all existing patterns (empty list if file doesn't exist)."""
        ...

    def append(self, entries: list[PatternEntry]) -> None:
        """Append entries, skipping duplicates (same test_id + repo)."""
        ...
```

### Deduplication

Before appending, check if an entry with the same `test_id` and `repo` already exists to avoid ballooning the store. The newest entry replaces the old one (upsert, not skip):

```python
def _upsert(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    key = lambda e: (e["repo"], e["test_id"])
    index = {key(e): i for i, e in enumerate(existing)}
    for entry in new_entries:
        k = key(entry)
        if k in index:
            existing[index[k]] = entry   # replace
        else:
            existing.append(entry)
    return existing
```

### Building entries from classification results

```python
def verdicts_to_entries(
    verdicts: list[ClassificationVerdict],
    repo: str,
    remediation: RemediationPlan,
) -> list[PatternEntry]:
    entries = []
    for verdict in verdicts:
        entry = PatternEntry(
            id=str(uuid4()),
            recorded_at=datetime.now(timezone.utc).isoformat(),
            repo=repo,
            test_id=verdict.test_id,
            labels=verdict.labels,
            summary=verdict.reasoning_trace[:500],
            resolution=_resolution_from_plan(remediation, verdict.test_id),
        )
        entries.append(entry)
    return entries
```

### Integration in `_run.py`

```python
# After classification and remediation
store = PatternsStore()
existing = store.read()
new_entries = verdicts_to_entries(result.verdicts, repo, remediation)
updated = _upsert(existing, [asdict(e) for e in new_entries])
store.write(updated)
```

## Consequences

### Files

| Action | File |
|---|---|
| Create | `src/glitch/analyze/_patterns.py` |

### New dependency?

`platformdirs` would be ideal but adds a dependency. The `Path.home() / ".local" / "share"` pattern with `XDG_DATA_HOME` env var support is sufficient and requires no new dependency.

### Acceptance criteria

1. `PatternsStore().read()` returns `[]` when `patterns.json` doesn't exist
2. `PatternsStore().append(entries)` creates the file with entries on first write
3. Appending duplicate `(repo, test_id)` replaces the old entry (upsert)
4. Store location respects `XDG_DATA_HOME` env var
5. Each entry includes all required fields: `id`, `recorded_at`, `repo`, `test_id`, `labels`, `summary`, `resolution`
6. `id` is a valid UUID string
7. `recorded_at` is ISO 8601 with timezone
