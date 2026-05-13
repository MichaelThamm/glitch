"""Tests for `glitch.discover.fanout` — ADR 0004.

HTTP mocked with `responses` (ADR 0008). Retry backoffs / rate-limit sleeps
are neutralised via monkeypatching `time.sleep` so the suite stays fast.

`responses` *does* work with `requests.Session` calls across threads — it
hooks the adapter level, which is shared. We use it for the per-endpoint
fan-out tests, and a fake `GitHubClient` for the genuine concurrency
assertion (multiple threads hammering `_maybe_sleep_for_rate_limit`).
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
import responses

from glitch.discover import client as client_mod
from glitch.discover import fanout as fanout_mod
from glitch.discover.client import (
    BASE_URL,
    GitHubClient,
    GitHubHTTPError,
    build_session,
)
from glitch.discover.fanout import (
    MAX_WORKERS,
    fetch_commits,
    fetch_jobs_for_runs,
    fetch_runs_for_workflows,
)


# --------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace `time.sleep` everywhere with a no-op recorder."""
    calls: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(client_mod.time, "sleep", _fake_sleep)
    monkeypatch.setattr(time, "sleep", _fake_sleep)
    return calls


@pytest.fixture
def gh_client() -> GitHubClient:
    """A client with a pre-built session — skips token resolution."""
    return GitHubClient(session=build_session("test-token"))


# ---------------------------------------------------------------- sanity check


class TestSanity:
    def test_max_workers_is_eight(self) -> None:
        # ADR 0004 pins this constant — no flag, no env override.
        assert MAX_WORKERS == 8


# ------------------------------------------------------- fetch_jobs_for_runs


class TestFetchJobsForRuns:
    @responses.activate
    def test_happy_path_three_runs(self, gh_client: GitHubClient) -> None:
        for run_id in (1, 2, 3):
            responses.add(
                responses.GET,
                f"{BASE_URL}/repos/o/r/actions/runs/{run_id}/jobs",
                json={"jobs": [{"id": run_id * 10}]},
                status=200,
            )

        result = fetch_jobs_for_runs(gh_client, "o", "r", [1, 2, 3])

        assert set(result.keys()) == {1, 2, 3}
        assert result[1] == {"jobs": [{"id": 10}]}
        assert result[2] == {"jobs": [{"id": 20}]}
        assert result[3] == {"jobs": [{"id": 30}]}
        assert len(responses.calls) == 3

    @responses.activate
    def test_exception_propagates_on_404(self, gh_client: GitHubClient) -> None:
        responses.add(
            responses.GET,
            f"{BASE_URL}/repos/o/r/actions/runs/1/jobs",
            json={"jobs": [{"id": 10}]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/repos/o/r/actions/runs/2/jobs",
            json={"message": "Not Found"},
            status=404,
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/repos/o/r/actions/runs/3/jobs",
            json={"jobs": [{"id": 30}]},
            status=200,
        )

        with pytest.raises(GitHubHTTPError) as excinfo:
            fetch_jobs_for_runs(gh_client, "o", "r", [1, 2, 3])

        assert excinfo.value.status_code == 404

    def test_empty_input_returns_empty_dict(self, gh_client: GitHubClient) -> None:
        # No HTTP traffic should be issued; responses is intentionally not
        # activated so any stray call would blow up.
        assert fetch_jobs_for_runs(gh_client, "o", "r", []) == {}


# -------------------------------------------------------- fetch_runs_for_workflows


class TestFetchRunsForWorkflows:
    @responses.activate
    def test_happy_path_two_workflows(self, gh_client: GitHubClient) -> None:
        for wf_id, runs in [(10, [{"id": 100}]), (20, [{"id": 200}, {"id": 201}])]:
            responses.add(
                responses.GET,
                f"{BASE_URL}/repos/o/r/actions/workflows/{wf_id}/runs",
                json={"total_count": len(runs), "workflow_runs": runs},
                status=200,
            )

        result = fetch_runs_for_workflows(
            gh_client, "o", "r", [10, 20], {"branch": "main"}
        )

        assert set(result.keys()) == {10, 20}
        assert result[10] == [{"id": 100}]
        assert result[20] == [{"id": 200}, {"id": 201}]
        # Verify correct endpoints were hit.
        urls = {c.request.url.split("?")[0] for c in responses.calls}
        assert f"{BASE_URL}/repos/o/r/actions/workflows/10/runs" in urls
        assert f"{BASE_URL}/repos/o/r/actions/workflows/20/runs" in urls

    def test_empty_input_returns_empty_dict(self, gh_client: GitHubClient) -> None:
        assert fetch_runs_for_workflows(gh_client, "o", "r", [], {}) == {}

    @responses.activate
    def test_error_propagates_on_404(self, gh_client: GitHubClient) -> None:
        responses.add(
            responses.GET,
            f"{BASE_URL}/repos/o/r/actions/workflows/10/runs",
            json={"workflow_runs": [{"id": 100}]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/repos/o/r/actions/workflows/99/runs",
            json={"message": "Not Found"},
            status=404,
        )

        with pytest.raises(GitHubHTTPError) as excinfo:
            fetch_runs_for_workflows(
                gh_client, "o", "r", [10, 99], {"branch": "main"}
            )

        assert excinfo.value.status_code == 404


# ----------------------------------------------------------------- fetch_commits


class TestFetchCommits:
    @responses.activate
    def test_happy_path_three_shas(self, gh_client: GitHubClient) -> None:
        for sha in ("aaa", "bbb", "ccc"):
            responses.add(
                responses.GET,
                f"{BASE_URL}/repos/o/r/commits/{sha}",
                json={"sha": sha, "commit": {"message": f"msg-{sha}"}},
                status=200,
            )

        result = fetch_commits(gh_client, "o", "r", ["aaa", "bbb", "ccc"])

        assert set(result.keys()) == {"aaa", "bbb", "ccc"}
        assert result["aaa"]["sha"] == "aaa"
        assert result["bbb"]["commit"]["message"] == "msg-bbb"
        assert len(responses.calls) == 3

    @responses.activate
    def test_deduplicates_input_shas(self, gh_client: GitHubClient) -> None:
        responses.add(
            responses.GET,
            f"{BASE_URL}/repos/o/r/commits/a",
            json={"sha": "a"},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/repos/o/r/commits/b",
            json={"sha": "b"},
            status=200,
        )

        result = fetch_commits(gh_client, "o", "r", ["a", "b", "a"])

        # Dict has 2 keys — the dup was collapsed.
        assert set(result.keys()) == {"a", "b"}
        # And — the critical part — only TWO HTTP requests went out.
        assert len(responses.calls) == 2
        a_hits = [c for c in responses.calls if c.request.url.endswith("/commits/a")]
        assert len(a_hits) == 1

    def test_empty_input_returns_empty_dict(self, gh_client: GitHubClient) -> None:
        assert fetch_commits(gh_client, "o", "r", []) == {}


# -------------------------------------------------------- concurrent rate-limit


class _FakeResponse:
    """Bare-bones stand-in for `requests.Response` used by the fake session."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers
        self.status_code = 200
        self.text = ""

    def json(self) -> dict[str, Any]:
        return {"ok": True}


class _FakeSession:
    """Mocked `requests.Session` that always returns a 200 with rate headers.

    Headers are configurable so each test can set `X-RateLimit-Remaining` /
    `Reset` to whatever it needs. Records every `get` call for assertions.
    """

    def __init__(self, headers: dict[str, str]) -> None:
        self._headers = headers
        self.calls: list[tuple[str, Any]] = []
        self._lock = threading.Lock()

    def get(self, url: str, params: Any = None, timeout: int = 0) -> _FakeResponse:
        with self._lock:
            self.calls.append((url, params))
        return _FakeResponse(self._headers)


class TestRateLimitLockUnderConcurrency:
    def test_lock_serialises_threads_under_low_rate_limit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _no_sleep: list[float],
    ) -> None:
        """Multiple threads concurrently hitting the guard must not race.

        We prime the client's rate-limit state to `remaining < threshold` so
        the guard fires, then fan a bunch of threads at
        `_maybe_sleep_for_rate_limit`. With the lock in place the test simply
        completes without `RuntimeError` / `ValueError` / deadlock and
        `time.sleep` is observed at least once.
        """
        fixed_now = 1_700_000_000
        monkeypatch.setattr(client_mod.time, "time", lambda: fixed_now)

        fake_session = _FakeSession(
            headers={
                "X-RateLimit-Remaining": "3",
                "X-RateLimit-Reset": str(fixed_now + 1),
            }
        )
        client = GitHubClient(session=fake_session)
        # Prime the rate-limit state by doing one request first — this makes
        # `_rate_remaining` and `_rate_reset` non-None so the guard activates.
        client.get("/zen")

        n_threads = 16
        errors: list[BaseException] = []
        barrier = threading.Barrier(n_threads)

        def worker() -> None:
            try:
                barrier.wait(timeout=5)
                client._maybe_sleep_for_rate_limit()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"unexpected exceptions from workers: {errors!r}"
        # At least one sleep call must have fired (one per thread — they all
        # see remaining<threshold even after acquiring the lock, since nothing
        # decrements `_rate_remaining` here).
        assert len(_no_sleep) >= 1
        # Sanity: no thread is still alive.
        assert all(not t.is_alive() for t in threads)

    @responses.activate
    def test_concurrent_fanout_under_low_rate_limit_does_not_crash(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _no_sleep: list[float],
        gh_client: GitHubClient,
    ) -> None:
        """Smoke test: a real fan-out where the first response primes a low
        rate-limit value. The lock-protected guard must keep everything sane.
        """
        fixed_now = 1_700_000_000
        monkeypatch.setattr(client_mod.time, "time", lambda: fixed_now)

        # Every endpoint returns headers below the threshold so each worker
        # will hit the guard on its way in.
        for run_id in range(1, 9):
            responses.add(
                responses.GET,
                f"{BASE_URL}/repos/o/r/actions/runs/{run_id}/jobs",
                json={"jobs": [run_id]},
                status=200,
                headers={
                    "X-RateLimit-Remaining": "2",
                    "X-RateLimit-Reset": str(fixed_now + 1),
                },
            )

        result = fetch_jobs_for_runs(gh_client, "o", "r", list(range(1, 9)))

        assert set(result.keys()) == set(range(1, 9))
        # After the first request lands and sets `_rate_remaining=2`, every
        # subsequent guard check should sleep. We can't pin an exact count
        # (timing-dependent), but at least one sleep must have fired.
        assert any(s >= 1 for s in _no_sleep)
