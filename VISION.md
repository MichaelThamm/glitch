# Vision: Automated CI Failure Remediation

**Project Name**: TBD

## Overview

This project provides intelligent, automated remediation for CI failures in charm development. By combining statistical analysis of historical runs, comprehensive telemetry collection, and LLM-powered diagnosis, we transform flaky tests and obscure failures from blockers into actionable insights.

## Core Philosophy

CI failures are not just errors to be fixed—they are **signals** carrying context. By systematically analyzing patterns, capturing state, and reasoning about failures, we reduce developer toil and accelerate feedback loops.

## The Three Phases

The system operates through three distinct phases that work together:

```
┌─────────────┐     ┌────────────┐     ┌──────────┐
│  DISCOVERY  │ ──▶ │ COLLECTION │ ──▶ │ ANALYSIS │
└─────────────┘     └────────────┘     └──────────┘
      │                                      │
      └──────────── informs ─────────────────┘
```

**Typical workflow**: Use Discovery to identify flaky tests worth investigating → Collection captures detailed telemetry on failures → Analysis diagnoses root cause and suggests fixes.

---

### Phase 1: Discovery

**Purpose**: Identify which tests are flaky and worth acting on.

Discovery performs statistical analysis across historical CI runs to surface patterns that indicate flakiness. This phase operates independently of whether telemetry artifacts exist—it works purely from CI run metadata and code changes.

**Capabilities**:
- **Cross-reference analysis**: correlate test failures with code changes to determine if failures are related to the diff or are spurious
- **Flakiness scoring**: compute likelihood that a test is flaky based on pass/fail patterns across runs
- **Trend detection**: identify tests that have become more/less stable over time
- **Repository-wide view**: aggregate data across multiple charm repositories

**Outputs**:
- Dashboard or visualization showing flaky tests ranked by severity/frequency
- Prioritized list of tests worth investigating
- Historical flakiness trends per test/suite

**Principles**:
- Works without telemetry—uses only CI API data and git history
- Provides actionable prioritization, not just raw data
- Enables informed decisions about where to invest remediation effort

**Open Questions**:
- Delivery mechanism: standalone dashboard, GitHub Action, CLI tool, or skill?
- Data retention and storage approach
- Cross-repository aggregation strategy

---

### Phase 2: Collection

**Purpose**: Capture comprehensive telemetry when tests fail.

Collection is an independent tool that gathers all relevant state from a failed CI run and uploads it as an artifact. It should be easy to integrate into existing workflows and produce self-contained, agent-consumable output.

**Scope**:
- **Runner telemetry**: logs, metrics, traces from the CI runner itself
- **Workload telemetry**: charm logs, Pebble logs, application metrics and traces
- **Infrastructure telemetry**: Kubernetes events, Ceph status, LXD state
- **Test artifacts**: stdout/stderr, pytest reports, coverage data, test timing

**Integration**:
- Runs automatically on test failure (or manually triggered)
- Uploads all telemetry as a single artifact to the GitHub Actions run
- Structured output format optimized for Analysis phase consumption

**Principles**:
- Collect comprehensively; Analysis phase filters what's relevant
- Artifacts must be self-contained and reproducible
- Minimal overhead—should not significantly extend CI run time
- Independent tool that can be adopted incrementally

---

### Phase 3: Analysis

**Purpose**: Diagnose root cause and suggest fixes using LLM-powered reasoning.

Analysis combines telemetry from Collection with contextual knowledge about how specific charms work to perform root cause analysis. It determines whether the issue lies in the charm, test, infrastructure, or is simply flakiness.

**Inputs**:
- Telemetry artifact from Collection phase
- Charm-specific context (reconciler patterns, hook behavior, known quirks)
- Common charm patterns and failure signatures
- Historical data from Discovery phase

**Execution Modes**:

1. **In-Runner**
   - Runs within the CI environment after test failure
   - Direct access to live state for deeper inspection
   - Can attempt fixes and re-run tests in place
   - *Constraint*: GitHub security policies may restrict agent execution

2. **Offline/Local**
   - Developer downloads artifact and runs analysis locally
   - Can iterate on hypotheses and test fixes
   - Full access to local tooling
   - Works with any artifact from Collection phase

**Outputs**:
- Root cause classification (charm bug, test bug, infrastructure issue, flakiness)
- Suggested code patches or configuration changes
- Diagnostic explanations (e.g., Mermaid diagrams of hook sequences)
- Confidence level and reasoning trace

**Principles**:
- Resolution is advisory—human confirms before applying fixes
- Analysis must be reproducible given the same inputs
- Learnings feed back into Discovery (known patterns, resolved flakiness)

---

## Boundaries

### In Scope
- GitHub Actions as the primary CI platform
- Juju charms and related workloads
- Kubernetes, Ceph, and LXD infrastructure
- Manual trigger initially; automated workflows in future

### Out of Scope (for now)
- Other CI systems (Jenkins, GitLab CI)
- Non-charm Python projects
- Fully automated remediation without human confirmation

---

## Success Criteria

1. **Visibility**: Developers can quickly see which tests are flaky across repositories
2. **Reduced MTTR**: Mean time to remediate failures decreases measurably
3. **Actionable output**: Failures come with root cause analysis and suggested fixes
4. **Knowledge capture**: Remediation patterns are captured and reusable
5. **Low friction**: Collection integrates easily; Analysis works both online and offline

---

## Relationship to Specs and ADRs

This vision document establishes the **what** and **why**. Implementation details are captured in:

- **Specs**: Define the detailed behavior of each phase (inputs, outputs, interfaces, tooling)
- **ADRs**: Record specific architectural decisions made during implementation

All specs and ADRs should trace back to one of the three phases defined here.
