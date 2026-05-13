"""Phase 2 - Collection: capture telemetry from a live deployment.

See: docs/specs/phase-2-collection.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def run(
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory to write the artifact bundle."),
    ] = Path("./glitch-artifact"),
    model: Annotated[
        str | None,
        typer.Option("--model", help="Juju model to collect from (default: active model)."),
    ] = None,
    namespace: Annotated[
        str | None,
        typer.Option(
            "--namespace",
            help="Kubernetes namespace to collect from (default: current kubectl context).",
        ),
    ] = None,
    test_artifacts_dir: Annotated[
        Path | None,
        typer.Option(
            "--test-artifacts-dir",
            help="Directory containing pre-existing test output files (JUnit XML, coverage, etc.).",
        ),
    ] = None,
) -> None:
    """Capture telemetry from the active deployment into an artifact bundle."""
    raise NotImplementedError(
        "Phase 2 (Collection) is not implemented yet. "
        "See docs/specs/phase-2-collection.md for the target behaviour."
    )
