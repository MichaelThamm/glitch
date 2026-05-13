"""Per-test heuristic computations and normalisation (ADR 0005).

Each heuristic consumes a single test's runs and/or jobs (i.e. one ``job.name``
group) and returns a ``float`` in ``[0, 1]``. The mappings are the fixed
thresholds defined in ADR 0005:

- volatility: identity (already a ratio)
- retry_rate: identity (already a ratio)
- timing_variance: ``min(1.0, cv / 0.5)``
- change_independence: identity, with a permissive Phase-1 default

Recency decay across runs is *not* handled here — see ADR 0006. These are
pure functions, stdlib only.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence

from glitch.discover.models import Commit, Heuristics, Job, Run


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


__all__ = [
    "change_independence",
    "heuristics_for_test",
    "raw_score",
    "retry_rate",
    "timing_variance",
    "volatility",
]
