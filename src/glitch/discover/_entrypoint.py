"""Typer entrypoint for ``glitch discover`` (ADR 0007).

This module owns the CLI surface and the orchestration that ties the discovery
components together: parse flags, resolve auth, fetch runs and jobs (with the
cache layer in front), score each test, render the result. Domain logic lives
in the sibling modules (``client``, ``cache``, ``models``, ``scoring``,
``render``, ``fanout``); this file should never grow business rules of its
own.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import typer

from glitch import __version__
from glitch.discover._duration import parse_duration
from glitch.discover.cache import (
    Cache,
    key_jobs,
    key_runs,
    key_workflows,
    ttl_for_jobs,
    ttl_for_runs_list,
    ttl_for_workflows,
)
from glitch.discover.client import (
    GitHubClient,
    GitHubHTTPError,
    build_session,
    resolve_token,
)
from glitch.discover.fanout import fetch_jobs_for_runs, fetch_runs_for_workflows
from glitch.discover.models import (
    DiscoveryReport,
    InsufficientData,
    Job,
    Meta,
    Run,
)
from glitch.discover.render import render_table, to_json
from glitch.discover.scoring import score_test

MIN_RUNS_FOR_SCORING = 3


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


def run(
    repo: Annotated[
        str,
        typer.Option("--repo", help="GitHub repository in owner/repo format.", show_default=False),
    ],
    since: Annotated[
        str,
        typer.Option("--since", help="Lookback window (e.g. 30d, 2w)."),
    ] = "30d",
    output: Annotated[
        OutputFormat,
        typer.Option("--output", help="Output format."),
    ] = OutputFormat.table,
    cache_dir: Annotated[
        Path,
        typer.Option("--cache-dir", help="Directory for cached API responses."),
    ] = Path.home() / ".cache" / "glitch",
    branch: Annotated[
        str | None,
        typer.Option("--branch", help="Filter to a specific branch (default: repo default branch)."),
    ] = None,
    workflow: Annotated[
        list[str] | None,
        typer.Option(
            "--workflow",
            help=(
                "Limit discovery to one or more workflows (repeatable). Each "
                "value is matched against the workflow's path, basename, "
                "display name, or numeric id, in that order."
            ),
        ),
    ] = None,
) -> None:
    """Score test flakiness from CI history for the given repo."""
    owner, repo_name = _parse_repo(repo)
    since_delta = _parse_since(since)
    workflow_filters: list[str] = list(workflow) if workflow else []

    now = datetime.now(UTC)
    since_dt = now - since_delta
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    token = resolve_token()
    client = GitHubClient(session=build_session(token))
    cache = Cache(cache_dir)

    try:
        target_branch = _resolve_branch(client, owner, repo_name, branch)
        if workflow_filters:
            resolved_workflows = _resolve_workflows(
                client, cache, owner, repo_name, workflow_filters
            )
            raw_runs = _fetch_runs_for_workflows(
                client,
                cache,
                owner,
                repo_name,
                target_branch,
                since_iso,
                resolved_workflows,
            )
            workflow_names = tuple(name for _, name in resolved_workflows)
        else:
            raw_runs = _fetch_runs(
                client, cache, owner, repo_name, target_branch, since_iso
            )
            workflow_names = ()
    except GitHubHTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise typer.Exit(code=1) from exc

    parsed_runs = [Run.from_api(raw) for raw in raw_runs]

    if not parsed_runs:
        print(
            f"warning: no workflow runs found for {repo} (branch {target_branch}) in the last {since}.",
            file=sys.stderr,
        )
        report = _empty_report(
            repo, target_branch, now, since_delta, workflow_names
        )
        _emit(report, output)
        return

    run_ids = [r.id for r in parsed_runs]
    try:
        jobs_payloads = _fetch_jobs(client, cache, owner, repo_name, run_ids)
    except GitHubHTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise typer.Exit(code=1) from exc

    test_scores, insufficient = _score_all_tests(parsed_runs, jobs_payloads, now)

    report = DiscoveryReport(
        meta=Meta(
            repo=repo,
            branch=target_branch,
            generated_at=now,
            lookback_days=max(1, since_delta.days),
            total_runs_analysed=len(parsed_runs),
            glitch_version=__version__,
            workflows=workflow_names,
        ),
        tests=tuple(test_scores),
        insufficient_data=tuple(insufficient),
    )

    if not test_scores:
        print(
            "warning: all tests fell below the minimum-runs threshold "
            f"({MIN_RUNS_FOR_SCORING} runs). See insufficient_data for details.",
            file=sys.stderr,
        )

    _emit(report, output)


# --- Helpers ----------------------------------------------------------------


def _parse_repo(repo: str) -> tuple[str, str]:
    """Split ``owner/repo`` into its two parts; exit 1 on a malformed value."""
    if "/" not in repo or repo.count("/") != 1:
        print(
            f"error: --repo must be in owner/repo format (got {repo!r}).",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)
    owner, repo_name = repo.split("/", 1)
    if not owner or not repo_name:
        print(
            f"error: --repo must be in owner/repo format (got {repo!r}).",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)
    return owner, repo_name


def _parse_since(since: str) -> timedelta:
    """Parse ``--since`` via ADR 0009's duration grammar; exit 1 on failure."""
    try:
        return parse_duration(since)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise typer.Exit(code=1) from exc


def _resolve_branch(
    client: GitHubClient, owner: str, repo: str, branch: str | None
) -> str:
    """Return ``branch`` if given, else fetch the repo's default branch."""
    if branch is not None:
        return branch
    response = client.get(f"/repos/{owner}/{repo}")
    return response.json()["default_branch"]


def _fetch_runs(
    client: GitHubClient,
    cache: Cache,
    owner: str,
    repo: str,
    branch: str,
    since_iso: str,
) -> list[dict[str, Any]]:
    """Return all run payloads for ``branch`` since ``since_iso``, cached at 300s.

    Pagination happens here (sequential, per ADR 0004); the aggregated list of
    raw run dicts is what gets cached so a re-run within 5 minutes hits the
    cache instead of re-walking the page chain.
    """
    cache_key = key_runs(owner, repo, branch, since_iso)
    cached = cache.get(cache_key, "runs")
    if cached is not None:
        return list(cached)

    runs: list[dict[str, Any]] = []
    params = {"branch": branch, "created": f">={since_iso}"}
    for page in client.paginate(f"/repos/{owner}/{repo}/actions/runs", params=params):
        runs.extend(page.json().get("workflow_runs", []))

    cache.put(cache_key, "runs", runs, ttl_for_runs_list())
    return runs


def _list_workflows(
    client: GitHubClient,
    cache: Cache,
    owner: str,
    repo: str,
) -> list[dict[str, Any]]:
    """Return the repo's full workflow listing, cached for an hour (ADR 0010)."""
    cache_key = key_workflows(owner, repo)
    cached = cache.get(cache_key, "workflows")
    if cached is not None:
        return list(cached)

    workflows: list[dict[str, Any]] = []
    params = {"per_page": 100}
    for page in client.paginate(
        f"/repos/{owner}/{repo}/actions/workflows", params=params
    ):
        workflows.extend(page.json().get("workflows", []))

    cache.put(cache_key, "workflows", workflows, ttl_for_workflows())
    return workflows


def _resolve_workflows(
    client: GitHubClient,
    cache: Cache,
    owner: str,
    repo: str,
    identifiers: list[str],
) -> list[tuple[int, str]]:
    """Resolve each ``--workflow`` identifier to a ``(id, display_name)`` pair.

    Per ADR 0010, identifiers are matched in this order — first match wins:
    1. exact ``path`` (e.g. ``.github/workflows/ci.yml``);
    2. exact basename of ``path`` (e.g. ``ci.yml``);
    3. exact ``name`` (the YAML ``name:`` display string);
    4. ``str(id)`` (the numeric id rendered as a string).

    An unmatched identifier exits ``1`` with a stderr message listing the
    candidate values for the repo, so a typo fails loud rather than producing
    an empty-window warning.
    """
    workflows = _list_workflows(client, cache, owner, repo)

    by_path: dict[str, dict[str, Any]] = {}
    by_basename: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for wf in workflows:
        path = wf.get("path") or ""
        if path:
            by_path.setdefault(path, wf)
            by_basename.setdefault(path.rsplit("/", 1)[-1], wf)
        name = wf.get("name")
        if name:
            by_name.setdefault(name, wf)
        wf_id = wf.get("id")
        if wf_id is not None:
            by_id.setdefault(str(wf_id), wf)

    resolved: list[tuple[int, str]] = []
    unmatched: list[str] = []
    seen_ids: set[int] = set()
    for identifier in identifiers:
        match = (
            by_path.get(identifier)
            or by_basename.get(identifier)
            or by_name.get(identifier)
            or by_id.get(identifier)
        )
        if match is None:
            unmatched.append(identifier)
            continue
        wf_id = int(match["id"])
        if wf_id in seen_ids:
            continue
        seen_ids.add(wf_id)
        resolved.append((wf_id, match.get("name") or match.get("path") or str(wf_id)))

    if unmatched:
        print(
            f"error: unknown workflow(s): {', '.join(repr(u) for u in unmatched)}.",
            file=sys.stderr,
        )
        if workflows:
            print("Available workflows:", file=sys.stderr)
            for wf in workflows:
                name = wf.get("name") or "(unnamed)"
                path = wf.get("path") or "(no path)"
                print(f"  - {name}  [{path}]  (id={wf.get('id')})", file=sys.stderr)
        else:
            print(
                "  (this repository has no workflows configured)",
                file=sys.stderr,
            )
        raise typer.Exit(code=1)

    return resolved


def _fetch_runs_for_workflows(
    client: GitHubClient,
    cache: Cache,
    owner: str,
    repo: str,
    branch: str,
    since_iso: str,
    resolved_workflows: list[tuple[int, str]],
) -> list[dict[str, Any]]:
    """Return aggregated runs for the resolved workflows; per-workflow cached.

    Each workflow gets its own cache entry under the existing ``runs`` kind,
    keyed by ``runs_{o}_{r}_{branch}_{since_iso}_w{workflow_id}.json`` per
    ADR 0010. Misses are dispatched through ``fetch_runs_for_workflows``.
    """
    aggregated: list[dict[str, Any]] = []
    misses: list[int] = []
    for workflow_id, _ in resolved_workflows:
        cache_key = key_runs(owner, repo, branch, since_iso, workflow_id)
        cached = cache.get(cache_key, "runs")
        if cached is not None:
            aggregated.extend(cached)
        else:
            misses.append(workflow_id)

    if misses:
        params = {"branch": branch, "created": f">={since_iso}"}
        fresh = fetch_runs_for_workflows(client, owner, repo, misses, params)
        for workflow_id, runs in fresh.items():
            cache.put(
                key_runs(owner, repo, branch, since_iso, workflow_id),
                "runs",
                runs,
                ttl_for_runs_list(),
            )
            aggregated.extend(runs)

    return aggregated


def _fetch_jobs(
    client: GitHubClient,
    cache: Cache,
    owner: str,
    repo: str,
    run_ids: Iterable[int],
) -> dict[int, dict[str, Any]]:
    """Return the jobs payload for each run id; cache-aware before fan-out.

    Hits the cache first; only cache misses are dispatched to the threadpool.
    Newly fetched payloads are written back with status-aware TTLs (immutable
    when every job is completed, else 3600s per ADR 0002).
    """
    results: dict[int, dict[str, Any]] = {}
    misses: list[int] = []
    for run_id in run_ids:
        cached = cache.get(key_jobs(owner, repo, run_id), "jobs")
        if cached is not None:
            results[run_id] = cached
        else:
            misses.append(run_id)

    if misses:
        fresh = fetch_jobs_for_runs(client, owner, repo, misses)
        for run_id, payload in fresh.items():
            cache.put(
                key_jobs(owner, repo, run_id),
                "jobs",
                payload,
                ttl_for_jobs(payload),
            )
            results[run_id] = payload

    return results


def _score_all_tests(
    parsed_runs: list[Run],
    jobs_payloads: dict[int, dict[str, Any]],
    now: datetime,
) -> tuple[list, list]:
    """Group runs+jobs by ``job.name``, score eligible groups, bin the rest.

    Returns ``(test_scores, insufficient)``: test_scores sorted by
    ``flakiness_index`` descending so the most-flaky tests render first.
    """
    runs_by_id = {r.id: r for r in parsed_runs}
    by_job_name: dict[str, dict[str, list]] = {}

    for run_id, payload in jobs_payloads.items():
        run = runs_by_id.get(run_id)
        if run is None:
            continue
        for raw_job in payload.get("jobs", []):
            job = Job.from_api(raw_job)
            bucket = by_job_name.setdefault(job.name, {"runs": [], "jobs": []})
            bucket["runs"].append(run)
            bucket["jobs"].append(job)

    test_scores = []
    insufficient = []
    for name, group in by_job_name.items():
        run_count = len(group["runs"])
        if run_count < MIN_RUNS_FOR_SCORING:
            insufficient.append(InsufficientData(id=name, run_count=run_count))
            continue
        test_scores.append(
            score_test(
                test_id=name,
                job_name=name,
                runs=group["runs"],
                jobs=group["jobs"],
                commits_by_sha=None,
                now=now,
            )
        )

    test_scores.sort(key=lambda t: t.flakiness_index, reverse=True)
    return test_scores, insufficient


def _empty_report(
    repo: str,
    branch: str,
    now: datetime,
    since_delta: timedelta,
    workflows: tuple[str, ...] = (),
) -> DiscoveryReport:
    """Build the empty-window report so callers can still render JSON cleanly."""
    return DiscoveryReport(
        meta=Meta(
            repo=repo,
            branch=branch,
            generated_at=now,
            lookback_days=max(1, since_delta.days),
            total_runs_analysed=0,
            glitch_version=__version__,
            workflows=workflows,
        ),
        tests=(),
        insufficient_data=(),
    )


def _emit(report: DiscoveryReport, output: OutputFormat) -> None:
    """Write the report to stdout in the requested format."""
    if output is OutputFormat.json:
        print(to_json(report))
    else:
        render_table(report)
