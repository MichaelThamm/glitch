# Vision: Automated CI Failure Remediation

**Project Name**: Glitch

## Overview

This project provides intelligent, automated remediation for CI failures in charm development. By combining statistical analysis of historical runs, comprehensive telemetry collection, and LLM-powered diagnosis, we transform flaky tests and obscure failures from blockers into actionable insights.

## Core Philosophy

CI failures are not just errors to be fixed—they are **signals** carrying context. By systematically analyzing patterns, capturing state, and reasoning about failures, we reduce developer toil and accelerate feedback loops.

## The Three Phases

The system operates through three distinct phases that work together:

```
┌─────────────┐     ┌────────────┐
│  DISCOVERY  │     │ COLLECTION │
│  (local,    │     │ (CI-side,  │
│  heuristic) │     │ telemetry) │
└──────┬──────┘     └─────┬──────┘
       │  flakiness score │  artifact bundle
       └────────┬─────────┘
                ▼
         ┌──────────────┐
         │   ANALYSIS   │
         │  (classify + │
         │  auto-fix)   │
         └──────────────┘
                │
       patches / issues / feedback
                ▼
         back to DISCOVERY
```

**Typical workflow**: Run Discovery locally to score and rank flaky tests → Collection captures telemetry the next time those tests fail in CI → Analysis classifies failures by cause with confidence scores and attempts automated remediation.

---

### Phase 1: Discovery

**Purpose**: Give developers a fast, local flakiness score for their test suite before investing in deeper investigation.

Discovery is a **local CLI tool** that applies heuristics to CI run history and git metadata to compute a per-test flakiness score. It requires no telemetry artifacts and no LLM — just a connection to the CI API and a git checkout. The output is designed to be visualized immediately.

**Scoring heuristics** (inputs to the score, not exhaustive):
- **Pass/fail volatility**: frequency of non-deterministic outcomes across runs on the same commit
- **Retry rate**: tests that pass only on retry signal infrastructural or timing sensitivity
- **Timing variance**: high coefficient of variation in test duration across runs
- **Change-independence**: failures that occur on commits with no related file changes
- **Recency weighting**: recent failures weighted more heavily than older ones

**Outputs**:
- A scored, ranked list of tests with a numeric flakiness index (0–1) per test
- A visual report (e.g., HTML or terminal table) showing score breakdown by heuristic
- Trend sparklines per test over time
- Machine-readable format (JSON/CSV) for downstream consumption by Phase 3

**Principles**:
- Runs **locally** — developer invokes it from their machine, results are immediate
- Pure heuristics, no LLM — deterministic and auditable
- Works from CI API metadata and git history only; no telemetry artifacts required
- Scoped to a single repository but exportable for cross-repo aggregation

**Open Questions**:
- Delivery mechanism: standalone CLI, GitHub Action, or integrated skill?
- Data retention and caching strategy for repeated runs
- Normalization of scores across repositories with different test suite sizes

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

**Purpose**: Classify failures by root cause with confidence scores, then attempt automated remediation.

Analysis is the synthesis layer. It ingests the flakiness scores from Phase 1 and the telemetry bundle from Phase 2 to produce a **classified, confidence-scored verdict** for each failure — and then acts on it. Where Phase 1 answers "is this test flaky?", Phase 3 answers "why, how sure are we, and what can be done about it automatically?"

**Inputs**:
- Flakiness scores and heuristic breakdown from Phase 1 (per-test JSON)
- Telemetry artifact from Phase 2 (logs, metrics, k8s events, pytest reports)
- Charm-specific context (reconciler patterns, hook behavior, known quirks)
- Known failure signatures and previously resolved patterns

**Classification taxonomy** (with confidence score 0–1 per label):
| Label | Meaning |
|---|---|
| `flaky` | Non-deterministic; likely timing/environment sensitivity |
| `charm-bug` | Defect in the charm's logic or configuration |
| `test-bug` | Defect in the test itself (bad assertion, wrong assumption) |
| `infrastructure` | CI runner, Kubernetes, Ceph, or LXD-level issue |
| `environment` | Transient external dependency (network, registry, upstream package) |
| `unknown` | Insufficient signal to classify with confidence |

A failure may carry multiple labels with independent confidence scores (e.g., `flaky: 0.7, test-bug: 0.4`).

**Automated remediation**:
- For `test-bug` and `charm-bug` classifications above a confidence threshold: the agent **attempts a fix** — generates a patch, applies it to a branch, and re-runs the affected test
- For `flaky`: proposes retry policies, ordering guards, or test isolation changes
- For `infrastructure` / `environment`: files an annotated issue with reproduction steps
- Human confirmation is required before merging any patch; the agent does not push without approval

**Execution Modes**:

1. **In-Runner**
   - Runs within the CI environment immediately after failure
   - Direct access to live state; can attempt fix-and-rerun in place
   - *Constraint*: GitHub security policies may restrict agent execution

2. **Offline/Local**
   - Developer downloads artifact and runs analysis locally
   - Can iterate on hypotheses, inspect reasoning trace, and apply patches manually
   - Works with any Phase 2 artifact

**Outputs**:
- Classified verdict per failure with confidence scores and reasoning trace
- For actionable classifications: a concrete patch or remediation PR
- Diagnostic narrative (e.g., Mermaid hook-sequence diagrams for charm-bug cases)
- Feedback signal written back to Phase 1's known-patterns store

**Principles**:
- Classification is always shown before any action is taken
- Automated fixes require human approval before landing
- Analysis must be reproducible given the same Phase 1 + Phase 2 inputs
- Resolved patterns feed back into Discovery to improve future heuristic scores

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
