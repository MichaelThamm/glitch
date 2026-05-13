# ADR-006: Execution UX and Progress Reporting

**Status**: Accepted  
**Phase**: 2 (Collection)  
**Date**: 2026-05-13

## Context

`glitch collect` runs in two contexts with different UX needs:

1. **CI runner** (`if: failure()` in GitHub Actions): output must be log-friendly, non-interactive, and not rely on TTY features
2. **Developer machine**: users benefit from visual progress indicators showing which collector is running and its status

The execution must be fast enough to not meaningfully extend CI run time after a failure.

## Decision

We use **Rich progress bars** for TTY sessions and plain log lines for non-TTY (CI) sessions, with automatic detection.

### Key elements

| Element | Decision |
|---------|----------|
| TTY detection | `sys.stdout.isatty()` — if True, use Rich Live display; if False, emit structured log lines |
| Progress display | Rich `Progress` with one task per collector, showing: `[green]✓[/] juju`, `[yellow]…[/] kubernetes`, `[red]✗[/] ceph` |
| CI output | `[COLLECT] juju: running…`, `[COLLECT] juju: ok (3 artifacts, 4.2s)`, `[COLLECT] ceph: skipped (CLI not found)` |
| Timing | Each collector's wall-clock time is recorded and displayed on completion |
| Verbose mode | `--verbose` / `-v` increases log detail; without it, only collector-level status is shown |

### Implementation sketch

```python
# src/glitch/collectors/runner.py
def run_collectors(
    collectors: list[Collector],
    output_dir: Path,
    *,
    model: str | None = None,
    namespace: str | None = None,
    test_artifacts_dir: Path | None = None,
) -> None:
    is_tty = sys.stdout.isatty()

    if is_tty:
        _run_with_progress(collectors, output_dir, ...)
    else:
        _run_with_logs(collectors, output_dir, ...)
```

### Collector status display

```
 ⠋ Collecting telemetry...
   ✓ juju (model: my-model, 3 artifacts, 8.4s)
   ✓ kubernetes (namespace: default, 2 artifacts, 1.2s)
   - lxd (skipped: CLI not found)
   - ceph (skipped: CLI not found)
   ✓ test-artifacts (from ./test-results, 12 files, 0.1s)
 ✓ Collection complete. 3/5 collectors ran successfully.
```

In CI mode, the same information is emitted as `[COLLECT]` prefixed log lines, one per collector.

## Consequences

- **Positive**: Rich progress bars give developers immediate visual feedback without flooding the terminal.
- **Positive**: CI output is grep-able (`[COLLECT]`, `ok`, `error`, `skipped`) and compatible with log viewers.
- **Positive**: Automatic TTY detection means no `--progress`/`--no-progress` flag is needed — the right behaviour is selected automatically.
- **Negative**: Rich `Live` display requires careful handling to avoid mangled output when subprocess stderr leaks through. Mitigation: capture stderr from subprocess calls; only emit collector-level status to the Rich display.

## Alternatives Considered

- **Always Rich progress bars**: Would produce ANSI escape sequences in CI logs, making them harder to read.
- **Always plain log lines**: Misses the opportunity for a polished developer experience, especially given Rich is already a dependency.
- **`--progress` CLI flag**: Unnecessary complexity; TTY detection handles the two cases automatically.
