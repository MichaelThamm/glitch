<p align="center">
  <img src="assets/glitch-full.png" alt="Glitch — AI-first CI failure automation" width="700">
</p>

Automated CI failure remediation for charm development — turn flaky tests and obscure failures into actionable fixes.

Three phases, one goal: **reduce MTTR**. Discovery scores flakiness locally. Collection captures telemetry on failure. Analysis classifies root causes and generates patches — all with human-in-the-loop approval.

---

## Output examples

### Phase 2: Collection — capture telemetry on failure

```
❯ uv run glitch collect
Collecting juju              ━━━━━━━━━━━━━━━━━━━━ 1/5  0:00:01   juju: ok (2 artifacts, 0.8s)
Collecting kubernetes        ━━━━━━━━━━━━━━━━━━━━ 2/5  0:00:06   kubernetes: ok (38 artifacts, 6.2s)
Collecting lxd               ━━━━━━━━━━━━━━━━━━━━ 3/5  0:00:07   lxd: ok (2 artifacts, 0.3s)
Collecting ceph              ━━━━━━━━━━━━━━━━━━━━ 4/5  0:00:07   ceph: skipped
Collecting test_artifacts    ━━━━━━━━━━━━━━━━━━━━ 5/5  0:00:08   test_artifacts: ok (12 artifacts, 1.1s)
```

### Phase 1: Discovery — score flakiness locally

```
❯ uv run glitch discover --repo canonical/opentelemetry-collector-operator --workflow "Release Charm" --output table
Workflows: Release Charm
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Rank ┃ Test Name                                        ┃ Score ┃ Volatility ┃ Retry ┃ Timing ┃ Change-Indep ┃ Trend ┃
┡━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━┩
│    1 │ Integration Tests (parallel)                     │  0.68 │       1.00 │  0.29 │   0.70 │         0.71 │ ↓↓↓↓↓ │
│      │ (test_external_config.py)                        │       │            │       │        │              │       │
│    2 │ Define Integration tests matrix                  │  0.63 │       1.00 │  0.29 │   0.51 │         0.71 │ ↓↓↓↓↓ │
│    3 │ Select snap channels                             │  0.61 │       1.00 │  0.29 │   0.45 │         0.71 │ ↓↓↓↓↓ │
│    4 │ Integration Tests (parallel) (test_tracing.py)   │  0.60 │       1.00 │  0.29 │   0.40 │         0.71 │ ↓↓↓↓↓ │
│    5 │ check                                            │  0.59 │       1.00 │  0.29 │   0.36 │         0.71 │ ↓↓↓↓↓ │
│    6 │ Lint alert rules                                 │  0.58 │       1.00 │  0.29 │   0.33 │         0.71 │ ↓↓↓↓↓ │
│    7 │ Define runner and build matrix                   │  0.58 │       0.50 │  0.24 │   1.00 │         0.59 │ ↓↓↓↓↓ │
│    8 │ Release any bumped charm library                 │  0.58 │       0.50 │  0.24 │   1.00 │         0.59 │ ↓↓↓↓↓ │
│    9 │ Integration Tests (parallel)                     │  0.58 │       1.00 │  0.29 │   0.32 │         0.71 │ ↓↓↓↓↓ │
│      │ (test_removal_hooks.py)                          │       │            │       │        │              │       │
│   10 │ Static analysis                                  │  0.58 │       1.00 │  0.29 │   0.31 │         0.71 │ ↓↓↓↓↓ │
│   11 │ Integration Tests (parallel) (test_principal.py) │  0.58 │       1.00 │  0.29 │   0.31 │         0.71 │ ↓↓↓↓↓ │
│   12 │ Validate Terraform files                         │  0.56 │       1.00 │  0.29 │   0.26 │         0.71 │ ↓↓↓↓↓ │
│   13 │ Integration Tests (parallel) (test_cos_agent.py) │  0.56 │       1.00 │  0.29 │   0.25 │         0.71 │ ↓↓↓↓↓ │
│   14 │ Integration Tests (parallel)                     │  0.55 │       1.00 │  0.00 │   0.20 │         1.00 │ ↓↓↓↓↓ │
│      │ (test_snap_refresh.py)                           │       │            │       │        │              │       │
│   15 │ Linting                                          │  0.55 │       1.00 │  0.29 │   0.19 │         0.71 │ ↓↓↓↓↓ │
│   16 │ Unit tests                                       │  0.55 │       1.00 │  0.29 │   0.19 │         0.71 │ ↓↓↓↓↓ │
│   17 │ Integration Tests (parallel)                     │  0.54 │       1.00 │  0.29 │   0.14 │         0.71 │ ↓↓↓↓↓ │
│      │ (test_log_rotation.py)                           │       │            │       │        │              │       │
│   18 │ Pack the charm                                   │  0.53 │       1.00 │  0.29 │   0.12 │         0.71 │ ↓↓↓↓↓ │
│   19 │ CodeQL analysis                                  │  0.52 │       1.00 │  0.29 │   0.08 │         0.71 │ ↓↓↓↓↓ │
│   20 │ Release the charm (ubuntu-latest)                │  0.50 │       0.00 │  0.67 │   1.00 │         0.33 │ ↑↓↓↑↑ │
│   21 │ Check against ignorelist                         │  0.49 │       0.50 │  0.24 │   0.62 │         0.59 │ ↓↓↓↓↓ │
│   22 │ Inclusive naming check                           │  0.23 │       0.00 │  0.31 │   0.00 │         0.62 │ ↑↓↓↓↓ │
│   23 │ Quality Checks                                   │ -0.35 │       0.00 │  0.00 │  -1.41 │         0.00 │ ↑↑↑   │
│   24 │ Release the charm                                │ -0.51 │       0.50 │  0.00 │  -3.27 │         0.73 │ ↓↓↓↓↓ │
│   25 │ Integration Tests (sequential)                   │ -0.96 │       1.00 │  0.29 │  -5.83 │         0.71 │ ↓↓↓↓↓ │
└──────┴──────────────────────────────────────────────────┴───────┴────────────┴───────┴────────┴──────────────┴───────┘

Insufficient data (fewer than 3 runs):
  Release the charm (Ubuntu_ARM64_4C_16G_03)  (2 runs)
```

### Phase 3: Analysis — classify and fix

```
❯ uv run glitch analyze --artifact bundle-2026-05-13.tar.gz --scores discover.json

  TEST                            CLASSIFICATION        CONFIDENCE   ACTION
  ──────────────────────────────  ────────────────────  ───────────  ────────────────────────
  test_ssl_termination            flaky                 0.82         Retry policy suggested
  test_scaling_events             infrastructure        0.91         Issue #1742 filed
  test_config_update_rollback     charm-bug             0.76         Patch generated → pr/112

→ 1 patch ready for review: gh pr checkout 112
```
