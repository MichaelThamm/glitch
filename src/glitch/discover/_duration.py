"""Duration string parser for the ``--since`` flag (ADR 0009)."""

from __future__ import annotations

import re
from datetime import timedelta

_UNIT_SECONDS = {"h": 3600, "d": 86400, "w": 7 * 86400}
_RE = re.compile(r"^(?P<n>\d+)(?P<u>[hdw])$")


def parse_duration(s: str) -> timedelta:
    """Parse a duration like ``30d`` or ``2w`` into a ``timedelta``.

    Accepted grammar: ``<digits><unit>`` where unit is ``h``, ``d``, or ``w``.
    Raises ``ValueError`` on anything else.
    """
    m = _RE.match(s)
    if not m:
        raise ValueError(f"invalid duration: {s!r}. Expected <N><h|d|w>")
    return timedelta(seconds=int(m["n"]) * _UNIT_SECONDS[m["u"]])
