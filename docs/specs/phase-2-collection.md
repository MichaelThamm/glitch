# Spec: Phase 2 — Collection

**Status**: Draft  
**Phase**: 2 of 3  
**Traces to**: [VISION.md — Phase 2: Collection](../../VISION.md)

---

## Purpose

Collection captures comprehensive telemetry from a live (or recently-failed) deployment and packages it as a structured artifact for use by Phase 3 (Analysis) and for human inspection. It runs wherever the deployment lives — on a CI runner or a developer's machine.

For shared CLI concerns (installation, packaging, global flags), see [glitch-cli.md](glitch-cli.md).

---

## CLI Interface

```
glitch collect [OPTIONS]

Options:
  --output-dir          Directory to write the artifact bundle (default: ./glitch-artifact)
  --model               Juju model to collect from (default: active model from `juju switch`)
  --namespace           Kubernetes namespace to collect from (default: current kubectl context namespace)
  --test-artifacts-dir  Directory containing pre-existing test output files (JUnit XML, coverage, etc.)
```

### Typical CI usage

```yaml
- name: Collect failure telemetry
  if: failure()
  run: glitch collect --test-artifacts-dir ./test-results

- name: Upload artifact
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: glitch-artifact
    path: ./glitch-artifact
```

`glitch collect` writes to the local filesystem only. Artifact upload is a separate workflow step using the standard `actions/upload-artifact` action.

---

## Collectors

Collection is modular. Each collector is independent and **skips gracefully** if its target environment is not present (missing CLI tool, unreachable endpoint, or no active model/context). A skipped collector is recorded in the manifest as `skipped` with a reason.

### Juju collector

Runs if `juju` CLI is available and an active model exists.

| Artefact | Command | Output file |
|---|---|---|
| Model status | `juju status --format json` | `juju/status.json` |
| Full debug log | `juju debug-log --limit 0` | `juju/debug-log.txt` |
| Unit detail | `juju show-unit <unit> --format json` per unit | `juju/units/<unit>.json` |
| Pebble logs | `juju exec --unit <unit> -- pebble logs` per workload container | `juju/pebble/<unit>-<container>.txt` |

Units and workload containers are discovered from `juju status` output.

### Kubernetes collector

Runs if `kubectl` is available and the current context is reachable.

| Artefact | Command | Output file |
|---|---|---|
| All events | `kubectl get events -A --sort-by=.lastTimestamp -o json` | `k8s/events.json` |
| Failed pod descriptions | `kubectl describe pod <pod>` for pods with non-zero exit or restart count | `k8s/pods/<pod>-describe.txt` |
| Failed container logs | `kubectl logs <pod> -c <container> --previous` for restarted/failed containers | `k8s/pods/<pod>-<container>.txt` |

### LXD collector

Runs if `lxc` CLI is available.

| Artefact | Command | Output file |
|---|---|---|
| Instance list | `lxc list --format json` | `lxd/list.json` |
| Instance detail | `lxc info <instance>` per instance | `lxd/instances/<instance>.txt` |

### Ceph collector

Runs if `ceph` CLI is available.

| Artefact | Command | Output file |
|---|---|---|
| Cluster status | `ceph status --format json` | `ceph/status.json` |
| Health detail | `ceph health detail --format json` | `ceph/health-detail.json` |

### Test artifacts collector

Runs if `--test-artifacts-dir` is provided and the directory exists. Copies the directory contents as-is into `test-artifacts/` in the bundle.

Expected inputs (all optional): JUnit XML reports, pytest coverage XML, test timing JSON.

---

## Artifact Bundle Layout

```
glitch-artifact/
├── manifest.json             # What was collected, timestamps, collector status
├── summary.md                # Human/LLM-readable narrative of the collected state
├── juju/
│   ├── status.json
│   ├── debug-log.txt
│   └── units/
│       └── <unit>.json
│   └── pebble/
│       └── <unit>-<container>.txt
├── k8s/
│   ├── events.json
│   └── pods/
│       ├── <pod>-describe.txt
│       └── <pod>-<container>.txt
├── lxd/
│   ├── list.json
│   └── instances/
│       └── <instance>.txt
├── ceph/
│   ├── status.json
│   └── health-detail.json
└── test-artifacts/
    └── <copied as-is from --test-artifacts-dir>
```

### `manifest.json` schema

```json
{
  "glitch_version": "0.1.0",
  "collected_at": "2026-05-13T10:00:00Z",
  "collectors": {
    "juju": { "status": "ok", "model": "my-model", "units": ["myapp/0"] },
    "kubernetes": { "status": "ok", "namespace": "default" },
    "lxd": { "status": "skipped", "reason": "lxc CLI not found" },
    "ceph": { "status": "skipped", "reason": "ceph CLI not found" },
    "test_artifacts": { "status": "ok", "source_dir": "./test-results" }
  }
}
```

### `summary.md`

A rule-based markdown document generated from the collected data. It is not LLM-generated. Contents:

- **Collection summary**: which collectors ran, which were skipped
- **Juju model overview**: application/unit status table, any units in error state highlighted
- **Recent Juju log excerpts**: last 50 lines of debug-log, filtered to `ERROR` and `WARNING` level
- **K8s anomalies**: events with `Warning` type, pods with non-zero restart counts
- **Test result summary**: pass/fail counts and failed test names from JUnit XML (if present)

---

## Error Handling

| Condition | Behaviour |
|---|---|
| Collector CLI not installed | Skip collector, record in manifest as `skipped: CLI not found` |
| Collector command fails | Skip that artefact, record error in manifest, continue remaining collection |
| `--test-artifacts-dir` not found | Warn to stderr, skip test artifacts collector |
| Output directory already exists | Overwrite — designed for repeated runs in the same CI job |
| No collectors ran | Exit with code 1 and a clear message |

---

## Principles

- **Collect comprehensively** — Analysis filters what's relevant; Collection does not pre-filter
- **Read-only** — Collection never modifies the deployment state
- **Minimal overhead** — all collector commands are fast status/log reads; no expensive operations
- **Self-contained** — the artifact bundle is fully interpretable without access to the original deployment

---

## Out of Scope (Phase 2)

- Remote collection from a run ID (telemetry must be gathered from a live or local deployment)
- Artifact upload — handled by `actions/upload-artifact` in the workflow
- LLM-generated summaries — `summary.md` is rule-based only
- Non-Juju workloads
- Metrics time-series (Prometheus/Grafana scraping)

---

## Relationship to Other Phases

- Phase 1 (Discovery) has no dependency on Phase 2.
- Phase 3 (Analysis) ingests the artifact bundle from this phase as its primary input. It expects `manifest.json` at the bundle root to locate collector outputs.
