"""GitHub REST API client for Phase 1 — Discovery.

Implements ADR 0001: a thin `requests.Session`-backed client with declarative
retry (via `tenacity`), `Link`-header pagination, and a rate-limit guard.

Scope notes
-----------
This module deliberately stops at "fetch JSON from the GitHub REST API." It
does not cache (ADR 0002), parse responses into domain models (ADR 0003), or
fan out across endpoints concurrently (ADR 0004). Each of those layers will
wrap this client without modifying it.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
ACCEPT_HEADER = "application/vnd.github+json"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_PER_PAGE = 100
RATE_LIMIT_THRESHOLD = 10


class GitHubAuthError(RuntimeError):
    """Raised when no usable GitHub token can be resolved."""


class GitHubHTTPError(RuntimeError):
    """Raised for non-retryable HTTP errors (typically 4xx)."""

    def __init__(self, status_code: int, url: str, body: str) -> None:
        super().__init__(f"GitHub API {status_code} for {url}: {body}")
        self.status_code = status_code
        self.url = url
        self.body = body


class _RetryableHTTPError(Exception):
    """Internal signal that a response should be retried (5xx)."""


def resolve_token() -> str:
    """Resolve a GitHub token per the spec: env var, then `gh auth token`.

    Exits the process with code 1 and a clear stderr message if neither is
    available. Returning an exception instead would be cleaner architecturally,
    but the spec mandates exit-on-failure at this layer.
    """
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token.strip()

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result = None

    if result is not None and result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    print(
        "error: no GitHub token available. Set GITHUB_TOKEN or run `gh auth login`.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def build_session(token: str) -> requests.Session:
    """Build a `requests.Session` with the three default headers set once."""
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
    )
    return session


class GitHubClient:
    """A thin synchronous client around `requests.Session`.

    One instance per `discover` invocation. Threadsafe for read-only use of the
    underlying `Session` (which `requests` documents as safe across threads
    for separate request calls); ADR 0004 will rely on that.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        base_url: str = BASE_URL,
    ) -> None:
        self._session = session if session is not None else build_session(resolve_token())
        self._base_url = base_url.rstrip("/")
        # Track the most recently observed rate-limit headers across requests.
        self._rate_remaining: int | None = None
        self._rate_reset: int | None = None

    # ------------------------------------------------------------------ public

    def get(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        """GET a single URL or path, returning the raw `Response`.

        Accepts either an absolute URL (used when following `Link` headers) or
        a path like `/repos/{owner}/{repo}/actions/runs` which is joined to
        the base URL.
        """
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        return self._request_with_retry(url, params)

    def paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Iterator[requests.Response]:
        """Yield each page of a paginated endpoint.

        Sets `per_page=100` unless the caller has already supplied it, then
        follows the `Link` header's `rel="next"` until exhausted. We yield
        whole `Response` objects (rather than parsed JSON) so callers can read
        headers — useful for `total_count` and for cache layers added later.
        """
        merged_params = {"per_page": DEFAULT_PER_PAGE, **(params or {})}
        url: str | None = (
            path if path.startswith("http") else f"{self._base_url}{path}"
        )
        # `params` only apply to the first request; subsequent `next` URLs
        # already carry their own query string.
        first = True
        while url is not None:
            response = self._request_with_retry(url, merged_params if first else None)
            yield response
            url = _next_link(response.headers.get("Link"))
            first = False

    # ----------------------------------------------------------------- private

    def _request_with_retry(
        self, url: str, params: dict[str, Any] | None
    ) -> requests.Response:
        """Wrap `_request_once` with tenacity-driven retries (5xx + network)."""

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(
                (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    _RetryableHTTPError,
                )
            ),
        )
        def _call() -> requests.Response:
            return self._request_once(url, params)

        return _call()

    def _request_once(
        self, url: str, params: dict[str, Any] | None
    ) -> requests.Response:
        """Issue a single GET, honouring the rate-limit guard.

        Raises `_RetryableHTTPError` for 5xx (so tenacity retries) and
        `GitHubHTTPError` for 4xx (so it propagates immediately).
        """
        self._maybe_sleep_for_rate_limit()

        response = self._session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        self._update_rate_limit(response)

        status = response.status_code
        if status >= 500:
            raise _RetryableHTTPError(f"GitHub returned {status} for {url}")
        if status >= 400:
            raise GitHubHTTPError(status, url, response.text[:500])
        return response

    def _update_rate_limit(self, response: requests.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        try:
            if remaining is not None:
                self._rate_remaining = int(remaining)
            if reset is not None:
                self._rate_reset = int(reset)
        except ValueError:
            # If GitHub ever returns a non-integer header we'd rather ignore
            # it than crash; the guard will simply not trigger.
            logger.debug("ignoring non-integer rate-limit headers: %s / %s", remaining, reset)

    def _maybe_sleep_for_rate_limit(self) -> None:
        if self._rate_remaining is None or self._rate_reset is None:
            return
        if self._rate_remaining >= RATE_LIMIT_THRESHOLD:
            return
        # +1s of headroom so we wake up just after the window flips.
        wait_seconds = max(0, self._rate_reset - int(time.time())) + 1
        print(
            f"glitch: approaching GitHub rate limit "
            f"(remaining={self._rate_remaining}); sleeping {wait_seconds}s",
            file=sys.stderr,
        )
        time.sleep(wait_seconds)


def _next_link(link_header: str | None) -> str | None:
    """Extract the `rel="next"` URL from a `Link` header, if present.

    The header format is `<url>; rel="next", <url>; rel="last"`. We parse it
    by hand rather than pulling in `requests.utils.parse_header_links` so the
    behaviour is explicit and easy to test in isolation.
    """
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = [s.strip() for s in part.split(";")]
        if len(segments) < 2:
            continue
        url_segment = segments[0]
        rel_segments = segments[1:]
        if not (url_segment.startswith("<") and url_segment.endswith(">")):
            continue
        if any(rel.strip() == 'rel="next"' for rel in rel_segments):
            return url_segment[1:-1]
    return None
