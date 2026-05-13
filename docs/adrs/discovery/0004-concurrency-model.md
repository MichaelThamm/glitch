# ADR 0004: Concurrency model

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

For a 30-day window, a busy charm repo may have 100–300 workflow runs. Each
run requires a `GET /runs/{run_id}/jobs` call to enumerate jobs, and the
change-independence heuristic requires a `GET /commits/{sha}` per unique SHA.
Sequentially this is ~250 ms × N — minutes for a busy repo on a cold cache.

[[0001-github-api-client]] locked the HTTP client to `requests` (sync), so
`asyncio` is not an option without a library swap. The choice narrows to
sequential vs threadpool.

## Decision

Fan-out fetches run on a **`concurrent.futures.ThreadPoolExecutor` with
`max_workers=8`**, layered above the sync `requests.Session`.

- A single `requests.Session` instance is shared across worker threads.
  `requests.Session` is thread-safe for concurrent reads of independent URLs;
  the only thread-safety caveat is mutating session state (headers, cookies)
  from multiple threads, which we don't do.
- Pagination *within* a single endpoint (e.g. walking pages of
  `/actions/runs`) stays sequential. Only the outer fan-out is parallelised:
  - jobs-per-run: one `GET /runs/{id}/jobs` per workflow run
  - commits-per-sha: one `GET /commits/{sha}` per unique commit SHA observed
    across runs
- Rate-limit shared state (`remaining`, `reset_at`) lives behind a
  `threading.Lock`. Each thread, before issuing, takes the lock, checks
  `remaining < 10`, and sleeps if needed.
- `max_workers=8` is a module-level constant for Phase 1. Not exposed as a
  flag — adding one would invite tuning without a clear knob to tune against.

## Alternatives considered

- **Strictly sequential** — simplest; rejected because cold-cache discovery
  on a busy repo is too slow for the "fast, local" promise in the spec.
- **`asyncio` + `httpx.AsyncClient`** — requires swapping out `requests` and
  colouring the call chain `async`. Not worth it for an 8-way fan-out.
- **`multiprocessing`** — overkill for I/O-bound work; pickling constraints
  on what crosses process boundaries.
- **Per-thread `requests.Session`** — also fine but slightly more code; the
  shared-session approach is documented as safe.

## Consequences

- Positive: ~6–7× faster cold-cache runs (back-of-envelope: ~1 min →
  ~10–15 s on a 200-run window); no async colouring of unrelated code.
- Negative: a small amount of locking discipline around the rate-limit
  shared state; bug surface if anyone ever mutates the shared session.
- Follow-ups: if a much higher fan-out is ever needed (>50×), revisit with
  async. Related: [[0001-github-api-client]] (the threadpool calls this
  client's helpers) and [[0008-testing-approach]] (tests typically run
  serially with a mocked transport, so concurrency does not complicate
  testing meaningfully).
