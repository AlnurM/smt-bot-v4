# Phase 2: Strategy Pipeline - Research

**Researched:** 2026-03-19
**Domain:** Claude code_execution backtesting, Binance OHLCV fetch, strategy validation, APScheduler job architecture
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Claude Prompt Design**
- Send 15m OHLCV data only (not 1h) — period determined by `backtest_period_months` (default 6 months, ~17,200 candles)
- 70/30 train/validation split for walk-forward validation — train on first 70%, validate on last 30%
- Strict JSON schema validation on Claude's response — must match strategy_data schema from spec exactly. If malformed, reject and retry once
- On Claude API failure (timeout, rate limit, error): send Telegram alert, fall back to existing strategies for coins that have them, retry failed coins in next scan cycle
- Sequential generation — one coin at a time, no parallel Claude calls
- 180-second timeout per Claude strategy generation call
- Claude model: `claude-sonnet-4-20250514` with `code_execution` tool (as specified in TZ)

**Scanner Coin Selection**
- Curated whitelist of approved coins (stored in DB/config), not auto-discovery
- Default whitelist managed via .env/config, overridable via Telegram command at runtime
- Scanner ranks whitelist coins by 24h USDT-M Perpetual volume, selects top-N (default: 10)
- Minimum history check: coin must have at least `backtest_period_months` of 15m OHLCV data available on Binance — skip if insufficient
- Configurable via Telegram `/settings` (top-N count already in spec)

**Filter Strictness**
- Default mode: relaxed (only return + drawdown must pass) — `strict_mode=false` as per spec default
- Priority queue for Claude API calls: coins with no strategy first → expired strategies → skip coins with active strategies
- When no coins pass criteria for multiple consecutive cycles: send Telegram alert with suggestion to loosen criteria (inline buttons)
- Alert threshold: configurable (e.g., after 3 consecutive empty scan cycles)

**Strategy Expiry Flow**
- Old strategy stays `is_active=true` until new one passes filter — no gap in coverage during re-generation
- Expiry checked by dedicated APScheduler job (daily), separate from hourly scan
- If re-generation fails filter: deactivate old strategy (`is_active=false`), coin drops from trading until next successful generation
- Version history: old strategy marked `is_active=false`, never hard-deleted (as per spec)
- `criteria_snapshot` saved with each strategy for audit trail

**Concurrent Generation**
- Sequential processing only — one Claude API call at a time per scan cycle
- No parallel Claude calls — avoids rate limiting and simplifies error handling

### Claude's Discretion
- OHLCV data serialization format (CSV vs JSON) for Claude prompt
- Exact prompt engineering for structured strategy output
- Token budget management per Claude call
- How to handle partial/incomplete backtest results from code_execution

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCAN-01 | Scanner retrieves top-N coins by 24h volume from Binance USDT-M Perpetual Futures | `AsyncClient.get_ticker()` with `futures=True`; filter to USDT pairs; sort by `quoteVolume`; filter against whitelist |
| SCAN-02 | Scanner runs on configurable schedule (default: hourly) | APScheduler `CronTrigger` with `hour='*'`; already scaffolded in `create_scheduler()` |
| SCAN-03 | Scanner filters out coins that don't meet minimum volume threshold | Compare `quoteVolume` against configurable `min_volume_usdt` threshold before ranking |
| SCAN-04 | Number of coins (top-N) configurable via Telegram `/settings` command | `top_n_coins` setting stored in `StrategyCriteria` or separate settings table; read at scan time |
| STRAT-01 | Claude API generates strategy via `code_execution` tool | `anthropic.messages.create()` with `tools=[{"type": "code_execution_20250825", ...}]`; parse `tool_result` blocks from response |
| STRAT-02 | Strategy JSON contains indicator params, SMC params, entry conditions, exit rules, backtest results | Validate against Pydantic schema mirroring spec section 6.2; reject if any required field missing |
| STRAT-03 | Claude backtesting uses OHLCV data for configurable period on 15m timeframe | `AsyncClient.futures_historical_klines()` with `HistoricalKlinesType.FUTURES`; pass as CSV to Claude via Files API |
| STRAT-04 | Strategy generation includes walk-forward validation (70/30 train/validation split) | Prompt Claude to use `df[:int(len(df)*0.7)]` for train, `df[int(len(df)*0.7):]` for validation; reject if validation Sharpe drops >30% vs train |
| STRAT-05 | Strategy Manager checks if active strategy exists and is not expired before requesting new generation | Query `strategies` table: `is_active=True AND next_review_at > now()`; skip Claude call if found |
| FILT-01 | Filter validates strategy against configurable criteria: min return, max drawdown, min win rate, min PF, min trades, min R/R | Pure function: compare `strategy_data["backtest"]` fields against `StrategyCriteria` DB row |
| FILT-02 | Default criteria: return ≥200%, drawdown ≤-12%, winrate ≥55%, PF ≥1.8, trades ≥30, avg R/R ≥2.0 | Already seeded in `StrategyCriteria` table by Phase 1 migration |
| FILT-03 | Strict mode (all criteria) and relaxed mode (only return + drawdown) configurable | `if strict_mode: check_all()` else `check_return_and_drawdown_only()` |
| FILT-04 | Failed strategies logged with which criteria were not met | Write to `skipped_coins` table: `failed_criteria` JSONB field lists failing criteria names + actual vs required values |
| FILT-05 | All filter criteria adjustable via Telegram `/criteria` command | Phase 4 wires Telegram; Phase 2 must ensure `StrategyCriteria` table row is always updated atomically |
| LIFE-01 | Strategies stored in PostgreSQL with full metadata | `Strategy` ORM model already defined; `is_active`, `next_review_at`, `criteria_snapshot` fields present |
| LIFE-02 | Strategy expires after configurable interval (default: 30 days) — triggers re-generation | Daily APScheduler job queries `WHERE is_active=True AND next_review_at <= now()`; marks for re-generation |
| LIFE-03 | Old strategy versions preserved (is_active=false), never hard-deleted | On new strategy write: `UPDATE strategies SET is_active=false WHERE symbol=? AND is_active=true`, then INSERT new |
| LIFE-04 | Review interval configurable via Telegram `/settings review_interval N` | `review_interval_days` column on `Strategy` model already exists; write at strategy creation time |
| LIFE-05 | Criteria snapshot saved with each strategy for audit trail | Serialize current `StrategyCriteria` row to dict → store in `Strategy.criteria_snapshot` JSONB on INSERT |

</phase_requirements>

---

## Summary

Phase 2 builds the strategy production pipeline: Market Scanner selects coins from a curated whitelist by 24h volume, Claude Strategy Engine generates SMC+MACD/RSI strategies using the `code_execution` tool with walk-forward validation, Strategy Filter validates against configurable criteria, and Strategy Manager handles versioned PostgreSQL storage with daily expiry checking.

The most complex component is the Claude Strategy Engine. The `code_execution_20250825` tool (current version as of 2026-03-19) runs in a sandboxed Python 3.11 environment with pandas, numpy, scipy, and matplotlib pre-installed — no additional pip installs needed for backtesting. The recommended approach for passing 17,200 candles of OHLCV data is the **Files API** (`files-api-2025-04-14` beta): upload a CSV, reference via `container_upload` content block, avoiding inline token cost. Each call is a fresh conversation — no state threads between retries.

The Scanner is straightforward: call `AsyncClient.get_ticker()` on Binance Futures, filter to the curated whitelist, rank by `quoteVolume`, return top-N. Minimum history verification requires a separate OHLCV fetch to check the earliest available timestamp. All jobs integrate cleanly with the existing `AsyncIOScheduler` from Phase 1.

**Primary recommendation:** Use the Files API to deliver OHLCV CSV to Claude's sandbox, parse the JSON strategy output with a strict Pydantic schema, and keep the Claude Engine as a pure async function that raises typed exceptions on failure so the Strategy Manager can route to fallback logic.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | 0.84.0 | Claude API client | Official SDK; `code_execution_20250825` tool available without beta header; Files API requires `files-api-2025-04-14` beta |
| python-binance | 1.0.35 | OHLCV fetch + 24h ticker | `futures_historical_klines()` with `HistoricalKlinesType.FUTURES` returns paginated candles; `get_ticker()` returns volume |
| pydantic v2 | (via pydantic-settings) | Strategy JSON schema validation | Type-safe validation of Claude's output; strict mode rejects extra fields |
| APScheduler | 3.11.2 | Hourly scan + daily expiry jobs | Already scaffolded; `CronTrigger` for both jobs |
| SQLAlchemy async | 2.0.48 | Strategy CRUD | All ORM models already defined in Phase 1 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio.timeout | stdlib | 180s timeout per Claude call | Wraps `client.messages.create()` |
| json | stdlib | Strategy JSON parsing + schema validation | Parse Claude text_block output before Pydantic |
| csv / io.StringIO | stdlib | OHLCV serialization for Claude prompt | CSV is more token-efficient than JSON for tabular data |
| loguru | 0.7+ | Structured logging per module | Already used in Phase 1 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Files API for OHLCV data | Inline CSV in prompt | Inline costs more tokens and risks context exhaustion at 17,200 candles; Files API is cleaner |
| Pydantic strict schema | jsonschema | Pydantic integrates with existing project patterns; generates clear error messages |
| Daily APScheduler job for expiry | Check in hourly scan | Separate job avoids bloating the scan loop; matches user's explicit decision |

**Installation:** All packages already installed in Phase 1. No new additions needed for Phase 2.

**ANTHROPIC_API_KEY gap:** `Settings` in `bot/config.py` does NOT currently include `anthropic_api_key`. This field MUST be added to `Settings` (as `SecretStr`) and to `.env.example` before the Claude Engine can be implemented.

---

## Architecture Patterns

### Recommended Project Structure for Phase 2

```
bot/
├── scanner/
│   ├── __init__.py
│   └── market_scanner.py        # SCAN-01 through SCAN-04
│
├── strategy/
│   ├── __init__.py
│   ├── claude_engine.py         # STRAT-01 through STRAT-04
│   ├── filter.py                # FILT-01 through FILT-05
│   └── manager.py               # STRAT-05, LIFE-01 through LIFE-05
│
└── db/
    └── repositories/
        └── strategy_repo.py     # Strategy CRUD extracted from manager
```

### Pattern 1: Priority Queue for Claude Calls

**What:** Before calling Claude, sort coins into three tiers: (1) no strategy at all, (2) expired strategy, (3) active strategy (skip). Process tier 1 first, then tier 2.

**When to use:** Every scan cycle — reduces unnecessary Claude API calls.

```python
# Source: CONTEXT.md Locked Decisions + LIFE-02 requirement
async def get_coins_needing_strategy(symbols: list[str], session) -> tuple[list, list]:
    """Returns (no_strategy_coins, expired_strategy_coins). Active coins excluded."""
    active = await strategy_repo.get_active_symbols(session)
    expired = await strategy_repo.get_expired_symbols(session)
    no_strategy = [s for s in symbols if s not in active and s not in expired]
    expired_in_list = [s for s in symbols if s in expired]
    return no_strategy, expired_in_list
```

### Pattern 2: Claude Engine as Pure Async Function

**What:** `claude_engine.py` contains one async function: `generate_strategy(symbol, ohlcv_df, criteria) -> dict`. No DB access, no Telegram. Raises `ClaudeTimeoutError`, `ClaudeResponseError`, `StrategySchemaError` for typed exception handling in the manager.

**When to use:** All Claude invocations go through this one function.

```python
# Source: Anthropic official docs + idea.md section 4.2
import asyncio
import anthropic

async def generate_strategy(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    criteria: dict,
    api_key: str,
    timeout_seconds: int = 180,
) -> dict:
    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Upload OHLCV as CSV via Files API
    csv_bytes = ohlcv_df.to_csv(index=False).encode()
    file_obj = await client.beta.files.upload(
        file=("ohlcv.csv", csv_bytes, "text/csv"),
    )

    try:
        async with asyncio.timeout(timeout_seconds):
            response = await client.beta.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                betas=["files-api-2025-04-14"],
                tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "container_upload", "file_id": file_obj.id},
                        {"type": "text", "text": _build_prompt(symbol, criteria)},
                    ]
                }]
            )
    except asyncio.TimeoutError:
        raise ClaudeTimeoutError(f"Claude timed out after {timeout_seconds}s for {symbol}")
    finally:
        # Always clean up the uploaded file
        await client.beta.files.delete(file_obj.id)

    return _parse_strategy_response(response)
```

### Pattern 3: Walk-Forward Validation in Claude Prompt

**What:** Instruct Claude explicitly to split the data 70/30, backtest on train set, validate on validation set, and reject strategies where validation Sharpe ratio drops more than 30% vs train.

**When to use:** Include in every strategy generation prompt to prevent overfitting.

```python
# Source: CONTEXT.md Locked Decisions + PITFALLS.md Pitfall 2
def _build_prompt(symbol: str, criteria: dict) -> str:
    return f"""
The file ohlcv.csv contains 15m OHLCV data for {symbol}.
Columns: timestamp, open, high, low, close, volume

TASK: Find optimal SMC + MACD/RSI strategy parameters.

WALK-FORWARD VALIDATION REQUIRED:
1. Split data: train = first 70%, validation = last 30%
2. Optimize all parameters on TRAIN set only
3. Evaluate final strategy on VALIDATION set
4. REJECT strategy if validation total_return < train total_return * 0.6
   (i.e., validation performance may not drop more than 40% vs train)

BACKTEST CRITERIA (must pass on VALIDATION set):
- total_return_pct >= {criteria['min_total_return_pct']}%
- max_drawdown_pct >= {criteria['max_drawdown_pct']}%  (e.g., -12 means drawdown must be > -12%)
- win_rate >= {criteria['min_win_rate_pct'] / 100}
- profit_factor >= {criteria['min_profit_factor']}
- total_trades >= {criteria['min_trades']}
- avg_rr >= {criteria['min_avg_rr']}

REQUIRED PARAMETERS TO OPTIMIZE:
- MACD: fast (8-15), slow (20-30), signal (7-12)
- RSI: period (10-20), oversold (25-35), overbought (65-75)
- SMC: ob_lookback_bars (10-30), fvg_min_size_pct (0.1-0.5), require_bos_confirm (bool), use_choch (bool)
- Exit: sl_method (ob_boundary or atr), sl_atr_mult (1.0-2.5), tp_rr_ratio (1.5-4.0)

OUTPUT: Return ONLY valid JSON matching this exact schema (no markdown, no explanation):
{{
  "symbol": "{symbol}",
  "timeframe": "15m",
  "indicators": {{"macd": {{"fast": N, "slow": N, "signal": N}}, "rsi": {{"period": N, "oversold": N, "overbought": N}}}},
  "smc": {{"ob_lookback_bars": N, "fvg_min_size_pct": F, "require_bos_confirm": bool, "use_choch": bool, "htf_confirmation": "1h"}},
  "entry": {{"long": [...], "short": [...]}},
  "exit": {{"sl_method": "...", "sl_atr_mult": F, "tp_rr_ratio": F, "trailing_stop": false}},
  "backtest": {{
    "period_months": N,
    "train_total_return_pct": F,
    "validation_total_return_pct": F,
    "total_trades": N,
    "total_return_pct": F,
    "win_rate": F,
    "profit_factor": F,
    "max_drawdown_pct": F,
    "avg_rr": F,
    "criteria_passed": true
  }}
}}
If no viable strategy found: {{"status": "no_strategy_found", "reason": "..."}}
"""
```

### Pattern 4: Strategy Filter as Pure Stateless Function

**What:** `filter.py` takes a strategy dict and a criteria dict, returns `FilterResult(passed: bool, failed_criteria: list[str], details: dict)`. No I/O, no exceptions for normal filter failures.

**When to use:** Called by Strategy Manager after every Claude response.

```python
# Source: FILT-01 through FILT-05 + idea.md section 5
from dataclasses import dataclass

@dataclass
class FilterResult:
    passed: bool
    failed_criteria: list[str]  # e.g. ["total_return_pct", "max_drawdown_pct"]
    details: dict  # actual vs required for each criterion

def filter_strategy(strategy_data: dict, criteria: dict, strict_mode: bool) -> FilterResult:
    backtest = strategy_data.get("backtest", {})
    checks = {
        "total_return_pct": backtest.get("total_return_pct", 0) >= criteria["min_total_return_pct"],
        "max_drawdown_pct": backtest.get("max_drawdown_pct", -999) >= criteria["max_drawdown_pct"],
        "win_rate": backtest.get("win_rate", 0) >= criteria["min_win_rate_pct"] / 100,
        "profit_factor": backtest.get("profit_factor", 0) >= criteria["min_profit_factor"],
        "total_trades": backtest.get("total_trades", 0) >= criteria["min_trades"],
        "avg_rr": backtest.get("avg_rr", 0) >= criteria["min_avg_rr"],
    }
    required = {"total_return_pct", "max_drawdown_pct"}  # always required
    if strict_mode:
        required = set(checks.keys())  # all required in strict mode

    failed = [k for k in required if not checks[k]]
    return FilterResult(passed=len(failed) == 0, failed_criteria=failed, details=checks)
```

### Pattern 5: Strategy Manager Expiry + Re-generation Flow

**What:** Two separate APScheduler jobs. Hourly scan job selects coins and generates strategies for coins in priority queue. Daily expiry job flags expired strategies and re-generates them.

```python
# Source: CONTEXT.md Locked Decisions — strategy expiry flow
async def strategy_manager_hourly(session_factory, claude_engine, ...):
    """Hourly: generate strategies for coins with no active strategy."""
    # Priority: no strategy > expired > skip active
    no_strategy, expired = await get_coins_needing_strategy(top_n_coins, session)
    candidates = no_strategy + expired  # process no_strategy first

    for symbol in candidates:
        try:
            ohlcv = await fetch_ohlcv(symbol, months=criteria.backtest_period_months)
            strategy = await claude_engine.generate_strategy(symbol, ohlcv, criteria)
            result = filter_strategy(strategy, criteria, strict_mode=criteria.strict_mode)
            if result.passed:
                await strategy_repo.save_strategy(session, symbol, strategy, criteria)
            else:
                await strategy_repo.log_skipped(session, symbol, strategy, result)
        except (ClaudeTimeoutError, ClaudeRateLimitError) as e:
            await notify_telegram_alert(f"Claude error for {symbol}: {e}")
            break  # stop processing; retry next cycle

async def expiry_checker_daily(session_factory, ...):
    """Daily: check for expired active strategies, trigger re-generation."""
    expired = await strategy_repo.get_expired_active_strategies(session)
    for strategy in expired:
        # Old strategy stays active until replacement succeeds
        try:
            new_strategy = await regenerate_strategy(strategy.symbol, ...)
            if new_strategy:
                await strategy_repo.replace_strategy(session, strategy, new_strategy)
            else:
                # Re-gen failed — deactivate old strategy per CONTEXT.md
                await strategy_repo.deactivate(session, strategy.id)
        except Exception:
            await strategy_repo.deactivate(session, strategy.id)
```

### Anti-Patterns to Avoid

- **Passing raw OHLCV JSON inline in the Claude prompt:** ~17,200 candles as JSON is roughly 3-5MB and millions of tokens. Always use the Files API.
- **Chaining retries as a multi-turn conversation:** Each retry attempt must be a fresh API call (new `messages=[]`). Accumulating failed attempts in one conversation exhausts context.
- **Running strategy generation inside the Market Scanner job:** These are two separate concerns. Scanner selects coins; Strategy Manager generates strategies. Combining them causes APScheduler `max_instances=1` to block hourly scans.
- **Hard-deleting old strategies:** Never. Always `is_active=False`. Required for LIFE-03 and audit trail.
- **Catching all exceptions from Claude without Telegram alert:** The user's fallback requirement is explicit: any Claude failure must notify Telegram so the trader knows.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OHLCV pagination from Binance | Custom pagination loop | `AsyncClient.futures_historical_klines()` with `HistoricalKlinesType.FUTURES` | Built-in batching with sleep between requests; handles >1000 candle limit automatically |
| OHLCV data delivery to Claude sandbox | Custom base64 encoding or chunking | Files API: `client.beta.files.upload()` + `container_upload` content block | Official pattern from Anthropic docs; files persist in sandbox for duration of call |
| Strategy JSON schema validation | `if "indicators" in response and "smc" in response...` | Pydantic model with `model_validate(data)` | Catches missing nested fields, wrong types, extra fields; generates actionable error messages |
| APScheduler cron setup | `scheduler.add_job(fn, 'interval', hours=1)` | `CronTrigger(hour='*', minute='5')` | CronTrigger fires at exact wall clock time (e.g., 12:05, 13:05); IntervalTrigger drifts based on last execution |
| Timeout on async Claude call | `asyncio.wait_for()` with manual cancellation | `asyncio.timeout(180)` context manager (Python 3.11+) | Cleaner, cancels the coroutine properly, re-raises as `asyncio.TimeoutError` |

**Key insight:** The Files API + code_execution sandbox is designed exactly for "send large data, get Python analysis back." Don't fight the token window with inline data.

---

## Common Pitfalls

### Pitfall 1: ANTHROPIC_API_KEY Missing from Settings

**What goes wrong:** `bot/config.py` `Settings` class does not include `anthropic_api_key`. Claude Engine cannot be instantiated. Bot starts silently without failing (field is optional unless you add it as required).

**Why it happens:** Phase 1 set up Binance and Telegram keys; Anthropic key was noted as a Phase 2 concern in CONTEXT.md.

**How to avoid:** Add `anthropic_api_key: SecretStr` to `Settings` as a required field. Add `ANTHROPIC_API_KEY=your_key_here` to `.env.example`. This triggers `sys.exit(1)` on startup if missing — correct behavior.

**Warning signs:** Claude Engine can be imported but throws `AttributeError: 'Settings' object has no attribute 'anthropic_api_key'` at first use.

---

### Pitfall 2: Files API Beta Header Required

**What goes wrong:** Uploading OHLCV CSV via `client.beta.files.upload()` without `betas=["files-api-2025-04-14"]` in the `messages.create()` call results in `400 Bad Request: container_upload block not recognized`.

**Why it happens:** The Files API is still under a beta header. The tool type `code_execution_20250825` does NOT require a beta header, but `container_upload` content blocks DO require `files-api-2025-04-14`.

**How to avoid:** Always pass `betas=["files-api-2025-04-14"]` in `client.beta.messages.create()` when using `container_upload`.

**Warning signs:** 400 errors on first attempt with `container_upload`; passing same request without `container_upload` works fine.

---

### Pitfall 3: Claude model string `claude-sonnet-4-20250514` is a real model ID

**What goes wrong:** The idea.md spec uses `claude-sonnet-4-20250514`. As of 2026-03-19, `code_execution_20250825` is confirmed compatible with `claude-sonnet-4-20250514`. Do not silently upgrade to `claude-sonnet-4-6` (the current flagship) without user confirmation — it may change strategy generation behavior.

**Why it happens:** Developers often use `latest` aliases or upgrade model IDs without realizing it.

**How to avoid:** Store the model ID in `Settings` as `claude_model: str = "claude-sonnet-4-20250514"`. Never hardcode. User can override via `.env`.

---

### Pitfall 4: Strategy Overfitting via Claude Optimization

**What goes wrong:** Claude optimizes indicator parameters against the full dataset, producing strategies with >65% winrate on backtest that immediately fail live. See PITFALLS.md Pitfall 2 in detail.

**Why it happens:** Without explicit walk-forward instructions in the prompt, Claude will find parameters that perfectly fit the training data.

**How to avoid:**
- Enforce 70/30 split explicitly in prompt (locked decision from CONTEXT.md)
- Require `validation_total_return_pct` field in the JSON output
- In `filter_strategy()`: check that `validation_total_return_pct >= train_total_return_pct * 0.6`
- Treat validation-set metrics as the authoritative filter inputs, not train-set metrics

**Warning signs:** All strategies passing filter show `win_rate > 0.65` and `profit_factor > 2.8`. This cluster indicates overfitting convergence.

---

### Pitfall 5: Candle Count Estimation and Minimum History Check

**What goes wrong:** The scanner assumes a coin has 6 months of 15m data, fetches OHLCV, and sends partial data (e.g., 2 months) to Claude. Claude generates a strategy on insufficient data, producing meaningless results.

**Why it happens:** Newer coins on Binance Futures don't have 6-month histories. `futures_historical_klines()` will return whatever is available without error.

**How to avoid:**
- 6 months of 15m candles = ~17,280 candles (6 * 30 * 24 * 4)
- After fetching OHLCV, check: `if len(df) < 15_000: skip_coin(symbol, "insufficient_history")`
- Log to `skipped_coins` with `reason="insufficient_history"`

**Warning signs:** Claude returns a strategy with `total_trades < 5` — insufficient data for meaningful statistics.

---

### Pitfall 6: Scanner Job Blocks Strategy Generation

**What goes wrong:** Hourly scan fetches tickers (fast), but then synchronously generates strategies for 3-4 coins (slow — each Claude call is up to 180s). Total job duration exceeds 1 hour. APScheduler's `max_instances=1` blocks the next scan trigger. After a few cycles, scanner stops running at all.

**Why it happens:** Scanner and Strategy Manager are combined into one APScheduler job.

**How to avoid:**
- Market Scanner job does ONLY coin selection and OHLCV history check — completes in <30s
- Strategy Manager job runs on a separate schedule (e.g., at :05 past each hour) and generates strategies
- Alternatively: Scanner triggers strategy generation as a background `asyncio.create_task()` that runs outside the scheduler job's execution window

---

### Pitfall 7: Empty Scan Loop Alerting Threshold Not Tracked

**What goes wrong:** All coins fail filter criteria for several cycles. Bot silently does nothing. Trader thinks bot is working but no strategies are being selected.

**Why it happens:** No counter tracks consecutive empty scan cycles.

**How to avoid:**
- Add `consecutive_empty_cycles: int` counter to a persistent state table (or in-memory with DB fallback)
- When counter reaches configurable threshold (default: 3), send Telegram alert with inline buttons
- Reset counter whenever at least one coin passes filter

---

## Code Examples

### Fetch Futures OHLCV with HistoricalKlinesType

```python
# Source: python-binance docs + GitHub issue #1202
from binance import AsyncClient, HistoricalKlinesType

async def fetch_ohlcv_15m(client: AsyncClient, symbol: str, months: int = 6) -> pd.DataFrame:
    """Fetch 15m OHLCV data from Binance USDT-M Futures."""
    start_str = f"{months} months ago UTC"
    klines = await client.futures_historical_klines(
        symbol=symbol,
        interval=AsyncClient.KLINE_INTERVAL_15MINUTE,
        start_str=start_str,
        klines_type=HistoricalKlinesType.FUTURES,
    )
    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df[["open_time", "open", "high", "low", "close", "volume"]]
```

### Upload CSV and Call Claude with code_execution

```python
# Source: Anthropic official docs (platform.claude.com/docs/en/docs/agents-and-tools/tool-use/code-execution-tool)
import anthropic
import asyncio

async def generate_strategy(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    criteria: dict,
    api_key: str,
    timeout: int = 180,
) -> dict:
    client = anthropic.AsyncAnthropic(api_key=api_key)
    csv_bytes = ohlcv_df.to_csv(index=False).encode("utf-8")

    file_obj = await client.beta.files.upload(
        file=("ohlcv.csv", csv_bytes, "text/csv"),
    )
    try:
        async with asyncio.timeout(timeout):
            response = await client.beta.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                betas=["files-api-2025-04-14"],
                tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "container_upload", "file_id": file_obj.id},
                        {"type": "text", "text": _build_prompt(symbol, criteria)},
                    ]
                }]
            )
    finally:
        await client.beta.files.delete(file_obj.id)

    return _parse_strategy_response(response)
```

### Parse Claude Response for Strategy JSON

```python
# Source: Anthropic response structure for code_execution tool
import json

def _parse_strategy_response(response) -> dict:
    """Extract JSON strategy from Claude response content blocks."""
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            # Remove markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            try:
                data = json.loads(text)
                # Validate against Pydantic schema
                return StrategySchema.model_validate(data).model_dump()
            except (json.JSONDecodeError, ValidationError) as e:
                raise StrategySchemaError(f"Invalid strategy JSON: {e}")
    raise StrategySchemaError("No text block found in Claude response")
```

### Pydantic Schema for strategy_data Validation

```python
# Source: idea.md section 6.2 — exact strategy_data JSON structure
from pydantic import BaseModel, field_validator

class MACDParams(BaseModel):
    fast: int
    slow: int
    signal: int

class RSIParams(BaseModel):
    period: int
    oversold: float
    overbought: float

class IndicatorParams(BaseModel):
    macd: MACDParams
    rsi: RSIParams

class SMCParams(BaseModel):
    ob_lookback_bars: int
    fvg_min_size_pct: float
    require_bos_confirm: bool
    use_choch: bool
    htf_confirmation: str

class EntryConditions(BaseModel):
    long: list[str]
    short: list[str]

class ExitRules(BaseModel):
    sl_method: str
    sl_atr_mult: float
    tp_rr_ratio: float
    trailing_stop: bool

class BacktestResults(BaseModel):
    period_months: int
    total_trades: int
    total_return_pct: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    avg_rr: float
    criteria_passed: bool
    # Optional walk-forward fields
    train_total_return_pct: float | None = None
    validation_total_return_pct: float | None = None

class StrategySchema(BaseModel):
    model_config = {"extra": "ignore"}  # ignore unknown fields from Claude
    symbol: str
    timeframe: str
    indicators: IndicatorParams
    smc: SMCParams
    entry: EntryConditions
    exit: ExitRules
    backtest: BacktestResults
```

### Fetch 24h Tickers and Rank by Volume

```python
# Source: python-binance docs — get_ticker returns all USDT-M pairs
async def get_top_n_by_volume(
    client: AsyncClient,
    whitelist: list[str],
    top_n: int,
    min_volume_usdt: float = 0,
) -> list[str]:
    """Return top-N symbols from whitelist ranked by 24h quoteVolume."""
    tickers = await client.futures_ticker()  # returns list of all USDT-M tickers
    volume_map = {t["symbol"]: float(t["quoteVolume"]) for t in tickers}

    ranked = sorted(
        [s for s in whitelist if s in volume_map],
        key=lambda s: volume_map[s],
        reverse=True,
    )
    filtered = [s for s in ranked if volume_map.get(s, 0) >= min_volume_usdt]
    return filtered[:top_n]
```

### Strategy Manager Save with Version Preservation

```python
# Source: LIFE-01 through LIFE-05 requirements + idea.md section 6.3
from datetime import datetime, timezone, timedelta

async def save_strategy(
    session,
    symbol: str,
    strategy_data: dict,
    criteria_snapshot: dict,
    review_interval_days: int = 30,
) -> Strategy:
    """Deactivate old strategy for symbol, insert new one as active."""
    # Deactivate all existing active strategies for this symbol (LIFE-03: never delete)
    await session.execute(
        sa.update(Strategy)
        .where(Strategy.symbol == symbol, Strategy.is_active == True)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )

    backtest_score = (
        strategy_data["backtest"]["profit_factor"]
        * strategy_data["backtest"]["win_rate"]
    )
    new_strategy = Strategy(
        symbol=symbol,
        timeframe=strategy_data["timeframe"],
        strategy_data=strategy_data,
        backtest_score=backtest_score,
        is_active=True,
        next_review_at=datetime.now(timezone.utc) + timedelta(days=review_interval_days),
        review_interval_days=review_interval_days,
        source="claude_generated",
        criteria_snapshot=criteria_snapshot,  # LIFE-05
    )
    session.add(new_strategy)
    await session.commit()
    return new_strategy
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline OHLCV data in Claude prompt | Files API (`files-api-2025-04-14`) + `container_upload` | 2025-04 | Eliminates token cost for data; enables large datasets |
| `code_execution_20250522` (Python only) | `code_execution_20250825` (Bash + file ops) | 2025-08-25 | Current version; no beta header needed; supports file creation |
| `claude-3-5-sonnet` model string | `claude-sonnet-4-20250514` | 2025 | Spec-mandated model; confirmed compatible with `code_execution_20250825` |
| Manual OHLCV pagination | `futures_historical_klines()` with `HistoricalKlinesType.FUTURES` | 2022+ | python-binance handles pagination + rate limit sleeps automatically |

**Deprecated/outdated:**
- `code_execution_20250522`: Legacy tool version (Python only). Use `code_execution_20250825`. Not backwards-compatible with all newer models.
- Inline OHLCV as JSON/CSV in prompt text: Works but wastes tokens. Files API is the documented replacement.

---

## Open Questions

1. **Whitelist storage location**
   - What we know: CONTEXT.md says "stored in DB/config"; `Settings` currently uses `.env` for criteria defaults
   - What's unclear: Should the whitelist be a new DB table, a JSONB field on `StrategyCriteria`, or a comma-separated env var?
   - Recommendation: Add `coin_whitelist: list[str]` to `Settings` (env var `COIN_WHITELIST=BTCUSDT,ETHUSDT,...`); overridable at runtime via a new `CoinWhitelist` DB table that takes precedence over env if populated. This defers the DB table to Phase 4 (Telegram commands) without blocking Phase 2.

2. **Consecutive empty cycles counter persistence**
   - What we know: Alert after N consecutive empty scan cycles; N is configurable
   - What's unclear: Where to persist this counter — in-memory (lost on restart) or DB?
   - Recommendation: Add `consecutive_empty_cycles: int` to a `ScanState` table (single row). Simple and survives restarts without adding complexity.

3. **Claude response content block type for code_execution results**
   - What we know: Response contains `text` blocks and `tool_result` blocks; JSON strategy must come from a `text` block
   - What's unclear: Claude may print the JSON inside the code execution output (stdout), not in a text block after code_execution
   - Recommendation: In `_parse_strategy_response()`, check both `text` blocks AND `tool_result` → `bash_code_execution_result` stdout. Budget 2-3 prompt engineering iterations to confirm where Claude writes the final JSON.

4. **`anthropic_api_key` in Settings**
   - What we know: Field is missing from `bot/config.py` (confirmed by code review)
   - What's unclear: Whether the .env already has `ANTHROPIC_API_KEY` set (not in the .env.example either)
   - Recommendation: Wave 0 task — add `anthropic_api_key: SecretStr` to `Settings` and `ANTHROPIC_API_KEY=your_key_here` to `.env.example`

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24+ |
| Config file | `pytest.ini` (check for existing) |
| Quick run command | `pytest tests/test_scanner.py tests/test_strategy_filter.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCAN-01 | Scanner returns top-N from whitelist ranked by volume | unit | `pytest tests/test_scanner.py::test_top_n_by_volume -x` | ❌ Wave 0 |
| SCAN-02 | Scanner job registered with APScheduler | unit | `pytest tests/test_scanner.py::test_scheduler_job_registered -x` | ❌ Wave 0 |
| SCAN-03 | Scanner excludes coins below volume threshold | unit | `pytest tests/test_scanner.py::test_volume_filter -x` | ❌ Wave 0 |
| SCAN-04 | Top-N count respects configurable setting | unit | `pytest tests/test_scanner.py::test_top_n_configurable -x` | ❌ Wave 0 |
| STRAT-01 | Claude engine constructs correct API request | unit (mock) | `pytest tests/test_claude_engine.py::test_request_structure -x` | ❌ Wave 0 |
| STRAT-02 | Strategy JSON validated against Pydantic schema | unit | `pytest tests/test_claude_engine.py::test_strategy_schema_validation -x` | ❌ Wave 0 |
| STRAT-03 | OHLCV fetch returns correct columns and types | unit (mock) | `pytest tests/test_scanner.py::test_ohlcv_fetch_format -x` | ❌ Wave 0 |
| STRAT-04 | Walk-forward split: prompt includes 70/30 instructions | unit | `pytest tests/test_claude_engine.py::test_prompt_contains_walk_forward -x` | ❌ Wave 0 |
| STRAT-05 | Strategy Manager skips Claude if active strategy exists | unit (mock DB) | `pytest tests/test_strategy_manager.py::test_skip_if_active -x` | ❌ Wave 0 |
| FILT-01 | Filter checks all six criteria fields | unit | `pytest tests/test_strategy_filter.py::test_all_criteria_checked -x` | ❌ Wave 0 |
| FILT-02 | Default criteria values match spec | unit | `pytest tests/test_strategy_filter.py::test_default_criteria -x` | ❌ Wave 0 |
| FILT-03 | Relaxed mode: only return + drawdown required | unit | `pytest tests/test_strategy_filter.py::test_relaxed_mode -x` | ❌ Wave 0 |
| FILT-04 | Failed strategies logged to skipped_coins | unit (mock DB) | `pytest tests/test_strategy_manager.py::test_failed_strategy_logged -x` | ❌ Wave 0 |
| FILT-05 | criteria snapshot saved on filter pass | unit (mock DB) | `pytest tests/test_strategy_manager.py::test_criteria_snapshot_saved -x` | ❌ Wave 0 |
| LIFE-01 | Strategy saved with all required fields | unit (mock DB) | `pytest tests/test_strategy_manager.py::test_strategy_fields_saved -x` | ❌ Wave 0 |
| LIFE-02 | Expired strategies detected by expiry checker | unit | `pytest tests/test_strategy_manager.py::test_expiry_detection -x` | ❌ Wave 0 |
| LIFE-03 | Old strategies marked inactive, not deleted | unit (mock DB) | `pytest tests/test_strategy_manager.py::test_old_strategy_deactivated -x` | ❌ Wave 0 |
| LIFE-04 | review_interval_days stored on strategy insert | unit | `pytest tests/test_strategy_manager.py::test_review_interval_stored -x` | ❌ Wave 0 |
| LIFE-05 | criteria_snapshot stored on strategy insert | unit | `pytest tests/test_strategy_manager.py::test_criteria_snapshot_stored -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_strategy_filter.py tests/test_scanner.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_scanner.py` — covers SCAN-01 through SCAN-04, STRAT-03
- [ ] `tests/test_claude_engine.py` — covers STRAT-01, STRAT-02, STRAT-04
- [ ] `tests/test_strategy_filter.py` — covers FILT-01, FILT-02, FILT-03
- [ ] `tests/test_strategy_manager.py` — covers STRAT-05, FILT-04, FILT-05, LIFE-01 through LIFE-05

All four test files are new; existing test infrastructure (`conftest.py`, `pytest.ini`) is sufficient — no framework changes needed.

---

## Sources

### Primary (HIGH confidence)

- `platform.claude.com/docs/en/docs/agents-and-tools/tool-use/code-execution-tool` — Tool version `code_execution_20250825`, Files API integration, container resource limits, pre-installed packages (fetched 2026-03-19)
- `bot/config.py`, `bot/db/models.py`, `bot/exchange/client.py` — Existing codebase (direct read)
- `.planning/phases/02-strategy-pipeline/02-CONTEXT.md` — Locked user decisions
- `idea.md` sections 4, 5, 6 — Canonical spec: prompt structure, criteria table, strategy_data JSON schema

### Secondary (MEDIUM confidence)

- python-binance readthedocs + GitHub issues #1202, #911 — `futures_historical_klines()` with `HistoricalKlinesType.FUTURES` confirmed working; `get_ticker()` for 24h volume
- `.planning/research/PITFALLS.md` — Pitfall 2 (strategy overfitting) and Pitfall 8 (APScheduler job drift) — research from project init

### Tertiary (LOW confidence)

- WebSearch results on python-binance klines — Community examples, not verified against current 1.0.35 changelog; treat as pattern references only

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages from Phase 1 research, code_execution tool version verified from official docs
- Architecture: HIGH — patterns derived directly from spec, CONTEXT.md decisions, and existing code structure
- Claude Engine specifics: HIGH for tool version and Files API; MEDIUM for exact JSON output parsing (requires prompt engineering iteration per STATE.md blocker note)
- Pitfalls: HIGH — overfitting from PITFALLS.md; APScheduler drift from PITFALLS.md; others from code analysis

**Research date:** 2026-03-19
**Valid until:** 2026-04-19 (30 days — anthropic SDK and python-binance move fast but breaking changes are unlikely within this window)
