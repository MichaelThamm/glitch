from unittest.mock import MagicMock
from unittest.mock import patch

import pytest


def _mock_copilot_sdk():
    mock_copilot = MagicMock()
    mock_copilot.__file__ = "/fake/copilot/__init__.py"

    mock_client = MagicMock()
    mock_session = MagicMock()
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
        "copilot.session": MagicMock(),
        "copilot.generated.session_events": MagicMock(),
    }


@pytest.fixture(autouse=True)
def mock_copilot():
    with patch.dict("sys.modules", _mock_copilot_sdk()):
        yield


@pytest.fixture
def temp_output_dir(tmp_path):
    d = tmp_path / "glitch-analysis"
    d.mkdir()
    return d


@pytest.fixture
def valid_manifest(tmp_path):
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    manifest = artifact_dir / "manifest.json"
    manifest.write_text('{"collectors": {"juju": "ok"}, "test_id": "test-foo", "repository": "test-repo"}'  )
    return artifact_dir


@pytest.fixture
def sample_verdict():
    return {
        "test_id": "integration (test_deploy_local)",
        "labels": {"charm-bug": 0.91, "flaky": 0.12},
        "reasoning_trace": "Step 1: ...",
    }
