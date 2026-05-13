# ADR-003: Artifact Bundle Design

**Status**: Accepted  
**Phase**: 2 (Collection)  
**Date**: 2026-05-13

## Context

The artifact bundle is the primary output of Phase 2 and the primary input of Phase 3. It must be:

- Self-contained — interpretable without access to the original deployment
- Machine-readable (for Phase 3) and human-readable (for developers inspecting failures)
- Robust against partial collection — skipped collectors must be recorded, not silently omitted

## Decision

We use a **Pydantic model** for `manifest.json` and a **fixed directory layout** for all collected data.

### manifest.json

```python
# src/glitch/collectors/manifest.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

class CollectorEntry(BaseModel):
    status: Literal["ok", "skipped", "error"]
    reason: str | None = None
    extra: dict = {}

class Manifest(BaseModel):
    glitch_version: str
    collected_at: datetime
    collectors: dict[str, CollectorEntry]
```

Serialization uses `Manifest.model_dump_json(indent=2)` and deserialization in Phase 3 uses `Manifest.model_validate_json(...)`. This provides runtime validation and a clear contract between phases.

### Artifact bundle layout

```
{output_dir}/
├── manifest.json
├── summary.md
├── juju/
│   ├── status.json
│   ├── debug-log.txt
│   ├── units/<unit>.json
│   └── pebble/<unit>-<container>.txt
├── k8s/
│   ├── events.json
│   └── pods/<pod>-describe.txt
│   └── pods/<pod>-<container>.txt
├── lxd/
│   ├── list.json
│   └── instances/<instance>.txt
├── ceph/
│   ├── status.json
│   └── health-detail.json
└── test-artifacts/
    └── <copied as-is>
```

### Key behaviours

| Decision | Rationale |
|----------|-----------|
| Overwrite silently if output dir exists | Designed for CI where prompts cannot work; repeated runs are the normal case |
| No log truncation | CI artifact limits are generous (~10GB on GitHub); analysis filters what's relevant |
| Full recursive copy for test artifacts | Simplest; Phase 3 can parse specific formats (JUnit XML) from whatever is present |
| `.json` extension for structured data, `.txt` for unstructured | Phase 3 can infer parsing strategy from extension |
| **Failed pods only** for K8s describes/logs | Per spec: collect from pods with non-Running phase or restart count > 0 |

## Consequences

- **Positive**: Pydantic gives Phase 3 a typed, validated entry point into the bundle — no guessing whether `manifest.json` exists or has the right shape.
- **Positive**: Fixed layout means Phase 3 can locate collector outputs without parsing the manifest (e.g., `juju/status.json` is always at the same path).
- **Positive**: No truncation means analysis gets full context; no silent data loss.
- **Negative**: Pydantic adds a dependency (`pydantic>=2.0.0`). However, it is already a near-universal Python dependency and will likely be needed in Phase 3 regardless.
- **Negative**: Large `debug-log.txt` files could exceed CI artifact limits for very noisy deployments. Mitigation: this is considered an edge case; the spec explicitly chooses completeness over size safety.

## Alternatives Considered

- **Documented schema with no validation**: Risks Phase 2/Phase 3 version skew where a manifest field rename silently breaks analysis.
- **JSON Schema + `jsonschema`**: More formal but adds two dependencies (`jsonschema` + schema maintenance) for no more value than Pydantic provides.
- **Truncation**: Rejected per spec principle "Collect comprehensively — Analysis filters what's relevant."
- **Selective copy for test artifacts**: Rejected; full copy is simpler and Phase 3 handles parsing.
