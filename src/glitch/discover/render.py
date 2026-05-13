"""Output rendering for the discovery report (ADR 0007).

This module owns every projection of ``DiscoveryReport`` to a user-facing
form: the canonical JSON wire format for ``--output json`` and the rich-table
rendering for ``--output table``.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

from rich.console import Console
from rich.table import Table

from glitch.discover.models import DiscoveryReport


def _isoformat(dt: datetime) -> str:
    """Render a timezone-aware UTC ``datetime`` as ``...Z``-suffix ISO 8601."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def to_json(report: DiscoveryReport) -> str:
    """Serialise a ``DiscoveryReport`` to the canonical JSON wire format."""
    return json.dumps(
        dataclasses.asdict(report),
        default=_isoformat,
        indent=2,
    )


def render_table(report: DiscoveryReport, console: Console | None = None) -> None:
    """Render ``report`` to ``console`` as the spec's terminal table.

    Columns: ``Rank``, ``Test Name``, ``Score``, the four heuristic component
    scores, and ``Trend`` (last 5 runs encoded as ``↑`` for pass / ``↓`` for
    fail). Tests in ``insufficient_data`` are listed below the table without
    a score, per the spec.
    """
    console = console if console is not None else Console()

    if report.meta.workflows:
        console.print(f"Workflows: {', '.join(report.meta.workflows)}")

    if report.tests:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Rank", justify="right")
        table.add_column("Test Name")
        table.add_column("Score", justify="right")
        table.add_column("Volatility", justify="right")
        table.add_column("Retry", justify="right")
        table.add_column("Timing", justify="right")
        table.add_column("Change-Indep", justify="right")
        table.add_column("Trend")
        for rank, test in enumerate(report.tests, start=1):
            trend = "".join("↑" if r == "pass" else "↓" for r in test.trend)
            short_name = test.job_name.rsplit(" / ", 1)[-1]
            table.add_row(
                str(rank),
                short_name,
                f"{test.flakiness_index:.2f}",
                f"{test.heuristics.volatility:.2f}",
                f"{test.heuristics.retry_rate:.2f}",
                f"{test.heuristics.timing_variance:.2f}",
                f"{test.heuristics.change_independence:.2f}",
                trend,
            )
        console.print(table)

    if report.insufficient_data:
        if report.tests:
            console.print()
        console.print("[bold]Insufficient data[/bold] (fewer than 3 runs):")
        for entry in report.insufficient_data:
            suffix = "" if entry.run_count == 1 else "s"
            short_id = entry.id.rsplit(" / ", 1)[-1]
            console.print(f"  {short_id}  ({entry.run_count} run{suffix})")


__all__ = ["render_table", "to_json"]
