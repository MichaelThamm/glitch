"""Collect pre-existing test output files."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from glitch.collectors.base import Collector, CollectorResult, register

logger = logging.getLogger(__name__)

__test__ = False  # Prevent pytest from attempting to collect this class


@register
class TestArtifactsCollector(Collector):
    """Copy test output files (JUnit XML, coverage, etc.) into the bundle.

    Args:
        source_dir: Directory containing pre-existing test artifacts.
    """

    name = "test_artifacts"
    priority = 60
    __test__ = False

    def __init__(self, *, source_dir: Path | None = None) -> None:
        self.source_dir = source_dir

    def detect(self) -> bool:
        return self.source_dir is not None and self.source_dir.is_dir()

    def collect(self, output_dir: Path) -> CollectorResult:
        if not self.detect():
            logger.warning("Test artifacts source directory not available")
            return CollectorResult(
                status="skipped", reason="source_dir not found or not a directory"
            )

        source = self.source_dir
        assert source is not None
        dest = output_dir / "test-artifacts"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, dest, dirs_exist_ok=True)

        artifacts = list(dest.rglob("*"))

        return CollectorResult(status="ok", artifacts=artifacts)