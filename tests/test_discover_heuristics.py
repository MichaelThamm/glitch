"""Tests for `glitch.discover.heuristics` — ADR 0005.

Covers each of the four heuristics at their boundaries, plus the
`heuristics_for_test` aggregator and `raw_score` mean. Pure functions, no
HTTP — fixtures are hand-built `Run` / `Job` dataclasses.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from glitch.discover.heuristics import (
    change_independence,
    heuristics_for_test,
    raw_score,
    retry_rate,
    timing_variance,
    volatility,
)
from glitch.discover.models import Heuristics, Job, Run

# --- Helper factories -------------------------------------------------------

_EPOCH = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)


def make_run(
    sha: str,
    conclusion: str | None,
    attempt: int = 1,
    created_at: datetime | None = None,
) -> Run:
    """Build a `Run` with sensible defaults for the fields the heuristics ignore."""
    if created_at is None:
        created_at = _EPOCH
    return Run(
        id=0,
        name="ci",
        head_sha=sha,
        head_branch="main",
        status="completed",
        conclusion=conclusion,
        created_at=created_at,
        updated_at=created_at,
        run_attempt=attempt,
    )


def make_job(
    name: str,
    started_at: datetime | None,
    completed_at: datetime | None,
    conclusion: str = "success",
) -> Job:
    """Build a `Job` carrying just the timestamps `timing_variance` cares about."""
    return Job(
        id=0,
        run_id=0,
        name=name,
        status="completed",
        conclusion=conclusion,
        started_at=started_at,
        completed_at=completed_at,
    )


# --- volatility -------------------------------------------------------------


def test_volatility_empty_runs_returns_zero() -> None:
    assert volatility([]) == 0.0


def test_volatility_single_run_on_one_sha_returns_zero() -> None:
    runs = [make_run("a", "success")]
    assert volatility(runs) == 0.0


def test_volatility_two_runs_same_sha_same_conclusion_is_zero() -> None:
    runs = [
        make_run("a", "success", created_at=_EPOCH),
        make_run("a", "success", created_at=_EPOCH + timedelta(minutes=1)),
    ]
    assert volatility(runs) == 0.0


def test_volatility_two_runs_same_sha_different_conclusion_is_one() -> None:
    runs = [
        make_run("a", "success", created_at=_EPOCH),
        make_run("a", "failure", created_at=_EPOCH + timedelta(minutes=1)),
    ]
    assert volatility(runs) == 1.0


def test_volatility_three_runs_pass_fail_pass_two_flips_two_pairs() -> None:
    runs = [
        make_run("a", "success", created_at=_EPOCH),
        make_run("a", "failure", created_at=_EPOCH + timedelta(minutes=1)),
        make_run("a", "success", created_at=_EPOCH + timedelta(minutes=2)),
    ]
    assert volatility(runs) == 1.0  # 2 flips / 2 pairs


def test_volatility_mixed_shas_aggregates_flips_and_pairs() -> None:
    # SHA a: pass, fail (1 flip / 1 pair)
    # SHA b: pass, pass, pass (0 flips / 2 pairs)
    runs = [
        make_run("a", "success", created_at=_EPOCH),
        make_run("a", "failure", created_at=_EPOCH + timedelta(minutes=1)),
        make_run("b", "success", created_at=_EPOCH),
        make_run("b", "success", created_at=_EPOCH + timedelta(minutes=1)),
        make_run("b", "success", created_at=_EPOCH + timedelta(minutes=2)),
    ]
    assert volatility(runs) == 1 / 3


def test_volatility_singleton_sha_contributes_nothing() -> None:
    # SHA a has only 1 run (ineligible); SHA b has [pass, fail].
    runs = [
        make_run("a", "success", created_at=_EPOCH),
        make_run("b", "success", created_at=_EPOCH),
        make_run("b", "failure", created_at=_EPOCH + timedelta(minutes=1)),
    ]
    assert volatility(runs) == 1.0  # 1 flip / 1 pair


def test_volatility_sorts_by_created_at_regardless_of_input_order() -> None:
    # If input order were used naively we'd see [fail, success, fail] and
    # count 2 flips; chronologically it's success → fail → success, still 2.
    # Use a non-symmetric sequence so order actually matters.
    early = _EPOCH
    mid = _EPOCH + timedelta(minutes=1)
    late = _EPOCH + timedelta(minutes=2)
    # Chronological order: success, success, failure → 1 flip / 2 pairs
    # If we *don't* sort, the input order below would yield: failure, success, success → 1/2 too.
    # Pick an order where the wrong answer differs: chrono = [s, f, s] = 2/2 = 1.0;
    # naive input order [f, s, s] = 1/2 = 0.5.
    runs = [
        make_run("a", "failure", created_at=mid),
        make_run("a", "success", created_at=late),
        make_run("a", "success", created_at=early),
    ]
    assert volatility(runs) == 1.0


# --- retry_rate -------------------------------------------------------------


def test_retry_rate_zero_runs_returns_zero() -> None:
    assert retry_rate([]) == 0.0


def test_retry_rate_no_retries_is_zero() -> None:
    runs = [make_run("a", "success") for _ in range(5)]
    assert retry_rate(runs) == 0.0


def test_retry_rate_two_of_four_success_on_retry_is_half() -> None:
    runs = [
        make_run("a", "success", attempt=1),
        make_run("b", "success", attempt=2),
        make_run("c", "failure", attempt=1),
        make_run("d", "success", attempt=3),
    ]
    assert retry_rate(runs) == 0.5


def test_retry_rate_excludes_failed_retry() -> None:
    # attempt=2 failure must NOT count toward retry-success.
    runs = [
        make_run("a", "success", attempt=1),
        make_run("b", "failure", attempt=2),
        make_run("c", "success", attempt=1),
        make_run("d", "failure", attempt=3),
    ]
    assert retry_rate(runs) == 0.0


def test_retry_rate_first_attempt_success_does_not_count() -> None:
    runs = [
        make_run("a", "success", attempt=1),
        make_run("b", "success", attempt=1),
    ]
    assert retry_rate(runs) == 0.0


# --- timing_variance --------------------------------------------------------


def test_timing_variance_zero_jobs_returns_zero() -> None:
    assert timing_variance([]) == 0.0


def test_timing_variance_single_job_returns_zero() -> None:
    jobs = [make_job("t", _EPOCH, _EPOCH + timedelta(seconds=60))]
    assert timing_variance(jobs) == 0.0


def test_timing_variance_two_identical_durations_returns_zero() -> None:
    jobs = [
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=60)),
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=60)),
    ]
    assert timing_variance(jobs) == 0.0


def test_timing_variance_ignores_jobs_with_missing_timestamps() -> None:
    # Only one fully-timed job remains → fewer than 2 valid durations → 0.0.
    jobs = [
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=60)),
        make_job("t", None, _EPOCH + timedelta(seconds=60)),
        make_job("t", _EPOCH, None),
        make_job("t", None, None),
    ]
    assert timing_variance(jobs) == 0.0


def test_timing_variance_high_variance_caps_at_one() -> None:
    # Durations 60s, 240s: μ=150, σ=90 (population), cv=0.6 → min(1.0, 0.6/0.5)=1.0
    jobs = [
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=60)),
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=240)),
    ]
    assert timing_variance(jobs) == 1.0


def test_timing_variance_mild_variance_scales_linearly() -> None:
    # Durations 100s, 120s: μ=110, σ=10 (pop), cv≈0.0909 → cv/0.5 ≈ 0.1818
    jobs = [
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=100)),
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=120)),
    ]
    result = timing_variance(jobs)
    assert math.isclose(result, (10 / 110) / 0.5, rel_tol=1e-9)


# --- change_independence ----------------------------------------------------


def test_change_independence_zero_runs_returns_zero() -> None:
    assert change_independence([]) == 0.0


def test_change_independence_all_success_is_zero() -> None:
    runs = [make_run(f"sha{i}", "success") for i in range(3)]
    assert change_independence(runs) == 0.0


def test_change_independence_two_of_four_failed_is_half() -> None:
    runs = [
        make_run("a", "success"),
        make_run("b", "failure"),
        make_run("c", "success"),
        make_run("d", "failure"),
    ]
    assert change_independence(runs) == 0.5


def test_change_independence_excludes_in_progress_runs() -> None:
    # 1 success + 1 in-progress (None) + 2 failures.
    # In-progress is excluded from both numerator and denominator: 2/3.
    runs = [
        make_run("a", "success"),
        make_run("b", None),
        make_run("c", "failure"),
        make_run("d", "failure"),
    ]
    assert math.isclose(change_independence(runs), 2 / 3, rel_tol=1e-9)


def test_change_independence_all_in_progress_returns_zero() -> None:
    runs = [make_run(f"sha{i}", None) for i in range(3)]
    assert change_independence(runs) == 0.0


# --- heuristics_for_test + raw_score ---------------------------------------


def test_heuristics_for_test_returns_normalised_heuristics_instance() -> None:
    # Small realistic mix: 2 SHAs, 1 retry, 2 timed jobs, 1 failure.
    runs = [
        make_run("a", "success", attempt=1, created_at=_EPOCH),
        make_run("a", "failure", attempt=1, created_at=_EPOCH + timedelta(minutes=1)),
        make_run("b", "success", attempt=2, created_at=_EPOCH + timedelta(minutes=2)),
        make_run("c", "success", attempt=1, created_at=_EPOCH + timedelta(minutes=3)),
    ]
    jobs = [
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=100)),
        make_job("t", _EPOCH, _EPOCH + timedelta(seconds=120)),
    ]
    h = heuristics_for_test(runs, jobs)

    assert isinstance(h, Heuristics)
    for value in (h.volatility, h.retry_rate, h.timing_variance, h.change_independence):
        assert 0.0 <= value <= 1.0


def test_raw_score_is_equal_weight_mean_of_four_heuristics() -> None:
    h = Heuristics(
        volatility=0.2,
        retry_rate=0.4,
        timing_variance=0.6,
        change_independence=0.8,
    )
    assert math.isclose(raw_score(h), (0.2 + 0.4 + 0.6 + 0.8) / 4, rel_tol=1e-9)


def test_raw_score_boundaries() -> None:
    zeros = Heuristics(0.0, 0.0, 0.0, 0.0)
    ones = Heuristics(1.0, 1.0, 1.0, 1.0)
    assert raw_score(zeros) == 0.0
    assert raw_score(ones) == 1.0
