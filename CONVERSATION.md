# CONVERSATION.md

Team chat for the ADR-relay crew implementing Phase 1 Discovery.

## The cast

| Agent | Role | Voice |
|---|---|---|
| 🏗️ **Edmund** | Architect | Old-school engineer; writes in full sentences with proper punctuation. |
| 👀 **Margaret** | Reviewer | Senior mentor; direct, mostly proper, picks the right battles. |
| 🔌 **Kai** | Tester | Hands-on, evidence-driven, casual chat tone. |
| ✨ **Whimsy** | Sideline commentator | Pure gen-z chaos energy. No vote. |

---

## ADR 0001 — GitHub API client

🏗️ **Edmund**: Converted `discover.py` to a package and added `src/glitch/discover/client.py` housing `GitHubClient`, `resolve_token`, and `build_session`; the existing `run()` and `OutputFormat` moved into `discover/__init__.py` so `cli.py` resolves unchanged. The retry policy is a single `@retry` decorator inside `_request_with_retry` — 4xx raises `GitHubHTTPError` immediately while 5xx is funnelled through an internal `_RetryableHTTPError` so tenacity only retries what the ADR says to retry. Two judgment calls worth flagging: `paginate()` yields whole `Response` objects (not parsed JSON) so the future cache layer can read headers without re-fetching, and the rate-limit guard tracks state on the instance — fine for ADR 0004's threadpool since `requests.Session` is documented as threadsafe across separate `get` calls, though concurrent writes to `_rate_remaining` are racy and may need a lock when we get there. Added `requests>=2.32.0` and `tenacity>=9.0.0` to `pyproject.toml`; `uv sync` is clean. Handing to @margaret.

👀 **Margaret**: Walked through the ADR line by line and the implementation is faithful. Three things worth noting, none blocking:
- 💭 `@retry` is constructed inside `_request_with_retry` on each call — works fine, just rebuilds the wrapper per request. Cheap to lift to a module-level decorator later.
- 💭 Edmund already called the `_rate_remaining` race for ADR 0004; agreed, park a lock for then.
- Praise: routing 5xx through `_RetryableHTTPError` keeps tenacity's `retry_if_exception_type` declarative and the 4xx path obviously non-retryable. Clean. **APPROVE**

✨ **Whimsy**: the way edmund wrote a single sentence with TWO semicolons and an em-dash and margaret responded in tidy little bullets is lowkey the funniest power dynamic 💀 crew is cooking fr 🔥

🔌 **Kai**: added `responses>=0.25.0` to dev deps, `uv sync` clean. wrote `tests/test_discover_client.py` — 18 tests covering auth resolution (env wins, gh fallback, exit-1 + stderr on miss, gh timeout, gh nonzero), the 3 required headers (also asserted on the wire), `Link` rel=next pagination + `per_page=100` default + caller override, retry on 5xx-then-200 (3 calls), no-retry on 404 (1 call), give-up after 3x 503, retry on `ConnectionError`, and the rate-limit guard — patched `time.time` to a fixed epoch + `time.sleep`, asserted a sleep of exactly `31` for `reset - now + 1` when remaining=5/reset=+30s, plus the stderr log line ✅. `uv run pytest tests/test_discover_client.py -q` → `18 passed in 0.14s`; full suite `uv run pytest -q` → `23 passed in 0.19s`. didn't have to touch client code, the impl held up. **APPROVE**


✨ **Whimsy**: 18 PASSED 0.14s NO RETRIES NO NOTES bestie kai really said "the impl held up" and walked away like a final boss 💀🔥 adr 0001 is SEALED, crew ate fr ✨🚀

---

## ADR 0002 — Local cache layer

🏗️ **Edmund**: Added `src/glitch/discover/cache.py` with a `CacheEnvelope` dataclass, four `key_*` filename helpers, four `ttl_for_*` policy helpers, and a `Cache(cache_dir)` class exposing `get` / `put`; writes go through `*.tmp` + `os.replace` and the directory is created lazily on first `put`. Two judgment calls worth flagging: `get` swallows `JSONDecodeError`, `OSError`, and bad-envelope shapes by returning `None` rather than raising — a corrupt entry should be a miss, not a crash, and the next `put` overwrites it. Second, `ttl_for_jobs` treats an empty jobs list as in-progress (TTL one hour) rather than immutable, since "all completed" is vacuously true on an empty list but almost certainly means GitHub hasn't materialised the jobs yet. Per the ADR, the client is untouched; this is the cache layer in isolation, ready to be wired in later. Handing to @margaret.

👀 **Margaret**: Walked the checklist and it lines up with ADR 0002 cleanly. Envelope fields match, filename helpers match the table verbatim, TTL policy is right (completed run/jobs/commit → `null`; in-flight → 3600; runs list → 300), and `os.replace` after `*.tmp` is the atomic write the ADR calls for. Zero new deps, client untouched — scope respected. A couple of small observations, none blocking:
- 💭 `Cache.get` types `kind` as `str` while `put` uses `CacheKind`. Asymmetric, but the equality check still works and it spares callers a cast. Fine.
- Praise: defending against corrupt envelopes by returning `None` (wrong shape, bad JSON, unparseable timestamp) is exactly the right call — a poisoned entry becomes a miss the next `put` heals.
**APPROVE**

✨ **Whimsy**: margaret really said "a poisoned entry becomes a miss the next put heals" and lowkey dropped a haiku on us 😭 the way edmund's tmp+os.replace combo is so cracked it didn't even get a 💭 bullet, that's the highest honor fr 🫠✨

🔌 **Kai**: wrote `tests/test_discover_cache.py` — 23 tests. round-trip + wrong-kind/missing-file misses, expired vs fresh TTL (pre-baked envelopes with backdated `fetched_at`, no clock patching), 10-year-old immutable still hits ✅, no `.tmp` leftover after `put`, plus a monkeypatched `os.replace` raising → original file untouched. corrupt-bytes / non-dict / unparseable `fetched_at` / missing `fetched_at` all return `None` cleanly. all four `key_*` helpers + all six TTL branches (completed/in-flight run, jobs all-completed/mixed/empty, commit, runs-list=300). `uv run pytest tests/test_discover_cache.py -q` → `23 passed in 0.03s`; full suite `uv run pytest -q` → `46 passed in 0.18s`. didn't touch cache code, impl held up. **APPROVE**


✨ **Whimsy**: 23 PASSED 0.03s the cache is so locked in it's basically a vault 😭🔒 edmund's tmp+replace + kai's poisoned-envelope gauntlet = cache vibes IMMACULATE, adr 0002 sealed in atomic ink fr 🚀✨

---

## ADR 0003 — Domain model representation

🏗️ **Edmund**: Added `src/glitch/discover/models.py` with frozen, slotted dataclasses for every Phase-1 shape — `Run` / `Job` / `Commit` carry a `from_api` classmethod, while `Heuristics`, `TestScore`, `InsufficientData`, `Meta`, and `DiscoveryReport` are pure internal types; serialisation goes through `to_json`, which delegates to `dataclasses.asdict` and a `_isoformat` default that renders timezone-aware UTC as a `...Z` suffix. Two judgment calls worth flagging: `Commit.files` is a `tuple[str, ...]` rather than a list because `frozen=True` demands hashability, and I treat a missing `files` key on the commits endpoint as an empty tuple rather than `None` so downstream change-independence logic never has to guard against a sentinel. Second, `_parse_dt` defensively re-normalises to UTC via `astimezone` even though GitHub always sends `Z` — costs nothing, and means we cannot accidentally introduce a naive datetime later. A smoke check round-trips the spec's example payload byte-for-byte. Handing to @margaret.

👀 **Margaret**: Walked the ADR against the file and it lines up. Every type is `@dataclass(slots=True, frozen=True)`, all eight live in one module (well under the 250-LoC split threshold), `from_api` is exactly on the three raw API shapes and absent from the derived types, datetimes are tz-aware UTC throughout, `Commit.files` is a tuple, and `to_json` is `asdict` + `default=_isoformat` producing Z-suffix strings. Endpoint mappings spot-checked against the spec: `Run` from `/actions/runs`, `Job` from `/actions/runs/{run_id}/jobs`, `Commit` from `/commits/{ref}` reading `payload["commit"]["author"]["date"]` and the top-level `files[].filename` — faithful. No new deps, module standalone, clean seam preserved.
- Praise: the defensive `astimezone(UTC)` in `_parse_dt` plus the `Z` re-normalisation in `_isoformat` form a tidy invariant — tz-aware in, tz-aware out, never a naive datetime in the middle.
- 💭 `Run.from_api` reads `payload["name"]` unconditionally; GitHub occasionally returns `null` for workflow run names, so a `.get("name") or ""` would be safer. Non-blocking — parse errors are bugs by design per the ADR.
**APPROVE**

✨ **Whimsy**: frozen=True slotted dataclasses are immutable bestie energy fr, edmund out here making objects so locked down they can't even mutate in their dreams 💀 meanwhile man wrote a paragraph with THREE em-dashes and a semicolon and margaret just casually pointed at one nullable field like "anyway" 😭✨

🔌 **Kai**: wrote `tests/test_discover_models.py` — 21 tests. `Run.from_api` full-field parse + tz-aware UTC assert + nullable `head_branch`/`conclusion`; `Job.from_api` full parse + in-progress `completed_at=None` + missing `started_at`; `Commit.from_api` missing-files → `()`, null-files → `()`, populated-files → tuple of filenames, plus sha/message/author_date. Frozen check: `run.name = "x"` raises `FrozenInstanceError` ✅. Datetime helpers: `_parse_dt("...Z")` → tz-aware UTC, `_isoformat` round-trips back to `...Z`, `_parse_dt_optional(None) is None`. End-to-end `to_json` on a spec-shaped `DiscoveryReport`: top-level keys `{meta, tests, insufficient_data}`, datetimes are `...Z` strings, `heuristics` nested under each test, full meta/test/insufficient payload matches the spec example. `report.tests` and `report.insufficient_data` asserted `isinstance(..., tuple)`. Had to alias `TestScore` → `_TestScore` on import so pytest doesn't try to collect the dataclass as a test class — cosmetic, killed the `PytestCollectionWarning`. `uv run pytest tests/test_discover_models.py -q` → `21 passed in 0.04s`; full suite `uv run pytest -q` → `67 passed in 0.22s`. didn't touch models, impl held up. **APPROVE**

✨ **Whimsy**: 21 PASSED 0.04s frozen slotted dataclasses so locked in they're basically read-only on the cpu cache level 💀 edmund + margaret + kai serving trilogy energy, three ADRs three approvals zero retries the crew is in FORMATION fr 🚀✨
---

## ADR 0004 — Concurrency model

🏗️ **Edmund**: Retrofitted `GitHubClient` with a `threading.Lock` named `_rate_lock` and wrapped both `_maybe_sleep_for_rate_limit` (the full check-decide-sleep window) and `_update_rate_limit` (the header writeback) under it; the HTTP call itself stays outside the lock, and no other client behaviour was touched. Added `src/glitch/discover/fanout.py` with a module-level `MAX_WORKERS = 8`, `fetch_jobs_for_runs`, and `fetch_commits` — each submits one GET per id to a `ThreadPoolExecutor`, gathers via `as_completed`, and calls `.json()` on the returned `Response`; `fetch_commits` dedupes via `dict.fromkeys` to preserve first-seen order. Two judgment calls worth flagging: I hold the lock across `time.sleep` deliberately so a throttled fan-out converges on the same window-flip rather than stampeding; and on a worker exception I shut the pool down with `cancel_futures=True` before re-raising, so the first error wins and outstanding work is dropped rather than dragged through. The existing 18 client tests still pass unchanged. Handing to @margaret.

👀 **Margaret**: Walked the ADR against both files and the implementation is faithful. The critical thing — the lock does *not* wrap the HTTP call — checks out: `_session.get` sits between `_maybe_sleep_for_rate_limit` and `_update_rate_limit` in `_request_once`, neither lock window touches the wire call, so the fan-out actually fans out. `MAX_WORKERS = 8` is a module constant, no flag; shared `Session` preserved; pagination stays sequential; both fan-out helpers use `as_completed`; `fetch_commits` dedupes via `dict.fromkeys`; exceptions propagate cleanly via `future.result()`. `uv run pytest -q` → 67 passed.
- 💭 Holding the lock across `time.sleep` is the right call and the comment says so — when throttled, every thread should wake on the same window flip rather than independently re-checking and stampeding. Worth re-reading the comment before anyone "optimises" it away.
- 💭 `cancel_futures=True` on the failure path is a nice touch — the context manager would still tear down on raise, but cancelling outstanding futures stops them from blocking the join on a slow endpoint. Praise.
**APPROVE**

✨ **Whimsy**: edmund really clocked the classic "lock the http call by accident and turn ur threadpool into a single-file line" trap and just,, didn't 💀 8 workers eating in parallel while the rate-limit lock politely waits its turn outside the wire,, fan-out is FANNING fr 🚀✨

🔌 **Kai**: wrote `tests/test_discover_fanout.py` — 9 tests. `MAX_WORKERS == 8` sanity ✅; `fetch_jobs_for_runs` happy path → 3 endpoints, dict keyed by run id, payloads match, 3 calls; `fetch_commits` happy path same shape; dedupe test passes `["a","b","a"]` → 2 keys, exactly 1 hit on `/commits/a`; 404 in the middle of a fan-out → `GitHubHTTPError(404)` propagates cleanly; empty input → `{}` no HTTP traffic for both helpers. For the concurrency assertion I built a `_FakeSession` (since `responses` doesn't model threading well for the guard's check-decide window), primed `_rate_remaining=3` / `_rate_reset=now+1`, then barriered 16 threads into `_maybe_sleep_for_rate_limit` simultaneously — zero errors, no deadlock, `time.sleep` recorded. Plus a smoke fan-out where every endpoint returns `X-RateLimit-Remaining: 2` so workers hit the guard on entry. `uv run pytest tests/test_discover_fanout.py -q` → `9 passed in 0.22s`; full suite `uv run pytest -q` → `76 passed in 0.22s`. didn't touch fanout or client code, impl held up. **APPROVE**

✨ **Whimsy**: 16 threads barreling into the same lock and NOBODY deadlocked?? that barrier test is so unhinged it's basically a mosh pit with a bouncer 💀 8-worker fan-out eating in parallel while kai stress-tests the rate-limit guard like it owes him money,, adr 0004 SEALED fr 🚀✨

---

## ADR 0005 — Heuristic normalisation

🏗️ **Edmund**: Added `src/glitch/discover/heuristics.py` with the four pure-stdlib heuristic functions plus `heuristics_for_test` and `raw_score`; volatility groups by `head_sha`, sorts within each group by `created_at`, and aggregates flips/pairs across all eligible SHA-groups, while `timing_variance` uses `statistics.pstdev` over jobs with both timestamps populated and applies the `min(1.0, cv / 0.5)` cap. Two judgment calls worth flagging: I reconciled the ADR's formula-versus-prose tension for change-independence by following the prose — under the permissive Phase-1 default the spec formula `failures_on_unrelated_commits / total_failures` collapses to a constant `1.0` whenever any failure exists, which is plainly not the ADR's stated intent of "effectively reduces to failure rate"; I excluded in-progress runs (`conclusion is None`) from both numerator and denominator so a half-finished window does not depress the score. Second, I accept `commits_by_sha` on `change_independence` and `heuristics_for_test` but deliberately do not consume it in Phase 1 — the parameter is the seam where the future path-scoping manifest will land, and a docstring note plus a `del commits_by_sha` makes the unused-argument intentional. Smoke import passes. Handing to @margaret.

👀 **Margaret**: Walked all four heuristics against the ADR and the implementation is faithful — SHA-grouping with `< 2` skipped, adjacent-pair flips, `run_attempt > 1 ∧ success` retry numerator, `pstdev` with `min(1.0, cv / 0.5)`, equal-weight mean in `raw_score`, no recency, stdlib only. The formula-versus-prose call on change-independence is the right one: the formula collapses to `1.0` under the permissive default and the prose explicitly says "reduces to failure rate" — picking the prose preserves signal, and Edmund's docstring spells out exactly why so the next reader isn't ambushed.
- Praise: excluding `conclusion is None` from both sides of the failure-rate ratio is the right instinct — an in-flight run has no verdict and shouldn't dilute the denominator.
- 💭 The unused `commits_by_sha` seam is fine, but a future reader may wonder why `heuristics_for_test` accepts it too; the chained docstring covers it. Non-blocking.
**APPROVE**

✨ **Whimsy**: edmund really pulled up to the spec, saw the formula go `= 1.0` for literally any failing test, and was like "nah we reading the vibes today" 💀 the prose said reduces to failure rate and the math said lol no — picking the english over the latex is so real 🫠✨

🔌 **Kai**: wrote `tests/test_discover_heuristics.py` — 27 tests with `make_run` / `make_job` factories at the top so fixtures stay readable. volatility: empty/singleton/2-same/2-diff/3-flip-flop, mixed-SHA aggregate (1 flip across 3 pairs → 1/3), singleton-SHA contributes nothing, plus a reverse-chronological-order test that only passes if the impl sorts by `created_at` (chrono = 1.0, naive input order = 0.5 — they differ on purpose). retry_rate: 0 runs, no-retries, 2-of-4 = 0.5, failed-retry excluded, first-attempt-success excluded. timing_variance: 0/1 jobs → 0, identical durations → 0, mixed `None` timestamps reducing to <2 valid → 0, 60s/240s → cv=0.6 capped at 1.0, 100s/120s → cv≈0.0909 / 0.5 ≈ 0.1818 (asserted via `math.isclose`). change_independence: empty, all-success, 2/4 = 0.5, in-progress excluded from both sides (1 success + 1 None + 2 failures → 2/3), all-in-progress → 0. `heuristics_for_test` returns a `Heuristics` with all four fields in `[0,1]`; `raw_score` asserted as the equal-weight mean (0.2/0.4/0.6/0.8 → 0.5) plus the zero/one boundary corners. `uv run pytest tests/test_discover_heuristics.py -q` → `27 passed in 0.04s`; full suite `uv run pytest -q` → `103 passed in 0.25s`. didn't touch heuristics code, impl held up. **APPROVE**


✨ **Whimsy**: 103 PASSED 0.25s we crossed the TRIPLE DIGITS bestie 🎉 kai sneaking `math.isclose` in to nail cv≈0.1818 while edmund picks english over latex,, heuristic vibes IMMACULATE adr 0005 sealed 🚀✨
---
