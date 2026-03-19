---
phase: 04-telegram-interface
plan: "03"
subsystem: telegram-settings
tags: [telegram, handlers, risk, criteria, settings, tdd]
dependency_graph:
  requires:
    - 04-01  # AllowedChatMiddleware, Bot, Dispatcher wiring
  provides:
    - /risk command handler (TG-07)
    - /criteria command handler (TG-08)
    - /settings command handler (TG-16)
  affects:
    - bot/main.py (settings_router wired)
tech_stack:
  added: []
  patterns:
    - aiogram Router with Command filter per handler
    - update_risk_settings() for RiskSettings writes
    - setattr + session.commit() for StrategyCriteria writes
    - In-memory mutation for settings.top_n_coins
    - RISK_ALIASES / CRITERIA_ALIASES dispatch tables for subcommand routing
key_files:
  created:
    - bot/telegram/handlers/settings.py
    - tests/test_telegram_settings.py
  modified:
    - bot/main.py
decisions:
  - RISK_ALIASES and CRITERIA_ALIASES dispatch tables route alias -> (db_field, type, min, max) — single lookup path for all set-mode subcommands
  - drawdown input is always positive from user; handler negates to -abs(value) before storing in max_drawdown_pct
  - /risk reset and /criteria reset call update_risk_settings / setattr in loops over spec defaults dicts — no partial update risk
  - /settings top_n mutation is in-memory only (settings.top_n_coins = new_value) — restart reverts to .env per locked CONTEXT.md decision
  - /settings review_interval fetches all active Strategy rows with SELECT + loop setattr, not bulk UPDATE — compatible with SQLAlchemy ORM session tracking
  - Each handler receives **kwargs to accept all Dispatcher workflow_data injections cleanly
metrics:
  duration_seconds: 251
  completed_date: "2026-03-19"
  tasks_completed: 2
  files_created: 2
  files_modified: 1
---

# Phase 4 Plan 3: Settings Command Handlers Summary

**One-liner:** Three Telegram command handlers (/risk, /criteria, /settings) giving full runtime parameter control via alias dispatch tables, drawdown negation, and in-memory/DB writes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wave 0 — settings test scaffolds (TDD RED) | d5badd5 | tests/test_telegram_settings.py |
| 2 | /risk, /criteria, /settings handlers + main.py wiring (TDD GREEN) | 50cfd1c | bot/telegram/handlers/settings.py, bot/main.py |

## Verification Results

All 18 settings tests pass. Full telegram suite (41 tests) passes.

Smoke test: `settings module structure ok` — RISK_ALIASES, CRITERIA_ALIASES, notify not in CRITERIA_ALIASES (correct — it's in BOOL_ALIASES).

All routers wired in main.py: AllowedChatMiddleware, commands_router, callbacks_router, settings_router.

## Decisions Made

1. **RISK_ALIASES / CRITERIA_ALIASES dispatch tables** — alias -> (db_field, type, min, max) tuples enable single-path validation and update for all numeric subcommands without branching per command.

2. **drawdown negation** — user inputs positive value (e.g., 12); handler stores -abs(value) (-12.0) in max_drawdown_pct. Documented in docstring and inline comment.

3. **reset uses loops over defaults dicts** — /risk reset calls update_risk_settings for each default field in sequence; /criteria reset uses setattr loop with single commit. Atomic at DB transaction level.

4. **settings.top_n_coins = new_value (in-memory)** — explicit restart warning in response message per CONTEXT.md locked decision.

5. **/settings review_interval uses ORM SELECT + loop** — compatible with SQLAlchemy asyncpg session; avoids raw UPDATE statement type issues.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- bot/telegram/handlers/settings.py: FOUND
- tests/test_telegram_settings.py: FOUND
- Commit d5badd5: FOUND
- Commit 50cfd1c: FOUND
