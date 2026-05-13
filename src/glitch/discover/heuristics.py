"""Per-test heuristic computations, normalisation, and scoring (ADRs 0005, 0006).

Each heuristic consumes a single test's runs and/or jobs (i.e. one ``job.name``
group) and returns a ``float`` in ``[0, 1]``. The mappings are the fixed
thresholds defined in ADR 0005:

- volatility: identity (already a ratio)
- retry_rate: identity (already a ratio)
- timing_variance: ``min(1.0, cv / 0.5)``
- change_independence: identity, with a permissive Phase-1 default

ADR 0006 adds recency-decay weighting (exponential, half-life 14 days) and the
high-level ``final_score`` / ``score_test`` aggregators that turn a sequence of
runs into a ``TestScore``. These are all pure functions, stdlib only.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from datetime import datetime

from glitch.discover.models import Commit, Heuristics, Job, Run, TestScore


# --- ADR 0006 constants -----------------------------------------------------

HALF_LIFE_DAYS = 14.0
"""Recency half-life in days. After ``HALF_LIFE_DAYS`` a run's weight halves."""

DECAY_K = HALF_LIFE_DAYS / math.log(2)
"""Decay constant ``k`` such that ``exp(-Δdays / k)`` halves at ``HALF_LIFE_DAYS``.

Approximately ``20.2`` days for the default 14-day half-life.
"""


# --- Individual heuristics --------------------------------------------------


def volatility(runs: Sequence[Run]) -> float:
    """Fraction of adjacent same-SHA run pairs that flipped conclusion.

    Runs are grouped by ``head_sha``; within each group of size >= 2 we sort
    by ``created_at`` and count adjacent pairs whose ``conclusion`` differs.
    The ratio is aggregated across all eligible SHA-groups (groups with < 2
    runs contribute neither flips nor pairs). Already in ``[0, 1]``.
    """
    by_sha: dict[str, list[Run]] = {}
    for run in runs:
        by_sha.setdefault(run.head_sha, []).append(run)

    total_flips = 0
    total_pairs = 0
    for group in by_sha.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda r: r.created_at)
        for prev, curr in zip(ordered, ordered[1:], strict=False):
            total_pairs += 1
            if prev.conclusion != curr.conclusion:
                total_flips += 1

    if total_pairs == 0:
        return 0.0
    return total_flips / total_pairs


def retry_rate(runs: Sequence[Run]) -> float:
    """Fraction of runs that succeeded only on a retry attempt.

    A "passed on retry" run is one with ``run_attempt > 1`` and
    ``conclusion == "success"``. Already in ``[0, 1]``.
    """
    total = len(runs)
    if total == 0:
        return 0.0
    passed_on_retry = sum(
        1 for r in runs if r.run_attempt > 1 and r.conclusion == "success"
    )
    return passed_on_retry / total


def timing_variance(jobs: Sequence[Job]) -> float:
    """Coefficient of variation of job durations, capped per ADR 0005.

    Considers only jobs with both ``started_at`` and ``completed_at`` set.
    Uses population stdev (``statistics.pstdev``). Returns ``0.0`` if fewer
    than two valid durations are available or if the mean is zero (no
    meaningful CV). The raw ``cv = sigma / mu`` is then mapped via
    ``min(1.0, cv / 0.5)``.
    """
    durations: list[float] = []
    for job in jobs:
        if job.started_at is None or job.completed_at is None:
            continue
        durations.append((job.completed_at - job.started_at).total_seconds())

    if len(durations) < 2:
        return 0.0
    mu = statistics.fmean(durations)
    if mu == 0:
        return 0.0
    sigma = statistics.pstdev(durations)
    cv = sigma / mu
    return min(1.0, cv / 0.5)


def change_independence(
    runs: Sequence[Run],
    commits_by_sha: Mapping[str, Commit] | None = None,
) -> float:
    """Failure rate, under ADR 0005's permissive Phase-1 default.

    The ADR's formula is ``failures_on_unrelated_commits / total_failures``,
    but with no path-scoping manifest configured every failure counts as
    change-independent, so the formula collapses to a constant ``1.0`` for
    any non-zero failure count. The ADR's prose ("effectively reduces to
    'failure rate'") clarifies the actual intent, so we implement that:
    ``failures / total_runs`` where a failure is any concluded run whose
    ``conclusion != "success"``. In-progress runs (``conclusion is None``)
    are excluded from both numerator and denominator since they have no
    verdict yet.

    The ``commits_by_sha`` parameter is accepted but unused in Phase 1; it
    marks the seam where a future ADR will introduce the path-scoping
    manifest that makes the ADR's formula non-degenerate.
    """
    # commits_by_sha intentionally unused — see docstring.
    del commits_by_sha

    concluded = [r for r in runs if r.conclusion is not None]
    if not concluded:
        return 0.0
    failures = sum(1 for r in concluded if r.conclusion != "success")
    return failures / len(concluded)


# --- Aggregation ------------------------------------------------------------


def heuristics_for_test(
    runs: Sequence[Run],
    jobs: Sequence[Job],
    commits_by_sha: Mapping[str, Commit] | None = None,
) -> Heuristics:
    """Compute all four heuristics for a single test and package them."""
    return Heuristics(
        volatility=volatility(runs),
        retry_rate=retry_rate(runs),
        timing_variance=timing_variance(jobs),
        change_independence=change_independence(runs, commits_by_sha),
    )


def raw_score(h: Heuristics) -> float:
    """Equal-weight mean of the four heuristic scores.

    Each input is in ``[0, 1]``, so the result is in ``[0, 1]``. Recency
    weighting across runs is handled separately (see ADR 0006).
    """
    return (
        h.volatility + h.retry_rate + h.timing_variance + h.change_independence
    ) / 4


# --- ADR 0006: recency decay + final aggregation ---------------------------


def recency_weight(run_created_at: datetime, now: datetime) -> float:
    """Exponential-decay weight for a run, half-life ``HALF_LIFE_DAYS``.

    ``weight = exp(-Δdays / DECAY_K)`` where ``Δdays`` is the difference
    between ``now`` and ``run_created_at`` in days. A run at ``now`` weighs
    ``1.0``; at the half-life it weighs ``0.5``.

    Future-dated ``run_created_at`` (``Δdays < 0``) yields a weight ``> 1.0``;
    the ADR does not pin behaviour for this case, so we let ``math.exp`` speak
    for itself and treat the caller's clock as the contract. In normal flow
    ``now`` is captured once per invocation (matching ``meta.generated_at``),
    so this only matters under clock skew between the runner and GitHub.
    """
    delta_days = (now - run_created_at).total_seconds() / 86400.0
    return math.exp(-delta_days / DECAY_K)


def final_score(
    per_run_scores: Sequence[tuple[float, datetime]],
    now: datetime,
) -> float:
    """Recency-weighted mean of per-run raw scores.

    ``per_run_scores`` is a sequence of ``(raw_score, run_created_at)`` pairs
    for a single test. Each run contributes ``w_i = recency_weight(t_i, now)``,
    and the return value is ``Σ(w_i * raw_score_i) / Σ(w_i)``.

    Returns ``0.0`` when ``per_run_scores`` is empty so the caller never has to
    guard the boundary; ADR 0006 notes that the spec's 3-run minimum already
    guarantees ``Σw > 0`` in the normal pipeline, but defending here keeps the
    function safe to call in isolation (tests, future call sites).
    """
    if not per_run_scores:
        return 0.0
    weighted_sum = 0.0
    weight_total = 0.0
    for raw, created_at in per_run_scores:
        w = recency_weight(created_at, now)
        weighted_sum += w * raw
        weight_total += w
    # weight_total > 0 is guaranteed for any non-empty input because exp(...)
    # is strictly positive for all finite inputs.
    return weighted_sum / weight_total


def score_test(
    test_id: str,
    job_name: str,
    runs: Sequence[Run],
    jobs: Sequence[Job],
    commits_by_sha: Mapping[str, Commit] | None,
    now: datetime,
) -> TestScore:
    """Compose a ``TestScore`` for one test from its runs, jobs, and commits.

    Thin orchestrator: derives the test-level ``Heuristics`` via
    ``heuristics_for_test``, projects the single ``raw_score`` across each
    run with recency weighting via ``final_score``, and packages the
    ``trend`` / ``last_failed_at`` / ``run_count`` fields.

    AMBIGUITY (ADR 0005 + ADR 0006): the spec defines ``raw_score(test)`` as
    a single test-level number (mean of four heuristics aggregated over all
    runs), then defines ``final_score(test) = weighted_mean(raw_score,
    weight=recency_multiplier) per run``. Taken literally, the weighted mean
    of a *constant* (the same test-level ``raw_score`` repeated per run)
    collapses to that constant — ``Σ(w_i · c) / Σ(w_i) = c`` — so the
    recency multiplier becomes a mathematical no-op in Phase 1. The only
    interpretation that makes recency *matter* is to weight per-run signals
    rather than the aggregate, but that contradicts the spec's definition of
    ``raw_score`` as test-level. We proceed with the literal reading so the
    recency machinery is wired and exercised, and flag this for a follow-up
    ADR to resolve (likely by redefining ``raw_score`` per-run, or by moving
    recency into the heuristic inputs themselves).
    """
    h = heuristics_for_test(runs, jobs, commits_by_sha)
    test_raw = raw_score(h)
    # Per the AMBIGUITY note above: raw_score is test-level, so every per-run
    # entry uses the same value. The weighted-mean collapses to test_raw in
    # Phase 1; the recency wiring is still exercised end-to-end.
    per_run_scores: list[tuple[float, datetime]] = [
        (test_raw, r.created_at) for r in runs
    ]
    flakiness_index = final_score(per_run_scores, now)

    # trend: last up-to-5 runs by created_at, success -> "pass", else "fail".
    ordered = sorted(runs, key=lambda r: r.created_at)
    tail = ordered[-5:]
    trend = tuple("pass" if r.conclusion == "success" else "fail" for r in tail)

    # last_failed_at: max created_at among concluded non-success runs.
    failure_times = [
        r.created_at
        for r in runs
        if r.conclusion is not None and r.conclusion != "success"
    ]
    last_failed_at = max(failure_times) if failure_times else None

    return TestScore(
        id=test_id,
        job_name=job_name,
        flakiness_index=flakiness_index,
        run_count=len(runs),
        heuristics=h,
        trend=trend,
        last_failed_at=last_failed_at,
    )


__all__ = [
    "DECAY_K",
    "HALF_LIFE_DAYS",
    "change_independence",
    "final_score",
    "heuristics_for_test",
    "raw_score",
    "recency_weight",
    "retry_rate",
    "score_test",
    "timing_variance",
    "volatility",
]
