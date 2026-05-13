# Spec: Phase 1 — Discovery

**Status**: Draft  
**Phase**: 1 of 3  
**Traces to**: [VISION.md — Phase 1: Discovery](../../VISION.md)

---

## Purpose

Discovery gives developers a fast, local flakiness score for their test suite before investing in deeper investigation. It requires no telemetry artifacts and no LLM — only a GitHub API connection and a git checkout.

---

## CLI Interface

The Discovery phase is exposed as the `discover` subcommand of the `glitch` CLI. For shared CLI concerns (installation, packaging, global flags), see [glitch-cli.md](glitch-cli.md).

```
glitch discover --repo <owner/repo> [OPTIONS]

Options:
  --repo        GitHub repository in owner/repo format (required)
  --since       Lookback window as a duration string, e.g. 30d, 2w (default: 30d)
  --output      Output format: table | json (default: table)
  --cache-dir   Directory for cached API responses (default: ~/.cache/glitch)
  --branch      Filter to a specific branch (default: default branch)
```

### Output routing

| Flag value | Destination | Consumer |
|---|---|---|
| `table` | stdout | Developer terminal |
| `json` | stdout | Dashboard / Phase 3 |

Both formats carry the same underlying data; `table` is a human-friendly rendering of the full JSON payload.

---

## Authentication

Authentication is resolved in order:

1. `GITHUB_TOKEN` environment variable — used directly as a Bearer token.
2. `gh auth token` — the output of the GitHub CLI's stored credential is used as a fallback.
3. If neither is available, the tool exits with a clear error message directing the user to set `GITHUB_TOKEN` or run `gh auth login`.

---

## Data Sources

Phase 1 uses the **GitHub REST API** exclusively. No telemetry artifacts are required.

### Endpoints used

| Data | Endpoint |
|---|---|
| Workflow runs | `GET /repos/{owner}/{repo}/actions/runs` |
| Jobs per run | `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` |
| Commit metadata | `GET /repos/{owner}/{repo}/commits/{ref}` |

All endpoints are paginated. The client respects `X-RateLimit-Remaining` and backs off when approaching limits.

---

## Test Identification

Phase 1 identifies tests at **job granularity**. Each GitHub Actions matrix job represents one test (or test group). The test identifier is the job name as returned by the API.

No JUnit XML or artifact parsing is performed. This is sufficient because charm CI parallelises tests using a matrix strategy — one job per test — making job-level pass/fail equivalent to per-test pass/fail.

---

## Scoring Model

Each test receives a **flakiness index** in the range `[0, 1]`, where `0` is perfectly stable and `1` is maximally flaky.

### Heuristics

Five heuristics contribute to the score with **equal base weight**. Recency is applied as a **decay multiplier** across all signals rather than as a standalone heuristic.

| Heuristic | Description |
|---|---|
| **Pass/fail volatility** | Frequency of non-deterministic outcomes across runs on the same commit SHA |
| **Retry rate** | Proportion of runs where the job passed only after one or more retries |
| **Timing variance** | Coefficient of variation (σ/μ) of job duration across runs |
| **Change-independence** | Proportion of failures on commits with no file changes affecting the job's path scope |
| **Recency multiplier** | Exponential decay applied per-run: recent failures weighted higher than older ones |

### Score computation

```
raw_score(test) = mean(
    volatility_score,
    retry_score,
    timing_score,
    change_independence_score
)

final_score(test) = weighted_mean(raw_score, weight=recency_multiplier) per run
```

All component scores are independently normalised to `[0, 1]` before averaging.

### Minimum data threshold

A test must have **at least 3 runs** within the lookback window to receive a score. Tests with fewer runs are reported as `insufficient_data` and excluded from ranking.

---

## Output Formats

### Terminal (`--output table`)

Rendered using the `rich` library. Columns:

```
Rank  Test Name                          Score  Volatility  Retry  Timing  Change-Indep  Trend
   1  integration (test_deploy_local)     0.87       0.91   0.82    0.71          0.88   ↑↑↓↑↑
   2  integration (test_upgrade_path)     0.74       0.80   0.60    0.55          0.73   ↑↓↑↓↑
  ...
```

- **Score**: final flakiness index rounded to 2 decimal places
- **Trend**: last 5 runs encoded as `↑` (pass) / `↓` (fail)
- Tests with `insufficient_data` are listed at the bottom without a score

### JSON (`--output json`)

Single JSON object written to stdout. Consumers (dashboard, Phase 3) parse this directly.

```json
{
  "meta": {
    "repo": "canonical/my-charm",
    "branch": "main",
    "generated_at": "2026-05-13T10:00:00Z",
    "lookback_days": 30,
    "total_runs_analysed": 142,
    "glitch_version": "0.1.0"
  },
  "tests": [
    {
      "id": "integration (test_deploy_local)",
      "job_name": "integration (test_deploy_local)",
      "flakiness_index": 0.87,
      "run_count": 38,
      "heuristics": {
        "volatility": 0.91,
        "retry_rate": 0.82,
        "timing_variance": 0.71,
        "change_independence": 0.88
      },
      "trend": ["pass", "pass", "fail", "pass", "pass"],
      "last_failed_at": "2026-05-12T14:22:00Z"
    }
  ],
  "insufficient_data": [
    {
      "id": "integration (test_new_feature)",
      "run_count": 2
    }
  ]
}
```

---

## Caching

API responses are cached locally to avoid redundant requests and reduce GitHub API quota usage.

- **Cache location**: `~/.cache/glitch/` (overridable via `--cache-dir`)
- **Cache key**: `{owner}_{repo}_{run_id}.json`
- **TTL**:
  - Completed runs: cached indefinitely (immutable)
  - In-progress runs: 1-hour TTL
- **Format**: raw API response JSON per run

The cache is read-through: on a cache miss the API is called and the response is written to disk before returning.

---

## Error Handling

| Condition | Behaviour |
|---|---|
| No auth token found | Exit with code 1, print instructions for `GITHUB_TOKEN` or `gh auth login` |
| Repo not found / no access | Exit with code 1, print the HTTP error from GitHub |
| Rate limit exceeded | Retry with exponential backoff; print wait time to stderr |
| No runs in lookback window | Exit with code 0, print a warning: "No workflow runs found in the last N days" |
| All tests below minimum threshold | Exit with code 0, warn and show the `insufficient_data` list |

---

## Out of Scope (Phase 1)

- Per-test scoring from JUnit XML or other artifacts
- Cross-repository aggregation or normalisation
- Configurable heuristic weights
- HTML report output
- Non-GitHub CI systems
- LLM involvement of any kind

---

## Relationship to Other Phases

- The JSON output is the **primary input to Phase 3 (Analysis)**, which consumes `tests[].flakiness_index` and `tests[].heuristics` to inform classification confidence.
- Phase 1 has no dependency on Phase 2 (Collection).
