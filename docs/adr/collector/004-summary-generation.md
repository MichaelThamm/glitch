# ADR-004: Summary Generation

**Status**: Accepted  
**Phase**: 2 (Collection)  
**Date**: 2026-05-13

## Context

`summary.md` is a rule-based Markdown document that accompanies the artifact bundle. It provides a human- and LLM-readable narrative of the collected state without requiring an LLM to generate it. The spec defines five sections:

1. Collection summary (which collectors ran/skipped)
2. Juju model overview (application/unit status table)
3. Recent Juju log excerpts (last 50 lines, filtered to ERROR/WARNING)
4. K8s anomalies (warning events, pods with non-zero restarts)
5. Test result summary (pass/fail counts from JUnit XML)

## Decision

We will use a **programmatic Markdown builder utility** inspired by Rich's table API, built atop raw string manipulation. No template engine dependency.

### Approach

A `SummaryBuilder` class in `src/glitch/collectors/summary.py` accumulates sections and renders them to Markdown:

```python
class SummaryBuilder:
    def __init__(self, manifest: Manifest) -> None: ...
    def add_section(self, heading: str, content: str) -> None: ...
    def add_table(self, heading: str, headers: list[str], rows: list[list[str]]) -> None: ...
    def add_code_block(self, content: str, language: str = "") -> None: ...
    def render(self) -> str: ...
    def write(self, path: Path) -> None: ...
```

### Why not Jinja2?

- Template engines introduce an indirection layer between data and output
- The summary is generated from structured data (Pydantic models, parsed JSON) — not freeform text
- Rich is already a dependency; the builder mirrors its `Table`/`Panel` API conventions
- No template file to maintain alongside the code

### Section generation order

1. Top-level heading + collection timestamp
2. Collector status table (from `manifest.json`)
3. Per-collector sections, generated only if that collector ran successfully:
   - Juju: status table + debug-log excerpt
   - K8s: warning events list + pod anomaly table
   - LXD/Ceph: status summary
   - Test artifacts: pass/fail counts

## Consequences

- **Positive**: Simple, testable — each section builder is a function that takes a Pydantic/dict input and returns a string.
- **Positive**: No new dependencies. Rich is already installed.
- **Positive**: Sections are independently testable; no template rendering to mock.
- **Negative**: Adding a new section requires Python code changes rather than template editing — but the sections are well-defined per spec and unlikely to change frequently.

## Alternatives Considered

- **Jinja2 template**: Adds a dependency, requires template file management, and separates logic from presentation in a way that doesn't benefit this use case (the summary is highly structured, not freeform).
- **Pure f-string building in a single function**: Would work for Phase 2 but becomes a long, untestable function as sections grow. The builder pattern keeps each section independently testable.
