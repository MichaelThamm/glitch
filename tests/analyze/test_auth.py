"""Tests for auth token resolution."""
from __future__ import annotations

import shutil
import subprocess
from unittest.mock import MagicMock

import pytest

from glitch.analyze._auth import AuthError, resolve_token


class TestResolveToken:
    def test_resolve_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "env-token")
        assert resolve_token() == "env-token"

    def test_resolve_token_gh_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(subprocess, "run", _fake_gh_success)
        monkeypatch.setattr(shutil, "which", lambda _cmd: "/usr/bin/gh")
        assert resolve_token() == "gh-token"

    def test_resolve_token_gh_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(shutil, "which", lambda _cmd: None)
        with pytest.raises(AuthError, match="Copilot authentication failed"):
            resolve_token()

    def test_resolve_token_gh_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(subprocess, "run", _fake_gh_failure)
        monkeypatch.setattr(shutil, "which", lambda _cmd: "/usr/bin/gh")
        with pytest.raises(AuthError, match="Copilot authentication failed"):
            resolve_token()

    def test_resolve_token_empty_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "   ")
        monkeypatch.setattr(subprocess, "run", _fake_gh_success)
        monkeypatch.setattr(shutil, "which", lambda _cmd: "/usr/bin/gh")
        assert resolve_token() == "gh-token"


def _fake_gh_success(*_args, **_kwargs) -> MagicMock:
    result = MagicMock()
    result.returncode = 0
    result.stdout = "gh-token\n"
    return result


def _fake_gh_failure(*_args, **_kwargs) -> MagicMock:
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    return result
