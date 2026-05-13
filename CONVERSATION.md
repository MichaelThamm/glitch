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
