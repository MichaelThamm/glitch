# team-quack

## Objective
Short term: Classification of error scenarios
Long term: Pipe this into an LLM for immediate remediation

## Refs
- [metrics in self-hosted runners](https://docs.google.com/presentation/d/1Kcf75y1m-UrhYgO_mIXXKIF6zybAyyMYUkyKIdhehNQ/edit?disco=AAAB6G81YuY)

## Deliverables
- [ ] GH Action
- [ ] Dashboard -> previous fails
- [ ] Skills, context files
- [ ] Telemetry artifacts

## Tasks
- [ ] rank scope items in terms of value vs. expensiveness
    - hide the expensive ones behind a flag?

## Scope
- For now, we can have this GH action be manually triggered. In the future, we can have this be dynamically allocated to runs which are failing AND have specific identifiers
- Pick a flaky charm e.g. otelcol and add the workflow there to start gethering

### Gather
- Per CI run, we should always output (artifact) this info on failed runs
- [ ] telemetry from the runner:
    - logs, metrics, traces
- [ ] telemetry from the workloads/charms:
    - logs, metrics, traces?
    - e.g. pebble logs
- [ ] telemetry from infra
    - k8s / ceph / LXD

### Classification
- skill
- context / knowledge-base
    - sourced from smaller knowledge bases: distributed per charm?
- Gather context from historical data
    - Is a 1-month artifact retention period enough?
    - Get the CI status with API

#### Examples / ideas
- context: the previous hook is re-run in the event that the charm hits error state
- context: some charms are reconciler patterns so any hook is a recreate-the-world
- skill: create a mermaid diagram of all previous hooks for context and reader understandability

## Verticals / Spec / ADRs
1. Agent runs in the runner
    - e.g., you hop into a TMate session and have access to an agent to troubleshoot on the spot
    - this is useful for cases where the flakiness is specific to the runner infra
    - Cons:
        - GH security might not allow agents in CI
        - We sometimes push too early and get CI failures due to laziness (gate this with a manual trigger)
2. Agent runs locally
    - e.g. you run Claude CLI within the repo of the failed CI and provide the runner artificats as context.
    - you can then re-run the test locally and test your/agent's theory


## Agentic work
