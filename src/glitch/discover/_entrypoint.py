"""Typer entrypoint for ``glitch discover`` (ADR 0007).

This module owns the CLI surface only: option parsing, defaults, and the
orchestration shell. Domain logic lives in sibling modules (``client``,
``cache``, ``models``, ``scoring``, ``render``); this file should never grow
business rules of its own.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated

import typer


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


def run(
    repo: Annotated[
        str,
        typer.Option("--repo", help="GitHub repository in owner/repo format.", show_default=False),
    ],
    since: Annotated[
        str,
        typer.Option("--since", help="Lookback window (e.g. 30d, 2w)."),
    ] = "30d",
    output: Annotated[
        OutputFormat,
        typer.Option("--output", help="Output format."),
    ] = OutputFormat.table,
    cache_dir: Annotated[
        Path,
        typer.Option("--cache-dir", help="Directory for cached API responses."),
    ] = Path.home() / ".cache" / "glitch",
    branch: Annotated[
        str | None,
        typer.Option("--branch", help="Filter to a specific branch (default: repo default branch)."),
    ] = None,
) -> None:
    """Score test flakiness from CI history for the given repo."""
    raise NotImplementedError(
        "Phase 1 (Discovery) is not implemented yet. "
        "See docs/specs/phase-1-discovery.md for the target behaviour."
    )
