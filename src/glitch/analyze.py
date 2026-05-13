"""Phase 3 - Analysis: classify CI failures and suggest remediations.

See: docs/specs/phase-3-analysis.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def run(
    artifact_dir: Annotated[
        Path,
        typer.Option(
            "--artifact-dir",
            help="Path to the Phase 2 artifact bundle directory.",
            show_default=False,
        ),
    ],
    discovery_json: Annotated[
        Path | None,
        typer.Option(
            "--discovery-json",
            help="Path to Phase 1 JSON output to enrich classification confidence.",
        ),
    ] = None,
    confidence_threshold: Annotated[
        float,
        typer.Option(
            "--confidence-threshold",
            help="Remediation is attempted above this confidence value.",
            min=0.0,
            max=1.0,
        ),
    ] = 0.8,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory to write verdict and report."),
    ] = Path("./glitch-analysis"),
    model: Annotated[
        str | None,
        typer.Option("--model", help="Copilot model to use (default: determined by Copilot SDK)."),
    ] = None,
) -> None:
    """Classify failures from a Phase 2 artifact bundle and suggest remediations."""
    raise NotImplementedError(
        "Phase 3 (Analysis) is not implemented yet. "
        "See docs/specs/phase-3-analysis.md for the target behaviour."
    )
