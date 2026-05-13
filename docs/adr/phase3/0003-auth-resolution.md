# 0003 — Auth Resolution

**Status**: proposed  
**Date**: 2026-05-13  
**Depends on**: [0001](0001-package-structure.md)  
**Traces to**: [phase-3-analysis.md — Authentication](../../specs/phase-3-analysis.md#authentication)

---

## Context and Problem

Copilot SDK requires authentication. The spec defines a two-step fallback chain:

1. `GITHUB_TOKEN` environment variable
2. `gh auth token` — fallback via the GitHub CLI credential

If neither works, Phase 3 must exit with exit code 1 and a clear message telling the user how to fix it.

## Decision

Implement `src/glitch/analyze/_auth.py` with a single function:

```python
def resolve_token() -> str:
    """Return a GitHub token, or raise AuthError with remediation instructions."""
```

### Resolution logic

```python
import os
import shutil
import subprocess

class AuthError(Exception):
    """Copilot authentication failed."""

def resolve_token() -> str:
    # 1. Try GITHUB_TOKEN env var
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token

    # 2. Try gh auth token
    if shutil.which("gh"):
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                token = result.stdout.strip()
                if token:
                    return token
        except (subprocess.TimeoutExpired, OSError):
            pass

    # 3. Fail with clear instructions
    raise AuthError(
        "Copilot authentication failed.\n"
        "Set GITHUB_TOKEN environment variable or run: gh auth login"
    )
```

### Integration with CopilotSession (0002)

The `CopilotSession` class receives the token from `resolve_token()` and passes it to `CopilotClient` via `SubprocessConfig`:

```python
from copilot import SubprocessConfig

client = CopilotClient(
    subprocess_config=SubprocessConfig(auth_token=token)
)
```

## Consequences

### Files

| Action | File |
|---|---|
| Create | `src/glitch/analyze/_auth.py` |

### Acceptance criteria

1. `resolve_token()` returns token when `GITHUB_TOKEN` is set
2. `resolve_token()` returns token from `gh auth token` when `GITHUB_TOKEN` is unset
3. `resolve_token()` raises `AuthError` with remediation message when neither works
4. Error message includes the literal commands `GITHUB_TOKEN` and `gh auth login`
