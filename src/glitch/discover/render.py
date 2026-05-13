"""Output rendering for the discovery report (ADR 0007).

This module owns every projection of ``DiscoveryReport`` to a user-facing
form. JSON serialisation lives here today; the rich-table renderer will join
it in a later commit.

TODO: add ``render_table(report) -> str`` (or write directly to a console)
for ``--output table``. Intentionally not scaffolded yet so the module
contains no half-finished surface.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

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


__all__ = ["to_json"]
