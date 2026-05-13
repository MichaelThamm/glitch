"""Abstract base classes and utilities for collectors."""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_registry: dict[str, type[Collector]] = {}


@dataclass
class CollectorResult:
    """The outcome of a single collector run."""

    status: Literal["ok", "skipped", "error"]
    """Execution status."""

    reason: str | None = None
    """Human-readable explanation when status is not 'ok'."""

    artifacts: list[Path] = field(default_factory=list)
    """Paths to collected artifact files (relative to output_dir)."""

    extra: dict = field(default_factory=dict)
    """Arbitrary metadata gathered during collection."""


class Collector(ABC):
    """Abstract base for all telemetry collectors."""

    name: str
    """Unique identifier used in the manifest."""

    priority: int = 50
    """Execution order (lower runs first)."""

    @abstractmethod
    def detect(self) -> bool:
        """Return True if the tool / data source this collector needs is available."""

    @abstractmethod
    def collect(self, output_dir: Path) -> CollectorResult:
        """Gather telemetry and write artifacts under *output_dir*."""


def register(cls: type[Collector]) -> type[Collector]:
    """Decorator that registers a collector class for automatic discovery."""
    _registry[cls.name] = cls
    return cls


def get_collectors() -> list[type[Collector]]:
    """Return all registered collector classes sorted by priority."""
    return sorted(_registry.values(), key=lambda c: c.priority)


def run_tool(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run an external tool with timeout and capture its output.

    Args:
        args: Command-line arguments (first element is the executable).
        timeout: Maximum wall-clock time in seconds.

    Returns:
        The completed process object.
    """
    logger.debug("Running: %s", " ".join(args))
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.stderr.strip():
        logger.debug("Stderr: %s", result.stderr.strip()[:200])
    return result