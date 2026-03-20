"""Claude Strategy Engine — generates SMC+MACD/RSI strategies via code_execution tool."""
from __future__ import annotations

import asyncio
import json
from typing import Optional

import anthropic
from loguru import logger
from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# Custom exceptions — allow Strategy Manager to route errors precisely
# ---------------------------------------------------------------------------

class ClaudeTimeoutError(Exception):
    """Claude API call exceeded the configured timeout."""

class ClaudeRateLimitError(Exception):
    """Claude API returned a rate limit error."""

class StrategySchemaError(Exception):
    """Claude response could not be parsed or validated against StrategySchema."""


# ---------------------------------------------------------------------------
# Pydantic schema — mirrors idea.md section 6.2 exactly
# ---------------------------------------------------------------------------

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
    train_total_return_pct: Optional[float] = None
    validation_total_return_pct: Optional[float] = None

class StrategySchema(BaseModel):
    model_config = {"extra": "ignore"}

    symbol: str
    timeframe: str
    indicators: IndicatorParams
    smc: SMCParams
    entry: EntryConditions
    exit: ExitRules
    backtest: BacktestResults


# ---------------------------------------------------------------------------
# Prompt builder — Claude fetches data himself via code_execution
# ---------------------------------------------------------------------------

def _build_prompt(symbol: str, criteria: dict) -> str:
    """Build the Claude strategy generation prompt.

    Claude uses code_execution to fetch OHLCV data from Binance directly
    and run backtesting — no CSV upload needed.
    """
    period_months = criteria.get('backtest_period_months', 6)
    return f"""TASK: Find optimal SMC + MACD/RSI trading strategy for {symbol} (Binance USDT-M Perpetual Futures, 15m timeframe).

STEP 1 — FETCH DATA:
Use code_execution to fetch {period_months} months of 15m OHLCV data for {symbol} from Binance public API.
Use this Python code to fetch data:

```python
import requests
import pandas as pd
from datetime import datetime, timedelta

symbol = "{symbol}"
interval = "15m"
end_time = int(datetime.utcnow().timestamp() * 1000)
start_time = int((datetime.utcnow() - timedelta(days={period_months * 30})).timestamp() * 1000)

all_klines = []
current_start = start_time
while current_start < end_time:
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={{symbol}}&interval={{interval}}&startTime={{current_start}}&limit=1500"
    resp = requests.get(url)
    data = resp.json()
    if not data:
        break
    all_klines.extend(data)
    current_start = data[-1][6] + 1  # close_time + 1ms

df = pd.DataFrame(all_klines, columns=[
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
])
df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
for col in ["open", "high", "low", "close", "volume"]:
    df[col] = df[col].astype(float)
print(f"Fetched {{len(df)}} candles for {{symbol}}")
```

STEP 2 — BACKTEST WITH WALK-FORWARD VALIDATION:
1. Split data: train = first 70%, validation = last 30%
2. Optimize ALL parameters on TRAIN set only — no lookahead into validation
3. Evaluate final strategy on VALIDATION set without re-fitting
4. REJECT strategy if validation total_return < train total_return * 0.6
5. Use VALIDATION set metrics as the authoritative backtest result

BACKTEST CRITERIA (must pass on VALIDATION set):
- total_return_pct >= {criteria.get('min_total_return_pct', 200.0)}%
- max_drawdown_pct >= {criteria.get('max_drawdown_pct', -12.0)}%  (e.g., -12 means drawdown must be no worse than -12%)
- win_rate >= {criteria.get('min_win_rate_pct', 55.0) / 100}  (as decimal fraction)
- profit_factor >= {criteria.get('min_profit_factor', 1.8)}
- total_trades >= {criteria.get('min_trades', 30)}
- avg_rr >= {criteria.get('min_avg_rr', 2.0)}

PARAMETERS TO OPTIMIZE:
- MACD: fast (8-15), slow (20-30), signal (7-12)
- RSI: period (10-20), oversold (25-35), overbought (65-75)
- SMC: ob_lookback_bars (10-30), fvg_min_size_pct (0.1-0.5), require_bos_confirm (bool), use_choch (bool)
- Exit: sl_method ("ob_boundary" or "atr"), sl_atr_mult (1.0-2.5), tp_rr_ratio (1.5-4.0)

SMC ENTRY LOGIC:
- Long: price retraces into demand Order Block, RSI oversold exit, MACD bullish crossover
- Short: price retraces into supply Order Block, RSI overbought exit, MACD bearish crossover

STEP 3 — OUTPUT:
After backtesting, print ONLY valid JSON matching this exact schema (no markdown, no explanation, no code fences):
{{
  "symbol": "{symbol}",
  "timeframe": "15m",
  "indicators": {{"macd": {{"fast": N, "slow": N, "signal": N}}, "rsi": {{"period": N, "oversold": N, "overbought": N}}}},
  "smc": {{"ob_lookback_bars": N, "fvg_min_size_pct": F, "require_bos_confirm": true/false, "use_choch": true/false, "htf_confirmation": "1h"}},
  "entry": {{"long": ["condition1", "condition2"], "short": ["condition1", "condition2"]}},
  "exit": {{"sl_method": "ob_boundary", "sl_atr_mult": F, "tp_rr_ratio": F, "trailing_stop": false}},
  "backtest": {{
    "period_months": {period_months},
    "total_trades": N,
    "total_return_pct": F,
    "win_rate": F,
    "profit_factor": F,
    "max_drawdown_pct": F,
    "avg_rr": F,
    "criteria_passed": true/false,
    "train_total_return_pct": F,
    "validation_total_return_pct": F
  }}
}}
If no viable strategy exists after optimization: {{"status": "no_strategy_found", "reason": "..."}}"""


# ---------------------------------------------------------------------------
# Response parser — handles text blocks and code execution output
# ---------------------------------------------------------------------------

def _parse_strategy_response(response) -> dict:
    """Extract and validate strategy JSON from Claude response content blocks."""
    candidates: list[str] = []

    for block in response.content:
        if hasattr(block, "type"):
            if block.type == "text":
                candidates.append(block.text.strip())
            elif block.type == "tool_result":
                if hasattr(block, "content"):
                    for inner in (block.content if isinstance(block.content, list) else [block.content]):
                        if hasattr(inner, "text"):
                            candidates.append(inner.text.strip())
            elif block.type == "code_execution_tool_result":
                if hasattr(block, "content"):
                    for inner in (block.content if isinstance(block.content, list) else [block.content]):
                        if hasattr(inner, "text"):
                            candidates.append(inner.text.strip())

    for raw in candidates:
        text = raw
        # Strip markdown fences
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
        # Try to find JSON in the text (might be surrounded by other output)
        for start_char in ['{']:
            idx = text.find(start_char)
            if idx >= 0:
                # Find matching closing brace
                depth = 0
                for i in range(idx, len(text)):
                    if text[i] == '{':
                        depth += 1
                    elif text[i] == '}':
                        depth -= 1
                        if depth == 0:
                            json_str = text[idx:i+1]
                            try:
                                data = json.loads(json_str)
                                if "no_strategy_found" in str(data.get("status", "")):
                                    raise StrategySchemaError(f"Claude found no viable strategy: {json_str[:200]}")
                                validated = StrategySchema.model_validate(data)
                                return validated.model_dump()
                            except (json.JSONDecodeError, ValidationError):
                                pass
                            break

    raise StrategySchemaError("No parseable strategy JSON found in Claude response")


# ---------------------------------------------------------------------------
# Main entry point — called by Strategy Manager
# ---------------------------------------------------------------------------

async def generate_strategy(
    symbol: str,
    ohlcv_df,  # kept for API compatibility but not used — Claude fetches data himself
    criteria: dict,
    api_key: str,
    timeout: int = 480,
) -> dict:
    """Generate a backtested SMC+MACD/RSI strategy for the given symbol via Claude.

    Claude fetches OHLCV data himself via code_execution and runs backtesting.
    No CSV upload needed — keeps prompt small and avoids context window limits.

    Raises:
        ClaudeTimeoutError: Claude call exceeded `timeout` seconds
        ClaudeRateLimitError: Anthropic API returned 429
        StrategySchemaError: Response could not be parsed or validated (after 1 retry)
    """
    # Set HTTP-level timeout on the Anthropic client itself.
    # Do NOT use asyncio.timeout — it kills the HTTP connection mid-stream,
    # causing Claude to see "Client disconnected" (499).
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        timeout=float(timeout),
    )
    prompt = _build_prompt(symbol, criteria)

    logger.info(f"Calling Claude for {symbol} (Claude will fetch data himself, timeout={timeout}s)")

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            tools=[{"type": "code_execution_20250522", "name": "code_execution"}],
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
    except anthropic.APITimeoutError:
        raise ClaudeTimeoutError(
            f"Claude strategy generation timed out after {timeout}s for {symbol}"
        )
    except anthropic.RateLimitError as e:
        raise ClaudeRateLimitError(f"Claude rate limit hit for {symbol}: {e}")

    # First parse attempt
    try:
        result = _parse_strategy_response(response)
        logger.info(f"Strategy generated for {symbol}: {result.get('backtest', {}).get('total_return_pct', '?')}% return")
        return result
    except StrategySchemaError as first_err:
        logger.warning(f"First parse attempt failed for {symbol}: {first_err}. Retrying once.")

    # Single retry — fresh API call
    logger.info(f"Retry: calling Claude again for {symbol}")
    try:
        response_retry = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            tools=[{"type": "code_execution_20250522", "name": "code_execution"}],
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
    except anthropic.APITimeoutError:
        raise ClaudeTimeoutError(
            f"Claude retry timed out after {timeout}s for {symbol}"
        )
    except anthropic.RateLimitError as e:
        raise ClaudeRateLimitError(f"Claude retry rate limit for {symbol}: {e}")

    return _parse_strategy_response(response_retry)
