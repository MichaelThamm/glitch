"""Tests for `glitch.discover.client` — ADR 0001.

HTTP mocked with `responses` (ADR 0008). Retry backoffs are neutralised via
monkeypatching `time.sleep` so the suite stays fast.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any

import pytest
import requests
import responses

from glitch.discover import client as client_mod
from glitch.discover.client import (
    ACCEPT_HEADER,
    BASE_URL,
    GITHUB_API_VERSION,
    GitHubClient,
    GitHubHTTPError,
    build_session,
    resolve_token,
)


# --------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace `time.sleep` everywhere with a no-op recorder.

    Tenacity's exponential backoff and the rate-limit guard both call
    `time.sleep`. We record every call so individual tests can assert on it,
    but the suite never actually waits.
    """
    calls: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(client_mod.time, "sleep", _fake_sleep)
    # `tenacity` imports `time.sleep` from the top-level module, so patch there
    # too in case the symbol was bound at import time.
    monkeypatch.setattr(time, "sleep", _fake_sleep)
    return calls


@pytest.fixture
def gh_client() -> GitHubClient:
    """A client with a pre-built session — skips token resolution."""
    return GitHubClient(session=build_session("test-token"))


# ------------------------------------------------------------------------ auth


class TestResolveToken:
    def test_returns_env_token_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "  env-token  ")
        # subprocess.run must NOT be called when env is set.
        called: list[Any] = []
        monkeypatch.setattr(
            client_mod.subprocess,
            "run",
            lambda *a, **kw: called.append((a, kw)) or None,
        )

        assert resolve_token() == "env-token"
        assert called == []

    def test_falls_back_to_gh_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        class _Result:
            returncode = 0
            stdout = "gh-token\n"
            stderr = ""

        def _fake_run(*_a: Any, **_kw: Any) -> _Result:
            return _Result()

        monkeypatch.setattr(client_mod.subprocess, "run", _fake_run)
        assert resolve_token() == "gh-token"

    def test_exits_when_no_token_anywhere(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        def _fake_run(*_a: Any, **_kw: Any) -> Any:
            raise FileNotFoundError("gh not installed")

        monkeypatch.setattr(client_mod.subprocess, "run", _fake_run)

        with pytest.raises(SystemExit) as excinfo:
            resolve_token()
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "no GitHub token available" in err

    def test_exits_when_gh_returns_nonzero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        class _Result:
            returncode = 1
            stdout = ""
            stderr = "not logged in"

        monkeypatch.setattr(
            client_mod.subprocess, "run", lambda *_a, **_kw: _Result()
        )
        with pytest.raises(SystemExit) as excinfo:
            resolve_token()
        assert excinfo.value.code == 1
        assert "no GitHub token available" in capsys.readouterr().err

    def test_handles_gh_timeout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        def _fake_run(*_a: Any, **_kw: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd="gh", timeout=5)

        monkeypatch.setattr(client_mod.subprocess, "run", _fake_run)
        with pytest.raises(SystemExit):
            resolve_token()
        assert "no GitHub token available" in capsys.readouterr().err


# --------------------------------------------------------------------- headers


class TestBuildSession:
    def test_sets_three_required_headers(self) -> None:
        session = build_session("abc123")
        assert session.headers["Authorization"] == "Bearer abc123"
        assert session.headers["Accept"] == ACCEPT_HEADER
        assert session.headers["X-GitHub-Api-Version"] == GITHUB_API_VERSION

    @responses.activate
    def test_headers_sent_on_actual_request(self, gh_client: GitHubClient) -> None:
        responses.add(
            responses.GET,
            f"{BASE_URL}/zen",
            json={"ok": True},
            status=200,
        )
        gh_client.get("/zen")
        sent = responses.calls[0].request.headers
        assert sent["Authorization"] == "Bearer test-token"
        assert sent["Accept"] == ACCEPT_HEADER
        assert sent["X-GitHub-Api-Version"] == GITHUB_API_VERSION


# ----------------------------------------------------------------- pagination


class TestPagination:
    @responses.activate
    def test_follows_link_next_until_exhausted(self, gh_client: GitHubClient) -> None:
        page1_url = f"{BASE_URL}/repos/o/r/actions/runs"
        page2_url = f"{BASE_URL}/repos/o/r/actions/runs?page=2&per_page=100"
        page3_url = f"{BASE_URL}/repos/o/r/actions/runs?page=3&per_page=100"

        responses.add(
            responses.GET,
            page1_url,
            json={"page": 1},
            status=200,
            headers={"Link": f'<{page2_url}>; rel="next", <{page3_url}>; rel="last"'},
        )
        responses.add(
            responses.GET,
            page2_url,
            json={"page": 2},
            status=200,
            headers={"Link": f'<{page3_url}>; rel="next"'},
        )
        responses.add(
            responses.GET,
            page3_url,
            json={"page": 3},
            status=200,
            # no Link header — terminates pagination
        )

        pages = list(gh_client.paginate("/repos/o/r/actions/runs"))
        assert [p.json()["page"] for p in pages] == [1, 2, 3]

    @responses.activate
    def test_sends_per_page_100_on_first_request(self, gh_client: GitHubClient) -> None:
        url = f"{BASE_URL}/repos/o/r/actions/runs"
        responses.add(responses.GET, url, json={"ok": True}, status=200)

        list(gh_client.paginate("/repos/o/r/actions/runs"))
        sent_qs = responses.calls[0].request.url
        assert "per_page=100" in sent_qs

    @responses.activate
    def test_caller_per_page_overrides_default(self, gh_client: GitHubClient) -> None:
        url = f"{BASE_URL}/repos/o/r/actions/runs"
        responses.add(responses.GET, url, json={"ok": True}, status=200)

        list(gh_client.paginate("/repos/o/r/actions/runs", params={"per_page": 50}))
        assert "per_page=50" in responses.calls[0].request.url

    @responses.activate
    def test_no_link_header_yields_single_page(self, gh_client: GitHubClient) -> None:
        url = f"{BASE_URL}/repos/o/r/actions/runs"
        responses.add(responses.GET, url, json={"only": True}, status=200)
        pages = list(gh_client.paginate("/repos/o/r/actions/runs"))
        assert len(pages) == 1


# ---------------------------------------------------------------------- retry


class TestRetry:
    @responses.activate
    def test_retries_5xx_then_succeeds(self, gh_client: GitHubClient) -> None:
        url = f"{BASE_URL}/repos/o/r/flaky"
        responses.add(responses.GET, url, json={"err": 1}, status=500)
        responses.add(responses.GET, url, json={"err": 2}, status=500)
        responses.add(responses.GET, url, json={"ok": True}, status=200)

        resp = gh_client.get("/repos/o/r/flaky")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert len(responses.calls) == 3

    @responses.activate
    def test_4xx_raises_immediately_no_retry(self, gh_client: GitHubClient) -> None:
        url = f"{BASE_URL}/repos/o/r/missing"
        responses.add(responses.GET, url, json={"message": "Not Found"}, status=404)

        with pytest.raises(GitHubHTTPError) as excinfo:
            gh_client.get("/repos/o/r/missing")

        assert excinfo.value.status_code == 404
        assert excinfo.value.url == url
        assert "Not Found" in excinfo.value.body
        assert len(responses.calls) == 1

    @responses.activate
    def test_gives_up_after_three_5xx(self, gh_client: GitHubClient) -> None:
        url = f"{BASE_URL}/repos/o/r/down"
        for _ in range(3):
            responses.add(responses.GET, url, json={"err": True}, status=503)

        with pytest.raises(Exception) as excinfo:
            gh_client.get("/repos/o/r/down")

        # tenacity reraises the underlying _RetryableHTTPError.
        assert "503" in str(excinfo.value) or "Retryable" in type(excinfo.value).__name__
        assert len(responses.calls) == 3

    @responses.activate
    def test_retries_on_connection_error(self, gh_client: GitHubClient) -> None:
        url = f"{BASE_URL}/repos/o/r/net"
        responses.add(
            responses.GET, url, body=requests.exceptions.ConnectionError("boom")
        )
        responses.add(responses.GET, url, json={"ok": True}, status=200)

        resp = gh_client.get("/repos/o/r/net")
        assert resp.status_code == 200
        assert len(responses.calls) == 2


# ----------------------------------------------------------------- rate limit


class TestRateLimitGuard:
    @responses.activate
    def test_sleeps_when_remaining_below_threshold(
        self,
        monkeypatch: pytest.MonkeyPatch,
        _no_sleep: list[float],
        gh_client: GitHubClient,
    ) -> None:
        # First response primes the rate-limit state with remaining=5 and a
        # reset 30s in the future.
        fixed_now = 1_700_000_000
        reset_at = fixed_now + 30
        monkeypatch.setattr(client_mod.time, "time", lambda: fixed_now)

        url = f"{BASE_URL}/repos/o/r/a"
        responses.add(
            responses.GET,
            url,
            json={"ok": 1},
            status=200,
            headers={
                "X-RateLimit-Remaining": "5",
                "X-RateLimit-Reset": str(reset_at),
            },
        )
        # Second request — guard should fire BEFORE this one.
        url2 = f"{BASE_URL}/repos/o/r/b"
        responses.add(
            responses.GET,
            url2,
            json={"ok": 2},
            status=200,
            headers={
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(reset_at + 3600),
            },
        )

        gh_client.get("/repos/o/r/a")
        sleeps_before = list(_no_sleep)
        gh_client.get("/repos/o/r/b")

        new_sleeps = _no_sleep[len(sleeps_before):]
        # Exactly one rate-limit sleep call should have been issued; the value
        # must be roughly `(reset - now) + 1` = 31.
        assert 31 in new_sleeps, f"expected a 31s sleep, got {new_sleeps}"

    @responses.activate
    def test_does_not_sleep_when_remaining_above_threshold(
        self,
        _no_sleep: list[float],
        gh_client: GitHubClient,
    ) -> None:
        url = f"{BASE_URL}/repos/o/r/a"
        responses.add(
            responses.GET,
            url,
            json={"ok": 1},
            status=200,
            headers={
                "X-RateLimit-Remaining": "4000",
                "X-RateLimit-Reset": "9999999999",
            },
        )
        url2 = f"{BASE_URL}/repos/o/r/b"
        responses.add(responses.GET, url2, json={"ok": 2}, status=200)

        gh_client.get("/repos/o/r/a")
        before = list(_no_sleep)
        gh_client.get("/repos/o/r/b")
        # No new sleep calls between the two requests.
        assert _no_sleep == before

    @responses.activate
    def test_logs_to_stderr_when_throttling(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        gh_client: GitHubClient,
    ) -> None:
        monkeypatch.setattr(client_mod.time, "time", lambda: 1_700_000_000)
        url = f"{BASE_URL}/repos/o/r/a"
        responses.add(
            responses.GET,
            url,
            json={"ok": 1},
            status=200,
            headers={
                "X-RateLimit-Remaining": "2",
                "X-RateLimit-Reset": "1700000010",
            },
        )
        url2 = f"{BASE_URL}/repos/o/r/b"
        responses.add(responses.GET, url2, json={"ok": 2}, status=200)

        gh_client.get("/repos/o/r/a")
        gh_client.get("/repos/o/r/b")

        err = capsys.readouterr().err
        assert "rate limit" in err.lower()
        assert "remaining=2" in err
