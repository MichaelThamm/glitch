# ADR 0003: Domain model representation

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

Phase 1 manipulates several internal data shapes: GitHub API objects (`Run`,
`Job`, `Commit`), per-test aggregates (a list of `(run, job)` pairs grouped
by `job.name`), per-heuristic raw values, normalised heuristic scores, and
the final JSON-output payload. We need a single representation strategy so
that types flow consistently through `client → cache → scoring → render`.

The spec does not constrain the in-memory representation.

## Decision

Use **frozen `@dataclass(slots=True, frozen=True)`** for every internal type.
No Pydantic. No `TypedDict`. No hand-rolled classes.

- All domain types live in a single file, `glitch/discover/models.py`.
- Parsing from raw API JSON is centralised: each dataclass exposes a
  `from_api(payload: dict) -> Self` classmethod (or, where shape-massaging is
  more procedural, a `parse_*` module-level function). The rest of the code
  only ever sees typed instances — no `dict[str, Any]` floats past the
  parsing layer.
- The final JSON-output payload is itself a dataclass. Serialisation:
  `dataclasses.asdict()` + `json.dumps(..., default=_isoformat)`, where the
  encoder turns `datetime` into ISO-8601 strings (Z-suffix UTC).
- A `datetime` is always timezone-aware UTC inside the program; ISO-8601
  strings are the wire/cache format only.

## Alternatives considered

- **Pydantic v2** — gives validation at boundaries and free JSON
  (de)serialisation. Rejected because we trust GitHub's response shape (it's
  internal API, not untrusted user input), and Pydantic is a heavyweight
  dependency to add for ergonomics we don't strictly need.
- **`TypedDict`** — static typing without runtime guarantees and without
  immutability. Code that passes dicts around tends to drift.
- **Plain classes** — more boilerplate than dataclasses for the same outcome.
- **Splitting into `models/api.py` + `models/scoring.py`** — premature; the
  type set is small enough to live in one file. We split if it crosses
  ~250 LoC.

## Consequences

- Positive: zero new dependencies; immutability prevents accidental mutation
  of cached or shared instances; `slots=True` keeps memory bounded for large
  run sets; the parsing layer is one obvious place to look when API shape
  changes.
- Negative: parse errors surface as `KeyError` / `TypeError` rather than
  pretty validation messages — acceptable since parse failures are bugs, not
  user-input errors, and they're confined to one module.
- Follow-ups: if Phase 3 needs validated I/O at module boundaries, revisit
  with Pydantic. Linked to [[0007-module-layout]] (this file lives in the
  subpackage).
