"""Tests for CopilotSession lifecycle and token handling."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def test_copilot_session_classify() -> None:
    import copilot

    response = MagicMock()
    response.data.content = '{"labels": {"flaky": 0.9}}'

    mock_session = MagicMock()
    mock_session.send_and_wait = AsyncMock(return_value=response)
    mock_client = MagicMock()
    mock_client.create_session = AsyncMock(return_value=mock_session)
    copilot.CopilotClient.return_value = mock_client

    from glitch.analyze._copilot import CopilotSession

    session = CopilotSession()
    result = session.classify("test prompt")
    assert result == '{"labels": {"flaky": 0.9}}'


def test_copilot_session_closed_raises() -> None:
    from glitch.analyze._copilot import CopilotSession

    session = CopilotSession()
    session.close()
    with pytest.raises(RuntimeError, match="Session is closed"):
        session.classify("test")


def test_copilot_session_close_idempotent() -> None:
    import copilot

    response = MagicMock()
    response.data.content = '{"labels": {"flaky": 0.9}}'
    mock_session = MagicMock()
    mock_session.send_and_wait = AsyncMock(return_value=response)
    mock_client = MagicMock()
    mock_client.create_session = AsyncMock(return_value=mock_session)
    copilot.CopilotClient.return_value = mock_client

    from glitch.analyze._copilot import CopilotSession

    session = CopilotSession()
    session.classify("test")
    session.close()
    session.close()


def test_copilot_session_token_passed() -> None:
    import copilot

    response = MagicMock()
    response.data.content = '{"labels": {"flaky": 0.9}}'
    mock_session = MagicMock()
    mock_session.send_and_wait = AsyncMock(return_value=response)
    mock_client = MagicMock()
    mock_client.create_session = AsyncMock(return_value=mock_session)
    copilot.CopilotClient.return_value = mock_client
    copilot.SubprocessConfig.reset_mock()

    from glitch.analyze._copilot import CopilotSession

    session = CopilotSession(token="ghp_test-token-1234")
    session.classify("test")
    copilot.SubprocessConfig.assert_called_once_with(github_token="ghp_test-token-1234")
