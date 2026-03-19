import pytest
import sys
from unittest.mock import patch
from pydantic import SecretStr, ValidationError


class TestSecretMasking:
    def test_secret_masking(self, test_settings):
        """API key must never appear in repr or str output."""
        key_repr = repr(test_settings.binance_api_key)
        key_str = str(test_settings.binance_api_key)
        assert "test_binance_key_abc123" not in key_repr
        assert "test_binance_key_abc123" not in key_str
        assert "**" in key_repr or "SecretStr" in key_repr

    def test_missing_required_var(self, monkeypatch):
        """Missing BINANCE_API_KEY must raise ValidationError."""
        from pydantic_settings import SettingsConfigDict
        from bot.config import Settings

        # Subclass with env_file disabled — prevents reading .env from disk
        class IsolatedSettings(Settings):
            model_config = SettingsConfigDict(
                env_file=None,
                extra="ignore",
            )

        # Remove env vars so pydantic-settings can't find BINANCE_API_KEY anywhere
        monkeypatch.delenv("BINANCE_API_KEY", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            IsolatedSettings(
                binance_api_secret=SecretStr("secret"),
                telegram_bot_token=SecretStr("token"),
                database_url=SecretStr("postgresql+asyncpg://u:p@h/db"),
                allowed_chat_id=123,
            )
        error_str = str(exc_info.value)
        assert "binance_api_key" in error_str

    def test_binance_env_valid_values(self, test_settings):
        """BINANCE_ENV accepts only testnet or production."""
        from bot.config import Settings
        # testnet is valid (default)
        assert test_settings.binance_env == "testnet"
        # production is valid
        prod_settings = Settings(
            binance_api_key=SecretStr("key"),
            binance_api_secret=SecretStr("secret"),
            telegram_bot_token=SecretStr("token"),
            database_url=SecretStr("postgresql+asyncpg://u:p@h/db"),
            allowed_chat_id=123,
            binance_env="production",
        )
        assert prod_settings.binance_env == "production"
        # invalid value raises ValidationError
        with pytest.raises(ValidationError):
            Settings(
                binance_api_key=SecretStr("key"),
                binance_api_secret=SecretStr("secret"),
                telegram_bot_token=SecretStr("token"),
                database_url=SecretStr("postgresql+asyncpg://u:p@h/db"),
                allowed_chat_id=123,
                binance_env="staging",
            )

    def test_defaults(self, test_settings):
        """Default risk and criteria values match spec."""
        assert test_settings.base_stake_pct == 3.0
        assert test_settings.max_open_positions == 5
        assert test_settings.leverage == 5
        assert test_settings.min_total_return_pct == 200.0
        assert test_settings.max_drawdown_pct == -12.0
        assert test_settings.min_trades == 30

    def test_configure_logging(self, test_settings):
        """configure_logging registers at least one loguru handler."""
        from loguru import logger
        from bot.config import configure_logging
        configure_logging(test_settings)
        assert len(logger._core.handlers) > 0
