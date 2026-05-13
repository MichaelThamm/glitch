# ADR 0002: Local cache layer

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

The spec mandates a read-through local cache at `~/.cache/glitch/`, keyed by
`{owner}_{repo}_{run_id}.json`, with completed runs cached indefinitely and
in-progress runs cached for one hour. It does not pin the cache *implementation*
(library vs raw files), the on-disk *format* (envelope vs raw API JSON), or
which adjacent endpoints (commits, run-list pages) also get cached.

We need each of those decisions before writing the client wrapper.

## Decision

A plain JSON-file cache on the local filesystem. No external cache library.

- **Backing store**: one file per cache entry under `<cache_dir>/`. Writes are
  atomic — write to `*.tmp`, then `os.replace` — so a crash mid-write cannot
  leave a half-written entry.
- **Cache keys**, extending the spec's `{owner}_{repo}_{run_id}.json`:

  | Filename pattern | Contents | TTL |
  |---|---|---|
  | `run_{owner}_{repo}_{run_id}.json` | single run metadata | `null` if `status=completed`, else `3600` |
  | `jobs_{owner}_{repo}_{run_id}.json` | jobs for a run | `null` if all jobs `completed`, else `3600` |
  | `commit_{owner}_{repo}_{sha}.json` | commit metadata | `null` (immutable) |
  | `runs_{owner}_{repo}_{branch}_{since_iso}.json` | run-list page | `300` (5 minutes) |
- **On-disk format — envelope**:

  ```json
  {
    "fetched_at": "2026-05-13T10:00:00Z",
    "ttl_seconds": null,
    "kind": "run" | "jobs" | "commit" | "runs",
    "data": <raw API response>
  }
  ```
  `ttl_seconds = null` is immutable; otherwise the entry is treated as a miss
  if `now - fetched_at > ttl_seconds`.
- **Read path**: cache reads validate the `kind` field matches what was
  requested (cheap sanity check) and check the TTL before returning the inner
  `data`.

## Alternatives considered

- **`requests-cache` / `hishel`** — neither models content-aware TTL (TTL that
  depends on the response body's `status` field) without bolting on hooks.
- **SQLite cache** — overkill for blob storage; harder to inspect with `jq`
  during debugging.
- **Raw API JSON without an envelope** — would force using file mtime as
  `fetched_at`, conflating filesystem state with cache metadata. The spec's
  prose says "raw API response JSON per run"; we depart from this
  intentionally so cache metadata travels with the data.
- **Cache eviction (LRU / size cap)** in Phase 1 — punted. A `--clear-cache`
  flag may arrive in a follow-up if the cache footprint becomes a problem.

## Consequences

- Positive: zero dependencies; cache files are inspectable by hand; tests
  can drop pre-baked envelope JSON into a `tmp_path` cache dir and exercise
  the read path without touching the network.
- Negative: we own the TTL and atomic-write logic; cache is unbounded.
- Follow-ups: schema version field in the envelope if we ever change the
  envelope shape; eviction strategy if disk usage becomes a problem.
  Related: [[0001-github-api-client]] (the cache wraps the client),
  [[0008-testing-approach]] (tests use a temp cache_dir).
