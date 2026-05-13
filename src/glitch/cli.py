"""Root Typer application for the `glitch` CLI.

Each subcommand is implemented in its own module:
- `glitch discover` -> glitch.discover.run
- `glitch collect`  -> glitch.collect.run
- `glitch analyze`  -> glitch.analyze.run
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from glitch import __version__, analyze, collect, discover

app = typer.Typer(
    name="glitch",
    help="Automated CI failure remediation: discovery, collection, analysis.",
    no_args_is_help=True,
    add_completion=False,
)

app.command("discover", help="Phase 1 - Score test flakiness from CI history.")(discover.run)
app.command("collect", help="Phase 2 - Capture telemetry from a live deployment.")(collect.run)
app.command("analyze", help="Phase 3 - Classify failures and suggest remediations.")(analyze.run)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"glitch {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Emit debug-level logs to stderr."),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Print the installed version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Global options shared by every subcommand."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
