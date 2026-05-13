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
