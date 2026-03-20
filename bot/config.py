import sys
from typing import Literal
from loguru import logger
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Secrets — SecretStr ensures these never appear in repr/str/logs
    binance_api_key: SecretStr
    binance_api_secret: SecretStr
    telegram_bot_token: SecretStr
    database_url: SecretStr  # contains DB password

    # Anthropic API
    anthropic_api_key: SecretStr
    claude_model: str = "claude-sonnet-4-20250514"

    # Market Scanner — whitelist of coins approved for scanning
    # Set COIN_WHITELIST=BTCUSDT,ETHUSDT,... in .env to override
    coin_whitelist: list[str] = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT",
        "DOTUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
    ]
    # Scanner config
    top_n_coins: int = 10
    min_volume_usdt: float = 50_000_000.0
    volume_norm_hours: int = 4  # baseline period for volume growth rate calculation
    min_volume_growth_rate: float = 1.0  # minimum growth rate (1.0 = no filter, 2.0 = 2x norm)
    consecutive_empty_cycles_alert: int = 3

    # Binance environment — drives testnet=True/False in exchange client
    binance_env: Literal["testnet", "production"] = "testnet"

    # Telegram
    allowed_chat_id: int

    # Logging
    log_level: str = "INFO"

    # Risk management defaults (seeded to risk_settings table on first boot)
    base_stake_pct: float = 3.0
    current_stake_pct: float = 3.0
    max_stake_pct: float = 8.0
    progressive_stakes: list[float] = [3.0, 5.0, 8.0]
    wins_to_increase: int = 1
    reset_on_loss: bool = True
    min_rr_ratio: float = 3.0
    max_open_positions: int = 5
    daily_loss_limit_pct: float = 5.0
    leverage: int = 5
    margin_type: str = "isolated"
    win_streak_current: int = 0

    # Strategy criteria defaults (seeded to strategy_criteria table on first boot)
    backtest_period_months: int = 6
    min_total_return_pct: float = 200.0
    max_drawdown_pct: float = -12.0
    min_win_rate_pct: float = 55.0
    min_profit_factor: float = 1.8
    min_trades: int = 30
    min_avg_rr: float = 2.0
    notify_on_skip: bool = True
    strict_mode: bool = False


def configure_logging(settings: Settings) -> None:
    """Configure loguru with level from settings. Call once at startup."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
        colorize=True,
    )


# Module-level settings instance — fail fast if any required var is missing
try:
    settings = Settings()
except ValidationError as e:
    for err in e.errors():
        field = err["loc"][0] if err["loc"] else "unknown"
        print(
            f"ERROR: Missing required environment variable: {str(field).upper()}",
            file=sys.stderr,
        )
    sys.exit(1)
