---
phase: 02-strategy-pipeline
verified: 2026-03-19T14:00:00Z
status: gaps_found
score: 18/19 must-haves verified
re_verification: false
gaps:
  - truth: "Coins with fewer than 15,000 15m candles are skipped and logged"
    status: failed
    reason: "fetch_ohlcv_15m logs a warning when len(df) < MIN_HISTORY_CANDLES but still returns the non-empty DataFrame. The caller in run_strategy_scan checks `ohlcv_df.empty`, which is only True when there are 0 rows. A coin with 500 candles (well below 15,000) passes the empty check and proceeds to Claude generation, violating the skip behavior."
    artifacts:
      - path: "bot/scanner/market_scanner.py"
        issue: "Lines 77-84: warning is logged but function returns the partial DataFrame instead of an empty one when len(df) < MIN_HISTORY_CANDLES"
      - path: "bot/strategy/manager.py"
        issue: "Line 224: `if ohlcv_df.empty:` only skips a completely empty DataFrame (0 rows), not a DataFrame with insufficient history"
    missing:
      - "In fetch_ohlcv_15m: after the warning log at line 79, return an empty DataFrame (e.g. `return pd.DataFrame(columns=['open_time', 'open', 'high', 'low', 'close', 'volume'])`) instead of continuing to return df"
      - "Remove or update the else branch on line 83 — the debug log should only fire for sufficient-history DataFrames"
human_verification:
  - test: "Run bot with a Telegram-adjustable criteria command (/criteria)"
    expected: "Criteria changes update the strategy_criteria DB table and are picked up on the next scan cycle"
    why_human: "FILT-05 (criteria adjustable via /criteria Telegram command) is claimed as phase 2 scope in REQUIREMENTS.md but the Telegram handler implementation is deferred to Phase 4. The DB schema (strategy_criteria table) and Settings defaults are in place, but the Telegram wiring is not present."
  - test: "Run bot with a Telegram /settings review_interval N command"
    expected: "review_interval_days updates and new strategies are stored with the new interval"
    why_human: "LIFE-04 (review interval configurable via Telegram) is deferred to Phase 4 for the same reason — the command handler doesn't exist yet."
---

# Phase 2: Strategy Pipeline Verification Report

**Phase Goal:** The bot can autonomously discover tradeable coins, generate a non-overfit SMC+MACD/RSI strategy via Claude, validate it against configurable criteria, and store versioned strategies in PostgreSQL
**Verified:** 2026-03-19T14:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Bot startup fails fast with a clear error if ANTHROPIC_API_KEY is missing from .env | VERIFIED | `bot/config.py` lines 84-93: `Settings()` at module level; `ValidationError` caught, field name printed to stderr, `sys.exit(1)` called |
| 2 | All 19 test cases exist, collect, and pass GREEN | VERIFIED | `pytest tests/test_scanner.py tests/test_claude_engine.py tests/test_strategy_filter.py tests/test_strategy_manager.py` → 19 passed |
| 3 | conftest.py provides test_settings fixture with anthropic_api_key and sample_criteria fixture | VERIFIED | `tests/conftest.py` lines 18 and 23-34 |
| 4 | Scanner returns top-N symbols from whitelist ranked by descending quoteVolume, excluding coins below min_volume_usdt | VERIFIED | `bot/scanner/market_scanner.py`: `get_top_n_by_volume` sorts by `quoteVolume` descending, filters by `min_volume_usdt`, slices to `top_n` |
| 5 | Coins with fewer than 15,000 15m candles (~6 months) are skipped and logged | FAILED | `fetch_ohlcv_15m` logs a warning but returns the partial DataFrame; `run_strategy_scan` checks `ohlcv_df.empty` which is only True at 0 rows — partial-history coins pass through |
| 6 | register_scanner_job adds a CronTrigger job to APScheduler | VERIFIED | `bot/scanner/market_scanner.py` lines 98-103: `scheduler.add_job()` with `CronTrigger` |
| 7 | fetch_ohlcv_15m returns DataFrame with columns [open_time, open, high, low, close, volume] and correct dtypes | VERIFIED | Lines 63-75: DataFrame constructed with 12 columns then sliced to 6; `open_time` converted to datetime, numeric columns cast to float |
| 8 | generate_strategy uploads OHLCV CSV via Files API with betas=['files-api-2025-04-14'] | VERIFIED | `bot/strategy/claude_engine.py` lines 225-235: `client.beta.files.upload()` then `client.beta.messages.create()` with `betas=["files-api-2025-04-14"]` |
| 9 | Prompt instructs Claude to split data 70/30 and reject strategy if validation return < train * 0.6 | VERIFIED | `_build_prompt`: contains "WALK-FORWARD VALIDATION REQUIRED", "70%", "30%", "train", "validation" |
| 10 | StrategySchema validates complete strategy dict and raises ValidationError on malformed input | VERIFIED | `StrategySchema.model_validate()` present with nested sub-models; `model_config = {"extra": "ignore"}` |
| 11 | ClaudeTimeoutError raised if timeout exceeded; file always deleted in finally | VERIFIED | Lines 247-258: `asyncio.TimeoutError` → `ClaudeTimeoutError`; `finally` block calls `client.beta.files.delete(file_id)` |
| 12 | On malformed JSON from Claude, engine retries once then raises StrategySchemaError | VERIFIED | Lines 262-302: first parse attempt; on `StrategySchemaError` a fresh API call is made with new file upload; second failure raises StrategySchemaError |
| 13 | filter_strategy returns FilterResult(passed=True) when all required criteria pass | VERIFIED | `bot/strategy/filter.py`: all 6 checks evaluated; `failed = [k for k in required if not checks[k]]` |
| 14 | In relaxed mode, filter_strategy passes if only total_return_pct and max_drawdown_pct pass | VERIFIED | Lines 46-50: `required = {"total_return_pct", "max_drawdown_pct"}` when `strict_mode=False` |
| 15 | Failed strategies are logged to skipped_coins table with failed_criteria JSONB list | VERIFIED | `log_skipped_coin`: `SkippedCoin(failed_criteria=filter_result.failed_criteria)` → `session.add()` + `commit()` |
| 16 | save_strategy deactivates existing active strategies before inserting a new one (never deletes) | VERIFIED | Lines 89-93: `sa.update(Strategy)...values(is_active=False)`; then `session.add(new_strategy)` |
| 17 | criteria_snapshot is saved with every new strategy row | VERIFIED | `Strategy(criteria_snapshot=criteria_snapshot)` in `save_strategy` line 107 |
| 18 | get_coins_needing_strategy returns empty lists when all symbols have active, non-expired strategies | VERIFIED | Function queries for `is_active==True AND next_review_at > now`; returns `([], [])` when all coins are in active set |
| 19 | get_expired_active_strategies returns strategies where next_review_at <= now() | VERIFIED | Lines 63-70: `select(Strategy).where(is_active==True, next_review_at<=now_utc)` |

**Score:** 18/19 truths verified

---

### Required Artifacts

| Artifact | Provides | Exists | Substantive | Wired | Status |
|----------|----------|--------|-------------|-------|--------|
| `bot/config.py` | anthropic_api_key, claude_model, coin_whitelist, scanner config fields | Yes | Yes — all fields present with correct types | Yes — imported in main.py, manager.py | VERIFIED |
| `.env.example` | ANTHROPIC_API_KEY placeholder | Yes | Yes — line 39 | N/A (docs) | VERIFIED |
| `tests/conftest.py` | test_settings with anthropic_api_key, sample_criteria fixture | Yes | Yes — both fixtures present | Yes — used by 19 tests | VERIFIED |
| `tests/test_scanner.py` | 5 tests for SCAN-01..04, STRAT-03 | Yes | Yes — 5 substantive tests | Yes — 5 passed GREEN | VERIFIED |
| `tests/test_claude_engine.py` | 3 tests for STRAT-01, STRAT-02, STRAT-04 | Yes | Yes — 3 substantive tests | Yes — 3 passed GREEN | VERIFIED |
| `tests/test_strategy_filter.py` | 3 tests for FILT-01, FILT-02, FILT-03 | Yes | Yes — 3 substantive tests | Yes — 3 passed GREEN | VERIFIED |
| `tests/test_strategy_manager.py` | 8 tests for STRAT-05, FILT-04, FILT-05, LIFE-01..05 | Yes | Yes — 8 substantive tests | Yes — 8 passed GREEN | VERIFIED |
| `bot/scanner/__init__.py` | Package marker | Yes | Empty (correct) | N/A | VERIFIED |
| `bot/scanner/market_scanner.py` | get_top_n_by_volume, fetch_ohlcv_15m, register_scanner_job | Yes | Yes — all 3 functions implemented | Yes — imported in manager.py | VERIFIED (with behavioral gap noted) |
| `bot/strategy/__init__.py` | Package marker | Yes | Empty (correct) | N/A | VERIFIED |
| `bot/strategy/claude_engine.py` | generate_strategy, _build_prompt, StrategySchema, ClaudeTimeoutError, StrategySchemaError | Yes | Yes — all 5 exports present | Yes — imported in manager.py | VERIFIED |
| `bot/strategy/filter.py` | filter_strategy, FilterResult | Yes | Yes — both present | Yes — imported in manager.py | VERIFIED |
| `bot/strategy/manager.py` | get_coins_needing_strategy, save_strategy, log_skipped_coin, get_expired_active_strategies, deactivate_strategy, run_strategy_scan, run_expiry_check | Yes | Yes — all 7 functions present | Yes — imported in main.py | VERIFIED |
| `bot/db/repositories/__init__.py` | Package marker | Yes | Empty (correct) | N/A | VERIFIED |
| `bot/main.py` | APScheduler CronTrigger jobs for scanner and expiry | Yes | Yes — two jobs registered | Yes — run_strategy_scan + run_expiry_check wired | VERIFIED |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bot/config.py Settings.anthropic_api_key` | `bot/strategy/claude_engine.py` | `settings.anthropic_api_key.get_secret_value()` | WIRED | `manager.py` line 232 calls `settings.anthropic_api_key.get_secret_value()` and passes to `generate_strategy(api_key=...)` |
| `bot/strategy/claude_engine.py generate_strategy` | `anthropic.AsyncAnthropic` | `anthropic.AsyncAnthropic(api_key=api_key)` | WIRED | `claude_engine.py` line 220 |
| `bot/strategy/claude_engine.py` | Anthropic Files API | `client.beta.files.upload()` + delete in finally | WIRED | Lines 225 and 256 |
| `bot/strategy/claude_engine.py _build_prompt` | walk-forward validation | "WALK-FORWARD VALIDATION" text in prompt | WIRED | Confirmed present in prompt string at line 102 |
| `bot/strategy/manager.py run_strategy_scan` | `bot/scanner/market_scanner.get_top_n_by_volume` | called with binance_client, settings values | WIRED | `manager.py` lines 190-194 |
| `bot/strategy/manager.py run_strategy_scan` | `bot/strategy/claude_engine.generate_strategy` | called for each candidate coin | WIRED | `manager.py` lines 228-234 |
| `bot/strategy/manager.py run_strategy_scan` | `bot/strategy/filter.filter_strategy` | called after generate_strategy returns | WIRED | `manager.py` lines 236-238 |
| `bot/main.py` | `run_strategy_scan + run_expiry_check` | `scheduler.add_job()` with CronTrigger | WIRED | `main.py` lines 178-192 |
| `bot/scanner/market_scanner.py register_scanner_job` | `bot/main.py` | (plan 02-01 key_link) | ORPHANED | `register_scanner_job` is not called in main.py — main.py uses `scheduler.add_job()` directly. This is intentional per plan 02-03 which supersedes 02-01's key_link. Function tested and working; not a blocker. |

---

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|---------|
| SCAN-01 | Scanner retrieves top-N coins by 24h volume from Binance USDT-M Futures | SATISFIED | `get_top_n_by_volume` calls `futures_ticker()`, filters whitelist, sorts by quoteVolume |
| SCAN-02 | Scanner runs on configurable schedule (default: hourly) | SATISFIED | `scheduler.add_job()` with `CronTrigger(hour="*", minute="5")` in main.py |
| SCAN-03 | Scanner filters out coins below minimum volume threshold | SATISFIED | `min_volume_usdt` filter applied in `get_top_n_by_volume` |
| SCAN-04 | Number of coins (top-N) configurable | SATISFIED | `top_n` parameter from `settings.top_n_coins`; configurable via .env / future Telegram command |
| STRAT-01 | Claude API generates strategy via code_execution tool | SATISFIED | `generate_strategy` uses `tools=[{"type": "code_execution_20250825", "name": "code_execution"}]` |
| STRAT-02 | Strategy JSON contains MACD, RSI, SMC params, entry/exit rules, backtest results | SATISFIED | `StrategySchema` enforces all required sub-models |
| STRAT-03 | Claude backtesting uses OHLCV data for configurable period | SATISFIED | `fetch_ohlcv_15m(months=criteria["backtest_period_months"])` wired; but insufficient-history skip is partially broken (see gaps) |
| STRAT-04 | Strategy generation includes walk-forward validation (70/30 split) | SATISFIED | `_build_prompt` contains explicit walk-forward instructions with 70/30 split and validation >= train*0.6 check |
| STRAT-05 | Strategy Manager checks for active, non-expired strategy before requesting new generation | SATISFIED | `get_coins_needing_strategy` queries active non-expired symbols and excludes them |
| FILT-01 | Filter validates against 6 configurable criteria in strict mode | SATISFIED | `filter_strategy` checks all 6 criteria when `strict_mode=True` |
| FILT-02 | Default criteria: return >=200%, drawdown <=-12%, winrate >=55%, PF >=1.8, trades >=30, avg R/R >=2.0 | SATISFIED | All 6 defaults in `filter_strategy` match spec; also in `Settings` fields and `sample_criteria` fixture |
| FILT-03 | Strict mode and relaxed mode configurable | SATISFIED | `strict_mode` parameter drives required set in `filter_strategy` |
| FILT-04 | Failed strategies logged with which criteria were not met | SATISFIED | `log_skipped_coin` stores `filter_result.failed_criteria` in SkippedCoin.failed_criteria JSONB |
| FILT-05 | All filter criteria adjustable via Telegram /criteria command | NEEDS HUMAN | DB schema (`strategy_criteria` table) and Settings defaults exist; Telegram /criteria handler is Phase 4 scope. Phase 2 provides the data model and seeding; command wiring deferred. |
| LIFE-01 | Strategies stored in PostgreSQL with full metadata | SATISFIED | `save_strategy` creates `Strategy` row with symbol, timeframe, strategy_data, backtest_score, is_active, timestamps |
| LIFE-02 | Strategy expires after configurable interval (default: 30 days) | SATISFIED | `next_review_at = now() + timedelta(days=review_interval_days)` in `save_strategy`; `get_expired_active_strategies` detects expired |
| LIFE-03 | Old strategy versions preserved (is_active=false), never hard-deleted | SATISFIED | `save_strategy` issues `UPDATE ... SET is_active=False` before insert; no DELETE anywhere |
| LIFE-04 | Review interval configurable via Telegram /settings review_interval N | NEEDS HUMAN | `review_interval_days` parameter exists in `save_strategy`; Telegram handler deferred to Phase 4 |
| LIFE-05 | Criteria snapshot saved with each strategy for audit trail | SATISFIED | `Strategy(criteria_snapshot=criteria_snapshot)` in `save_strategy` |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bot/strategy/manager.py` | 252 | `# TODO: send Telegram alert (Phase 4 wires this)` | Info | Intentional deferral to Phase 4 — not a blocker |
| `bot/scanner/market_scanner.py` | 77-84 | Logs warning but returns partial DataFrame when `len(df) < MIN_HISTORY_CANDLES`; caller's `ohlcv_df.empty` check won't catch it | Blocker | Coins with < 15,000 candles are not skipped as specified; they proceed to Claude generation |

---

### Human Verification Required

#### 1. Telegram /criteria command wires to filter (FILT-05)

**Test:** From Telegram, send `/criteria min_total_return 250` or equivalent
**Expected:** `strategy_criteria` DB row updated; next scan cycle uses the new threshold
**Why human:** The Telegram handler for `/criteria` is Phase 4 scope. The DB model and default seeding are complete. Phase 2 satisfies the data-layer half of FILT-05 only.

#### 2. Telegram /settings review_interval N command (LIFE-04)

**Test:** From Telegram, send `/settings review_interval 14`
**Expected:** Next strategy saved uses `review_interval_days=14`
**Why human:** Same reason as FILT-05 — Telegram command handler deferred to Phase 4.

---

### Gaps Summary

**One behavioral gap found** (blocker for the STRAT-03 truth about insufficient-history skipping):

`fetch_ohlcv_15m` in `bot/scanner/market_scanner.py` was specified to return an empty DataFrame when the fetched history has fewer than 15,000 candles (6 months of 15m data). The actual implementation logs a warning but returns the full (short) DataFrame. The caller in `run_strategy_scan` only skips if `ohlcv_df.empty`, which is True only for zero-row DataFrames. A coin with 500 candles passes the check and proceeds to Claude generation with insufficient data, which can produce overfit or unreliable strategies.

**Fix:** In `fetch_ohlcv_15m`, change the insufficient-history branch to return an empty DataFrame:

```python
if len(df) < MIN_HISTORY_CANDLES:
    logger.warning(
        f"Insufficient OHLCV history for {symbol}: got {len(df)} candles, "
        f"need >= {MIN_HISTORY_CANDLES}. Skipping."
    )
    return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
```

Note on FILT-05 and LIFE-04: These requirements have a Telegram-command component that is explicitly planned for Phase 4. The Phase 2 data model (DB table, Settings defaults, filter function accepting criteria dict) satisfies the Phase 2 deliverable. The Telegram wiring being deferred does not constitute a Phase 2 failure for the core goal ("validate against configurable criteria") since criteria are already configurable via Settings/env.

---

_Verified: 2026-03-19T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
