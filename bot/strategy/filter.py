"""Strategy Filter — validates Claude-generated strategy against configurable criteria."""
from __future__ import annotations

from dataclasses import dataclass
from loguru import logger


@dataclass
class FilterResult:
    passed: bool
    failed_criteria: list[str]
    details: dict  # criterion_name -> bool (True = passed)


def filter_strategy(
    strategy_data: dict,
    criteria: dict,
    strict_mode: bool,
) -> FilterResult:
    """Validate strategy_data backtest results against criteria.

    In relaxed mode (strict_mode=False), only total_return_pct and max_drawdown_pct
    are required (FILT-03). In strict mode, all 6 criteria must pass (FILT-01).

    Args:
        strategy_data: dict with "backtest" sub-dict from Claude
        criteria: dict with min_total_return_pct, max_drawdown_pct, min_win_rate_pct,
                  min_profit_factor, min_trades, min_avg_rr
        strict_mode: True -> all 6 required; False -> only return + drawdown required

    Returns:
        FilterResult with passed, failed_criteria list, and details dict
    """
    backtest = strategy_data.get("backtest", {})

    # Evaluate all 6 criteria
    checks: dict[str, bool] = {
        "total_return_pct": backtest.get("total_return_pct", 0.0) >= criteria.get("min_total_return_pct", 200.0),
        "max_drawdown_pct": backtest.get("max_drawdown_pct", -999.0) >= criteria.get("max_drawdown_pct", -12.0),
        "win_rate": backtest.get("win_rate", 0.0) >= criteria.get("min_win_rate_pct", 55.0) / 100.0,
        "profit_factor": backtest.get("profit_factor", 0.0) >= criteria.get("min_profit_factor", 1.8),
        "total_trades": backtest.get("total_trades", 0) >= criteria.get("min_trades", 30),
        "avg_rr": backtest.get("avg_rr", 0.0) >= criteria.get("min_avg_rr", 2.0),
    }

    # Determine which criteria are required
    required: set[str] = {"total_return_pct", "max_drawdown_pct"}  # always required
    if strict_mode:
        required = set(checks.keys())  # all 6 required in strict mode

    failed = [k for k in required if not checks[k]]
    passed = len(failed) == 0

    if not passed:
        logger.info(
            f"Strategy filter FAILED — criteria: {failed} | "
            f"return={backtest.get('total_return_pct', '?')}% "
            f"drawdown={backtest.get('max_drawdown_pct', '?')}% "
            f"strict_mode={strict_mode}"
        )
    else:
        logger.info(
            f"Strategy filter PASSED | "
            f"return={backtest.get('total_return_pct', '?')}% "
            f"drawdown={backtest.get('max_drawdown_pct', '?')}%"
        )

    return FilterResult(passed=passed, failed_criteria=failed, details=checks)
