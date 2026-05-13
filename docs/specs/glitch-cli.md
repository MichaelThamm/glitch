# Spec: `glitch` CLI

**Status**: Draft  
**Traces to**: [VISION.md](../../VISION.md)

---

## Purpose

`glitch` is a unified Python CLI tool that delivers all three phases of the automated CI failure remediation system. Each phase is an independent subcommand; they can be adopted incrementally.

---

## Subcommands

| Subcommand | Phase | Primary runtime |
|---|---|---|
| `glitch discover` | 1 — Discovery | Local developer machine |
| `glitch collect` | 2 — Collection | CI runner (GitHub Actions) |
| `glitch analyze` | 3 — Analysis | Local or CI runner |

Each subcommand is fully documented in its own spec:

- [phase-1-discovery.md](phase-1-discovery.md)
- [phase-2-collection.md](phase-2-collection.md)
- [phase-3-analysis.md](phase-3-analysis.md)

---

## Installation

### Developer machines

```bash
pipx install glitch
```

### CI runners (GitHub Actions)

```bash
pip install glitch
```

No system dependencies beyond Python are required.

---

## Requirements

- **Python**: 3.11 or later
- **OS**: Linux, macOS (Windows is not a supported target)
- **GitHub CLI** (`gh`): optional — used as an auth fallback by `glitch discover` and `glitch collect`

---

## Global Flags

These flags are available on every subcommand:

| Flag | Description |
|---|---|
| `--verbose`, `-v` | Emit debug-level logs to stderr |
| `--version` | Print the installed version and exit |

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | User error (bad arguments, missing auth, repo not found) |
| `2` | Runtime error (API failure, unexpected state) |

---

## Packaging

- Distributed on **PyPI** under the package name `glitch`
- Entry point: `glitch` → `glitch.cli:main`
- Dependencies are pinned in `pyproject.toml`; subcommand dependencies (e.g. `rich` for Discovery's table output) are declared as optional extras if they are not shared across all phases
