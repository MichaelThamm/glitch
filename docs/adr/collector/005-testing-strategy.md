# ADR-005: Testing Strategy for Collectors

**Status**: Accepted  
**Phase**: 2 (Collection)  
**Date**: 2026-05-13

## Context

Collectors depend on external CLIs (`juju`, `kubectl`, `lxc`, `ceph`) that are not available in a standard development environment or CI test runner. Tests must:

- Run deterministically without requiring actual Juju/K8s/LXD/Ceph infrastructure
- Be fast enough to run on every PR (no long-running integration suite in the critical path)
- Validate collector logic (detection, command construction, output parsing, error handling) without executing real subprocess calls

## Decision

We use **mock-based unit tests with fixture files** checked into the repository.

### Strategy

| Layer | What is tested | How |
|-------|---------------|-----|
| Detection | `detect()` returns correct bool based on CLI presence | `unittest.mock.patch("shutil.which")` to simulate present/absent CLIs |
| Command construction | Correct `subprocess.run` arguments for each artifact | Assert on the args list passed to a mocked `subprocess.run` |
| Output parsing | JSON parsing, text filtering, pod/unit enumeration | Feed fixture files as mock return values and validate parsed output |
| Error handling | Non-zero exit codes, timeouts, missing fields | Simulate `subprocess.CalledProcessError`, empty stdout, malformed JSON |
| Summary generation | Correct Markdown output for each section | Feed known dataset, assert on rendered Markdown string |
| End-to-end wiring | `glitch collect` CLI → collector dispatch → output files | Mock all `subprocess.run` calls, inspect written files on disk |

### Fixture files

```
tests/fixtures/
├── juju/
│   ├── status.json           # Realistic juju status output
│   ├── debug-log.txt         # Excerpt of debug-log with ERROR/WARNING lines
│   └── show-unit.json        # Single unit detail
├── k8s/
│   ├── events.json           # Events including Warning type
│   └── pod-describe.txt      # kubectl describe output for a failed pod
├── lxd/
│   └── list.json             # lxc list output
└── ceph/
    └── status.json           # ceph status output
```

Fixture files are realistic output captures from actual tools, sanitized of any sensitive information.

### What is NOT tested in unit tests

- Actual subprocess execution against real infrastructure
- CLI tool version compatibility
- Timeout behavior at the OS level

These are deferred to integration tests that gate releases, run manually or on a dedicated CI runner with actual Juju/K8s access.

## Consequences

- **Positive**: Tests run in <1 second and work in any environment (no infra dependencies).
- **Positive**: Fixture files serve as documentation of expected CLI output formats.
- **Negative**: Fixtures can become stale if CLI output formats change. Mitigation: periodically refresh fixtures from real infra.
- **Negative**: Does not catch issues where the mock diverges from real subprocess behavior (e.g., encoding differences, shell quirks). Mitigation: integration gating suite.

## Alternatives Considered

- **Integration tests on real infrastructure**: Too slow for PR CI; better suited as a gating/release suite.
- **Record/replay (VCR-style)**: Overkill for CLI subprocess calls; mock objects are simpler and more explicit.
- **Docker-based test infra (kind, microk8s, lxd)**: Viable but heavyweight. Deferred to integration suite.
