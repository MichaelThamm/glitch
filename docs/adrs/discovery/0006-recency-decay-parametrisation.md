# ADR 0006: Recency-decay parametrisation

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

The spec mandates that recency is applied as an exponential decay multiplier
across all per-run scores:

> *Recency multiplier — Exponential decay applied per-run: recent failures
> weighted higher than older ones.*
> *`final_score(test) = weighted_mean(raw_score, weight=recency_multiplier)
> per run`*

What is **not** pinned is the decay rate (half-life), nor which timestamp on
the run defines its age, nor how to handle the edge cases at `Σw = 0`.

## Decision

Use an **exponential decay with half-life τ = 14 days**, applied per run.

- Run age: `Δdays = (now - run.created_at).total_seconds() / 86400`
  - `now = datetime.now(timezone.utc)`, captured once per invocation and
    re-used everywhere (matches `meta.generated_at` in the JSON output for
    reproducibility).
  - `run.created_at` (the spec's GitHub API field) is preferred over
    `updated_at` because re-runs shift `updated_at` and would artificially
    weight an old failure as recent.
- Weight: `weight(run) = exp(-Δdays / k)`, where `k = τ / ln 2 ≈ 20.2 days`.
- Final score per test: `Σ(weight_i * raw_score_i) / Σ(weight_i)` across all
  runs of that test in the lookback window.
- The 3-run minimum from the spec guarantees `Σweight > 0`, so the divide is
  safe.

Sample weights for sanity:

| Run age | Weight |
|---|---|
| 0 d | 1.00 |
| 7 d | 0.71 |
| 14 d | 0.50 (half-life) |
| 21 d | 0.35 |
| 30 d | 0.23 |

## Alternatives considered

- **τ = 7 days** — too aggressive; failures at the 30-day boundary would
  drop to ~5% weight, wasting data we already fetched.
- **τ = 30 days** — flattens the recent/old gradient too much; defeats the
  point of the recency signal.
- **τ scaled with `--since`** (e.g. `τ = since_days / 2`) — appealing but
  would make scores incomparable across invocations with different lookback
  windows. Rejected for the same reason we chose fixed thresholds in
  [[0005-heuristic-normalisation]].
- **Linear decay** (`max(0, 1 - Δdays / window)`) — the spec explicitly
  specifies exponential, so we honour that literally.
- **`updated_at`** for run age — shifts on re-run; would weight stale
  failures as recent. Rejected.

## Consequences

- Positive: a single tunable (τ = 14d) drives the entire recency behaviour;
  the formula is reproducible from the run's `created_at` and the
  invocation's `generated_at`.
- Negative: 14 days is a guess based on a 30-day default window; if real
  usage settles on a different default window, τ should be revisited.
- Follow-ups: revisit after a few real-world invocations on charm repos;
  consider exposing τ as a hidden flag if tuning becomes useful. Related:
  [[0005-heuristic-normalisation]] (the raw_scores being weighted are
  produced there).
