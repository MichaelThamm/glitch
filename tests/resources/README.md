# Real-World Telemetry Samples

Captured from a live COS Lite deployment (Juju model `cos-lite`) on 2026-05-13
using `glitch collect --model cos-lite`. These serve as integration-test fixtures
representing realistic production data.

| File | Source | Size | Content |
|------|--------|------|---------|
| `juju-status.json` | `juju status --format json` | 30 KB | 6 COS apps (alertmanager, catalogue, grafana, loki, prometheus, traefik), all active |
| `juju-debug-log.txt` | `juju debug-log --limit 0` | 94 KB | WARNING/ERROR lines showing TLS cert skips, deprecation warnings, insecure trace connections |
| `k8s-events.json` | `kubectl get events -A -o json` | 184 KB | 177 events including Warning-level FailedMount and Unhealthy (502) across 6 namespaces |
| `lxd-list.json` | `lxc list --format json` | 15 KB | 1 microk8s container instance |