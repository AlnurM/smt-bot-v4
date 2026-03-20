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
# Prompt builder — walk-forward instructions per CONTEXT.md locked decisions
# ---------------------------------------------------------------------------

def _build_prompt(symbol: str, criteria: dict) -> str:
    """Build the Claude strategy generation prompt.

    Includes WALK-FORWARD VALIDATION instructions (70/30 train/validation split).
    All 6 filter criteria thresholds are embedded so Claude targets them directly.
    """
    return f"""The file ohlcv.csv contains 15m OHLCV data for {symbol}.
Columns: timestamp, open, high, low, close, volume

TASK: Find optimal SMC + MACD/RSI strategy parameters for {symbol}.

WALK-FORWARD VALIDATION REQUIRED:
1. Split data: train = first 70%, validation = last 30%
2. Optimize ALL parameters on TRAIN set only — no lookahead into validation
3. Evaluate final strategy on VALIDATION set without re-fitting
4. REJECT strategy if validation total_return < train total_return * 0.6
   (validation performance may not drop more than 40% relative to train)
5. Use VALIDATION set metrics as the authoritative backtest result

BACKTEST CRITERIA (must pass on VALIDATION set):
- total_return_pct >= {criteria.get('min_total_return_pct', 200.0)}%
- max_drawdown_pct >= {criteria.get('max_drawdown_pct', -12.0)}%  (e.g., -12 means drawdown must be greater than -12%)
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
- Long: price retraces into demand Order Block, RSI oversold exit, MACD bullish crossover, BOS/CHOCH above current price
- Short: price retraces into supply Order Block, RSI overbought exit, MACD bearish crossover, BOS/CHOCH below current price

OUTPUT: Return ONLY valid JSON matching this exact schema (no markdown, no explanation, no code fences):
{{
  "symbol": "{symbol}",
  "timeframe": "15m",
  "indicators": {{"macd": {{"fast": N, "slow": N, "signal": N}}, "rsi": {{"period": N, "oversold": N, "overbought": N}}}},
  "smc": {{"ob_lookback_bars": N, "fvg_min_size_pct": F, "require_bos_confirm": true/false, "use_choch": true/false, "htf_confirmation": "1h"}},
  "entry": {{"long": ["condition1", "condition2"], "short": ["condition1", "condition2"]}},
  "exit": {{"sl_method": "ob_boundary", "sl_atr_mult": F, "tp_rr_ratio": F, "trailing_stop": false}},
  "backtest": {{
    "period_months": {criteria.get('backtest_period_months', 6)},
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
    """Extract and validate strategy JSON from Claude response content blocks.

    Checks text blocks first, then tool_result blocks (Claude may print JSON in stdout).
    Strips markdown code fences if present.
    Raises StrategySchemaError on any parse or validation failure.
    """
    candidates: list[str] = []

    for block in response.content:
        if hasattr(block, "type"):
            if block.type == "text":
                candidates.append(block.text.strip())
            elif block.type == "tool_result":
                # code_execution output may appear here
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
        # Check for no_strategy_found signal
        if '"no_strategy_found"' in text or "'no_strategy_found'" in text:
            raise StrategySchemaError(f"Claude found no viable strategy: {text[:200]}")
        try:
            data = json.loads(text)
            validated = StrategySchema.model_validate(data)
            return validated.model_dump()
        except (json.JSONDecodeError, ValidationError):
            continue  # try next candidate block

    raise StrategySchemaError("No parseable strategy JSON found in Claude response")


# ---------------------------------------------------------------------------
# Main entry point — called by Strategy Manager
# ---------------------------------------------------------------------------

async def generate_strategy(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    criteria: dict,
    api_key: str,
    timeout: int = 480,
) -> dict:
    """Generate a backtested SMC+MACD/RSI strategy for the given symbol via Claude.

    Uses Files API to deliver OHLCV CSV to Claude's code_execution sandbox.
    Retries schema parsing once on failure before raising StrategySchemaError.

    Raises:
        ClaudeTimeoutError: Claude call exceeded `timeout` seconds
        ClaudeRateLimitError: Anthropic API returned 429
        StrategySchemaError: Response could not be parsed or validated (after 1 retry)
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)
    csv_text = ohlcv_df.to_csv(index=False)
    prompt = _build_prompt(symbol, criteria)

    # Embed CSV directly in the prompt — simpler and more reliable than Files API
    full_prompt = f"{prompt}\n\nOHLCV DATA (CSV format, {len(ohlcv_df)} rows):\n\n{csv_text}"

    logger.info(f"Calling Claude for {symbol} ({len(ohlcv_df)} rows, {len(csv_text)//1024}KB CSV)")

    try:
        async with asyncio.timeout(timeout):
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                tools=[{"type": "code_execution_20250522", "name": "code_execution"}],
                messages=[
                    {
                        "role": "user",
                        "content": full_prompt,
                    }
                ],
            )
    except asyncio.TimeoutError:
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

    # Single retry — fresh API call (per RESEARCH.md anti-pattern: no multi-turn retry)
    logger.info(f"Retry: calling Claude again for {symbol}")
    try:
        async with asyncio.timeout(timeout):
            response_retry = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                tools=[{"type": "code_execution_20250522", "name": "code_execution"}],
                messages=[
                    {
                        "role": "user",
                        "content": full_prompt,
                    }
                ],
            )
    except asyncio.TimeoutError:
        raise ClaudeTimeoutError(
            f"Claude retry timed out after {timeout}s for {symbol}"
        )
    except Exception as cleanup_err:
            logger.warning(f"Failed to delete retry file {file_id_retry}: {cleanup_err}")

    return _parse_strategy_response(response_retry)
