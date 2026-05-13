# Glitch

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
❯ uv run glitch discover --repo charm-nginx
Scanning 120 CI runs across 14 test suites...

  TEST                            FLAKINESS   VOLATILITY   RETRY   TIMING   CHANGE-INDEP
  ──────────────────────────────  ──────────  ───────────  ──────  ───────  ─────────────
  test_ssl_termination            0.92        ██████████   █████   ████     ██
  test_scaling_events             0.78        ████████     ████    ███      █
  test_config_update_rollback     0.65        ██████       ███     ██       ████
  test_health_check_basic         0.03        █            ·       ·        ·
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
