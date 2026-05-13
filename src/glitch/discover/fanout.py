"""Threadpool fan-out helpers for Phase 1 — Discovery.

Implements ADR 0004: outer fan-out across independent endpoints runs on a
`ThreadPoolExecutor`, layered above the sync `GitHubClient`. Pagination
*within* a single endpoint is deliberately *not* parallelised — only the
one-call-per-id outer loops are.

Scope notes
-----------
This module is a pattern, not a class: two small functions that submit
independent GET requests to a pool and collect the parsed JSON keyed by the
input identifier. The shared `GitHubClient` handles auth, retry, and the
rate-limit guard (which now takes a lock — see `client.py`).
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from glitch.discover.client import GitHubClient

MAX_WORKERS = 8


def fetch_jobs_for_runs(
    client: GitHubClient,
    owner: str,
    repo: str,
    run_ids: Iterable[int],
) -> dict[int, Any]:
    """Fan out `GET /repos/{owner}/{repo}/actions/runs/{id}/jobs` per run id.

    Returns a mapping of `run_id -> parsed JSON payload`. If any worker
    raises, the first such exception propagates and outstanding futures are
    cancelled when the executor exits its context.
    """
    ids = list(run_ids)
    results: dict[int, Any] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_id = {
            executor.submit(
                _fetch_json,
                client,
                f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
            ): run_id
            for run_id in ids
        }
        try:
            for future in as_completed(future_to_id):
                run_id = future_to_id[future]
                results[run_id] = future.result()
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    return results


def fetch_commits(
    client: GitHubClient,
    owner: str,
    repo: str,
    shas: Iterable[str],
) -> dict[str, Any]:
    """Fan out `GET /repos/{owner}/{repo}/commits/{sha}` per unique sha.

    Shas are deduplicated up front (preserving first-seen order via
    `dict.fromkeys`) so we never pay twice for the same commit. Returns a
    mapping of `sha -> parsed JSON payload`.
    """
    unique_shas = list(dict.fromkeys(shas))
    results: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_sha = {
            executor.submit(
                _fetch_json,
                client,
                f"/repos/{owner}/{repo}/commits/{sha}",
            ): sha
            for sha in unique_shas
        }
        try:
            for future in as_completed(future_to_sha):
                sha = future_to_sha[future]
                results[sha] = future.result()
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    return results


def _fetch_json(client: GitHubClient, path: str) -> Any:
    """Issue a single GET via the shared client and return parsed JSON."""
    return client.get(path).json()
