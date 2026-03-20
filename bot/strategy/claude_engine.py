"""Claude Strategy Engine — generates SMC+MACD/RSI strategies via code_execution tool."""
from __future__ import annotations

import asyncio
import json
from typing import Optional

import anthropic
import pandas as pd
from loguru import logger
from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ClaudeTimeoutError(Exception):
    """Claude API call exceeded the configured timeout."""

class ClaudeRateLimitError(Exception):
    """Claude API returned a rate limit error."""

class StrategySchemaError(Exception):
    """Claude response could not be parsed or validated against StrategySchema."""


# ---------------------------------------------------------------------------
# Pydantic schema — mirrors idea.md section 6.2
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
# Prompt builder — CSV data embedded in prompt
# ---------------------------------------------------------------------------

def _build_prompt(symbol: str, criteria: dict, row_count: int) -> str:
    """Build strategy generation prompt. CSV data is appended separately."""
    return f"""You have REAL 15m OHLCV data for {symbol} (Binance USDT-M Perpetual Futures).
The data is provided below as CSV ({row_count} rows). Use it directly — do NOT generate synthetic data.

TASK: Find optimal SMC + MACD/RSI strategy parameters using code_execution.

WALK-FORWARD VALIDATION:
1. Split the CSV data: train = first 70%, validation = last 30%
2. Optimize on TRAIN only
3. Evaluate on VALIDATION without re-fitting
4. REJECT if validation return < train return * 0.6

BACKTEST CRITERIA (validation set):
- total_return_pct >= {criteria.get('min_total_return_pct', 200.0)}%
- max_drawdown_pct >= {criteria.get('max_drawdown_pct', -12.0)}%
- win_rate >= {criteria.get('min_win_rate_pct', 55.0) / 100}
- profit_factor >= {criteria.get('min_profit_factor', 1.8)}
- total_trades >= {criteria.get('min_trades', 30)}
- avg_rr >= {criteria.get('min_avg_rr', 2.0)}

PARAMETERS TO OPTIMIZE:
- MACD: fast (8-15), slow (20-30), signal (7-12)
- RSI: period (10-20), oversold (25-35), overbought (65-75)
- SMC: ob_lookback_bars (10-30), fvg_min_size_pct (0.1-0.5)
- Exit: sl_atr_mult (1.0-2.5), tp_rr_ratio (1.5-4.0)

Test 3-5 parameter combos (not exhaustive grid search). Pick the best.

OUTPUT: After backtesting, print ONLY valid JSON (no markdown, no explanation):
{{
  "symbol": "{symbol}",
  "timeframe": "15m",
  "indicators": {{"macd": {{"fast": N, "slow": N, "signal": N}}, "rsi": {{"period": N, "oversold": N, "overbought": N}}}},
  "smc": {{"ob_lookback_bars": N, "fvg_min_size_pct": F, "require_bos_confirm": true, "use_choch": true, "htf_confirmation": "1h"}},
  "entry": {{"long": ["cond1", "cond2"], "short": ["cond1", "cond2"]}},
  "exit": {{"sl_method": "atr", "sl_atr_mult": F, "tp_rr_ratio": F, "trailing_stop": false}},
  "backtest": {{
    "period_months": 3,
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
If no viable strategy: {{"status": "no_strategy_found", "reason": "..."}}"""


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_strategy_response(response) -> dict:
    """Extract and validate strategy JSON from Claude response."""
    candidates: list[str] = []

    for block in response.content:
        if hasattr(block, "type"):
            if block.type == "text":
                candidates.append(block.text.strip())
            elif block.type in ("tool_result", "code_execution_tool_result"):
                if hasattr(block, "content"):
                    for inner in (block.content if isinstance(block.content, list) else [block.content]):
                        if hasattr(inner, "text"):
                            candidates.append(inner.text.strip())

    for raw in candidates:
        text = raw
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

        # Find JSON object with "symbol" key
        idx = text.find('{"symbol"')
        if idx < 0:
            idx = text.find('{')
        if idx >= 0:
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
                                raise StrategySchemaError(f"No viable strategy: {json_str[:200]}")
                            validated = StrategySchema.model_validate(data)
                            return validated.model_dump()
                        except (json.JSONDecodeError, ValidationError):
                            pass
                        break

    raise StrategySchemaError("No parseable strategy JSON found in Claude response")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Max rows to send to Claude — 3000 rows ≈ 3 weeks of 15m data ≈ 40k tokens
MAX_OHLCV_ROWS = 3000


async def generate_strategy(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    criteria: dict,
    api_key: str,
    timeout: int = 480,
) -> dict:
    """Generate a backtested SMC+MACD/RSI strategy via Claude code_execution.

    Sends real OHLCV data as CSV in the prompt (truncated to MAX_OHLCV_ROWS).
    Uses Anthropic client-level timeout (not asyncio.timeout) to avoid killing
    the HTTP connection during long code_execution runs.
    """
    # Truncate to fit context window (~40k tokens for 3000 rows)
    if len(ohlcv_df) > MAX_OHLCV_ROWS:
        logger.info(
            f"Truncating OHLCV for {symbol}: {len(ohlcv_df)} → {MAX_OHLCV_ROWS} rows (last {MAX_OHLCV_ROWS})"
        )
        ohlcv_df = ohlcv_df.tail(MAX_OHLCV_ROWS).reset_index(drop=True)

    csv_text = ohlcv_df.to_csv(index=False)
    prompt = _build_prompt(symbol, criteria, len(ohlcv_df))
    full_prompt = f"{prompt}\n\nOHLCV DATA (CSV, {len(ohlcv_df)} rows):\n\n{csv_text}"

    # Client-level HTTP timeout — does NOT kill connection mid-stream
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=float(timeout))

    logger.info(f"Calling Claude for {symbol} ({len(ohlcv_df)} rows, {len(csv_text)//1024}KB, timeout={timeout}s)")

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            tools=[{"type": "code_execution_20250522", "name": "code_execution"}],
            messages=[{"role": "user", "content": full_prompt}],
        )
    except anthropic.APITimeoutError:
        raise ClaudeTimeoutError(f"Claude timed out after {timeout}s for {symbol}")
    except anthropic.RateLimitError as e:
        raise ClaudeRateLimitError(f"Claude rate limit for {symbol}: {e}")

    logger.info(f"Claude response for {symbol}: tokens in={response.usage.input_tokens} out={response.usage.output_tokens}")

    # First parse attempt
    try:
        result = _parse_strategy_response(response)
        logger.info(f"Strategy for {symbol}: return={result['backtest']['total_return_pct']}%, wr={result['backtest']['win_rate']}, passed={result['backtest']['criteria_passed']}")
        return result
    except StrategySchemaError as first_err:
        logger.warning(f"Parse failed for {symbol}: {first_err}. Retrying once.")

    # Single retry
    try:
        response_retry = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            tools=[{"type": "code_execution_20250522", "name": "code_execution"}],
            messages=[{"role": "user", "content": full_prompt}],
        )
    except anthropic.APITimeoutError:
        raise ClaudeTimeoutError(f"Claude retry timed out for {symbol}")
    except anthropic.RateLimitError as e:
        raise ClaudeRateLimitError(f"Claude retry rate limit for {symbol}: {e}")

    return _parse_strategy_response(response_retry)
