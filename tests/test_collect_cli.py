"""Tests for the `glitch collect` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from glitch.cli import app

runner = CliRunner()


class TestCollectCLIOptions:
    def test_help_lists_options(self) -> None:
        result = runner.invoke(app, ["collect", "--help"])
        assert result.exit_code == 0
        assert "--output-dir" in result.stdout
        assert "--model" in result.stdout
        assert "--namespace" in result.stdout
        assert "--test-artifacts-dir" in result.stdout

    def test_output_dir_default(self) -> None:
        result = runner.invoke(app, ["collect", "--help"])
        assert "[default: glitch-artifact]" in result.stdout

    def test_model_option_accepts_value(self) -> None:
        with patch("glitch.collect.run_collectors") as mock_runner:
            _ = runner.invoke(
                app, ["collect", "--output-dir", "/tmp/out", "--model", "my-model"]
            )
        mock_runner.assert_called_once_with(
            Path("/tmp/out"),
            model="my-model",
            namespace=None,
            test_artifacts_dir=None,
        )

    def test_namespace_option_accepts_value(self) -> None:
        with patch("glitch.collect.run_collectors") as mock_runner:
            _ = runner.invoke(
                app,
                ["collect", "--output-dir", "/tmp/out", "--namespace", "kube-system"],
            )
        mock_runner.assert_called_once_with(
            Path("/tmp/out"),
            model=None,
            namespace="kube-system",
            test_artifacts_dir=None,
        )

    def test_test_artifacts_dir_option_accepts_value(self) -> None:
        with patch("glitch.collect.run_collectors") as mock_runner:
            _ = runner.invoke(
                app,
                [
                    "collect",
                    "--output-dir",
                    "/tmp/out",
                    "--test-artifacts-dir",
                    "/tmp/artifacts",
                ],
            )
        mock_runner.assert_called_once_with(
            Path("/tmp/out"),
            model=None,
            namespace=None,
            test_artifacts_dir=Path("/tmp/artifacts"),
        )

    def test_all_options_combined(self) -> None:
        with patch("glitch.collect.run_collectors") as mock_runner:
            _ = runner.invoke(
                app,
                [
                    "collect",
                    "--output-dir",
                    "/tmp/bundle",
                    "--model",
                    "prod",
                    "--namespace",
                    "default",
                    "--test-artifacts-dir",
                    "/tmp/tests",
                ],
            )
        mock_runner.assert_called_once_with(
            Path("/tmp/bundle"),
            model="prod",
            namespace="default",
            test_artifacts_dir=Path("/tmp/tests"),
        )

    def test_default_args_passed(self) -> None:
        with patch("glitch.collect.run_collectors") as mock_runner:
            _ = runner.invoke(app, ["collect"])
        mock_runner.assert_called_once_with(
            Path("./glitch-artifact"),
            model=None,
            namespace=None,
            test_artifacts_dir=None,
        )

    def test_runner_exit_propagated(self) -> None:
        with patch(
            "glitch.collect.run_collectors",
            side_effect=typer.Exit(1),
        ):
            result = runner.invoke(app, ["collect", "--output-dir", "/tmp/out"])
        assert result.exit_code == 1