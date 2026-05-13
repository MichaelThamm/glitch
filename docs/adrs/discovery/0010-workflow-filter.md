# ADR 0010: Workflow filter for `--workflow`

**Status**: Accepted
**Phase**: 1 — Discovery
**Date**: 2026-05-13

## Context

Real charm repositories run more than one GitHub Actions workflow — typically
a fast PR-gating workflow (`ci.yml`), a slower integration matrix
(`integration.yml`), and a release pipeline (`release.yml`). Today `glitch
discover` fetches every workflow run in the lookback window indiscriminately
and only filters at the job-name layer. That mixes the signal from
fundamentally different pipelines: an integration job that is genuinely flaky
gets averaged together with PR-CI failures from a workflow the user is not
currently investigating.

The spec (`docs/specs/phase-1-discovery.md`) does not pin per-workflow
behaviour either way. Adding a workflow filter lets developers narrow
discovery to the pipeline they actually care about, and meaningfully reduces
the API call volume for repos with many workflows.

### What the GitHub API supports

- `GET /repos/{owner}/{repo}/actions/runs` (the flat endpoint we use today)
  accepts `actor`, `branch`, `event`, `status`, `created`, `head_sha`,
  `check_suite_id`, and `exclude_pull_requests`. It does **not** accept a
  `workflow_id` query parameter — server-side filtering by workflow on this
  endpoint is impossible.
- `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs` is the
  workflow-scoped variant. `workflow_id` may be either the numeric ID or the
  workflow file name (e.g. `ci.yml`). The response shape is otherwise
  identical to the flat endpoint.
- `GET /repos/{owner}/{repo}/actions/workflows` lists all workflows in the
  repo. Each entry carries `id`, `name` (the display name from the workflow
  YAML's `name:` field), `path` (e.g. `.github/workflows/ci.yml`), and
  `state` (`active`, `disabled_*`, `deleted`).

## Decision

Add a repeatable `--workflow` flag to `glitch discover`. When at least one
value is supplied, fan out across the matching workflow-scoped endpoints
instead of hitting the flat `/actions/runs` endpoint. When `--workflow` is
omitted, behaviour is unchanged — every workflow's runs are considered.

### CLI surface

```
glitch discover --repo owner/repo [--workflow IDENTIFIER]...
```

- The flag is repeatable: `--workflow ci.yml --workflow release.yml` selects
  two workflows.
- An `IDENTIFIER` is matched against the workflow listing in this order; the
  first match wins:
  1. Exact `path` match — e.g. `.github/workflows/ci.yml`.
  2. Exact filename match against `basename(path)` — e.g. `ci.yml`.
  3. Exact `name` (display name) match, case-sensitive — e.g. `CI`.
  4. String form of the numeric `id` — e.g. `12345678`.
- If any identifier does not match exactly one workflow, exit `1` with a
  stderr message listing the candidate values for the repo (much like the
  spec's "no auth" branch — the user gave a bad input and we tell them what
  was available).
- Disabled workflows (`state != "active"`) are *not* excluded from matching;
  the user explicitly asked for them, and the empty-window warning will
  trigger if no runs exist.

### Resolution flow

1. On invocation with at least one `--workflow`, issue a single
   `GET /repos/{owner}/{repo}/actions/workflows?per_page=100` (paginated as
   usual). The response is cached under a new `workflows` cache kind with a
   1-hour TTL: workflows change rarely, but a new YAML committed during the
   day should be picked up reasonably promptly.
2. Build an in-memory map keyed by the four accepted identifier forms;
   resolve each `--workflow` value to its numeric `id`.
3. Fan out one `GET /repos/{owner}/{repo}/actions/workflows/{id}/runs` call
   per resolved id, using the existing
   [[0004-concurrency-model]] `ThreadPoolExecutor`. Each call carries the
   same `branch` and `created` filters as today.
4. Aggregate the workflow-scoped run lists into a single
   `list[dict]` before handing off to the scoring pipeline. Down-stream
   modules (`scoring.py`, `render.py`) are unchanged — the per-test grouping
   still happens by `job.name`.

### Cache key extension

The current run-list cache key (`runs_{owner}_{repo}_{branch}_{since_iso}.json`)
is extended to include the workflow id when the workflow-scoped endpoint is
used:

```
runs_{owner}_{repo}_{branch}_{since_iso}_w{workflow_id}.json
```

Each workflow gets its own cache entry under the same `runs` kind, so a user
who runs once with `--workflow ci.yml` and later with `--workflow ci.yml
--workflow release.yml` reuses the `ci.yml` cache and only pays the network
cost for `release.yml`. The unfiltered call retains the original key shape
(no `_w*` suffix).

A separate cache kind, `workflows`, holds the result of the list-workflows
call:

```
workflows_{owner}_{repo}.json   # kind=workflows, ttl=3600
```

### Model change

Add a `workflows: tuple[str, ...]` field to `Meta` recording the resolved
display names of the workflows the report covers (empty tuple when no
filter was applied). This makes downstream consumers — and the eventual
Phase 3 analyser — able to attribute scores to the right pipeline without
re-deriving the filter from CLI history.

The JSON output gains a `meta.workflows` array:

```json
"meta": {
  "repo": "canonical/my-charm",
  "branch": "main",
  "workflows": ["CI", "Integration"],
  ...
}
```

The table renderer prints a one-line `Workflows: CI, Integration` header
above the table when the filter is non-empty.

## Alternatives considered

- **Flat `/actions/runs` + client-side filter** — would let us keep the
  existing code path unchanged, but means downloading every run only to
  discard most of them. On a repo with a large `integration` workflow and
  a tiny `release` workflow, asking for `--workflow release.yml` would
  still transfer the full integration history. Rejected: the whole point
  of the filter is to do less work, not the same work with a `if` at the
  end.
- **Numeric ID only** — simplest API surface but UI-hostile. Nobody knows
  their workflow IDs offhand; making users curl the API just to construct
  the filter defeats the ergonomic win.
- **Filename only** — middle ground (what GitHub's own URL parameter
  accepts), but excludes display-name matching. Users who think of their
  workflows by the `name:` field at the top of the YAML (which is what the
  Actions tab shows) would be confused when their natural input doesn't
  match anything.
- **Glob patterns** (e.g. `--workflow "release-*.yml"`) — appealing for
  matrix-style workflow setups, but every glob library is a dep we'd add,
  and shell-quoting rules make glob input fiddly in CI. Defer to a
  follow-up if users actually ask for it.
- **Negation** (`--exclude-workflow ...`) — symmetric and useful in
  practice ("everything except the release pipeline"), but the inclusive
  form covers the common case; adding negation now doubles the surface for
  a feature we have no evidence is wanted yet.
- **Comma-separated single flag** (`--workflow ci.yml,release.yml`) — Typer
  supports repeated flags natively, comma-separated values would need a
  custom parser and break the moment a workflow filename ever contains a
  comma (unlikely but possible). Repeated flag is the conventional shape.

## Consequences

- Positive: scoring is meaningful per pipeline; cold-cache cost is lower
  when the filter is set (only the matched workflows are paged); the JSON
  output gains a `meta.workflows` field that records exactly what was
  scored.
- Negative: one extra request per invocation when the filter is on (the
  list-workflows call), partially offset by its 1-hour cache; the cache
  layout gains one new kind (`workflows`) and one new key shape
  (`runs_..._w{id}.json`); `Meta` gains a field, which is a non-breaking
  addition to the JSON payload but still touches every consumer.
- Failure mode worth flagging: if a user names a workflow that doesn't
  exist, we exit `1` rather than warning and continuing. A typo should
  fail loud, not silently produce an "empty window" warning that hides
  the real problem.

## Follow-ups

- **Negation** (`--exclude-workflow`) — natural sequel once we see real
  usage.
- **Glob patterns** — only if users ask.
- **State-aware filtering** — automatically skipping `disabled_*` workflows
  unless `--include-disabled` is passed; depends on whether disabled
  workflows turn out to be a real source of noise.
- **Workflow-aware scoring** — the heuristics in
  [[0005-heuristic-normalisation]] treat jobs as the unit; with the filter
  in place we could revisit whether some heuristics (e.g. timing variance)
  should be normalised within a workflow rather than globally.

Related:
[[0001-github-api-client]] (the workflow-scoped endpoint is just another
path through the same client),
[[0002-local-cache-layer]] (new `workflows` kind + extended `runs` key),
[[0003-domain-model-representation]] (`Meta.workflows` field),
[[0004-concurrency-model]] (fan-out across resolved workflow ids),
[[0008-testing-approach]] (a `workflows_list.json` fixture joins the
existing three).
