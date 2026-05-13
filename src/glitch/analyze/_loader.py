"""Artifact bundle loading: manifest.json, collector paths, discovery JSON."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COLLECTORS = ("juju", "k8s", "lxd", "ceph", "test-artifacts")


@dataclass
class AnalysisContext:
    artifact_dir: Path
    manifest: dict[str, Any]
    collector_paths: dict[str, Path | None]
    discovery: dict[str, Any] | None


def load_context(
    artifact_dir: Path,
    discovery_json: Path | None = None,
) -> AnalysisContext:
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"No manifest.json found in {artifact_dir}. "
            f"This does not look like a Phase 2 artifact bundle."
        )

    manifest = json.loads(manifest_path.read_text())

    collector_paths: dict[str, Path | None] = {}
    for name in COLLECTORS:
        path = artifact_dir / name
        collector_paths[name] = path if path.is_dir() else None

    discovery: dict[str, Any] | None = None
    if discovery_json:
        if not discovery_json.is_file():
            print(
                f"Warning: --discovery-json not found at {discovery_json}",
                file=sys.stderr,
            )
        else:
            discovery = json.loads(discovery_json.read_text())

    return AnalysisContext(
        artifact_dir=artifact_dir,
        manifest=manifest,
        collector_paths=collector_paths,
        discovery=discovery,
    )


def read_collector_content(ctx: AnalysisContext) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, path in ctx.collector_paths.items():
        if path is None:
            continue
        parts: list[str] = []
        for f in sorted(path.iterdir()):
            if f.is_file():
                try:
                    parts.append(f.read_text())
                except (OSError, UnicodeDecodeError):
                    parts.append(f"[could not read {f.name}]")
        if parts:
            result[name] = "\n\n".join(parts)
    return result
