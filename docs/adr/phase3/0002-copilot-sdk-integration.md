# 0002 — Copilot SDK Integration

**Status**: proposed  
**Date**: 2026-05-13  
**Depends on**: [0001](0001-package-structure.md)  
**Traces to**: [phase-3-analysis.md — LLM Integration](../../specs/phase-3-analysis.md#llm-integration), [theow `_gateway/_copilot.py`](/home/ivdi/Repo/theow/src/theow/_gateway/_copilot.py)

---

## Context and Problem

Phase 3 is the only phase that uses an LLM. The spec mandates the GitHub Copilot SDK (`copilot` package). The SDK is async-only (asyncio) but Phase 3's Typer CLI commands are synchronous. We need to bridge async ↔ sync cleanly.

The theow project solves this with a **persistent event loop** pattern — creating one `asyncio.AbstractEventLoop` with `asyncio.new_event_loop()`, reusing it across calls with `loop.run_until_complete()`, and closing it on teardown. This avoids `asyncio.run()` which closes the loop after each call, breaking multi-turn sessions.

We follow that pattern but simplified: Phase 3 uses a **single `send_and_wait()` call** per analysis (one-shot classification), not multi-turn. So we *could* use `asyncio.run()`. However, following theow's persistent-loop pattern is safer for future extensibility (e.g., retry on malformed output).

The spec also notes: the Copilot SDK bundles a native binary at `copilot/bin/copilot` that ships without execute permission on Linux. Theow's workaround applies `chmod +x` on module import.

## Decision

Implement `src/glitch/analyze/_copilot.py` with a `CopilotSession` class that:

1. On module import: applies the Linux `chmod` workaround.
2. Creates a persistent `asyncio.AbstractEventLoop` via `asyncio.new_event_loop()`.
3. Provides `async _create_session()` and `async _send(prompt)` methods.
4. Wraps them with a sync `classify()` method using `self._loop.run_until_complete()`.
5. Provides a `close()` method that destroys session, stops client, and closes the loop.

### Interface sketch

```python
# src/glitch/analyze/_copilot.py

class CopilotSession:
    def __init__(self, model: str | None = None) -> None:
        self._model = model
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None
        self._session = None

    def classify(self, prompt: str) -> str:
        """Sync wrapper: send prompt to Copilot, return raw response text."""
        ...

    def close(self) -> None:
        """Destroy session, stop client, close loop."""
        ...
```

### Key implementation details (from theow)

```python
# Linux chmod workaround (run at module level or in __init__)
import copilot
import os, stat
from pathlib import Path

_copilot_bin = Path(copilot.__file__).parent / "bin" / "copilot"
if _copilot_bin.exists() and not os.access(_copilot_bin, os.X_OK):
    _copilot_bin.chmod(_copilot_bin.stat().st_mode | stat.S_IXUSR)

# Session creation
from copilot import CopilotClient, PermissionHandler

client = CopilotClient()
session = await client.create_session({
    "model": self._model,
    "on_permission_request": PermissionHandler.approve_all,
})

# Send prompt and wait (timeout 900s matches theow)
response = await session.send_and_wait({"prompt": prompt}, timeout=900)

# Teardown
await session.destroy()
await client.stop()
```

## Consequences

### Files

| Action | File |
|---|---|
| Create | `src/glitch/analyze/_copilot.py` |

### Dependencies

`github-copilot-sdk>=0.1.30` is added to `pyproject.toml` by 0001.

### Acceptance criteria

1. `from glitch.analyze._copilot import CopilotSession` succeeds when copilot SDK is installed
2. `CopilotSession().classify("hello")` returns a non-empty string
3. `CopilotSession().close()` runs without error, and calling `classify()` on a closed session raises a clear error
4. The `chmod` workaround runs automatically on Linux when the module is imported (no manual step)
