---
phase: 4
slug: telegram-interface
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24+ |
| **Config file** | `pytest.ini` (exists from Phase 1) |
| **Quick run command** | `pytest tests/test_telegram*.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_telegram*.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 25 seconds

---

## Wave 0 Requirements

- [ ] `tests/test_telegram_middleware.py` — covers TG-01 (single-user filter)
- [ ] `tests/test_telegram_dispatch.py` — covers TG-02, TG-03, signal expiry
- [ ] `tests/test_telegram_commands.py` — covers TG-05 through TG-18
- [ ] `tests/test_telegram_settings.py` — covers TG-07, TG-08, TG-16 (/risk, /criteria parsing)
- [ ] `tests/test_telegram_callbacks.py` — covers TG-03, TG-04 (confirm/reject, double-tap)
- [ ] `tests/test_telegram_notifications.py` — covers TG-20, TG-21, TG-22
- [ ] Alembic migration: add `telegram_message_id` column to signals table

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Signal with chart PNG in Telegram | TG-02 | Requires live bot token + Telegram | Send test signal, verify photo + caption |
| Inline buttons functional | TG-03 | Requires Telegram interaction | Tap Confirm/Reject, verify message edit |
| Bot ignores other users | TG-01 | Requires second Telegram account | Message bot from different account |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 25s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
