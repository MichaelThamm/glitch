"""Smoke tests for the glitch CLI skeleton."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from glitch import __version__
from glitch.cli import app

runner = CliRunner()


def test_root_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in ("discover", "collect", "analyze"):
        assert sub in result.stdout


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.parametrize("sub", ["discover", "collect", "analyze"])
def test_subcommand_help(sub: str) -> None:
    result = runner.invoke(app, [sub, "--help"])
    assert result.exit_code == 0
