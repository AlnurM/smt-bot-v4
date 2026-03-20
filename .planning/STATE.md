---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 06-03-PLAN.md (skipped coins loosen buttons + cmd_skipped drill-down)
last_updated: "2026-03-20T08:14:00.477Z"
last_activity: 2026-03-19 — Completed Plan 01-01 (scaffold, config, Docker stack, pytest infra)
progress:
  total_phases: 6
  completed_phases: 6
  total_plans: 21
  completed_plans: 21
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-19)

**Core value:** The full trade loop must work end-to-end: Claude generates a strategy → bot identifies a signal → trader confirms in Telegram → order executes on Binance Futures.
**Current focus:** Phase 1 — Foundation

## Current Position

Phase: 1 of 6 (Foundation)
Plan: 1 of 3 in current phase
Status: Executing
Last activity: 2026-03-19 — Completed Plan 01-01 (scaffold, config, Docker stack, pytest infra)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01-foundation P01 | 3 | 1 tasks | 17 files |
| Phase 01-foundation P02 | 7 | 2 tasks | 7 files |
| Phase 01-foundation P03 | 525384 | 2 tasks | 8 files |
| Phase 02-strategy-pipeline P00 | 5 | 2 tasks | 7 files |
| Phase 02-strategy-pipeline P01 | 4 | 1 tasks | 2 files |
| Phase 02-strategy-pipeline P02 | 4 | 1 tasks | 3 files |
| Phase 02-strategy-pipeline P03 | 4 | 2 tasks | 3 files |
| Phase 03-signal-and-risk P00 | 12 | 3 tasks | 8 files |
| Phase 03-signal-and-risk P01 | 7 | 2 tasks | 3 files |
| Phase 03-signal-and-risk P02 | 3 | 1 tasks | 1 files |
| Phase 03-signal-and-risk P03 | 6 | 1 tasks | 2 files |
| Phase 03-signal-and-risk P04 | 6 | 1 tasks | 2 files |
| Phase 04-telegram-interface P01 | 7 | 3 tasks | 13 files |
| Phase 04-telegram-interface P03 | 251 | 2 tasks | 3 files |
| Phase 04-telegram-interface P02 | 5 | 3 tasks | 5 files |
| Phase 05-order-execution-and-position-monitoring P00 | 2 | 2 tasks | 5 files |
| Phase 05-order-execution-and-position-monitoring P01 | 7 | 2 tasks | 6 files |
| Phase 05-order-execution-and-position-monitoring P02 | 5 | 2 tasks | 4 files |
| Phase 06-reporting-and-audit P01 | 3 | 2 tasks | 4 files |
| Phase 06-reporting-and-audit P02 | 5 | 3 tasks | 9 files |
| Phase 06-reporting-and-audit P03 | 3 | 2 tasks | 4 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Init]: python-binance over CCXT (deeper Binance Futures feature coverage)
- [Init]: APScheduler 3.11.2 only — 4.x explicitly unsafe per maintainer
- [Init]: pandas-ta-classic (community fork) — original pandas-ta at risk of archival
- [Init]: PostgreSQL from day one — no SQLite migration path later
- [Phase 01-foundation]: SecretStr on all secret fields — pydantic masks in repr/str automatically, no custom logging filter needed
- [Phase 01-foundation]: Module-level settings = Settings() with sys.exit(1) on ValidationError — fail fast if any required env var missing
- [Phase 01-foundation]: postgres:16 pinned in docker-compose.yml — ensures gen_random_uuid() built-in, no pgcrypto needed
- [Phase 01-foundation]: json.dumps() required for JSONB list seed values in Alembic op.bulk_insert — asyncpg cannot encode raw Python list as JSONB bind parameter
- [Phase 01-foundation]: greenlet added to requirements.txt — SQLAlchemy 2.0 asyncpg dialect requires it for sync-in-async bridging during migrations
- [Phase 01-foundation]: APScheduler not started at import time — create_scheduler() returns instance only; scheduler.start() called in main() after event loop is running
- [Phase 01-foundation]: startup_position_sync() is non-fatal — position sync failure logged as warning, bot continues startup regardless
- [Phase 01-foundation]: loguru caplog incompatibility — log capture in tests uses logger.add() custom sink, not pytest caplog
- [Phase 02-strategy-pipeline]: pytest.importorskip at module level for RED-state stubs — entire module skipped until production module exists, avoiding ImportError noise
- [Phase 02-strategy-pipeline]: anthropic_api_key placed after database_url in Settings — groups all required SecretStr fields before optional fields
- [Phase 02-strategy-pipeline]: coin_whitelist defaults to 15 hardcoded coins — overridable via COIN_WHITELIST env var per SettingsConfigDict config
- [Phase 02-strategy-pipeline]: MIN_HISTORY_CANDLES check logs warning but returns data to caller — fetch_ohlcv_15m is pure fetch; callers own skip logic
- [Phase 02-strategy-pipeline]: pandas installed in .venv (was missing despite requirements.txt)
- [Phase 02-strategy-pipeline]: StrategySchema extra='ignore': Claude may return extra fields — silently drop rather than reject valid strategies
- [Phase 02-strategy-pipeline]: Single retry with fresh API call on StrategySchemaError — no multi-turn conversation to avoid confusing Claude
- [Phase 02-strategy-pipeline]: asyncio.timeout() used over asyncio.wait_for() — cleaner syntax, compatible with Python 3.12+
- [Phase 02-strategy-pipeline]: filter_strategy is a pure stateless function — relaxed mode checks only total_return_pct + max_drawdown_pct; strict mode checks all 6 criteria
- [Phase 02-strategy-pipeline]: run_expiry_check logs only — never deactivates; save_strategy owns the atomic deactivate+insert to prevent coverage gaps
- [Phase 02-strategy-pipeline]: backtest_score = profit_factor * win_rate stored for ranking/analytics on every Strategy row
- [Phase 03-signal-and-risk]: OHLCV fixture uses numpy seed=42 random walk — deterministic across all environments, no network calls needed in tests
- [Phase 03-signal-and-risk]: pytest.importorskip at module level for Phase 3 RED-state test stubs — entire file skips until production module exists, cleaner than per-function skips
- [Phase 03-signal-and-risk]: pandas_ta_classic is correct import name for pandas-ta-classic (not pandas_ta)
- [Phase 03-signal-and-risk]: MACD columns from pandas-ta-classic normalised to uppercase at function boundary (MACDh->MACDH, MACDs->MACDS)
- [Phase 03-signal-and-risk]: Lazy binance import inside generate_signal() — pure helpers importable without binance for unit tests
- [Phase 03-signal-and-risk]: HTF 4h fetch non-fatal — exception caught, proceeds without HTF confirmation rather than aborting signal
- [Phase 03-signal-and-risk]: Both directions scored independently, highest wins; tie favors long to avoid short bias
- [Phase 03-signal-and-risk]: Liquidation safety formula uses leverage-aware condition (liq_distance*mult >= leverage*sl_distance) — higher leverage requires proportionally tighter SL relative to liquidation distance
- [Phase 03-signal-and-risk]: Risk Manager: all calculation functions are pure (no DB, no network) — only update_risk_settings is async for Phase 4 Telegram /risk handler
- [Phase 03-signal-and-risk]: matplotlib.use('Agg') at module level before mplfinance import — Docker headless rendering
- [Phase 03-signal-and-risk]: asyncio.to_thread() offloads CPU-bound _render_chart() — never block event loop with mplfinance rendering
- [Phase 03-signal-and-risk]: plt.close(fig) mandatory after fig.savefig() — memory hygiene for long-running bot process
- [Phase 03-signal-and-risk]: _get() accessor handles both dataclass attrs and dict keys — tests use dicts, production uses dataclasses
- [Phase 04-telegram-interface]: _bot_state module-level dict in commands.py shared with Plan 02 dispatch — avoids Dispatcher workflow_data mutation complexity
- [Phase 04-telegram-interface]: AllowedChatMiddleware on dp.update covers all update types with single registration point
- [Phase 04-telegram-interface]: Signal dispatch block in run_strategy_scan uses lazy guarded imports for bot.telegram.dispatch — safe no-op until Plan 02 creates dispatch.py
- [Phase 04-telegram-interface]: RISK_ALIASES and CRITERIA_ALIASES dispatch tables route alias to (db_field, type, min, max) — single validation path for all numeric /risk and /criteria subcommands
- [Phase 04-telegram-interface]: /criteria drawdown negation: user inputs positive, handler stores -abs(value) — max_drawdown_pct always negative in DB
- [Phase 04-telegram-interface]: /settings top_n in-memory only (settings.top_n_coins = new_value) — restart warning shown; CONTEXT.md locked decision
- [Phase 04-telegram-interface]: Caption truncated at 1020 chars (not 1024) — leaves 4-char safety buffer
- [Phase 04-telegram-interface]: expire_signal_job uses plain select (no FOR UPDATE) — scheduler job id uniqueness is sufficient for single-writer expiry path
- [Phase 04-telegram-interface]: callback.answer() called FIRST in all handlers before any DB work — satisfies Telegram 60s deadline (Pattern established)
- [Phase 04-telegram-interface]: SELECT FOR UPDATE + status == pending filter = atomic idempotency for Confirm/Reject double-tap protection
- [Phase 05-order-execution-and-position-monitoring]: Phase 5 double-tap protection relies on uq_orders_signal_id DB constraint — executor catches IntegrityError and returns early
- [Phase 05-order-execution-and-position-monitoring]: RED stubs use pytest.importorskip at module level — consistent with Phase 2/3 pattern, avoids ImportError noise
- [Phase 05-order-execution-and-position-monitoring]: mock_binance_client extended in-place (not replaced) — backward compatible with all existing Phase 2-4 tests
- [Phase 05-order-execution-and-position-monitoring]: Lazy import of _bot_state inside execute_order() to avoid circular import: executor -> commands -> nothing from executor
- [Phase 05-order-execution-and-position-monitoring]: asyncio.create_task() fires execute_order from handle_confirm after session.commit() — session exited before task runs, so SELECT FOR UPDATE sees committed status
- [Phase 05-order-execution-and-position-monitoring]: Sequential position loop in monitor_positions (not asyncio.gather) prevents win_streak_current race condition when two positions close in same cycle
- [Phase 05-order-execution-and-position-monitoring]: ORDER_DOES_NOT_EXIST (-2013) marks position 'orphaned' with no Telegram alert — testnet wipe scenario handled gracefully
- [Phase 06-reporting-and-audit]: pnl_sign_fmt uses abs(pnl) with explicit sign prefix — avoids Python float formatting placing minus after dollar sign
- [Phase 06-reporting-and-audit]: Etc/GMT-5 timezone used in APScheduler CronTrigger for UTC+5 (inverted POSIX convention)
- [Phase 06-reporting-and-audit]: generate_pine_script() accepts individual params (not Signal ORM) — pure function with no DB dependency, fully unit-testable
- [Phase 06-reporting-and-audit]: _zones_to_json_safe() uses hasattr(__dataclass_fields__) duck-typing — handles both dataclass instances from generator and plain dicts from DB JSONB
- [Phase 06-reporting-and-audit]: Pine Script zones capped at 5 per type — Pine editor performance degrades with many box/line objects
- [Phase 06-reporting-and-audit]: LoosenCriteria prefix 'lc' + field name fits well within 64-byte Telegram callback_data limit
- [Phase 06-reporting-and-audit]: send_skipped_coins_alert throttle logic moved inline — keyboard markup requires direct bot.send_message, not send_error_alert helper
- [Phase 06-reporting-and-audit]: noop field on LoosenCriteria removes keyboard without DB write — avoids phantom criterion updates

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: Claude `code_execution` prompt for walk-forward backtesting needs iteration — budget 2-3 prompt engineering cycles
- [Phase 3]: SMC OB/FVG detection parameter ranges not standardized — validate against known historical setups
- [Phase 1]: APScheduler PostgreSQL job store requires psycopg2 (sync) — evaluate overhead; fallback is in-memory job store

## Session Continuity

Last session: 2026-03-20T08:14:00.474Z
Stopped at: Completed 06-03-PLAN.md (skipped coins loosen buttons + cmd_skipped drill-down)
Resume file: None
