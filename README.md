# team-quack

## Refs
- [metrics in self-hosted runners](https://docs.google.com/presentation/d/1Kcf75y1m-UrhYgO_mIXXKIF6zybAyyMYUkyKIdhehNQ/edit?disco=AAAB6G81YuY)

## Tech-stack

## Scope
- We need to rank things in terms of value vs. expensiveness
    - hide the expensive ones behind an --extra flag?
- For now, we can have this GH action be manually triggered. In the future, we can have this be dynamically allocated to runs which are failing AND have specific identifiers

### Gather
- [ ] telemetry from the runner:
    - logs, metrics, traces
- [ ] telemetry from the workloads/charms:
    - logs, metrics, traces?
    - e.g. pebble logs
- [ ] telemetry from infra
    - k8s / ceph / LXD
- We should always gather this info on any failed run and dump to artifacts

### Classification
- skill
- context / knowledge-base
    - sourced from smaller knowledge bases: distributed per charm?
- 

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
