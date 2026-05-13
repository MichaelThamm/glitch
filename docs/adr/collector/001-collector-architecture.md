# ADR-001: Collector Module Architecture

**Status**: Accepted  
**Phase**: 2 (Collection)  
**Date**: 2026-05-13

## Context

Phase 2 must capture telemetry from five distinct domains (Juju, Kubernetes, LXD, Ceph, and test artifacts). Each collector has its own CLI dependencies, data sources, and output formats. The architecture must:

- Allow collectors to be added or removed without modifying a central dispatcher
- Gracefully skip collectors whose target environment is absent
- Keep execution simple and sequential to avoid coordination complexity
- Support clear error boundaries so one failing collector does not block others

## Decision

We will use an **abstract base class (ABC) with a global registry** pattern. Collectors self-register on import, and a central runner iterates them sequentially.

### Key elements

| Element | Decision |
|---------|----------|
| Base class | `Collector(ABC)` with `name: str`, `detect() -> bool`, `collect(output_dir: Path) -> CollectorResult` |
| Registry | Global `dict[str, type[Collector]]` populated at module import time via `@register` decorator |
| Execution order | Sequential, ordered by collector priority (deterministic) |
| Source layout | `src/glitch/collectors/` package containing `base.py`, `juju.py`, `kubernetes.py`, `lxd.py`, `ceph.py`, `test_artifacts.py` |
| Detection | `shutil.which("juju")` (etc.) in each collector's `detect()` — fast, standard-library-only, no side effects |
| Error isolation | Each collector wrapped in try/except; failures logged but do not abort remaining collectors |

### CollectorContract

```python
@dataclass
class CollectorResult:
    status: Literal["ok", "skipped", "error"]
    reason: str | None        # explanation when skipped/error
    artifacts: list[Path]     # files written by this collector
```

### Registration pattern

```python
# src/glitch/collectors/base.py
_registry: dict[str, type[Collector]] = {}

def register(cls: type[Collector]) -> type[Collector]:
    _registry[cls.name] = cls
    return cls

def get_collectors() -> list[type[Collector]]:
    return list(_registry.values())
```

```python
# src/glitch/collectors/juju.py
from .base import Collector, register

@register
class JujuCollector(Collector):
    name = "juju"
    priority = 10

    def detect(self) -> bool:
        return shutil.which("juju") is not None

    def collect(self, output_dir: Path) -> CollectorResult:
        ...
```

## Consequences

- **Positive**: Decoupled collectors can evolve independently. Adding a new collector requires only a new file in `collectors/` — no changes to the runner.
- **Positive**: Sequential execution avoids concurrency bugs around shared subprocess/file resources.
- **Positive**: `shutil.which` detection is zero-cost and side-effect-free.
- **Negative**: Registry populated by import side effects — all collector modules must be imported explicitly (e.g., in `collectors/__init__.py`). Missing an import means a collector is silently absent.

## Alternatives Considered

- **Plugin/entry-point system**: Too heavyweight for 5 collectors; adds packaging complexity without near-term benefit.
- **Simple function dispatch with hardcoded list**: Fragile; every new collector requires touching the dispatcher.
- **Concurrent execution**: Subprocess calls already dominate runtime; parallel execution adds coordination complexity for marginal wall-clock gain.
