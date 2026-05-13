# ADR 0005: Heuristic normalisation

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

The spec lists four scoring heuristics (volatility, retry rate, timing
variance, change-independence) that contribute equally to the raw flakiness
index. It says only: *"All component scores are independently normalised to
`[0, 1]` before averaging."* It does not pin **how** each raw measurement
maps into that range.

The candidate strategies are:

- **Fixed thresholds** — a hardcoded function per heuristic (e.g. "CV of 0.5
  ⇒ 1.0"). Stable, comparable across runs/repos, opinionated.
- **Min-max over the run set** — rescale by the most-flaky test in the
  current invocation. Adaptive but unstable — adding one wild outlier
  compresses everyone else's score.
- **Empirical CDF / rank** — rank-based. Unbiased to outliers but opaque to
  users who want to know "what does 0.7 mean".

## Decision

Use **fixed thresholds per heuristic**.

| Heuristic | Raw signal | Mapping to `[0, 1]` |
|---|---|---|
| Volatility | `flips / pairs`, where `flips` = adjacent pairs of runs on the same SHA with different conclusions, `pairs` = total adjacent pairs on SHAs with ≥ 2 runs | identity (already in `[0, 1]`) |
| Retry rate | `runs_passed_on_retry / total_runs`, where "passed on retry" = `run_attempt > 1 ∧ conclusion == "success"` | identity |
| Timing variance | `cv = σ / μ` of job duration in seconds across runs (population stdev) | `min(1.0, cv / 0.5)` — a CV of 0.5 caps at 1.0 |
| Change-independence | `failures_on_unrelated_commits / total_failures` (see scoping note below) | identity |

- **SHAs with < 2 runs** contribute nothing to volatility — neither
  numerator nor denominator.
- **Tests with < 2 runs at all** cannot have timing CV computed; we report
  `timing_variance = 0` for them (not flaky on this signal). The spec's
  3-run minimum threshold for being scored at all still applies overall.
- **Change-independence scoping**: Phase 1 has no per-job path mapping
  configured, so the default policy is **permissive** — every failure
  counts as change-independent unless a future ADR introduces a manifest
  mapping job name → path globs. This means in Phase 1, change-independence
  effectively reduces to "failure rate". This is a documented known
  limitation, not a bug.

Raw scores from the four heuristics are averaged with equal weight (per
spec) to produce the per-run raw score; recency weighting across runs is
handled in [[0006-recency-decay-parametrisation]].

## Alternatives considered

- **Min-max over the run set** — common in flakiness tools (e.g. Flaky Test
  Detector), but produces drifting scores between invocations and breaks
  cross-repo comparability. Rejected.
- **Empirical CDF / rank** — robust to outliers but unintuitive ("0.7 means
  you're in the 70th percentile of this run") and impossible to sanity-check
  against domain knowledge. Rejected.
- **Configurable thresholds** — out of scope per the spec ("configurable
  heuristic weights" is listed as out-of-scope). The fixed thresholds chosen
  here are themselves a decision we can revisit in a follow-up ADR.

## Consequences

- Positive: scores are stable across invocations; comparable across repos;
  every threshold is a single number a human can sanity-check.
- Negative: thresholds are opinionated. If real-world CI durations vary a
  lot from the assumed 5–20 min range, the `cv / 0.5` cap may need tuning.
  Change-independence in Phase 1 is degenerate (≈ failure rate); this is
  acceptable for an MVP but should be revisited.
- Follow-ups:
  - Path-scope manifest for per-job change-independence (likely Phase 1.5
    or a Phase 3 input).
  - Tuning of the CV cap once we have a representative real-world sample.

Related: [[0006-recency-decay-parametrisation]] for how these per-run scores
combine over time.
