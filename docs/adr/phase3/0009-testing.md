# 0009 — Testing

**Status**: done  
**Date**: 2026-05-13  
**Depends on**: [0001](0001-package-structure.md) through [0008](0008-patterns-store.md)  
**Traces to**: [theow test patterns](/home/ivdi/Repo/theow/tests/gateway/test_copilot.py)

---

## Context and Problem

Phase 3 modules depend on `github-copilot-sdk`, which requires a native binary and network access to Copilot servers. Tests must run offline in CI without the SDK installed. The theow project solves this by mocking the entire `copilot` package via `sys.modules` patching.

Additionally, all modules need unit test coverage: auth, loading, classification parsing, remediation planning, output writing, patterns store.

## Decision

### Test structure

Mirror the analyze package structure:

```
tests/
├── analyze/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures: mock copilot, temp artifact dir
│   ├── test_auth.py          # 0003
│   ├── test_loader.py        # 0004
│   ├── test_classify.py      # 0005 (parse only, no live LLM)
│   ├── test_remediate.py     # 0006
│   ├── test_output.py        # 0007
│   ├── test_patterns.py      # 0008
│   └── test_run.py           # Integration: full pipeline with mock copilot
```

### Mocking Copilot SDK (from theow pattern)

```python
# tests/analyze/conftest.py

import sys
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

def _mock_copilot_sdk():
    """Build mock modules for copilot package to avoid native binary / network requirement."""
    mock_copilot = MagicMock()
    mock_copilot.__file__ = "/fake/copilot/__init__.py"

    # CopilotClient returns a mock that yields a session
    mock_client = MagicMock()
    mock_session = MagicMock()

    # Mock send_and_wait to return a fake classification response
    mock_session.send_and_wait.return_value = {"text": '{"labels": {"flaky": 0.9}}'}

    mock_client.create_session.return_value = mock_session
    mock_copilot.CopilotClient.return_value = mock_client
    mock_copilot.PermissionHandler = MagicMock()
    mock_copilot.Tool = MagicMock()
    mock_copilot.SubprocessConfig = MagicMock()

    mock_types = MagicMock()
    mock_types.ToolInvocation = dict
    mock_types.ToolResult = dict

    return {
        "copilot": mock_copilot,
        "copilot.types": mock_types,
        "copilot.generated.session_events": MagicMock(),
    }

@pytest.fixture(autouse=True)
def mock_copilot():
    """Patch sys.modules to mock the entire copilot package."""
    with patch.dict("sys.modules", _mock_copilot_sdk()):
        yield

@pytest.fixture
def temp_output_dir(tmp_path):
    d = tmp_path / "glitch-analysis"
    d.mkdir()
    return d

@pytest.fixture
def valid_manifest(tmp_path):
    """Create a minimal valid artifact bundle."""
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    manifest = artifact_dir / "manifest.json"
    manifest.write_text('{"collectors": {"juju": "ok"}}')
    return artifact_dir

@pytest.fixture
def sample_verdict():
    return {
        "test_id": "integration (test_deploy_local)",
        "labels": {"charm-bug": 0.91, "flaky": 0.12},
        "reasoning_trace": "Step 1: ...",
    }
```

### Test coverage by ADR

| ADR | Test file | What to test |
|---|---|---|
| 0003 | `test_auth.py` | `resolve_token()` with GITHUB_TOKEN set, unset, gh fallback, AuthError raised |
| 0004 | `test_loader.py` | `load_context()` with valid manifest, missing manifest, missing collectors, bad JSON, discovery JSON warn |
| 0005 | `test_classify.py` | `parse_classification()` with valid JSON, fenced JSON, malformed → error; prompt construction with/without discovery |
| 0006 | `test_remediate.py` | `plan_remediation()` for each label at/above/below threshold; single-patch constraint |
| 0007 | `test_output.py` | `write_verdict()` schema validation, `write_report()` section presence, `write_patch()` only when applicable, directory creation |
| 0008 | `test_patterns.py` | Read empty store, append entries, upsert duplicates, XDG_DATA_HOME, required fields |
| 0002 | `test_copilot.py` | `CopilotSession` creation, `classify()` returns response, `close()` cleanup, Linux chmod (not tested, just covered) |
| 0001 | `test_run.py` | Full pipeline with mock copilot: load artifact → classify → remedial → write outputs → patterns store |

### Integration test (test_run.py)

One integration test that exercises the full pipeline end-to-end with mocked copilot:

```python
def test_full_pipeline(temp_output_dir, valid_manifest, mock_copilot):
    from glitch.analyze._run import run_pipeline

    result = run_pipeline(
        artifact_dir=valid_manifest,
        output_dir=temp_output_dir,
        confidence_threshold=0.8,
    )

    # Check outputs exist
    assert (temp_output_dir / "verdict.json").is_file()
    assert (temp_output_dir / "report.md").is_file()
    assert result.patch_generated  # depends on mock copilot response
```

### CLI smoke tests

Existing tests in `tests/test_cli.py` must continue to pass. The import path `from glitch.analyze import run` must work after the package conversion.

## Consequences

### Files

| Action | File |
|---|---|
| Create | `tests/analyze/__init__.py` |
| Create | `tests/analyze/conftest.py` |
| Create | `tests/analyze/test_auth.py` |
| Create | `tests/analyze/test_loader.py` |
| Create | `tests/analyze/test_classify.py` |
| Create | `tests/analyze/test_remediate.py` |
| Create | `tests/analyze/test_output.py` |
| Create | `tests/analyze/test_patterns.py` |
| Create | `tests/analyze/test_copilot.py` |
| Create | `tests/analyze/test_run.py` |
| Modify | `tests/test_cli.py` | (only if needed; should pass as-is if `__init__.py` is correct) |

### Acceptance criteria

1. `just test` passes all existing and new tests
2. Tests run without `github-copilot-sdk` installed (fully mocked)
3. Integration test covers the full pipeline
4. `test_cli.py` smoke tests pass unchanged
5. `test_auth.py` tests all three auth paths
6. `test_loader.py` tests all five error conditions from the spec
