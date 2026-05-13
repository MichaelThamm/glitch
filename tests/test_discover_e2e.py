"""End-to-end tests for the discovery pipeline — ADR 0008.

Drives ``glitch discover`` via Typer's ``CliRunner`` against a ``responses``-
mocked GitHub and a ``tmp_path`` cache dir. The original placeholder test
that pinned the entrypoint's ``NotImplementedError`` has been replaced now
that the orchestration in ``_entrypoint.run`` is wired up.

The tests below walk the spec's error-handling table from
``docs/specs/phase-1-discovery.md``:

- happy path → exit 0, spec-shaped JSON, cache envelopes on disk
- ``--output table`` → exit 0, prints a rendered table to stdout
- no auth token → exit 1
- invalid ``--since`` → exit 1
- invalid ``--repo`` → exit 1
- repo not found / 404 → exit 1
- no runs in lookback window → exit 0 + warning
- all tests below 3-run threshold → exit 0 + warning + insufficient_data

A separate, lower-level test still exercises the component public APIs
directly (``responses`` → client → cache → scoring → render) so a regression
in the orchestrator does not mask a regression in the components themselves.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
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

OWNER = "canonical"
REPO = "my-charm"
REPO_FULL = f"{OWNER}/{REPO}"


# --- helpers ---------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run(
    run_id: int,
    head_sha: str,
    conclusion: str | None,
    created_at: datetime,
    *,
    status: str = "completed",
    run_attempt: int = 1,
    name: str = "CI",
) -> dict[str, Any]:
    return {
        "id": run_id,
        "name": name,
        "head_sha": head_sha,
        "head_branch": "main",
        "status": status,
        "conclusion": conclusion,
        "created_at": _iso(created_at),
        "updated_at": _iso(created_at + timedelta(minutes=15)),
        "run_attempt": run_attempt,
    }


def _make_job(
    job_id: int,
    run_id: int,
    name: str,
    started_at: datetime,
    completed_at: datetime,
    conclusion: str = "success",
) -> dict[str, Any]:
    return {
        "id": job_id,
        "run_id": run_id,
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "started_at": _iso(started_at),
        "completed_at": _iso(completed_at),
    }


def _register_repo(default_branch: str = "main") -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/repos/{OWNER}/{REPO}",
        json={"default_branch": default_branch},
        status=200,
    )


def _register_runs(runs: list[dict[str, Any]]) -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/repos/{OWNER}/{REPO}/actions/runs",
        json={"total_count": len(runs), "workflow_runs": runs},
        status=200,
    )


def _register_jobs_for_run(run_id: int, jobs: list[dict[str, Any]]) -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/repos/{OWNER}/{REPO}/actions/runs/{run_id}/jobs",
        json={"total_count": len(jobs), "jobs": jobs},
        status=200,
    )


# --- 1. Happy path through the Typer entrypoint ----------------------------


@responses.activate
def test_typer_happy_path_emits_spec_shaped_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``glitch discover --output json`` end-to-end produces the spec JSON."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    test_name = "integration (test_deploy_local)"

    runs = []
    jobs_per_run = {}
    # Three runs across two SHAs (a flip on the second SHA) so the scorer has
    # enough data to clear the 3-run minimum.
    for idx in range(3):
        run_id = 1000 + idx
        sha = "a" * 40 if idx == 0 else "b" * 40
        conclusion = "success" if idx != 2 else "failure"
        run_payload = _make_run(
            run_id, sha, conclusion, now - timedelta(days=idx + 1)
        )
        runs.append(run_payload)
        jobs_per_run[run_id] = [
            _make_job(
                job_id=9000 + idx,
                run_id=run_id,
                name=test_name,
                started_at=now - timedelta(days=idx + 1),
                completed_at=now - timedelta(days=idx + 1) + timedelta(minutes=10),
                conclusion=conclusion,
            )
        ]

    _register_repo()
    _register_runs(runs)
    for run_id, jobs in jobs_per_run.items():
        _register_jobs_for_run(run_id, jobs)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            REPO_FULL,
            "--since",
            "30d",
            "--output",
            "json",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )

    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"meta", "tests", "insufficient_data"}
    assert payload["meta"]["repo"] == REPO_FULL
    assert payload["meta"]["branch"] == "main"
    assert payload["meta"]["total_runs_analysed"] == 3
    assert payload["meta"]["glitch_version"] == "0.1.0"
    assert len(payload["tests"]) == 1
    entry = payload["tests"][0]
    assert entry["id"] == test_name
    assert entry["run_count"] == 3
    assert set(entry["heuristics"].keys()) == {
        "volatility",
        "retry_rate",
        "timing_variance",
        "change_independence",
    }
    assert payload["insufficient_data"] == []


@responses.activate
def test_typer_happy_path_writes_cache_envelopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run-list and jobs payloads land on disk wrapped in the ADR-0002 envelope."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)

    runs = [
        _make_run(2001, "a" * 40, "success", now - timedelta(days=2)),
        _make_run(2002, "b" * 40, "failure", now - timedelta(days=1)),
        _make_run(2003, "c" * 40, "success", now - timedelta(hours=12)),
    ]
    _register_repo()
    _register_runs(runs)
    for run_payload in runs:
        _register_jobs_for_run(
            run_payload["id"],
            [
                _make_job(
                    job_id=run_payload["id"] + 1,
                    run_id=run_payload["id"],
                    name="integration (test_x)",
                    started_at=now,
                    completed_at=now + timedelta(minutes=10),
                )
            ],
        )

    cache_dir = tmp_path / "cache"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            REPO_FULL,
            "--branch",
            "main",
            "--cache-dir",
            str(cache_dir),
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout

    # Run-list page envelope exists with kind="runs".
    runs_files = list(cache_dir.glob("runs_*.json"))
    assert len(runs_files) == 1
    envelope = json.loads(runs_files[0].read_text())
    assert envelope["kind"] == "runs"
    assert envelope["ttl_seconds"] == 300
    assert isinstance(envelope["data"], list)
    assert len(envelope["data"]) == 3

    # Each run's jobs envelope is written with kind="jobs".
    for run_payload in runs:
        path = cache_dir / key_jobs(OWNER, REPO, run_payload["id"])
        assert path.exists(), f"missing cache file for run {run_payload['id']}"
        env = json.loads(path.read_text())
        assert env["kind"] == "jobs"
        # All jobs completed → null TTL (immutable).
        assert env["ttl_seconds"] is None


@responses.activate
def test_typer_table_output_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--output table`` writes a rendered table to stdout."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    test_name = "integration (test_deploy_local)"
    runs = [
        _make_run(3000 + i, "a" * 40, "success", now - timedelta(days=i + 1))
        for i in range(3)
    ]
    _register_repo()
    _register_runs(runs)
    for run_payload in runs:
        _register_jobs_for_run(
            run_payload["id"],
            [
                _make_job(
                    job_id=run_payload["id"] + 5000,
                    run_id=run_payload["id"],
                    name=test_name,
                    started_at=now,
                    completed_at=now + timedelta(minutes=10),
                )
            ],
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            REPO_FULL,
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0
    # The table renderer prints the column header and trend arrows; the test
    # name may be truncated by the rendered column width, so we look for a
    # stable prefix rather than the full string.
    stdout = result.stdout
    assert "Rank" in stdout
    assert "Trend" in stdout
    assert "integrati" in stdout  # truncated form of the test name is fine
    assert "↑" in stdout  # all-success trend arrow


# --- 2. Error-handling table -----------------------------------------------


def test_no_auth_token_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ``GITHUB_TOKEN`` and no ``gh`` available → exit 1 with stderr."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("PATH", "")  # hide `gh` so the fallback also fails

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            REPO_FULL,
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 1
    assert "GITHUB_TOKEN" in (result.stderr or "")


def test_invalid_since_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid ``--since`` value short-circuits before any HTTP calls."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            REPO_FULL,
            "--since",
            "1.5d",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 1
    assert "invalid duration" in (result.stderr or "")


def test_invalid_repo_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed ``--repo`` value exits 1 with a clear message."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            "not-owner-slash-repo",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 1
    assert "owner/repo" in (result.stderr or "")


@responses.activate
def test_repo_not_found_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 404 from GitHub surfaces the HTTP error and exits 1."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    responses.add(
        responses.GET,
        f"{BASE_URL}/repos/{OWNER}/{REPO}",
        json={"message": "Not Found"},
        status=404,
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            REPO_FULL,
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 1
    assert "404" in (result.stderr or "")


@responses.activate
def test_no_runs_in_window_exits_zero_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty run list → exit 0, warning on stderr, empty JSON payload."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    _register_repo()
    _register_runs([])

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            REPO_FULL,
            "--output",
            "json",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0
    assert "no workflow runs" in (result.stderr or "").lower()
    payload = json.loads(result.stdout)
    assert payload["tests"] == []
    assert payload["insufficient_data"] == []
    assert payload["meta"]["total_runs_analysed"] == 0


@responses.activate
def test_all_tests_below_threshold_warns_and_lists_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs only → all tests bucketed as insufficient_data; exit 0 + warning."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    runs = [
        _make_run(5000, "a" * 40, "success", now - timedelta(days=2)),
        _make_run(5001, "b" * 40, "failure", now - timedelta(days=1)),
    ]
    _register_repo()
    _register_runs(runs)
    for run_payload in runs:
        _register_jobs_for_run(
            run_payload["id"],
            [
                _make_job(
                    job_id=run_payload["id"] + 9000,
                    run_id=run_payload["id"],
                    name="integration (only_two_runs)",
                    started_at=now,
                    completed_at=now + timedelta(minutes=5),
                )
            ],
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover",
            "--repo",
            REPO_FULL,
            "--output",
            "json",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0
    assert "minimum-runs threshold" in (result.stderr or "").lower()
    payload = json.loads(result.stdout)
    assert payload["tests"] == []
    assert payload["insufficient_data"] == [
        {"id": "integration (only_two_runs)", "run_count": 2}
    ]


# --- 3. Component-pipeline e2e (kept from the ADR 0008 scaffolding) --------


@responses.activate
def test_pipeline_components_compose_to_spec_shaped_json(
    fixtures_dir: Path,
    tmp_path: Path,
) -> None:
    """Compose the public component APIs end-to-end without the entrypoint.

    Kept as an independent check so a regression in the orchestrator does not
    mask a regression in the component seams themselves.
    """
    runs_payload = json.loads((fixtures_dir / "runs_page_1.json").read_text())
    jobs_payload = json.loads((fixtures_dir / "jobs_run_123.json").read_text())

    owner, repo = "canonical", "my-charm"
    runs_url = f"{BASE_URL}/repos/{owner}/{repo}/actions/runs"
    jobs_url = f"{BASE_URL}/repos/{owner}/{repo}/actions/runs/123/jobs"

    responses.add(responses.GET, runs_url, json=runs_payload, status=200)
    responses.add(responses.GET, jobs_url, json=jobs_payload, status=200)

    client = GitHubClient(session=build_session("test-token"))

    raw_runs: list[dict] = []
    for page in client.paginate(f"/repos/{owner}/{repo}/actions/runs"):
        raw_runs.extend(page.json()["workflow_runs"])
    parsed_runs = [Run.from_api(item) for item in raw_runs]
    assert len(parsed_runs) == 2

    jobs_response = client.get(f"/repos/{owner}/{repo}/actions/runs/123/jobs")
    raw_jobs = jobs_response.json()["jobs"]
    parsed_jobs = [Job.from_api(item) for item in raw_jobs]
    assert len(parsed_jobs) == 2

    cache = Cache(tmp_path / "cache")
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
    cached_run = cache.get(key_run(owner, repo, 123), "run")
    cached_jobs = cache.get(key_jobs(owner, repo, 123), "jobs")
    assert cached_run is not None
    assert cached_run["id"] == 123
    assert cached_jobs is not None
    assert cached_jobs["total_count"] == 2

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

    upgrade_name = "integration (test_upgrade_path)"
    insufficient = InsufficientData(id=upgrade_name, run_count=1)

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
    payload = json.loads(to_json(report))
    assert set(payload.keys()) == {"meta", "tests", "insufficient_data"}
    assert payload["meta"]["repo"] == f"{owner}/{repo}"
    assert payload["meta"]["generated_at"] == "2026-05-13T10:00:00Z"


# --- 4. ADR 0010 — Workflow filter tests -----------------------------------

# Shared workflow listing fixture for resolution tests.
_WORKFLOWS = [
    {
        "id": 101,
        "name": "CI",
        "path": ".github/workflows/ci.yml",
        "state": "active",
    },
    {
        "id": 202,
        "name": "Integration",
        "path": ".github/workflows/integration.yml",
        "state": "active",
    },
]


def _register_workflows(workflows: list[dict] | None = None) -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/repos/{OWNER}/{REPO}/actions/workflows",
        json={"total_count": len(workflows or _WORKFLOWS), "workflows": workflows or _WORKFLOWS},
        status=200,
    )


def _register_workflow_runs(workflow_id: int, runs: list[dict]) -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/repos/{OWNER}/{REPO}/actions/workflows/{workflow_id}/runs",
        json={"total_count": len(runs), "workflow_runs": runs},
        status=200,
    )


@responses.activate
def test_workflow_flag_resolve_by_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--workflow .github/workflows/ci.yml`` resolves by full path."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)

    runs = [
        _make_run(7000 + i, "a" * 40, "success", now - timedelta(days=i + 1))
        for i in range(3)
    ]
    _register_repo()
    _register_workflows()
    _register_workflow_runs(101, runs)
    for r in runs:
        _register_jobs_for_run(
            r["id"],
            [_make_job(r["id"] + 5000, r["id"], "build", now, now + timedelta(minutes=5))],
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover", "--repo", REPO_FULL,
            "--workflow", ".github/workflows/ci.yml",
            "--output", "json",
            "--cache-dir", str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert payload["meta"]["workflows"] == ["CI"]


@responses.activate
def test_workflow_flag_resolve_by_basename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--workflow ci.yml`` resolves by basename of the path."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)

    runs = [
        _make_run(8000 + i, "b" * 40, "success", now - timedelta(days=i + 1))
        for i in range(3)
    ]
    _register_repo()
    _register_workflows()
    _register_workflow_runs(101, runs)
    for r in runs:
        _register_jobs_for_run(
            r["id"],
            [_make_job(r["id"] + 5000, r["id"], "build", now, now + timedelta(minutes=5))],
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover", "--repo", REPO_FULL,
            "--workflow", "ci.yml",
            "--output", "json",
            "--cache-dir", str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert payload["meta"]["workflows"] == ["CI"]


@responses.activate
def test_workflow_flag_resolve_by_display_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--workflow CI`` resolves by display name."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)

    runs = [
        _make_run(8500 + i, "c" * 40, "success", now - timedelta(days=i + 1))
        for i in range(3)
    ]
    _register_repo()
    _register_workflows()
    _register_workflow_runs(101, runs)
    for r in runs:
        _register_jobs_for_run(
            r["id"],
            [_make_job(r["id"] + 5000, r["id"], "build", now, now + timedelta(minutes=5))],
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover", "--repo", REPO_FULL,
            "--workflow", "CI",
            "--output", "json",
            "--cache-dir", str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert payload["meta"]["workflows"] == ["CI"]


@responses.activate
def test_workflow_flag_resolve_by_numeric_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--workflow 101`` resolves by str(id)."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)

    runs = [
        _make_run(8800 + i, "d" * 40, "success", now - timedelta(days=i + 1))
        for i in range(3)
    ]
    _register_repo()
    _register_workflows()
    _register_workflow_runs(101, runs)
    for r in runs:
        _register_jobs_for_run(
            r["id"],
            [_make_job(r["id"] + 5000, r["id"], "build", now, now + timedelta(minutes=5))],
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover", "--repo", REPO_FULL,
            "--workflow", "101",
            "--output", "json",
            "--cache-dir", str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert payload["meta"]["workflows"] == ["CI"]


@responses.activate
def test_workflow_flag_unmatched_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unknown workflow identifier exits 1 with stderr listing candidates."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    _register_repo()
    _register_workflows()

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover", "--repo", REPO_FULL,
            "--workflow", "nope.yml",
            "--cache-dir", str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 1
    stderr = result.stderr or ""
    assert "nope.yml" in stderr
    assert "CI" in stderr  # lists available workflows


@responses.activate
def test_workflow_flag_dedupe_same_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two identifiers resolving to the same workflow → single entry, one fan-out."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    now = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)

    runs = [
        _make_run(9000 + i, "e" * 40, "success", now - timedelta(days=i + 1))
        for i in range(3)
    ]
    _register_repo()
    _register_workflows()
    _register_workflow_runs(101, runs)
    for r in runs:
        _register_jobs_for_run(
            r["id"],
            [_make_job(r["id"] + 5000, r["id"], "build", now, now + timedelta(minutes=5))],
        )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "discover", "--repo", REPO_FULL,
            "--workflow", "ci.yml",
            "--workflow", "CI",  # same workflow, different identifier
            "--output", "json",
            "--cache-dir", str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)
    # Deduplicated: only one workflow name despite two identifiers.
    assert payload["meta"]["workflows"] == ["CI"]


def test_workflow_flag_shows_in_help() -> None:
    """``--workflow`` appears in ``glitch discover --help``."""
    runner = CliRunner()
    result = runner.invoke(app, ["discover", "--help"])
    assert "--workflow" in result.stdout
