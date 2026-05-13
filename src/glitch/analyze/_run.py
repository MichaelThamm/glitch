"""Main orchestration entry point for Phase 3 analysis."""

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
    from rich.console import Console

    console = Console()

    from ._auth import resolve_token
    from ._classify import classify
    from ._copilot import CopilotSession
    from ._loader import load_context, read_collector_content
    from ._output import write_outputs
    from ._patterns import PatternsStore, verdicts_to_entries, _upsert
    from ._remediate import plan_remediation, generate_content

    from dataclasses import asdict
    from glitch import __version__

    with console.status("[bold cyan]Resolving auth token...[/bold cyan]"):
        token = resolve_token()

    with console.status("[bold cyan]Loading artifact context...[/bold cyan]"):
        ctx = load_context(artifact_dir, discovery_json)

    session = CopilotSession(token=token, model=model)
    try:
        with console.status("[bold cyan]Classifying failure with Copilot...[/bold cyan]"):
            classification = classify(ctx, session)

        with console.status("[bold cyan]Planning remediation...[/bold cyan]"):
            remediation = plan_remediation(classification.verdicts, confidence_threshold)

        collector_content = read_collector_content(ctx)
        evidence_summary = "\n".join(
            f"- {name}: {len(text)} chars" for name, text in collector_content.items()
        ) or "(no collector telemetry available)"

        with console.status("[bold cyan]Generating remediation content...[/bold cyan]"):
            generate_content(remediation, session, classification.verdicts, evidence_summary)

        with console.status("[bold cyan]Writing outputs...[/bold cyan]"):
            write_outputs(output_dir, classification, remediation, ctx, __version__, confidence_threshold)

        from rich.table import Table
        from ._remediate import RemediationAction

        label_action: dict[str, str] = {
            RemediationAction.PATCH.name: "Patch generated",
            RemediationAction.SUGGESTION.name: "Retry / fix suggested",
            RemediationAction.ISSUE_TEMPLATE.name: "Issue template filed",
            RemediationAction.NARRATIVE.name: "Insufficient signal",
        }

        table = Table(title="glitch analyze")
        table.add_column("Test", style="cyan", no_wrap=True, max_width=48)
        table.add_column("Classification", style="magenta")
        table.add_column("Confidence", justify="right", style="yellow")
        table.add_column("Action", style="green")

        for verdict in classification.verdicts:
            top_label, top_conf = max(verdict.labels.items(), key=lambda x: x[1])
            action = next(
                (e.action for e in remediation.entries
                 if e.test_id == verdict.test_id and e.label == top_label),
                RemediationAction.NARRATIVE,
            )
            test_name = verdict.test_id
            if len(test_name) > 48:
                test_name = "…" + test_name[-47:]
            action_text = label_action.get(action.name, str(action))
            if action == RemediationAction.PATCH:
                action_text += " → fix.patch"

            table.add_row(test_name, top_label, f"{top_conf:.2f}", action_text)

        console.print()
        console.print(table)
        console.print(f"\n[bold]Output written to [green]{output_dir}[/green][/bold]")
        for f in sorted(output_dir.iterdir()):
            if f.is_file():
                console.print(f"  • {f.name}")

        with console.status("[bold cyan]Persisting to patterns store...[/bold cyan]"):
            store = PatternsStore()
            existing = store.read()
            repo = ctx.manifest.get("repository", "unknown")
            new_entries = verdicts_to_entries(classification.verdicts, repo, remediation)
            updated = _upsert(existing, [asdict(e) for e in new_entries])
            store.write(updated)
    finally:
        session.close()
