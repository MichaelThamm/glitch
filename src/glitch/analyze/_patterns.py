"""Known-patterns store for persisting resolved failure patterns."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ._classify import ClassificationVerdict
    from ._remediate import RemediationPlan


@dataclass
class PatternEntry:
    id: str
    recorded_at: str
    repo: str
    test_id: str
    labels: dict[str, float]
    summary: str
    resolution: str


def _patterns_path() -> Path:
    xdg_data = os.environ.get(
        "XDG_DATA_HOME", str(Path.home() / ".local" / "share")
    )
    store_dir = Path(xdg_data) / "glitch"
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir / "patterns.json"


def _upsert(
    existing: list[dict[str, Any]], new_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    def key(entry: dict[str, Any]) -> tuple[str, str]:
        return (entry["repo"], entry["test_id"])

    index = {key(e): i for i, e in enumerate(existing)}
    for entry in new_entries:
        k = key(entry)
        if k in index:
            existing[index[k]] = entry
        else:
            existing.append(entry)
    return existing


class PatternsStore:
    def __init__(self) -> None:
        self._path = _patterns_path()

    def read(self) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text())
            return data.get("patterns", [])
        except (json.JSONDecodeError, OSError):
            return []

    def write(self, patterns: list[dict[str, Any]]) -> None:
        self._path.write_text(
            json.dumps({"patterns": patterns}, indent=2)
        )

    def append(self, entries: list[PatternEntry]) -> None:
        existing = self.read()
        new = [asdict(e) for e in entries]
        updated = _upsert(existing, new)
        self.write(updated)


def verdicts_to_entries(
    verdicts: list[ClassificationVerdict],
    repo: str,
    remediation: RemediationPlan,
) -> list[PatternEntry]:
    from ._remediate import RemediationAction

    action_map: dict[str, str] = {}
    for entry in remediation.entries:
        if entry.test_id not in action_map or entry.action == RemediationAction.PATCH:
            action_map[entry.test_id] = entry.action.name.lower()

    entries = []
    for verdict in verdicts:
        resolution = action_map.get(verdict.test_id, "narrative")
        entry = PatternEntry(
            id=str(uuid4()),
            recorded_at=datetime.now(timezone.utc).isoformat(),
            repo=repo,
            test_id=verdict.test_id,
            labels=verdict.labels,
            summary=verdict.reasoning_trace[:500],
            resolution=resolution,
        )
        entries.append(entry)
    return entries


