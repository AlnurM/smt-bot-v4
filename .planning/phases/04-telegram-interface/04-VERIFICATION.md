---
phase: 04-telegram-interface
verified: 2026-03-20T12:00:00Z
status: gaps_found
score: 21/22 must-haves verified
re_verification: false
gaps:
  - truth: "TG-04: Reject button optionally captures free-text reason"
    status: partial
    reason: "Reject handler sets signal.status='rejected' and edits the message caption, but no mechanism to capture or store a free-text rejection reason exists — no rejection_reason field on Signal model, no follow-up message prompt, no storage of user-typed reason."
    artifacts:
      - path: "bot/telegram/handlers/callbacks.py"
        issue: "handle_reject does not prompt for or store free-text reason"
      - path: "bot/db/models.py"
        issue: "Signal model has no rejection_reason column"
    missing:
      - "Optional free-text reason capture on Reject (e.g., bot asking for reason via follow-up message, or storing pre-defined reason options)"
      - "OR explicit documented decision that free-text capture is deferred to a later phase"
human_verification:
  - test: "Verify AllowedChatMiddleware blocks non-allowed chat_id"
    expected: "Sending a message from a different chat_id receives no response at all"
    why_human: "Cannot run live Telegram bot in automated verification"
  - test: "Verify signal message renders correctly with chart PNG and inline buttons"
    expected: "Photo message with formatted Russian caption, 3 buttons (Confirm / Reject / Pine Script) in 2+1 layout"
    why_human: "Requires live bot + Telegram client to see rendered message"
  - test: "Tap Confirm twice on same signal"
    expected: "First tap marks confirmed and removes buttons; second tap silently removes buttons with no second DB write"
    why_human: "Requires live bot + Telegram client + PostgreSQL"
  - test: "Signal auto-expiry after 15 minutes"
    expected: "Signal status becomes 'expired', Telegram message caption updated with expiry note, buttons removed"
    why_human: "Requires running APScheduler + live Telegram bot"
  - test: "Verify /pause stops signal dispatch and /resume re-enables it"
    expected: "/pause responds with pause confirmation; subsequent signal scan does not send Telegram message; /resume responds and signals flow again"
    why_human: "Requires live bot with APScheduler running"
---

# Phase 4: Telegram Interface Verification Report

**Phase Goal:** The trader can receive signal messages with chart images, confirm or reject trades via inline buttons, and manage all bot settings through Telegram commands — with single-user security enforced on every interaction
**Verified:** 2026-03-20T12:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A message from any chat_id other than ALLOWED_CHAT_ID is silently dropped | VERIFIED | `AllowedChatMiddleware.__call__` returns `None` without calling handler when `chat_id != allowed_chat_id`; 3 middleware tests pass |
| 2 | /start returns system status with balance, open positions, current stake | VERIFIED | `cmd_start` queries RiskSettings + Position count + Binance futures_account; 5 command tests pass |
| 3 | /status returns balance, open positions, daily PnL, streak/stake | VERIFIED | `cmd_status` queries DailyStats with `sa.cast(DailyStats.date, sa.Date) == today`; complete implementation |
| 4 | All 12 commands respond correctly (/signals, /positions, /history, /strategies, /skipped, /scan, /chart, /help, /pause, /resume, /risk, /criteria, /settings) | VERIFIED | 12 handlers on `commands_router` + 3 on `settings_router`; 41 tests pass across 6 test files |
| 5 | Error alerts throttle to once per 15 min per error key | VERIFIED | `_THROTTLE_MINUTES = 15`; in-memory `_last_alert` dict with elapsed check; throttle tests pass |
| 6 | 80% daily loss warning fires when loss >= 80% of daily limit | VERIFIED | `limit_reached_pct >= 80` check in `check_and_warn_daily_loss`; notification tests pass |
| 7 | All-coins-skipped alert fires when consecutive_empty_cycles >= threshold | VERIFIED | `send_skipped_coins_alert` with threshold guard; wired in `run_strategy_scan` via lazy import |
| 8 | Signal message arrives as photo with chart PNG, caption, and inline buttons | VERIFIED | `send_signal_message` calls `bot.send_photo` with `BufferedInputFile` + formatted caption + `InlineKeyboardBuilder`; 6 dispatch tests pass |
| 9 | MIN_NOTIONAL signals sent with no Confirm button (2-button keyboard) | VERIFIED | `if not is_min_notional: builder.button(...)` — Confirm only added when `is_min_notional=False`; test passes |
| 10 | Tapping Confirm marks signal status='confirmed' atomically via SELECT FOR UPDATE; second tap has no effect | VERIFIED | `select(Signal).where(..., Signal.status == "pending").with_for_update()`; double-tap test passes |
| 11 | Tapping Reject marks signal status='rejected' and edits message to remove buttons | VERIFIED | `handle_reject` with SELECT FOR UPDATE + `signal.status = "rejected"` + `edit_caption`; test passes |
| 12 | TG-04: Reject optionally captures free-text reason | FAILED | `handle_reject` rejects without any mechanism to capture or store a free-text reason; Signal model has no `rejection_reason` column |
| 13 | Pine Script button returns placeholder message (Phase 6 deferred) | VERIFIED | `handle_pine` calls `callback.message.answer("📊 Pine Script будет доступен в следующем обновлении.")` |
| 14 | Signal auto-expires after configured timeout: status='expired', buttons removed | VERIFIED | `schedule_signal_expiry` schedules `expire_signal_job` via `DateTrigger`; `expire_signal_job` checks `status == "pending"` before updating; test passes |
| 15 | Caption truncated to 1020 chars if over limit | VERIFIED | `if len(caption) > 1020: caption = caption[:1020] + "..."`; test passes |
| 16 | /risk views and modifies all risk parameters | VERIFIED | RISK_ALIASES dispatch table covers 6 subcommands; progressive special-cased; reset loops over defaults; 9 risk tests pass |
| 17 | /criteria views and modifies strategy filter criteria | VERIFIED | CRITERIA_ALIASES + BOOL_ALIASES; drawdown negation `stored_value = -abs(typed_value)`; 6 criteria tests pass |
| 18 | /settings views/modifies top_n_coins and review_interval | VERIFIED | `settings.top_n_coins = new_value` (in-memory); review_interval loops active Strategy rows; 3 settings tests pass |
| 19 | Validation errors show allowed range and current value in Russian | VERIFIED | Pattern: `f"❌ Неверное значение: {alias} должен быть {min_val}-{max_val}. Текущее: {current_val}"` |
| 20 | Alembic migration 0002 adds telegram_message_id + caption to signals | VERIFIED | `0002_add_signal_telegram_fields.py` with `op.add_column` for both; `down_revision = "0001"` |
| 21 | Signal model ORM updated with telegram_message_id + caption columns | VERIFIED | `telegram_message_id: Mapped[Optional[int]]` and `caption: Mapped[Optional[str]]` in Signal model |
| 22 | run_strategy_scan wired with bot + scheduler; calls notification helpers + signal dispatch | VERIFIED | `bot=None, scheduler=None` params; lazy imports of `send_skipped_coins_alert`, `send_error_alert`, `send_signal_message`, `schedule_signal_expiry` |

**Score:** 21/22 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bot/telegram/__init__.py` | Package marker | VERIFIED | Exists |
| `bot/telegram/handlers/__init__.py` | Package marker | VERIFIED | Exists |
| `bot/telegram/middleware.py` | AllowedChatMiddleware | VERIFIED | Substantive — full `__call__` with Message + CallbackQuery chat_id extraction and silent drop |
| `bot/telegram/callbacks.py` | SignalAction CallbackData | VERIFIED | `class SignalAction(CallbackData, prefix="sig")` with `signal_id: str` and `action: str` |
| `bot/telegram/notifications.py` | send_error_alert, check_and_warn_daily_loss, send_skipped_coins_alert | VERIFIED | All three functions implemented with correct logic |
| `bot/telegram/handlers/commands.py` | 12 command handlers + router + _bot_state | VERIFIED | 12 `@router.message(Command(...))` handlers; `_bot_state = {"paused": False}` at module level |
| `bot/telegram/dispatch.py` | send_signal_message, schedule_signal_expiry, expire_signal_job | VERIFIED | All three exported; `_format_signal_caption` private helper |
| `bot/telegram/handlers/callbacks.py` | Confirm/Reject/Pine handlers + router | VERIFIED | 3 handlers with `callback.answer()` first; SELECT FOR UPDATE in confirm + reject |
| `bot/telegram/handlers/settings.py` | /risk, /criteria, /settings handlers + router | VERIFIED | RISK_ALIASES, CRITERIA_ALIASES, BOOL_ALIASES, SETTINGS_ALIASES; drawdown negation correct |
| `alembic/versions/0002_add_signal_telegram_fields.py` | telegram_message_id + caption migration | VERIFIED | Both `op.add_column` calls; `down_revision = "0001"` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bot/main.py` | `bot/telegram/middleware.py` | `dp.update.middleware(AllowedChatMiddleware(...))` | WIRED | Line 220: `dp.update.middleware(AllowedChatMiddleware(settings.allowed_chat_id))` |
| `bot/main.py` | `bot/telegram/handlers/commands.py` | `dp.include_router(commands_router)` | WIRED | Line 222: `dp.include_router(commands_router)` |
| `bot/main.py` | `bot/telegram/handlers/callbacks.py` | `dp.include_router(callbacks_router)` | WIRED | Line 224: `dp.include_router(callbacks_router)` |
| `bot/main.py` | `bot/telegram/handlers/settings.py` | `dp.include_router(settings_router)` | WIRED | Line 226: `dp.include_router(settings_router)` |
| `bot/main.py` | workflow_data | `dp["bot"]`, `dp["session_factory"]`, etc. | WIRED | Lines 228-232: all 5 keys injected |
| `bot/telegram/dispatch.py` | `bot.send_photo` | `await bot.send_photo(chat_id, BufferedInputFile(...), ...)` | WIRED | Line 131: `msg = await bot.send_photo(...)` |
| `bot/telegram/handlers/callbacks.py` | Signal DB | `select(Signal).where(..., status=="pending").with_for_update()` | WIRED | 2 `with_for_update()` calls (confirm + reject) |
| `bot/telegram/dispatch.py` | APScheduler | `scheduler.add_job(expire_signal_job, trigger=DateTrigger(...))` | WIRED | Lines 160-166 |
| `bot/telegram/handlers/settings.py` | `update_risk_settings` | `await update_risk_settings(session, field_name, value)` | WIRED | Called in set mode and reset mode of `/risk` |
| `bot/telegram/handlers/settings.py` | StrategyCriteria table | `setattr(criteria_row, field_name, value); await session.commit()` | WIRED | Used in `/criteria` bool and numeric set modes |
| `bot/telegram/handlers/settings.py` | settings object | `data["settings"].top_n_coins = new_value` (via `settings` param) | WIRED | Line 421: `settings.top_n_coins = new_value` |
| `bot/strategy/manager.py` | `send_signal_message` | lazy import after `generate_signal()` returns non-None | WIRED | Lines 277-307: full dispatch block including message_id storage and `schedule_signal_expiry` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TG-01 | 04-01 | Bot accepts commands only from ALLOWED_CHAT_ID | SATISFIED | AllowedChatMiddleware on dp.update; 3 tests pass |
| TG-02 | 04-02 | Signal message includes direction, prices, R/R, stake, reasoning, chart image | SATISFIED | `send_signal_message` + `_format_signal_caption` covers all fields |
| TG-03 | 04-02 | Signal has inline buttons: Confirm, Reject, Pine Script | SATISFIED | InlineKeyboardBuilder with 3 buttons; adjust(2,1) layout |
| TG-04 | 04-02 | Reject button optionally captures free-text reason | BLOCKED | Reject sets status='rejected' and edits caption — no free-text capture mechanism |
| TG-05 | 04-01 | /start — system status | SATISFIED | `cmd_start` with balance, open_count, stake |
| TG-06 | 04-01 | /status — balance, PnL, streak/stake | SATISFIED | `cmd_status` with all fields |
| TG-07 | 04-03 | /risk — view and modify risk parameters | SATISFIED | RISK_ALIASES dispatch; 9 tests pass |
| TG-08 | 04-03 | /criteria — view and modify strategy filter criteria | SATISFIED | CRITERIA_ALIASES + BOOL_ALIASES; drawdown negation; 6 tests pass |
| TG-09 | 04-01 | /signals — last 10 signals | SATISFIED | `cmd_signals` with status emojis and empty state |
| TG-10 | 04-01 | /positions — open positions with PnL | SATISFIED | `cmd_positions` filtering `status='open'` |
| TG-11 | 04-01 | /history — last 20 closed trades | SATISFIED | `cmd_history` ORDER BY closed_at DESC LIMIT 20 |
| TG-12 | 04-01 | /strategies — active strategies with review dates | SATISFIED | `cmd_strategies` WHERE is_active=True |
| TG-13 | 04-01 | /skipped — coins skipped with time filters | SATISFIED | `cmd_skipped` handles 24h/7d/SYMBOL args |
| TG-14 | 04-01 | /scan — trigger manual market scan | SATISFIED | `cmd_scan` with non-blocking `asyncio.create_task` |
| TG-15 | 04-01 | /chart SYMBOL — Pine Script placeholder | SATISFIED | Phase 6 deferred; placeholder response confirmed by plan design |
| TG-16 | 04-03 | /settings — top-N, review interval | SATISFIED | `cmd_settings` with top_n in-memory + review_interval ORM loop |
| TG-17 | 04-01 | /pause and /resume | SATISFIED | `_bot_state["paused"]` toggled; dispatch checks before sending |
| TG-18 | 04-01 | /help — full command reference | SATISFIED | Static text with all commands including /start |
| TG-20 | 04-01 | Warning at 80% of daily loss limit | SATISFIED | `check_and_warn_daily_loss` with `limit_reached_pct >= 80` |
| TG-21 | 04-01 | Error notifications — throttled | SATISFIED | `send_error_alert` with 15-min per-key throttle |
| TG-22 | 04-01 | Notification when all coins skipped repeatedly | SATISFIED | `send_skipped_coins_alert` wired in `run_strategy_scan` |

**Note:** TG-19 (daily summary at 21:00) is Phase 6 scope — correctly not in any Phase 4 plan.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bot/telegram/handlers/commands.py` | 343 | `"""Phase 4 placeholder — Pine Script for symbol (next update)."""` | INFO | Intentional — /chart is a Phase 6 feature; placeholder is correct Phase 4 behavior |
| `bot/telegram/handlers/callbacks.py` | 140 | `"""Pine Script placeholder — Phase 6 implementation deferred."""` | INFO | Intentional — handle_pine Phase 6 deferred by design |
| `bot/telegram/dispatch.py` | 104 | Comment: `# Build signal_id: get from signal dict if present; otherwise use a placeholder` | INFO | Fallback UUID is defensive coding — real signal_id injected by caller in Phase 5 |

No blocker anti-patterns found. All placeholders are intentional Phase 6 deferrals documented in plan success criteria.

### Human Verification Required

#### 1. Single-User Security End-to-End

**Test:** Send a command from a Telegram account with a different chat_id than ALLOWED_CHAT_ID
**Expected:** No response is received; nothing appears in bot logs at INFO level
**Why human:** Cannot run a live Telegram bot interaction in automated verification

#### 2. Signal Message Visual Rendering

**Test:** Trigger a signal scan with a live Binance connection and chart generator
**Expected:** Photo message received with PNG chart, Russian caption containing all 7 data fields (direction, entry, SL, TP, R/R, stake%, signal_strength), 3 inline buttons in 2+1 layout
**Why human:** Requires live bot + Telegram client + real chart PNG bytes

#### 3. Confirm Double-Tap Idempotency (Live)

**Test:** Tap Confirm on a pending signal, then tap Confirm again on the same message
**Expected:** First tap: message caption updated with "Подтверждено", buttons removed. Second tap: nothing happens (no error, no double DB write)
**Why human:** Requires live Telegram + PostgreSQL with actual SELECT FOR UPDATE behavior

#### 4. Signal Expiry After Timeout

**Test:** Configure `signal_expiry_minutes=1`, trigger a signal, wait 1 minute without confirming
**Expected:** Signal status becomes 'expired' in DB; Telegram message caption appends "Истёк срок действия"; buttons removed
**Why human:** Requires live APScheduler + Telegram + PostgreSQL running together

#### 5. /pause and /resume Live Behavior

**Test:** Issue `/pause`, then trigger a strategy scan manually via `/scan`
**Expected:** Scan runs (shows "Запуск сканирования рынка...") but if a signal is generated, no Telegram photo message is sent
**Why human:** Requires live running bot with actual signal generation

### Gaps Summary

One gap was identified against the 22 must-have truths:

**TG-04: Free-text rejection reason not implemented.** The requirement states the Reject button "optionally captures free-text reason." The current implementation marks the signal as rejected and edits the Telegram message caption with "Отклонено" — but there is no mechanism to prompt the user for a free-text reason or store one. The Signal ORM model has no `rejection_reason` column. The plan's own success criteria framed TG-04 as "Reject edits message and sets status='rejected', no forced reason prompt" — which suggests the plan intentionally narrowed the scope to not force a reason. However, "optionally captures" in REQUIREMENTS.md implies at least an optional path should exist. This gap needs either:
1. Implementation of optional free-text capture (e.g., bot sends follow-up message asking for reason after tap)
2. OR an explicit documented decision to defer free-text capture to a later phase

All other 21 must-haves are fully verified. All 41 tests pass (3 middleware + 5 notifications + 5 commands + 6 dispatch + 4 callbacks + 18 settings). All key links are wired. No blocker anti-patterns.

---

_Verified: 2026-03-20T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
