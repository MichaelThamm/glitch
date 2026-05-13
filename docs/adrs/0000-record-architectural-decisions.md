# ADR 0000: Record architectural decisions as ADRs

**Status**: Accepted
**Date**: 2026-05-13

## Context

As Glitch grows across three phases (Discovery, Collection, Analysis) and
their supporting infrastructure, design decisions need to be traceable. Without
a written record, the reasoning behind a choice is lost the moment the team
moves on, and future changes have to re-derive it from scratch.

The project already separates *what* the system does (specs, in `docs/specs/`)
from *why* the code was written the way it was. We need a home for the *why*.

## Decision

Use **Markdown Architectural Decision Records (MADR)** to capture every
non-trivial design choice.

- ADRs live under `docs/adrs/`. Phase-scoped ADRs are nested under a folder
  named after the phase's CLI subcommand (e.g. `docs/adrs/discovery/` for
  Phase 1, `docs/adrs/collect/` for Phase 2, `docs/adrs/analyze/` for Phase 3).
  Project-wide ADRs (like this one) live at the `docs/adrs/` root.
- File naming: `NNNN-kebab-slug.md`, four-digit zero-padded. Numbering is
  per-folder; the meta ADR root counter is independent from each phase's
  counter.
- Template (MADR-lite):

  ```markdown
  # ADR NNNN: <Title>

  **Status**: Proposed | Accepted | Superseded by [#NNNN]
  **Phase**: <name>          # omit for project-wide ADRs
  **Date**: YYYY-MM-DD

  ## Context
  ## Decision
  ## Alternatives considered
  ## Consequences
  ```
- Workflow:
  1. ADR is drafted with status `Proposed`.
  2. Author reviews and approves it.
  3. Status flips to `Accepted` before any code is written against it.
  4. If a later ADR overturns it, the old one stays in place with status
     `Superseded by [#NNNN]` — ADRs are append-only history.

## Alternatives considered

- **No ADRs, comments in code** — decisions get lost when the code is
  refactored; comments rot.
- **A single decisions.md log** — search degrades quickly as it grows; no
  per-decision review unit.

## Consequences

- Positive: every significant decision has a durable, reviewable home with a
  rationale; new contributors can read the ADRs to understand *why* the code
  looks the way it does.
- Negative: writing an ADR is friction; small decisions may not warrant one,
  and judging "small" is a soft call.
- Follow-ups: a deferred-decisions backlog can live in `docs/adrs/backlog.md`
  if and when one becomes useful — not created yet.
