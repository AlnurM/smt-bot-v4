# Phase 4: Telegram Interface - Research

**Researched:** 2026-03-19
**Domain:** aiogram 3.26 handler architecture, inline keyboards, middleware, APScheduler signal dispatch integration
**Confidence:** HIGH — primary sources are existing project code (Phases 1-3 complete), STACK.md, PITFALLS.md, and idea.md spec. No external verification needed for stack choices (already locked). aiogram 3.x patterns verified against project's existing working main.py.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Signal Message UX**
- Signals auto-expire after configurable timeout (default 15 min) — marked as 'expired' in DB, inline buttons removed from message
- After Confirm tap: original message edited to "✅ Confirmed — placing order...", buttons removed. Second tap has no effect (DB unique constraint)
- After Reject tap: message edited to "❌ Rejected", buttons removed. Reason is optional — trader can type a freeform reason as a follow-up message if they want, but no forced prompt
- Signal message includes chart PNG as attached photo with caption containing all required fields (direction, symbol, entry/SL/TP, R/R, stake %, reasoning)
- Three inline buttons: ✅ Confirm | ❌ Reject | 📊 Pine Script
- MIN_NOTIONAL signals sent as informational only (no Confirm button, "too small" warning label)

**Command Response Style**
- Language: Russian labels, English data (symbol names, percentages, timestamps in standard format) — follow spec section 8 templates
- Compact responses: key metrics only, one-line per item, fits mobile screen without scrolling
- Empty states: friendly Russian message (e.g., "Нет открытых позиций. Сигналы появятся, когда условия будут выполнены.")
- All commands only respond to `ALLOWED_CHAT_ID` — other users silently ignored

**Settings Commands UX**
- Inline text commands as defined in spec section 7.4 and 5.3 (e.g., `/risk stake 3`, `/criteria return 200`)
- Validation errors: "❌ Неверное значение: stake должен быть 1-100%. Текущее: 3%" — show allowed range and current value
- Successful changes: "✅ base_stake_pct: 3% → 5%" — show old and new value
- `/risk` and `/criteria` without params show current settings table
- `/risk reset` and `/criteria reset` restore spec defaults from Alembic seed values

**Error & Alert Messages**
- User-friendly: no stack traces, actionable info only ("⚠️ Binance API: connection timeout. Retry through 60s.")
- 80% daily loss limit warning: prominent alert with 🚨 emoji emphasis ("🚨 ВНИМАНИЕ: Дневной убыток 80% от лимита ($4.00/$5.00). Следующий убыток может остановить торговлю.")
- Repeated error throttling: alert on first occurrence, suppress for 15 min, repeat if still happening
- Claude API errors include error type (rate limit vs timeout vs other) in the alert
- "All coins skipped" alert: fires after consecutive_empty_cycles_alert threshold, suggest loosening criteria

### Claude's Discretion
- aiogram router/handler organization (single router vs multiple)
- Callback data format for inline buttons
- Message parsing approach for settings commands
- How to wire the bot into the existing main.py event loop
- Telegram message length limits handling (split long responses)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TG-01 | Bot accepts commands only from configured `ALLOWED_CHAT_ID` | aiogram BaseMiddleware on Dispatcher — runs before every handler, cannot be bypassed per security pitfall |
| TG-02 | Signal message: direction, symbol, timeframe, entry/SL/TP, R/R, stake%, position size, signal strength, reasoning, chart image | `send_photo()` with caption — caption is the structured text, photo is `generate_chart()` bytes wrapped in `BufferedInputFile` |
| TG-03 | Signal inline buttons: Confirm, Reject, Pine Script | `InlineKeyboardMarkup` + `CallbackData` factory; Pine Script deferred to Phase 6 per CONTEXT.md |
| TG-04 | Reject button optionally captures free-text reason | No forced prompt per locked decision; just edit message to "❌ Rejected" and remove buttons |
| TG-05 | `/start` — system status, current stake, deposit balance | Reads RiskSettings (current_stake_pct) + Binance futures_account balance |
| TG-06 | `/status` — balance, open positions, daily PnL, streak/stake | Queries Position (open), DailyStats, RiskSettings |
| TG-07 | `/risk` — view and modify all risk parameters | Reads/writes RiskSettings; `update_risk_settings()` already exists in risk/manager.py |
| TG-08 | `/criteria` — view and modify strategy filter criteria | Reads/writes StrategyCriteria table |
| TG-09 | `/signals` — last 10 signals | SELECT FROM signals ORDER BY created_at DESC LIMIT 10 |
| TG-10 | `/positions` — open positions with current PnL | SELECT FROM positions WHERE status='open' |
| TG-11 | `/history` — last 20 closed trades | SELECT FROM trades ORDER BY closed_at DESC LIMIT 20 |
| TG-12 | `/strategies` — active strategies with next review dates | SELECT FROM strategies WHERE is_active=true |
| TG-13 | `/skipped` — coins skipped due to criteria | SELECT FROM skipped_coins; time filter and per-coin filter from command args |
| TG-14 | `/scan` — trigger manual market scan | `asyncio.create_task(run_strategy_scan(...))` — non-blocking |
| TG-15 | `/chart SYMBOL` — get Pine Script for last signal | Pine Script generation is Phase 6; Phase 4 returns "недоступно" placeholder |
| TG-16 | `/settings` — general settings (top-N, timeframes, review interval) | Reads/writes Settings fields — needs a DB table or in-memory config update |
| TG-17 | `/pause` and `/resume` — pause/resume signal generation | In-memory flag on Dispatcher state or bot-level attribute; persisted in DB if restart survives |
| TG-18 | `/help` — full command reference | Static formatted text from idea.md section 8.1 |
| TG-20 | Warning at 80% of daily loss limit | Proactive notification from risk check path; triggered by check_daily_loss() returning near-limit |
| TG-21 | Error notifications — API errors, order failures, insufficient balance | Notification dispatch function callable from scheduler jobs and strategy scan |
| TG-22 | Notification when strategy criteria causes all coins to be skipped repeatedly | Already tracked in strategy/manager.py `_consecutive_empty_cycles`; needs wiring to `bot.send_message()` |
</phase_requirements>

---

## Summary

Phase 4 builds the complete Telegram interface on top of an already-working foundation. Phases 1-3 are fully complete: the bot process is running (main.py has `Bot`, `Dispatcher`, polling), all database tables and ORM models exist, signal generation produces a populated dict with all TG-02 fields, chart generation returns PNG bytes, and the risk/criteria managers expose async write functions ready for command handlers.

The phase's central challenge is architecture: wiring 21 requirements into a clean aiogram 3.x Router structure without polluting `main.py`, ensuring the single-user middleware runs first on every interaction, and creating a reliable signal dispatch path from the APScheduler job to `bot.send_photo()`. The double-tap idempotency constraint and signal expiry via APScheduler `date` trigger are the two non-trivial async coordination problems.

The `/settings` command touches a gap: `top_n_coins`, timeframes, and `review_interval_days` live in `Settings` (pydantic-settings, read from `.env` at startup) and `Strategy.review_interval_days` (per-row in DB), not in a dedicated mutable DB table. The planner must decide how to handle runtime mutation of `top_n_coins` — options are an in-memory override on the settings object, or a new `BotSettings` DB table. Both are feasible; this is flagged as a design decision.

**Primary recommendation:** Use a single `bot/telegram/` package with one Router per logical group (commands, callbacks, notifications), registered on the Dispatcher in `main.py`. Pass `bot` and `session_factory` through middleware context so all handlers have access without global state.

---

## Standard Stack

### Core (already installed — no new packages needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiogram | 3.26.0 | Telegram handler framework | Locked by spec, already installed, fully async |
| SQLAlchemy | 2.0.48 | DB queries for command responses | Already installed, async session pattern established |
| APScheduler | 3.11.2 | Signal expiry `date` trigger | Already installed; used for existing hourly scan |

### New Dependencies Required

None. All required libraries are already in the project's requirements. The `bot` instance and `Dispatcher` are already created in `main.py`. No pip installs needed for Phase 4.

### Supporting (already installed)

| Library | Version | Purpose |
|---------|---------|---------|
| loguru | 0.7+ | Handler logging (established pattern) |
| pytest-asyncio | 0.24+ | Testing async handlers |

**Installation:** No new packages. All dependencies satisfied by Phases 1-3 install.

---

## Architecture Patterns

### Recommended Project Structure

```
bot/
├── telegram/
│   ├── __init__.py
│   ├── middleware.py        # AllowedChatMiddleware — registered first on Dispatcher
│   ├── dispatch.py         # send_signal_message() — called by scheduler job
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── commands.py     # /start /status /signals /positions /history /strategies /skipped /scan /chart /help
│   │   ├── settings.py     # /risk /criteria /settings /pause /resume
│   │   └── callbacks.py    # Confirm / Reject / Pine Script inline button handlers
│   └── notifications.py    # send_error_alert() send_80pct_warning() send_skipped_alert()
└── main.py                 # registers router(s) and middleware on Dispatcher — minimal changes
```

### Pattern 1: AllowedChat Middleware (TG-01)

**What:** A `BaseMiddleware` subclass that checks `chat_id` from every Update before any handler runs. Non-matching chat IDs are silently dropped (no response).

**Why middleware, not handler guard:** Security pitfall from PITFALLS.md — handler-level checks can be bypassed by code bugs. Middleware runs first and cannot be skipped.

```python
# bot/telegram/middleware.py
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from typing import Callable, Awaitable, Any

class AllowedChatMiddleware(BaseMiddleware):
    def __init__(self, allowed_chat_id: int):
        self.allowed_chat_id = allowed_chat_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        # Extract chat_id from message or callback_query
        chat_id = None
        if hasattr(event, "message") and event.message:
            chat_id = event.message.chat.id
        elif hasattr(event, "callback_query") and event.callback_query:
            chat_id = event.callback_query.message.chat.id
        if chat_id != self.allowed_chat_id:
            return  # silently ignore
        return await handler(event, data)

# Registration in main.py:
# dp.update.middleware(AllowedChatMiddleware(settings.allowed_chat_id))
```

**Confidence:** HIGH — this is the standard aiogram 3.x middleware pattern.

### Pattern 2: Signal Dispatch (TG-02, TG-03)

**What:** `send_signal_message()` in `bot/telegram/dispatch.py` is called by the APScheduler job (or wherever signal generation fires a result). It uses `bot.send_photo()` with caption + inline keyboard.

**Key constraint:** The `bot` instance lives in `main.py`. Signal dispatch needs access to it. Options:
1. Pass `bot` as a parameter to `run_strategy_scan()` — cleanest, no global state
2. Store `bot` in a module-level variable set during startup — works but couples modules

Recommended: pass `bot` as parameter to `run_strategy_scan()`. The `main.py` already passes `binance_client` and `settings` as parameters — adding `bot` follows the same established pattern.

```python
# bot/telegram/dispatch.py
from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

async def send_signal_message(
    bot: Bot,
    chat_id: int,
    signal: dict,
    chart_bytes: bytes,
    position_size: dict,
    is_min_notional: bool = False,
) -> int:
    """Send signal photo with caption and inline buttons. Returns message_id."""
    caption = _format_signal_caption(signal, position_size, is_min_notional)
    keyboard = _build_signal_keyboard(signal["id"], is_min_notional)

    msg = await bot.send_photo(
        chat_id=chat_id,
        photo=BufferedInputFile(chart_bytes, filename="chart.png"),
        caption=caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    return msg.message_id
```

**Caption length:** Telegram photo captions are limited to 1024 characters. The spec signal format (section 8.2) fits within this limit. Verify during implementation.

### Pattern 3: CallbackData Factory (TG-03, TG-04)

**What:** aiogram 3.x `CallbackData` is a typed dataclass-like factory for callback query data. Preferred over raw string parsing.

```python
# bot/telegram/callbacks.py
from aiogram.filters.callback_data import CallbackData

class SignalAction(CallbackData, prefix="sig"):
    signal_id: str   # UUID as string
    action: str      # "confirm" | "reject" | "pine"
```

Callback data format: `sig:550e8400-e29b-41d4-a716-446655440000:confirm`

**Maximum callback_data length:** 64 bytes. A UUID (36 chars) + prefix + action fits comfortably.

### Pattern 4: Double-Tap Idempotency (Pitfall 5 from PITFALLS.md)

**What:** When Confirm is tapped, atomically update signal status to `'confirmed'` in the DB before doing anything else. A second concurrent tap hits the DB check and returns early.

```python
# bot/telegram/handlers/callbacks.py
async def handle_confirm(callback: CallbackQuery, session: AsyncSession, data: SignalAction):
    await callback.answer()  # must answer within 60s or Telegram shows error

    # Atomic status check-and-set
    result = await session.execute(
        select(Signal).where(
            Signal.id == uuid.UUID(data.signal_id),
            Signal.status == "pending",  # only pending signals can be confirmed
        ).with_for_update()  # row-level lock
    )
    signal = result.scalar_one_or_none()
    if signal is None:
        # Already confirmed, rejected, or expired — second tap
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    signal.status = "confirmed"
    await session.commit()

    # Edit message immediately to remove buttons
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ Подтверждено — размещение ордера...",
        reply_markup=None,
    )
    # Phase 5 Order Executor will pick up signal.status == 'confirmed'
```

**The `with_for_update()` is critical** — it prevents two concurrent coroutines from both reading `status == 'pending'` before either writes. This is the DB-level race protection from PITFALLS.md.

### Pattern 5: Signal Expiry via APScheduler `date` Trigger (CONTEXT.md locked decision)

**What:** When a signal message is sent, schedule a one-shot APScheduler `date` job to fire after the expiry timeout. That job edits the Telegram message and marks the signal expired in DB.

```python
# Called immediately after send_signal_message()
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timezone, timedelta

def schedule_signal_expiry(
    scheduler,
    bot: Bot,
    chat_id: int,
    message_id: int,
    signal_id: str,
    session_factory,
    timeout_minutes: int = 15,
):
    run_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
    scheduler.add_job(
        expire_signal_job,
        trigger=DateTrigger(run_date=run_at),
        args=[bot, chat_id, message_id, signal_id, session_factory],
        id=f"expire_{signal_id}",
        replace_existing=True,
    )

async def expire_signal_job(bot, chat_id, message_id, signal_id, session_factory):
    async with session_factory() as session:
        signal = await session.get(Signal, uuid.UUID(signal_id))
        if signal and signal.status == "pending":
            signal.status = "expired"
            await session.commit()
            try:
                await bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=message_id, reply_markup=None
                )
                await bot.edit_message_caption(
                    chat_id=chat_id, message_id=message_id,
                    caption=...,  # original caption + "\n\n⏱ Истёк срок действия"
                )
            except Exception:
                pass  # message may have been deleted
```

**Gotcha:** Editing a message that the user has deleted throws `MessageToEditNotFound`. Always wrap message edits in try/except per PITFALLS.md technical debt table.

### Pattern 6: Settings Command Parsing

**What:** Commands like `/risk stake 3` need to parse `stake` and `3` from the message text. Use a simple split approach — no need for a full parser.

```python
# In handler:
# message.text = "/risk stake 3"
parts = message.text.split()
# parts = ["/risk", "stake", "3"]
if len(parts) == 1:
    # show current settings
elif len(parts) == 3:
    field_alias, raw_value = parts[1], parts[2]
    # validate and dispatch to update_risk_settings()
elif len(parts) == 2 and parts[1] == "reset":
    # restore defaults
```

**Alias mapping for /risk:**

| Command arg | DB field | Validation range |
|-------------|----------|-----------------|
| `stake` | `base_stake_pct` | 1–100 (float) |
| `max_stake` | `max_stake_pct` | 1–100 (float) |
| `rr` | `min_rr_ratio` | 0.5–10.0 (float) |
| `leverage` | `leverage` | 1–20 (int) |
| `daily_limit` | `daily_loss_limit_pct` | 1–50 (float) |
| `max_pos` | `max_open_positions` | 1–20 (int) |
| `progressive` | `progressive_stakes` | 3 space-separated floats |

**Alias mapping for /criteria:**

| Command arg | DB field | Validation range |
|-------------|----------|-----------------|
| `period` | `backtest_period_months` | 1–24 (int) |
| `return` | `min_total_return_pct` | 10–1000 (float) |
| `drawdown` | `max_drawdown_pct` | stored negative; input positive 1–100 |
| `winrate` | `min_win_rate_pct` | 30–90 (float) |
| `pf` | `min_profit_factor` | 1.0–5.0 (float) |
| `trades` | `min_trades` | 10–200 (int) |
| `rr` | `min_avg_rr` | 1.0–5.0 (float) |
| `notify` | `notify_on_skip` | `on`/`off` |
| `strict` | `strict_mode` | `on`/`off` |

### Pattern 7: Error Throttling (TG-21)

**What:** Track last-alert timestamps per error type in an in-memory dict. Send alert on first occurrence, suppress for 15 minutes, re-alert if still happening.

```python
# bot/telegram/notifications.py
from datetime import datetime, timezone, timedelta

_last_alert: dict[str, datetime] = {}
_THROTTLE_MINUTES = 15

async def send_error_alert(bot: Bot, chat_id: int, error_key: str, message: str):
    now = datetime.now(timezone.utc)
    last = _last_alert.get(error_key)
    if last and (now - last) < timedelta(minutes=_THROTTLE_MINUTES):
        return  # suppressed
    _last_alert[error_key] = now
    await bot.send_message(chat_id, f"⚠️ {message}")
```

Error keys: `"claude_rate_limit"`, `"claude_timeout"`, `"binance_connection"`, `"binance_order_fail"`, etc.

### Pattern 8: Wiring into main.py

The Dispatcher (`dp`) is created at the end of `main()` in `main.py`. Routers and middleware must be registered before `dp.start_polling(bot)`. The `bot` and `scheduler` instances are already available at that point.

```python
# Addition to main.py (in main(), before dp.start_polling):
from bot.telegram.middleware import AllowedChatMiddleware
from bot.telegram.handlers.commands import router as commands_router
from bot.telegram.handlers.settings import router as settings_router
from bot.telegram.handlers.callbacks import router as callbacks_router

dp.update.middleware(AllowedChatMiddleware(settings.allowed_chat_id))
dp.include_router(commands_router)
dp.include_router(settings_router)
dp.include_router(callbacks_router)
```

The `bot`, `scheduler`, `binance_client`, and `SessionLocal` (session_factory) need to be accessible to handlers and the dispatch function. Pass them via `data` on startup workflow or set them as workflow_data:

```python
# Inject shared dependencies into Dispatcher workflow_data
dp["bot"] = bot
dp["session_factory"] = SessionLocal
dp["scheduler"] = scheduler
dp["binance_client"] = binance_client
dp["settings"] = settings
```

Handlers receive these via `**kwargs` or explicit parameter names matching the dict keys.

### Anti-Patterns to Avoid

- **Global `bot` variable:** Storing `bot` at module level creates import-time circular dependencies and makes testing harder. Pass it as `dp["bot"]` or function parameter.
- **Handler-level chat_id check:** Must be middleware, not a per-handler `if message.from_user.id != allowed_id`. Middleware cannot be bypassed.
- **Blocking DB calls in callback handler without `with_for_update()`:** Creates race condition on double-tap (Pitfall 5).
- **Editing messages without try/except:** `MessageNotModified` and `MessageToEditNotFound` will crash the handler if the user deleted the message.
- **Calling `generate_chart()` synchronously in a handler:** It offloads via `asyncio.to_thread()` internally (already implemented), so calling `await generate_chart(...)` in a handler is safe. Do NOT call the internal `_render_chart()` directly.
- **Storing `bot` instance in APScheduler job args directly:** APScheduler serializes job args if using a persistent job store. Use in-memory job store (which is the default/current setup) so passing Bot as arg works fine.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Callback data parsing | Custom string split/regex | `CallbackData` factory (aiogram built-in) | Type-safe, validated, handles prefix collisions |
| Chat ID security | Per-handler `if` checks | `BaseMiddleware` | Handler-level checks can be bypassed by code bugs |
| Keyboard building | Raw `InlineKeyboardMarkup(inline_keyboard=[[...]])` lists | `InlineKeyboardBuilder` | Less error-prone for dynamic keyboards |
| Message text escaping | Manual `<`, `>`, `&` replacement | `aiogram.utils.markdown` or HTML parse_mode with explicit tags | Bot API parses HTML/Markdown — malformed tags cause send failures |
| Double-tap prevention | In-memory `set()` of processed IDs | DB `SELECT ... WITH FOR UPDATE` + status check | In-memory is lost on restart; concurrent coroutines can both pass an in-memory check before either writes |
| Signal expiry | `asyncio.sleep()` task | APScheduler `DateTrigger` | Sleep tasks are lost on restart; APScheduler handles process restart correctly if scheduler state is checked at startup |

---

## Common Pitfalls

### Pitfall 1: `callback.answer()` Deadline

**What goes wrong:** Telegram requires `callback_query.answer()` within 60 seconds of receiving the callback, or the user sees a loading spinner and eventual error. If the handler awaits a DB query or Binance API call before calling `answer()`, and those calls take > 60s (which Claude API calls can), the deadline is missed.

**How to avoid:** Call `await callback.answer()` as the FIRST await in every callback handler, before any DB or API calls. It acknowledges receipt immediately; further processing happens after.

**Warning signs:** Telegram shows "Message expired" or loading spinner that never resolves.

### Pitfall 2: Message Edit on Deleted Message

**What goes wrong:** When a signal expires, the expiry job calls `bot.edit_message_reply_markup()`. If the user deleted the message from their chat, this raises `MessageToEditNotFound`. Unhandled, it crashes the APScheduler job and logs an exception.

**How to avoid:** Always wrap message edits in try/except and log at DEBUG level (not ERROR — it's expected).

```python
try:
    await bot.edit_message_reply_markup(...)
except Exception:
    logger.debug(f"Could not edit message {message_id} — likely deleted by user")
```

### Pitfall 3: Session Sharing Across Concurrent Handlers

**What goes wrong:** Two simultaneous callback handlers (double-tap scenario) both receive the same SQLAlchemy `AsyncSession` from `dp["session_factory"]` if a shared session is injected. SQLAlchemy raises `DetachedInstanceError` or silent data corruption.

**How to avoid:** Each handler must open its own session via `async with session_factory() as session:`. Do NOT inject a shared session instance — inject the factory. This is the established pattern from all Phase 1-3 code.

### Pitfall 4: `progressive` Arg Parsing for `/risk progressive 3 5 8`

**What goes wrong:** The command `/risk progressive 3 5 8` has 5 parts, not 3. The simple `len(parts) == 3` parser fails.

**How to avoid:** Special-case the `progressive` subcommand to accept 3 trailing float values. Parse: `parts[2:]` as the stakes list when `parts[1] == "progressive"`.

### Pitfall 5: Telegram Caption Length

**What goes wrong:** `send_photo` caption is limited to 1024 characters. The signal caption (spec section 8.2) with all fields, reasoning, and formatting is approximately 400-500 characters — within limits. But if reasoning from `generate_signal()` is long (it can be), the total may exceed 1024.

**How to avoid:** Truncate `signal["reasoning"]` to 200 characters max in the caption formatter. Full reasoning can be sent as a follow-up text message if needed.

### Pitfall 6: `/settings` Mutation of In-Memory Config

**What goes wrong:** `settings.top_n_coins` and `settings.coin_whitelist` are pydantic-settings fields read from `.env` at startup. Mutating them at runtime (`settings.top_n_coins = 15`) works in Python (pydantic v2 models are mutable by default) but the change is lost on restart and not persisted to DB.

**How to avoid:** For Phase 4, mutate the in-memory settings object for runtime effect. Document that restart reverts to `.env` values. Alternatively (Claude's discretion), add a `BotSettings` DB table — but this is scope creep for Phase 4. The simpler in-memory approach is sufficient for MVP.

### Pitfall 7: Error Throttle State Lost on Restart

**What goes wrong:** The in-memory `_last_alert` dict in `notifications.py` is reset on process restart. If the bot crashes and restarts, it may send duplicate alerts for ongoing errors.

**How to avoid:** This is acceptable behavior for an MVP. The throttle window is 15 minutes, and restarts are infrequent. Do not over-engineer; in-memory throttle is sufficient.

---

## Code Examples

### Send Signal with Chart (TG-02, TG-03)

```python
# bot/telegram/dispatch.py
from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.telegram.callbacks import SignalAction

async def send_signal_message(
    bot: Bot,
    chat_id: int,
    signal: dict,        # from generate_signal()
    chart_bytes: bytes,  # from generate_chart()
    position_size: dict, # from calculate_position_size()
    is_min_notional: bool = False,
) -> int:
    caption = _format_signal_caption(signal, position_size, is_min_notional)
    # Truncate if needed
    if len(caption) > 1020:
        caption = caption[:1020] + "..."

    builder = InlineKeyboardBuilder()
    if not is_min_notional:
        builder.button(
            text="✅ Открыть сделку",
            callback_data=SignalAction(signal_id=str(signal["id"]), action="confirm"),
        )
    builder.button(
        text="❌ Отклонить",
        callback_data=SignalAction(signal_id=str(signal["id"]), action="reject"),
    )
    builder.button(
        text="📊 Pine Script",
        callback_data=SignalAction(signal_id=str(signal["id"]), action="pine"),
    )
    builder.adjust(2, 1)  # 2 buttons on row 1, 1 on row 2

    msg = await bot.send_photo(
        chat_id=chat_id,
        photo=BufferedInputFile(chart_bytes, filename="chart.png"),
        caption=caption,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    return msg.message_id
```

### Signal Caption Formatter

```python
def _format_signal_caption(signal: dict, pos: dict, is_min_notional: bool) -> str:
    direction_emoji = "🟢" if signal["direction"] == "long" else "🔴"
    direction_label = "LONG" if signal["direction"] == "long" else "SHORT"

    sl_pct = abs(signal["entry_price"] - signal["stop_loss"]) / signal["entry_price"] * 100
    tp_pct = abs(signal["take_profit"] - signal["entry_price"]) / signal["entry_price"] * 100

    lines = [
        f"{direction_emoji} СИГНАЛ: {direction_label}  |  {signal['symbol']}  |  {signal['timeframe']}",
        "",
        f"📌 Вход:         ${signal['entry_price']:.4f}  (рыночный)",
        f"🛑 Stop Loss:    ${signal['stop_loss']:.4f}  (-{sl_pct:.2f}%)",
        f"🎯 Take Profit:  ${signal['take_profit']:.4f}  (+{tp_pct:.2f}%)",
        f"⚖️  R/R Ratio:    1 : {signal['rr_ratio']:.2f}",
        f"💰 Ставка:        {pos['stake_pct']:.0f}% депозита  (${pos['risk_usdt']:.2f} риск)",
        f"📊 Размер:        ~{pos['contracts']:.2f} контр.  (${pos['position_usdt']:.2f} с плечом)",
        f"💪 Сила сигнала: {signal['signal_strength']}",
    ]

    if is_min_notional:
        lines.append("\n⚠️ Позиция слишком мала для исполнения (MIN_NOTIONAL)")

    reasoning = (signal.get("reasoning") or "")[:200]
    if reasoning:
        lines.append(f"\n📈 Обоснование:\n  • {reasoning}")

    return "\n".join(lines)
```

### DB Query Pattern for Command Handlers

```python
# Established project pattern — use everywhere in handlers
from bot.db.session import SessionLocal

@router.message(Command("signals"))
async def cmd_signals(message: Message, session_factory=SessionLocal):
    async with session_factory() as session:
        result = await session.execute(
            select(Signal)
            .order_by(Signal.created_at.desc())
            .limit(10)
        )
        signals = result.scalars().all()

    if not signals:
        await message.answer("Нет сигналов. История появится после первого сигнала.")
        return

    lines = ["<b>Последние сигналы:</b>"]
    for s in signals:
        emoji = {"confirmed": "✅", "rejected": "❌", "expired": "⏱", "pending": "⏳"}.get(s.status, "?")
        lines.append(f"{emoji} {s.symbol} {s.direction.upper()} @ ${s.entry_price:.4f} — R/R {s.rr_ratio:.1f}")

    await message.answer("\n".join(lines), parse_mode="HTML")
```

---

## Integration Points

### Signal Dispatch Integration (TG-21, TG-22)

The `run_strategy_scan()` in `strategy/manager.py` has two `# TODO: send Telegram alert (Phase 4 wires this)` markers:

1. Line 252: Claude API error → needs `send_error_alert(bot, chat_id, "claude_api", message)`
2. Lines 209-213: consecutive empty cycles → needs `await bot.send_message(chat_id, alert_text)`

Phase 4 wires these by passing `bot` and `chat_id` into `run_strategy_scan()`.

**Updated signature:**
```python
async def run_strategy_scan(
    session_factory,
    binance_client,
    settings,
    bot=None,           # NEW: Bot instance for alerts
) -> None:
```

The APScheduler job registration in `main.py` then becomes:
```python
scheduler.add_job(
    lambda: asyncio.create_task(
        run_strategy_scan(SessionLocal, binance_client, settings, bot)
    ),
    ...
)
```

### 80% Loss Warning Integration (TG-20)

`check_daily_loss()` in `risk/manager.py` checks if the daily loss limit is reached (returns True at 100%). A separate check is needed at 80%. This logic belongs in a notification helper:

```python
# bot/telegram/notifications.py
async def check_and_warn_daily_loss(
    bot: Bot,
    chat_id: int,
    total_pnl: float,
    starting_balance: float,
    daily_loss_limit_pct: float,
):
    if starting_balance <= 0 or total_pnl >= 0:
        return
    loss_pct = abs(total_pnl) / starting_balance * 100
    limit_reached_pct = loss_pct / daily_loss_limit_pct * 100
    if limit_reached_pct >= 80:
        loss_abs = abs(total_pnl)
        limit_abs = starting_balance * daily_loss_limit_pct / 100
        msg = (
            f"🚨 ВНИМАНИЕ: Дневной убыток {limit_reached_pct:.0f}% от лимита "
            f"(${loss_abs:.2f}/${limit_abs:.2f}). "
            f"Следующий убыток может остановить торговлю."
        )
        await send_error_alert(bot, chat_id, "daily_loss_80pct", msg)
```

This is called from the signal dispatch path after calculating position size.

### `/scan` Manual Trigger (TG-14)

```python
@router.message(Command("scan"))
async def cmd_scan(message: Message):
    await message.answer("Запуск сканирования рынка...")
    asyncio.create_task(
        run_strategy_scan(SessionLocal, binance_client, settings, bot)
    )
    # Non-blocking — result arrives via signal message or error notification
```

---

## Signal Model Gap: `message_id` Field

The current `Signal` model (bot/db/models.py) does not have a `telegram_message_id` column. This column is required to:
- Edit the message when the signal is confirmed/rejected/expired (TG-03, TG-04)
- Schedule the expiry job with the correct message_id

**Required migration:** Add `telegram_message_id: Mapped[Optional[int]]` to the `Signal` model and a corresponding Alembic migration. This is a Wave 0 task for Phase 4.

Additionally, `signals.status` currently has values `pending`, `confirmed`, `rejected` (implied). Add `expired` as a valid status value. The column is VARCHAR(20), so no migration needed — just document it.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-telegram-bot (sync) | aiogram 3.x (async, FSM) | aiogram 3.0 (2022) | Full asyncio compatibility |
| aiogram 2.x handler decorators | aiogram 3.x Router + filters | aiogram 3.0 | Modular handler organization |
| Raw callback_data strings | `CallbackData` factory with typed fields | aiogram 3.x | Type-safe, no parsing bugs |
| Global bot variable | `dp.workflow_data` dependency injection | aiogram 3.x | Testable, no global state |

**Deprecated/outdated:**
- `Dispatcher(bot=bot)` (aiogram 2.x): In aiogram 3.x, Bot is passed to `start_polling(bot)`, not the Dispatcher constructor. The existing `main.py` already uses the correct 3.x pattern.
- `types.InlineKeyboardButton` raw construction: Use `InlineKeyboardBuilder` instead.

---

## Open Questions

1. **`/settings` command persistence on restart**
   - What we know: `top_n_coins`, `review_interval_days`, and `coin_whitelist` live in pydantic-settings (from `.env`) or per-Strategy rows in DB.
   - What's unclear: Should `/settings top_n 15` persist across restarts? A `BotSettings` DB table would handle this, but is scope creep.
   - Recommendation: For Phase 4, mutate the in-memory `settings` object for runtime effect. Document that restart reverts to `.env`. If persistence is needed, it becomes a Phase 4+ enhancement.

2. **Chart bytes storage for expiry editing**
   - What we know: When expiry fires, we edit the message but the caption must be preserved. `edit_message_caption` requires the full new caption text.
   - What's unclear: Should the original caption be stored in DB (Signal.caption field) to reconstruct it during expiry edit?
   - Recommendation: Store the formatted caption text in a new `Signal.caption` DB column (or reconstruct from signal fields), or append to the existing caption by fetching `callback.message.caption` — but that's not available in the scheduled job. Store the caption at dispatch time.

3. **Pine Script for TG-15 (Phase 4 scope)**
   - What we know: PINE-01/02/03 are Phase 6 requirements. `/chart SYMBOL` (TG-15) is Phase 4.
   - Recommendation: Phase 4 implements `/chart SYMBOL` as a lookup of the last signal for SYMBOL and returns "Pine Script будет доступен в следующем обновлении." The inline Pine Script button on the signal message triggers the same placeholder.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24+ |
| Config file | `pytest.ini` (exists at project root) |
| Quick run command | `pytest tests/test_telegram*.py -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TG-01 | AllowedChatMiddleware blocks non-allowed chat_id | unit | `pytest tests/test_telegram_middleware.py -x` | ❌ Wave 0 |
| TG-01 | AllowedChatMiddleware passes allowed chat_id | unit | `pytest tests/test_telegram_middleware.py -x` | ❌ Wave 0 |
| TG-02 | `send_signal_message()` calls `bot.send_photo` with correct args | unit (mock bot) | `pytest tests/test_telegram_dispatch.py -x` | ❌ Wave 0 |
| TG-02 | Caption truncated at 1024 chars | unit | `pytest tests/test_telegram_dispatch.py::test_caption_truncation -x` | ❌ Wave 0 |
| TG-03 | Keyboard has 3 buttons for normal signal | unit | `pytest tests/test_telegram_dispatch.py -x` | ❌ Wave 0 |
| TG-03 | Keyboard has 2 buttons (no Confirm) for MIN_NOTIONAL signal | unit | `pytest tests/test_telegram_dispatch.py::test_min_notional_keyboard -x` | ❌ Wave 0 |
| TG-05 | `/start` handler returns status text | unit (mock DB, mock Binance) | `pytest tests/test_telegram_commands.py::test_cmd_start -x` | ❌ Wave 0 |
| TG-07 | `/risk stake 3` updates base_stake_pct | unit (mock DB) | `pytest tests/test_telegram_settings.py::test_risk_stake -x` | ❌ Wave 0 |
| TG-07 | `/risk stake 999` returns validation error | unit | `pytest tests/test_telegram_settings.py::test_risk_stake_invalid -x` | ❌ Wave 0 |
| TG-07 | `/risk reset` restores defaults | unit (mock DB) | `pytest tests/test_telegram_settings.py::test_risk_reset -x` | ❌ Wave 0 |
| TG-08 | `/criteria return 200` updates min_total_return_pct | unit (mock DB) | `pytest tests/test_telegram_settings.py::test_criteria_return -x` | ❌ Wave 0 |
| TG-20 | 80% warning sent when loss >= 80% of limit | unit | `pytest tests/test_telegram_notifications.py::test_80pct_warning -x` | ❌ Wave 0 |
| TG-21 | Error throttle suppresses repeat within 15 min | unit | `pytest tests/test_telegram_notifications.py::test_throttle -x` | ❌ Wave 0 |
| TG-22 | Consecutive empty cycles alert fires at threshold | unit | `pytest tests/test_telegram_notifications.py::test_empty_cycles -x` | ❌ Wave 0 |
| Double-tap | Confirm callback is idempotent (second tap no-ops) | unit (mock DB with status) | `pytest tests/test_telegram_callbacks.py::test_double_confirm -x` | ❌ Wave 0 |
| Expiry | Signal marked expired after timeout | unit (mock APScheduler + DB) | `pytest tests/test_telegram_dispatch.py::test_signal_expiry -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_telegram*.py -x -q`
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_telegram_middleware.py` — covers TG-01
- [ ] `tests/test_telegram_dispatch.py` — covers TG-02, TG-03, signal expiry
- [ ] `tests/test_telegram_commands.py` — covers TG-05 through TG-18
- [ ] `tests/test_telegram_settings.py` — covers TG-07, TG-08, TG-16, /risk and /criteria parsing
- [ ] `tests/test_telegram_callbacks.py` — covers TG-03, TG-04, double-tap idempotency
- [ ] `tests/test_telegram_notifications.py` — covers TG-20, TG-21, TG-22

All test files use `pytest.importorskip` at module level until production modules exist (established Phase 2-3 pattern per STATE.md).

---

## Sources

### Primary (HIGH confidence)
- Existing `bot/main.py` — Bot and Dispatcher instantiation pattern, confirmed working
- Existing `bot/risk/manager.py` — `update_risk_settings()` signature and UPDATABLE_FIELDS
- Existing `bot/db/models.py` — All Signal, RiskSettings, StrategyCriteria fields confirmed
- Existing `bot/signals/generator.py` — signal dict structure with all TG-02 fields
- Existing `bot/charts/generator.py` — `generate_chart()` async API returning bytes
- `.planning/research/STACK.md` — aiogram 3.26.0 confirmed current, installed
- `.planning/research/PITFALLS.md` — Double-tap race condition pattern (Pitfall 5), message edit exception pattern (Tech Debt table)
- `idea.md` Section 8 — Exact signal format, all command specs
- `idea.md` Sections 7.4 + 5.3 — Exact `/risk` and `/criteria` subcommand specs

### Secondary (MEDIUM confidence)
- aiogram 3.x middleware docs (verified against working main.py pattern)
- APScheduler 3.11.2 DateTrigger — same library already in use, `date` trigger is documented

### Tertiary (LOW confidence)
- Telegram Bot API caption limit (1024 chars for `send_photo`) — commonly cited, not verified against current API docs during this research session. Verify at implementation time.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all existing
- Architecture patterns: HIGH — based directly on working Phase 1-3 code
- aiogram handler patterns: HIGH — confirmed against working main.py; aiogram 3.x API is stable
- Signal format: HIGH — directly from idea.md spec section 8.2 and existing signal dict structure
- Pitfalls: HIGH — sourced from project's own PITFALLS.md with DB-confirmed patterns
- Settings mutation: MEDIUM — in-memory approach is simple but has known restart behavior
- Caption length limit: MEDIUM — commonly documented but not verified against current API

**Research date:** 2026-03-19
**Valid until:** 2026-04-19 (aiogram 3.x is stable; no breaking changes expected in 30 days)
