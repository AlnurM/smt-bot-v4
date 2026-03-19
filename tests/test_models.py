"""Tests for SQLAlchemy ORM models and session factory (Task 1 TDD)."""
import pytest
from sqlalchemy.dialects.postgresql import JSONB


class TestModelsImportable:
    """test_models_importable: all 10 model classes import without error."""

    def test_imports(self):
        from bot.db.models import (
            Base,
            Strategy,
            StrategyCriteria,
            RiskSettings,
            Signal,
            SkippedCoin,
            Order,
            Position,
            Trade,
            DailyStats,
            Log,
        )
        assert Base is not None
        assert Strategy is not None
        assert StrategyCriteria is not None
        assert RiskSettings is not None
        assert Signal is not None
        assert SkippedCoin is not None
        assert Order is not None
        assert Position is not None
        assert Trade is not None
        assert DailyStats is not None
        assert Log is not None


class TestTableNames:
    """test_table_names: all 10 models have correct __tablename__ values."""

    def test_strategy_tablename(self):
        from bot.db.models import Strategy
        assert Strategy.__tablename__ == "strategies"

    def test_strategy_criteria_tablename(self):
        from bot.db.models import StrategyCriteria
        assert StrategyCriteria.__tablename__ == "strategy_criteria"

    def test_risk_settings_tablename(self):
        from bot.db.models import RiskSettings
        assert RiskSettings.__tablename__ == "risk_settings"

    def test_signals_tablename(self):
        from bot.db.models import Signal
        assert Signal.__tablename__ == "signals"

    def test_skipped_coins_tablename(self):
        from bot.db.models import SkippedCoin
        assert SkippedCoin.__tablename__ == "skipped_coins"

    def test_orders_tablename(self):
        from bot.db.models import Order
        assert Order.__tablename__ == "orders"

    def test_positions_tablename(self):
        from bot.db.models import Position
        assert Position.__tablename__ == "positions"

    def test_trades_tablename(self):
        from bot.db.models import Trade
        assert Trade.__tablename__ == "trades"

    def test_daily_stats_tablename(self):
        from bot.db.models import DailyStats
        assert DailyStats.__tablename__ == "daily_stats"

    def test_logs_tablename(self):
        from bot.db.models import Log
        assert Log.__tablename__ == "logs"


class TestUUIDPrimaryKey:
    """test_uuid_pk: UUID PKs use gen_random_uuid() server default."""

    def test_strategy_uuid_pk_server_default(self):
        from bot.db.models import Strategy
        server_default = Strategy.__table__.c["id"].server_default
        assert server_default is not None
        assert "gen_random_uuid()" in str(server_default.arg)

    def test_all_tables_have_id_column(self):
        from bot.db.models import (
            Base, Strategy, StrategyCriteria, RiskSettings, Signal,
            SkippedCoin, Order, Position, Trade, DailyStats, Log,
        )
        for model in [Strategy, StrategyCriteria, RiskSettings, Signal,
                      SkippedCoin, Order, Position, Trade, DailyStats, Log]:
            assert "id" in model.__table__.c, f"{model.__name__} missing 'id' column"


class TestJSONBColumns:
    """test_jsonb_columns: JSONB columns use PostgreSQL JSONB type, not JSON."""

    def test_strategy_data_is_jsonb(self):
        from bot.db.models import Strategy
        col_type = Strategy.__table__.c["strategy_data"].type
        assert col_type.__class__.__name__ == "JSONB", (
            f"Expected JSONB, got {col_type.__class__.__name__}"
        )

    def test_strategy_criteria_snapshot_is_jsonb(self):
        from bot.db.models import Strategy
        col_type = Strategy.__table__.c["criteria_snapshot"].type
        assert col_type.__class__.__name__ == "JSONB", (
            f"Expected JSONB, got {col_type.__class__.__name__}"
        )

    def test_risk_settings_progressive_stakes_is_jsonb(self):
        from bot.db.models import RiskSettings
        col_type = RiskSettings.__table__.c["progressive_stakes"].type
        assert col_type.__class__.__name__ == "JSONB", (
            f"Expected JSONB, got {col_type.__class__.__name__}"
        )

    def test_skipped_coin_backtest_results_is_jsonb(self):
        from bot.db.models import SkippedCoin
        col_type = SkippedCoin.__table__.c["backtest_results"].type
        assert col_type.__class__.__name__ == "JSONB"

    def test_skipped_coin_failed_criteria_is_jsonb(self):
        from bot.db.models import SkippedCoin
        col_type = SkippedCoin.__table__.c["failed_criteria"].type
        assert col_type.__class__.__name__ == "JSONB"


class TestAllTablesInMetadata:
    """All 10 table names appear in Base.metadata.tables."""

    def test_all_10_tables_in_metadata(self):
        from bot.db.models import Base
        expected = {
            "strategies", "strategy_criteria", "risk_settings", "signals",
            "skipped_coins", "orders", "positions", "trades", "daily_stats", "logs",
        }
        actual = set(Base.metadata.tables.keys())
        missing = expected - actual
        assert not missing, f"Tables missing from metadata: {missing}"


class TestSessionFactory:
    """test_session_factory: SessionLocal has expire_on_commit=False."""

    def test_session_local_expire_on_commit_false(self):
        import os
        os.environ.setdefault("BINANCE_API_KEY", "test")
        os.environ.setdefault("BINANCE_API_SECRET", "test")
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
        os.environ.setdefault("ALLOWED_CHAT_ID", "123")
        os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
        from bot.db.session import SessionLocal
        assert SessionLocal.kw["expire_on_commit"] is False

    def test_session_importable(self):
        import os
        os.environ.setdefault("BINANCE_API_KEY", "test")
        os.environ.setdefault("BINANCE_API_SECRET", "test")
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
        os.environ.setdefault("ALLOWED_CHAT_ID", "123")
        os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
        from bot.db.session import engine, SessionLocal, get_session
        assert engine is not None
        assert SessionLocal is not None
        assert get_session is not None
