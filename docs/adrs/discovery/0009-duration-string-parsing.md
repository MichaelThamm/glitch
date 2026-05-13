# ADR 0009: Duration string parsing

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

The `--since` flag accepts strings like `30d`, `2w`. The spec uses these in
examples (`30d`, `2w`) but does not define a grammar, an error mode, or
which library (if any) handles the parsing.

## Decision

A small custom regex-based parser. No external dependency.

- **Grammar**: one non-negative integer followed by exactly one unit suffix.
  ```
  duration := <digits><unit>
  unit     := 'h' | 'd' | 'w'    (hours / days / weeks)
  ```
- **Accepted**: `1h`, `12h`, `30d`, `2w`, `0d`.
- **Rejected**: `1.5d`, `30 d`, `1d2h`, `30`, `30days`, `1m`, `1M`,
  anything negative.
- **Function**:
  ```python
  def parse_duration(s: str) -> timedelta: ...
  ```
- **Error behaviour**: raises `ValueError("invalid duration: {s!r}. Expected
  <N><h|d|w>")`. The Typer entrypoint catches this and exits with code 1
  (the spec's "User error" exit code).
- `0d` is accepted — it is not itself an error. The spec's "All tests below
  minimum threshold" branch will trigger as a warning + exit 0.

Implementation will live in `glitch/discover/_duration.py` per
[[0007-module-layout]]. Reference shape:

```python
_UNIT_SECONDS = {"h": 3600, "d": 86400, "w": 7 * 86400}
_RE = re.compile(r"^(?P<n>\d+)(?P<u>[hdw])$")

def parse_duration(s: str) -> timedelta:
    m = _RE.match(s)
    if not m:
        raise ValueError(f"invalid duration: {s!r}. Expected <N><h|d|w>")
    return timedelta(seconds=int(m["n"]) * _UNIT_SECONDS[m["u"]])
```

## Alternatives considered

- **`pytimeparse`** — supports richer grammars (`1d 2h 30m`) we don't want
  to expose. Restricting it via a wrapper is more code than the regex.
- **`humanfriendly`** — too large for one use.
- **Add `m` (minutes)** — finer-grained than CI history needs; the
  shortest useful lookback is on the order of hours.
- **Add `M` (months)** — ambiguous (28/30/31 days). Users wanting "a
  month" can write `30d` or `4w`.
- **Support compound durations** (`1d2h`) — unnecessary; CI lookback
  windows are coarse.

## Consequences

- Positive: zero dependencies; ~10 LoC; grammar is fully documented in
  this ADR. Easy to extend later.
- Negative: any future user expecting `30 days` to work will get a
  `ValueError`. The error message tells them the expected form.
- Follow-ups: revisit if compound or finer-grained durations become a
  common ask.
