import pytest
from unittest.mock import AsyncMock, patch, MagicMock

pytest.importorskip("bot.strategy.claude_engine", reason="Wave 0: module not yet built")
from bot.strategy.claude_engine import _build_prompt, StrategySchema, ClaudeTimeoutError, StrategySchemaError


def test_prompt_contains_walk_forward(sample_criteria):
    """STRAT-04: Prompt instructs Claude to use 70/30 train/validation split."""
    prompt = _build_prompt("BTCUSDT", sample_criteria)
    assert "70" in prompt
    assert "30" in prompt
    assert "validation" in prompt.lower()
    assert "train" in prompt.lower()
    assert "WALK-FORWARD" in prompt.upper() or "walk-forward" in prompt.lower()


def test_strategy_schema_validation():
    """STRAT-02: StrategySchema accepts a valid strategy dict and rejects a malformed one."""
    valid = {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "indicators": {"macd": {"fast": 12, "slow": 26, "signal": 9}, "rsi": {"period": 14, "oversold": 30, "overbought": 70}},
        "smc": {"ob_lookback_bars": 20, "fvg_min_size_pct": 0.3, "require_bos_confirm": True, "use_choch": True, "htf_confirmation": "1h"},
        "entry": {"long": ["price > ob_low"], "short": ["price < ob_high"]},
        "exit": {"sl_method": "ob_boundary", "sl_atr_mult": 1.5, "tp_rr_ratio": 3.0, "trailing_stop": False},
        "backtest": {
            "period_months": 6, "total_trades": 45, "total_return_pct": 215.0,
            "win_rate": 0.58, "profit_factor": 2.1, "max_drawdown_pct": -9.5, "avg_rr": 2.3,
            "criteria_passed": True,
        },
    }
    schema = StrategySchema.model_validate(valid)
    assert schema.symbol == "BTCUSDT"
    assert schema.backtest.total_trades == 45

    # Malformed: missing required 'backtest' key
    import pydantic
    with pytest.raises((pydantic.ValidationError, Exception)):
        StrategySchema.model_validate({"symbol": "BTCUSDT"})


@pytest.mark.asyncio
async def test_request_structure(test_settings):
    """STRAT-01: generate_strategy makes a beta.messages.create call with correct model, tool type, and beta header."""
    pytest.importorskip("bot.strategy.claude_engine", reason="Wave 0")
    from bot.strategy.claude_engine import generate_strategy
    import pandas as pd
    import numpy as np
    df = pd.DataFrame({
        "open_time": pd.date_range("2024-01-01", periods=5, freq="15min"),
        "open": [100.0]*5, "high": [105.0]*5, "low": [95.0]*5,
        "close": [102.0]*5, "volume": [1000.0]*5,
    })
    mock_client_instance = AsyncMock()
    # files.upload and files.delete
    mock_file = MagicMock()
    mock_file.id = "file_abc123"
    mock_client_instance.beta = AsyncMock()
    mock_client_instance.beta.files = AsyncMock()
    mock_client_instance.beta.files.upload = AsyncMock(return_value=mock_file)
    mock_client_instance.beta.files.delete = AsyncMock()
    # messages.create returns a fake response with a text block containing valid JSON
    import json
    valid_strategy_json = json.dumps({
        "symbol": "BTCUSDT", "timeframe": "15m",
        "indicators": {"macd": {"fast": 12, "slow": 26, "signal": 9}, "rsi": {"period": 14, "oversold": 30, "overbought": 70}},
        "smc": {"ob_lookback_bars": 20, "fvg_min_size_pct": 0.3, "require_bos_confirm": True, "use_choch": True, "htf_confirmation": "1h"},
        "entry": {"long": ["ob"], "short": ["ob"]},
        "exit": {"sl_method": "ob_boundary", "sl_atr_mult": 1.5, "tp_rr_ratio": 3.0, "trailing_stop": False},
        "backtest": {"period_months": 6, "total_trades": 45, "total_return_pct": 215.0,
                     "win_rate": 0.58, "profit_factor": 2.1, "max_drawdown_pct": -9.5, "avg_rr": 2.3,
                     "criteria_passed": True},
    })
    fake_text_block = MagicMock()
    fake_text_block.type = "text"
    fake_text_block.text = valid_strategy_json
    fake_response = MagicMock()
    fake_response.content = [fake_text_block]
    mock_client_instance.beta.messages = AsyncMock()
    mock_client_instance.beta.messages.create = AsyncMock(return_value=fake_response)

    criteria = {
        "backtest_period_months": 6, "min_total_return_pct": 200.0, "max_drawdown_pct": -12.0,
        "min_win_rate_pct": 55.0, "min_profit_factor": 1.8, "min_trades": 30, "min_avg_rr": 2.0,
    }
    with patch("bot.strategy.claude_engine.anthropic.AsyncAnthropic", return_value=mock_client_instance):
        result = await generate_strategy(
            symbol="BTCUSDT", ohlcv_df=df, criteria=criteria,
            api_key="test_key", timeout=180,
        )
    # Verify Files API was used
    mock_client_instance.beta.files.upload.assert_called_once()
    # Verify messages.create was called with correct model and beta header
    call_kwargs = mock_client_instance.beta.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-20250514"
    assert "files-api-2025-04-14" in call_kwargs.get("betas", [])
    assert any(t.get("type") == "code_execution_20250825" for t in call_kwargs.get("tools", []))
    # Verify file was cleaned up
    mock_client_instance.beta.files.delete.assert_called_once_with("file_abc123")
