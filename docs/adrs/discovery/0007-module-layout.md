# ADR 0007: Module layout of `glitch.discover`

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

The current code has a single module `src/glitch/discover.py` containing only
the Typer entrypoint with a `NotImplementedError`. The implementation will
add roughly five concerns: HTTP client + auth, local cache, domain models,
scoring, output rendering — each with its own ADR. We need to decide whether
they live in one file or as a subpackage of separate modules.

## Decision

Convert `glitch.discover` from a single module to a **subpackage** with
one file per concern.

```
src/glitch/discover/
├── __init__.py        # re-exports `run` (preserves `glitch.cli` wiring)
├── _entrypoint.py     # Typer `run()` (orchestration only)
├── client.py          # GitHub API client + auth (ADR-0001)
├── cache.py           # local cache layer    (ADR-0002)
├── models.py          # frozen dataclasses   (ADR-0003)
├── scoring.py         # heuristics + recency (ADR-0005, ADR-0006)
├── render.py          # rich table + JSON output
└── _duration.py       # duration string parser (ADR-0009)
```

- `__init__.py` does `from ._entrypoint import run` (and nothing else), so
  `glitch.cli`'s existing line
  `app.command("discover", help=...)(discover.run)` continues to work
  without change.
- Underscore-prefixed modules (`_entrypoint`, `_duration`) signal "internal,
  not a public surface". The rest are un-prefixed because they're the
  natural review/navigation units.
- Tests mirror the structure: `tests/test_discover_<module>.py`. One test
  file per module, plus a top-level end-to-end test
  `tests/test_discover_e2e.py` that drives `glitch discover` against a
  mocked HTTP transport.

## Alternatives considered

- **Single `discover.py`** — fine while small but quickly hides structure;
  reviewing one ADR's implementation would mean grepping a long file.
- **`run()` inside `__init__.py`** — works but mixes orchestration with
  package re-exports; a pure re-export `__init__.py` is easier to read.
- **No underscore prefixes** — minor style choice; underscores make it
  obvious which modules are wiring vs domain logic.

## Consequences

- Positive: each ADR maps to a single file; review-against-ADR is a single
  diff; tests can be narrow.
- Negative: more files; a one-off contributor has to learn the layout
  first.
- Follow-ups: if `models.py` ever crosses ~250 LoC, split into
  `models/api.py` + `models/scoring.py` (mentioned in
  [[0003-domain-model-representation]]). Related:
  [[0008-testing-approach]] (test files mirror this layout).
