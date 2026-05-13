"""Shared pytest fixtures for the glitch test suite.

Per ADR 0008: canned API fixtures live under ``tests/fixtures/discover/`` and
are loaded by hand-rolled JSON files rather than recorded by ``vcrpy``. Tests
that need them request the ``fixtures_dir`` fixture and read the JSON they
need explicitly.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Absolute path to ``tests/fixtures/discover/``."""
    return Path(__file__).parent / "fixtures" / "discover"
