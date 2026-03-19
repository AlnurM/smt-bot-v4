---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 03-signal-and-risk-01-PLAN.md
last_updated: "2026-03-19T15:06:51.695Z"
last_activity: 2026-03-19 — Completed Plan 01-01 (scaffold, config, Docker stack, pytest infra)
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 12
  completed_plans: 9
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

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: Claude `code_execution` prompt for walk-forward backtesting needs iteration — budget 2-3 prompt engineering cycles
- [Phase 3]: SMC OB/FVG detection parameter ranges not standardized — validate against known historical setups
- [Phase 1]: APScheduler PostgreSQL job store requires psycopg2 (sync) — evaluate overhead; fallback is in-memory job store

## Session Continuity

Last session: 2026-03-19T15:06:51.692Z
Stopped at: Completed 03-signal-and-risk-01-PLAN.md
Resume file: None
