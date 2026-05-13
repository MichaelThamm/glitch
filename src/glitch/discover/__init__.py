"""Phase 1 - Discovery: local flakiness scoring from CI history.

Per ADR 0007, this package's ``__init__`` is a pure re-export of the Typer
entrypoint so that ``glitch.cli`` can wire ``discover.run`` without caring
about the internal layout. All implementation lives in sibling modules.

See: docs/specs/phase-1-discovery.md
"""

from glitch.discover._entrypoint import run

__all__ = ["run"]
