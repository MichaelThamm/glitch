"""End-to-end tests for the discovery pipeline — ADR 0008.

Two tests live here:

1. ``test_discover_cli_currently_raises_not_implemented`` drives the Typer
   ``glitch discover --repo o/r`` surface via ``CliRunner`` and asserts the
   *current* behaviour — exit code 1, ``NotImplementedError`` surfaced. The
   ADR's stated full e2e (assert spec-shaped JSON on stdout, assert cache
   envelopes on disk) cannot be done yet because no ADR has mandated the
   orchestration inside ``_entrypoint.run``; the entrypoint still raises
   ``NotImplementedError``. This test is a deliberate placeholder so the
   CLI surface is exercised in CI today, and a future ADR can replace its
   assertions with the spec-shape / exit-code matrix described in ADR 0008.

2. ``test_pipeline_components_compose_to_spec_shaped_json`` is the real
   end-to-end validation: it wires the component public APIs together as
   the eventual orchestration will — ``responses``-backed ``GitHubClient``
   → ``client.paginate`` → ``Run.from_api`` → ``client.get`` → ``Job.from_api``
   → ``Cache(tmp_path)`` round-trip → ``scoring.score_test`` → assemble a
   ``DiscoveryReport`` → ``render.to_json`` — and asserts the resulting
   JSON matches the spec's top-level shape. No orchestration code is
   invented; only the existing component seams are exercised.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import responses
from typer.testing import CliRunner

from glitch.cli import app
from glitch.discover.cache import (
    Cache,
    key_jobs,
    key_run,
    ttl_for_jobs,
    ttl_for_run,
)
from glitch.discover.client import BASE_URL, GitHubClient, build_session
from glitch.discover.models import (
    DiscoveryReport,
    InsufficientData,
    Job,
    Meta,
    Run,
)
from glitch.discover.render import to_json
from glitch.discover.scoring import score_test


# --- 1. Forward-looking Typer placeholder ----------------------------------
#
# NOTE: this test will expand once the orchestration in
# ``glitch.discover._entrypoint.run`` lands (currently raises
# ``NotImplementedError``). The full ADR-0008 e2e is: drive
# ``glitch discover --repo o/r`` with ``responses`` mocks + a ``tmp_path``
# cache, then assert (a) JSON output shape matches the spec, (b) exit codes
# match the spec's error-handling table, and (c) cache envelopes are
# written to disk. None of that can be asserted while ``run()`` raises
# unconditionally; this placeholder pins the *current* exit-1 contract so
# the CLI wiring is at least exercised in CI today.


def test_discover_cli_currently_raises_not_implemented() -> None:
    """``glitch discover --repo o/r`` exits non-zero and surfaces a NIE.

    The Typer wiring (option parsing, command registration via ``glitch.cli``)
    is real; only the orchestration body is stubbed. ``CliRunner`` captures
    the raised ``NotImplementedError`` and reports a non-zero exit code.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["discover", "--repo", "owner/repo"])

    # Typer surfaces uncaught exceptions as a non-zero exit; the exact code
    # depends on the Click/Typer version, so we only assert "did not succeed".
    assert result.exit_code != 0
    # The exception itself should round-trip out of CliRunner.
    assert isinstance(result.exception, NotImplementedError)
    assert "Phase 1" in str(result.exception)


# --- 2. Component-pipeline end-to-end --------------------------------------


@responses.activate
def test_pipeline_components_compose_to_spec_shaped_json(
    fixtures_dir: Path,
    tmp_path: Path,
) -> None:
    """Compose the public component APIs end-to-end without the entrypoint.

    Exercises: ``responses`` → ``GitHubClient.paginate`` → ``Run.from_api`` →
    ``GitHubClient.get`` → ``Job.from_api`` → ``Cache`` round-trip →
    ``scoring.score_test`` → ``DiscoveryReport`` → ``render.to_json``. The
    final JSON string is parsed and asserted against the spec's top-level
    shape (``meta`` / ``tests`` / ``insufficient_data``).
    """
    # --- fixtures -----------------------------------------------------------
    runs_payload = json.loads((fixtures_dir / "runs_page_1.json").read_text())
    jobs_payload = json.loads((fixtures_dir / "jobs_run_123.json").read_text())

    owner, repo = "canonical", "my-charm"
    runs_url = f"{BASE_URL}/repos/{owner}/{repo}/actions/runs"
    jobs_url = f"{BASE_URL}/repos/{owner}/{repo}/actions/runs/123/jobs"

    # Single-page result — no Link header → paginate stops after one yield.
    responses.add(
        responses.GET,
        runs_url,
        json=runs_payload,
        status=200,
    )
    responses.add(
        responses.GET,
        jobs_url,
        json=jobs_payload,
        status=200,
    )

    # --- client + paginate → Run.from_api ----------------------------------
    client = GitHubClient(session=build_session("test-token"))

    raw_runs: list[dict] = []
    for page in client.paginate(f"/repos/{owner}/{repo}/actions/runs"):
        raw_runs.extend(page.json()["workflow_runs"])
    parsed_runs = [Run.from_api(item) for item in raw_runs]
    assert len(parsed_runs) == 2

    # --- client.get → Job.from_api -----------------------------------------
    jobs_response = client.get(f"/repos/{owner}/{repo}/actions/runs/123/jobs")
    raw_jobs = jobs_response.json()["jobs"]
    parsed_jobs = [Job.from_api(item) for item in raw_jobs]
    assert len(parsed_jobs) == 2

    # --- cache round-trip --------------------------------------------------
    cache = Cache(tmp_path / "cache")
    # Put each raw run individually, then a jobs payload.
    for raw in raw_runs:
        cache.put(
            key_run(owner, repo, raw["id"]),
            "run",
            raw,
            ttl_for_run(raw),
        )
    cache.put(
        key_jobs(owner, repo, 123),
        "jobs",
        jobs_payload,
        ttl_for_jobs(jobs_payload),
    )
    # Read-back proves the envelope was well-formed.
    cached_run = cache.get(key_run(owner, repo, 123), "run")
    cached_jobs = cache.get(key_jobs(owner, repo, 123), "jobs")
    assert cached_run is not None
    assert cached_run["id"] == 123
    assert cached_jobs is not None
    assert cached_jobs["total_count"] == 2

    # --- score_test → TestScore --------------------------------------------
    # Group jobs by name and score each. With only one run per group below
    # the 3-run minimum, real Phase-1 logic would route these to
    # insufficient_data; the test still wants to exercise score_test, so we
    # pick one group, score it, and route the other to insufficient_data.
    by_name: dict[str, list[Job]] = {}
    for job in parsed_jobs:
        by_name.setdefault(job.name, []).append(job)

    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    deploy_name = "integration (test_deploy_local)"
    deploy_score = score_test(
        test_id=deploy_name,
        job_name=deploy_name,
        runs=parsed_runs,
        jobs=by_name[deploy_name],
        commits_by_sha=None,
        now=now,
    )
    assert 0.0 <= deploy_score.flakiness_index <= 1.0
    assert deploy_score.run_count == 2

    upgrade_name = "integration (test_upgrade_path)"
    insufficient = InsufficientData(id=upgrade_name, run_count=1)

    # --- assemble report → render.to_json ----------------------------------
    meta = Meta(
        repo=f"{owner}/{repo}",
        branch="main",
        generated_at=now,
        lookback_days=30,
        total_runs_analysed=len(parsed_runs),
        glitch_version="0.1.0",
    )
    report = DiscoveryReport(
        meta=meta,
        tests=(deploy_score,),
        insufficient_data=(insufficient,),
    )
    rendered = to_json(report)

    # --- spec-shape assertions ---------------------------------------------
    payload = json.loads(rendered)
    assert set(payload.keys()) == {"meta", "tests", "insufficient_data"}

    assert payload["meta"]["repo"] == f"{owner}/{repo}"
    assert payload["meta"]["branch"] == "main"
    assert payload["meta"]["generated_at"] == "2026-05-13T10:00:00Z"
    assert payload["meta"]["lookback_days"] == 30
    assert payload["meta"]["total_runs_analysed"] == 2
    assert payload["meta"]["glitch_version"] == "0.1.0"

    assert len(payload["tests"]) == 1
    test_entry = payload["tests"][0]
    assert test_entry["id"] == deploy_name
    assert test_entry["job_name"] == deploy_name
    assert test_entry["run_count"] == 2
    assert set(test_entry["heuristics"].keys()) == {
        "volatility",
        "retry_rate",
        "timing_variance",
        "change_independence",
    }
    assert isinstance(test_entry["trend"], list)

    assert payload["insufficient_data"] == [
        {"id": upgrade_name, "run_count": 1},
    ]
