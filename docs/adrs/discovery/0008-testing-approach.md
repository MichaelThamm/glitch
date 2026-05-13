# ADR 0008: Testing approach for the GitHub API

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

`glitch discover` is HTTP-bound — every meaningful code path eventually
talks to the GitHub REST API. Tests need to exercise the real client
([[0001-github-api-client]]: `requests` + `tenacity`) up to (but not past)
the transport boundary, without hitting the network. Three approaches are
candidate:

- **`responses`** — HTTP mocking for `requests`: tests register URL +
  payload mappings; unexpected calls error out.
- **`vcrpy`** — record-once / replay-many fixtures captured against a
  live API.
- **Hand-rolled fakes** — replace the client object with a stub.

## Decision

Use **`responses`** for any test that touches HTTP, plus hand-built fixture
JSON files for canned API responses. **No `vcrpy`.**

- **`responses`** is added as a dev dependency. It patches at the
  `requests.adapters` level, so the entire `requests.Session` configured
  in `client.py` (headers, retry decorator, pagination) is exercised
  end-to-end against the registered mocks.
- **Canned fixtures** live in `tests/fixtures/discover/`:
  ```
  tests/fixtures/discover/
  ├── runs_page_1.json   # one page of /actions/runs
  ├── jobs_run_123.json  # /actions/runs/123/jobs
  └── commit_abc.json    # /commits/{sha}
  ```
  Each fixture is small and hand-written so its diff is reviewable.
- **Cache tests** use `pytest`'s `tmp_path` directly — no HTTP involved.
- **Scoring / duration / models tests** are pure-function unit tests with
  no mocking infrastructure.
- **End-to-end** test (`tests/test_discover_e2e.py`) drives the Typer
  `run()` against `responses` + a `tmp_path` cache and asserts:
  - JSON output shape matches the spec
  - exit codes match the spec's error-handling table
  - cache files are written with the expected envelope

### Test pyramid

| Layer | Tool | Scope |
|---|---|---|
| Pure unit (`_duration.py`, `scoring.py`, `models.py`) | none | math + parsing |
| Unit (`client.py`) | `responses` | auth fallback, pagination, retry, rate-limit guard |
| Unit (`cache.py`) | `tmp_path` | envelope I/O, TTL, atomic write |
| Unit (`render.py`) | `rich.console.Console(record=True)` for the table; raw `json.loads` for JSON | spec-shape compliance |
| End-to-end (`_entrypoint.py`) | `responses` + `tmp_path` | exit codes, error-table branches, JSON output |

## Alternatives considered

- **`vcrpy`** — recorded fixtures are large, noisy, and tied to a real API
  account at recording time. The set of API shapes we care about (~3
  endpoints, ~4 variations) is small enough that hand-writing fixtures is
  faster than re-recording.
- **`requests-mock`** — equivalent to `responses`; `responses` is more
  widely used in the ecosystem.
- **Hand-rolled fakes everywhere** — tests against our *model* of
  `requests`, not against `requests` itself. We would lose coverage of
  pagination via the `Link` header, retry behaviour, and header handling.

## Consequences

- Positive: tests exercise the real HTTP-client wiring; fixtures are small
  and human-readable; no recorded-fixture rot.
- Negative: hand-writing fixtures means we may miss real-world API
  surprises. Mitigated by occasional manual `curl` against the live API as
  a sanity check.
- Follow-ups: add a smoke-test script that runs `glitch discover` against
  a known public charm repo, gated behind `GITHUB_TOKEN`, for periodic
  reality checks. Related: [[0001-github-api-client]] (the SUT),
  [[0002-local-cache-layer]] (tested with `tmp_path`),
  [[0007-module-layout]] (test files mirror the subpackage layout).
