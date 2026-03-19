---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24+ |
| **Config file** | `pytest.ini` (Wave 0 — does not exist yet) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | INFRA-02 | unit | `pytest tests/test_config.py::test_secret_masking -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | INFRA-06 | smoke | manual — `docker compose up --build -d && docker compose ps` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | INFRA-03 | integration | `pytest tests/test_migrations.py::test_all_tables_exist -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | INFRA-01 | unit | `pytest tests/test_exchange_client.py::test_testnet_toggle -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | INFRA-04 | unit | `pytest tests/test_scheduler.py::test_scheduler_starts -x` | ❌ W0 | ⬜ pending |
| 01-03-03 | 03 | 2 | INFRA-05 | unit | `pytest tests/test_main.py::test_single_event_loop -x` | ❌ W0 | ⬜ pending |
| 01-03-04 | 03 | 2 | INFRA-07 | unit | `pytest tests/test_main.py::test_graceful_shutdown -x` | ❌ W0 | ⬜ pending |
| 01-03-05 | 03 | 2 | INFRA-08 | unit | `pytest tests/test_startup.py::test_position_sync -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pytest.ini` — pytest + asyncio-mode=auto configuration
- [ ] `tests/conftest.py` — async engine fixture (test PostgreSQL or in-memory), settings fixture with test values
- [ ] `tests/test_config.py` — covers INFRA-02 (secret masking)
- [ ] `tests/test_exchange_client.py` — covers INFRA-01 (testnet toggle, mock Binance ping)
- [ ] `tests/test_migrations.py` — covers INFRA-03 (all 10 tables, seed rows)
- [ ] `tests/test_scheduler.py` — covers INFRA-04 (scheduler starts, CronTrigger)
- [ ] `tests/test_main.py` — covers INFRA-05, INFRA-07 (event loop, graceful shutdown)
- [ ] `tests/test_startup.py` — covers INFRA-08 (position sync, reconciliation)
- [ ] Framework install: `pip install pytest pytest-asyncio`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker Compose starts with healthy state | INFRA-06 | Requires Docker daemon, cannot run in CI easily | `docker compose up --build -d && docker compose ps` — verify both services show "healthy" |
| Startup Telegram message sent | INFRA-07 | Requires live Telegram bot token | Check Telegram chat for "Bot started" message after `docker compose up` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
