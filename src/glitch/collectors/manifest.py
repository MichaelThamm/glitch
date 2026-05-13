"""Pydantic model for the collection manifest."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CollectorEntry(BaseModel):
    """Per-collector outcome recorded in the manifest."""

    status: Literal["ok", "skipped", "error"]
    reason: str | None = None
    extra: dict = {}


class Manifest(BaseModel):
    """Top-level manifest describing the collection run."""

    glitch_version: str
    collected_at: datetime
    collectors: dict[str, CollectorEntry]