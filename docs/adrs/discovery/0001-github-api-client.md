# ADR 0001: GitHub API client

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

`glitch discover` is built on the GitHub REST API. The spec
(`docs/specs/phase-1-discovery.md`) fixes the endpoints called, the auth
resolution order (`GITHUB_TOKEN` → `gh auth token` → exit 1), and that the
client must respect `X-RateLimit-Remaining`. It does **not** pin the HTTP
library, the retry strategy, or the rate-limit guard threshold.

## Decision

Use **`requests`** as the HTTP client and **`tenacity`** as the retry library.

- One `requests.Session` per `discover` invocation, with default headers set
  once on the session:
  - `Authorization: Bearer <token>`
  - `Accept: application/vnd.github+json`
  - `X-GitHub-Api-Version: 2022-11-28`
- `base URL`: `https://api.github.com`. A small helper wraps
  `session.get(url, timeout=60, ...)` so the timeout is applied uniformly.
- Pagination: walk the `Link` header looking for `rel="next"`. Always request
  `per_page=100` (the GitHub maximum) to minimise round-trips.
- Retry policy (via `tenacity`):
  - Retry on `requests.exceptions.ConnectionError`,
    `requests.exceptions.Timeout`, and any response with HTTP status `>= 500`.
  - `stop_after_attempt(3)` total attempts.
  - `wait_exponential(multiplier=1, min=1, max=8)` — backoffs roughly 1 s,
    2 s, 4 s.
  - 4xx responses are **not** retried; they propagate as fatal errors.
- Rate-limit guard: before issuing a request, if the most recently observed
  `X-RateLimit-Remaining` is `< 10`, sleep until `X-RateLimit-Reset + 1s` and
  log the wait time to stderr. The threshold is 10 (not 1) to leave headroom
  for the concurrent fan-out described in [[0004-concurrency-model]].
- Per-request timeout: **60 seconds**. GitHub's median response is well under
  a second; 60 s catches genuinely stuck connections while tolerating slow
  large-page responses.

## Alternatives considered

- **`httpx` (sync)** — modern and typed, and would have unlocked an async
  path later, but `requests` is more ubiquitous in the Python ecosystem and
  the team is comfortable with it; no concrete need today for async.
- **stdlib `urllib`** — too low-level for paginated, authenticated REST.
  Every feature would be hand-rolled.
- **Hand-rolled retry loop** — works but `tenacity` is the de facto standard;
  using it costs one dependency and avoids reinventing decorator-driven
  backoff/jitter, which we'll want eventually.

## Consequences

- Positive: two well-known, widely-deployed dependencies; retry behaviour is
  declarative (a single `@retry(...)` decorator) and easy to reason about.
- Negative: `requests` is synchronous-only; if a future phase wants async I/O
  we'd revisit. `tenacity` adds a dep for a feature we could have inlined,
  but the readability win is worth it.
- Follow-ups: revisit if rate limits become a bottleneck — we may need
  conditional requests (`If-None-Match` / `ETag`) before going wider. See
  also [[0002-local-cache-layer]] (the cache is layered above this client),
  [[0004-concurrency-model]] (fan-out uses a threadpool over this client),
  and [[0008-testing-approach]] (HTTP mocking will use the `responses`
  library because it pairs with `requests`).
