# Discovery (Phase 1) ADRs

Architectural decisions specific to the `glitch discover` subcommand. Each
ADR captures one decision the spec (`docs/specs/phase-1-discovery.md`) does
not pin. The spec remains the authoritative behavioural contract; these ADRs
explain *how* we chose to satisfy it.

See [`../0000-record-architectural-decisions.md`](../0000-record-architectural-decisions.md)
for the ADR template and workflow.

| # | Title |
|---|---|
| 0001 | [GitHub API client](0001-github-api-client.md) |
| 0002 | [Local cache layer](0002-local-cache-layer.md) |
| 0003 | [Domain model representation](0003-domain-model-representation.md) |
| 0004 | [Concurrency model](0004-concurrency-model.md) |
| 0005 | [Heuristic normalisation](0005-heuristic-normalisation.md) |
| 0006 | [Recency-decay parametrisation](0006-recency-decay-parametrisation.md) |
| 0007 | [Module layout](0007-module-layout.md) |
| 0008 | [Testing approach](0008-testing-approach.md) |
| 0009 | [Duration string parsing](0009-duration-string-parsing.md) |
| 0010 | [Workflow filter for `--workflow`](0010-workflow-filter.md) |
