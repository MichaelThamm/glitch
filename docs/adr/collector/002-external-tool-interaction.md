# ADR-002: External Tool Interaction

**Status**: Accepted  
**Phase**: 2 (Collection)  
**Date**: 2026-05-13

## Context

Collectors depend on external CLIs (`juju`, `kubectl`, `lxc`, `ceph`) to gather telemetry. The interaction layer must:

- Be reliable and predictable across CI and developer environments
- Handle timeouts and non-zero exit codes cleanly
- Avoid pulling in heavy Python client libraries that duplicate CLI functionality
- Produce structured outputs (JSON where available) for downstream consumption

## Decision

We will use **pure `subprocess.run` with per-command timeouts** for all external CLI invocations. No Python client libraries (libjuju, lightkube, etc.) will be used.

### Key elements

| Element | Decision |
|---------|----------|
| Invocation | `subprocess.run(cmd, capture_output=True, text=True, timeout=N)` |
| Timeouts | Per-command, based on expected data volume: 30s for `juju status`, 120s for `juju debug-log`, 60s for `kubectl get events`, etc. |
| Shell | Never. Commands are passed as `list[str]` to avoid injection risk. |
| Structured data | Parse JSON stdout where CLI supports `--format json` (juju, kubectl, lxc, ceph) |
| Error handling | Non-zero exit codes caught as `CollectorResult(status="error", reason="<stderr summary>")`; stderr captured alongside stdout |
| Environment | Inherit parent environment (for `$PATH`, `$KUBECONFIG`, `$HOME/.local/share/juju`, etc.) |

### Helper utility

A shared `run_tool` helper in `src/glitch/collectors/base.py` wraps `subprocess.run` with:

```python
def run_tool(
    args: list[str],
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,  # caller inspects returncode
    )
```

Collectors call this helper rather than `subprocess.run` directly, ensuring consistent timeout/error semantics.

## Consequences

- **Positive**: Zero additional dependencies. Works anywhere the CLI tools are installed.
- **Positive**: `subprocess.run` is synchronous and trivial to reason about — no async machinery needed.
- **Positive**: JSON-format CLI output avoids fragile regex parsing. Tools that support `--format json` (juju, kubectl, lxc, ceph) are used in that mode.
- **Negative**: Requires CLI tools to be pre-installed on the CI runner. The collector skips gracefully if absent, but no data is collected.
- **Negative**: Timeout values are estimates; very large debug logs could exceed them. The spec explicitly disallows truncation, so timeouts must err on the generous side.

## Alternatives Considered

- **Python client libraries (libjuju, lightkube)**: Add heavy dependencies (libjuju alone pulls in asyncio, websockets, etc.), require async run loops, and duplicate CLI functionality. Rejected for Phase 2.
- **asyncio.subprocess**: Adds complexity for no practical benefit since collectors run sequentially.
- **`sh` library**: More ergonomic API but adds a third-party dependency for marginal gain over stdlib.
