"""Tests for bot.telegram.handlers.settings — /risk, /criteria, /settings handlers (TG-07, TG-08, TG-16).
All tests are RED until bot/telegram/handlers/settings.py is implemented.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

settings_handlers = pytest.importorskip("bot.telegram.handlers.settings")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_message():
    """Factory fixture: returns a MagicMock Message with .text and .answer = AsyncMock()."""
    def _make(text: str):
        msg = MagicMock()
        msg.text = text
        msg.answer = AsyncMock()
        return msg
    return _make


@pytest.fixture
def mock_risk_row():
    """MagicMock RiskSettings row with spec defaults."""
    row = MagicMock()
    row.base_stake_pct = 3.0
    row.max_stake_pct = 8.0
    row.progressive_stakes = [3.0, 5.0, 8.0]
    row.wins_to_increase = 1
    row.reset_on_loss = True
    row.min_rr_ratio = 3.0
    row.max_open_positions = 5
    row.daily_loss_limit_pct = 5.0
    row.leverage = 5
    row.margin_type = "isolated"
    row.win_streak_current = 0
    return row


@pytest.fixture
def mock_criteria_row():
    """MagicMock StrategyCriteria row with spec defaults."""
    row = MagicMock()
    row.backtest_period_months = 6
    row.min_total_return_pct = 200.0
    row.max_drawdown_pct = -12.0
    row.min_win_rate_pct = 55.0
    row.min_profit_factor = 1.8
    row.min_trades = 30
    row.min_avg_rr = 2.0
    row.notify_on_skip = True
    row.strict_mode = False
    return row


@pytest.fixture
def mock_session_factory(mock_risk_row, mock_criteria_row):
    """AsyncMock context manager factory that yields a MagicMock session with AsyncMock execute()."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_risk_row
    result_mock.scalars.return_value.first.return_value = mock_risk_row
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    return factory


# ---------------------------------------------------------------------------
# /risk tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_risk_show_current(mock_message, mock_session_factory, mock_risk_row):
    """'/risk' with no args calls message.answer with 'base_stake_pct' in text."""
    msg = mock_message("/risk")

    # Patch update_risk_settings and session
    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        # Setup session to return risk_row
        session = mock_session_factory.return_value.__aenter__.return_value
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = mock_risk_row
        session.execute.return_value = result_mock

        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    msg.answer.assert_called_once()
    call_args = msg.answer.call_args
    text = call_args[0][0] if call_args[0] else call_args[1].get("text", "")
    assert "base_stake_pct" in text


@pytest.mark.asyncio
async def test_risk_stake_valid(mock_message, mock_session_factory, mock_risk_row):
    """'/risk stake 5.0' calls update_risk_settings with ('base_stake_pct', 5.0)."""
    msg = mock_message("/risk stake 5.0")

    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = True
        session = mock_session_factory.return_value.__aenter__.return_value
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = mock_risk_row
        session.execute.return_value = result_mock

        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    mock_update.assert_called_once()
    call_args = mock_update.call_args
    assert call_args[0][1] == "base_stake_pct" or call_args[1].get("field_name") == "base_stake_pct"
    assert call_args[0][2] == 5.0 or call_args[1].get("value") == 5.0


@pytest.mark.asyncio
async def test_risk_stake_invalid_above_100(mock_message, mock_session_factory):
    """'/risk stake 150' sends validation error containing '1-100'."""
    msg = mock_message("/risk stake 150")

    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        session = mock_session_factory.return_value.__aenter__.return_value
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = MagicMock(base_stake_pct=3.0)
        session.execute.return_value = result_mock

        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "1-100" in text or "1.0-100.0" in text
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_risk_stake_invalid_below_1(mock_message, mock_session_factory):
    """'/risk stake 0' sends validation error."""
    msg = mock_message("/risk stake 0")

    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        session = mock_session_factory.return_value.__aenter__.return_value
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = MagicMock(base_stake_pct=3.0)
        session.execute.return_value = result_mock

        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "❌" in text
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_risk_progressive_valid(mock_message, mock_session_factory, mock_risk_row):
    """'/risk progressive 3 5 8' calls update_risk_settings with [3.0, 5.0, 8.0]."""
    msg = mock_message("/risk progressive 3 5 8")

    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = True
        session = mock_session_factory.return_value.__aenter__.return_value
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = mock_risk_row
        session.execute.return_value = result_mock

        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    mock_update.assert_called_once()
    call_args = mock_update.call_args
    field = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("field_name")
    value = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("value")
    assert field == "progressive_stakes"
    assert value == [3.0, 5.0, 8.0]


@pytest.mark.asyncio
async def test_risk_progressive_wrong_count(mock_message, mock_session_factory):
    """'/risk progressive 3 5' sends validation error (needs exactly 3 values)."""
    msg = mock_message("/risk progressive 3 5")

    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "❌" in text or "progressive" in text.lower()
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_risk_reset(mock_message, mock_session_factory, mock_risk_row):
    """'/risk reset' calls update_risk_settings for all defaults."""
    msg = mock_message("/risk reset")

    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = True
        session = mock_session_factory.return_value.__aenter__.return_value
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = mock_risk_row
        session.execute.return_value = result_mock

        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    # Should call update_risk_settings multiple times (once per default field)
    assert mock_update.call_count >= 1
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "✅" in text


@pytest.mark.asyncio
async def test_risk_leverage_valid(mock_message, mock_session_factory, mock_risk_row):
    """'/risk leverage 10' calls update_risk_settings('leverage', 10)."""
    msg = mock_message("/risk leverage 10")

    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = True
        session = mock_session_factory.return_value.__aenter__.return_value
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = mock_risk_row
        session.execute.return_value = result_mock

        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    mock_update.assert_called_once()
    call_args = mock_update.call_args
    field = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("field_name")
    value = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("value")
    assert field == "leverage"
    assert value == 10


@pytest.mark.asyncio
async def test_risk_leverage_out_of_range(mock_message, mock_session_factory):
    """'/risk leverage 25' sends validation error '1-20'."""
    msg = mock_message("/risk leverage 25")

    with patch("bot.telegram.handlers.settings.update_risk_settings", new_callable=AsyncMock) as mock_update:
        session = mock_session_factory.return_value.__aenter__.return_value
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = MagicMock(leverage=5)
        session.execute.return_value = result_mock

        await settings_handlers.cmd_risk(
            msg,
            session_factory=mock_session_factory,
            settings=MagicMock(),
        )

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "1-20" in text or "1" in text
    mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# /criteria tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_criteria_show_current(mock_message, mock_session_factory, mock_criteria_row):
    """'/criteria' with no args sends message with 'min_total_return_pct' in text."""
    msg = mock_message("/criteria")

    session = mock_session_factory.return_value.__aenter__.return_value
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = mock_criteria_row
    session.execute.return_value = result_mock

    await settings_handlers.cmd_criteria(
        msg,
        session_factory=mock_session_factory,
        settings=MagicMock(),
    )

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "min_total_return_pct" in text


@pytest.mark.asyncio
async def test_criteria_return_valid(mock_message, mock_session_factory, mock_criteria_row):
    """'/criteria return 250' sets StrategyCriteria.min_total_return_pct = 250.0."""
    msg = mock_message("/criteria return 250")

    session = mock_session_factory.return_value.__aenter__.return_value
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = mock_criteria_row
    session.execute.return_value = result_mock

    await settings_handlers.cmd_criteria(
        msg,
        session_factory=mock_session_factory,
        settings=MagicMock(),
    )

    # setattr should have been called with min_total_return_pct = 250.0
    assert mock_criteria_row.min_total_return_pct == 250.0
    session.commit.assert_called_once()
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "✅" in text


@pytest.mark.asyncio
async def test_criteria_drawdown_stored_negative(mock_message, mock_session_factory, mock_criteria_row):
    """'/criteria drawdown 15' stores -15.0 in DB (negated)."""
    msg = mock_message("/criteria drawdown 15")

    session = mock_session_factory.return_value.__aenter__.return_value
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = mock_criteria_row
    session.execute.return_value = result_mock

    await settings_handlers.cmd_criteria(
        msg,
        session_factory=mock_session_factory,
        settings=MagicMock(),
    )

    assert mock_criteria_row.max_drawdown_pct == -15.0
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_criteria_strict_on(mock_message, mock_session_factory, mock_criteria_row):
    """'/criteria strict on' sets strict_mode = True."""
    msg = mock_message("/criteria strict on")

    session = mock_session_factory.return_value.__aenter__.return_value
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = mock_criteria_row
    session.execute.return_value = result_mock

    await settings_handlers.cmd_criteria(
        msg,
        session_factory=mock_session_factory,
        settings=MagicMock(),
    )

    assert mock_criteria_row.strict_mode is True
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_criteria_strict_off(mock_message, mock_session_factory, mock_criteria_row):
    """'/criteria strict off' sets strict_mode = False."""
    msg = mock_message("/criteria strict off")
    mock_criteria_row.strict_mode = True  # start with True

    session = mock_session_factory.return_value.__aenter__.return_value
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = mock_criteria_row
    session.execute.return_value = result_mock

    await settings_handlers.cmd_criteria(
        msg,
        session_factory=mock_session_factory,
        settings=MagicMock(),
    )

    assert mock_criteria_row.strict_mode is False
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_criteria_reset(mock_message, mock_session_factory, mock_criteria_row):
    """'/criteria reset' restores all defaults."""
    msg = mock_message("/criteria reset")

    session = mock_session_factory.return_value.__aenter__.return_value
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = mock_criteria_row
    session.execute.return_value = result_mock

    await settings_handlers.cmd_criteria(
        msg,
        session_factory=mock_session_factory,
        settings=MagicMock(),
    )

    # Defaults should be restored
    assert mock_criteria_row.min_total_return_pct == 200.0
    assert mock_criteria_row.max_drawdown_pct == -12.0
    assert mock_criteria_row.strict_mode is False
    session.commit.assert_called_once()
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "✅" in text


# ---------------------------------------------------------------------------
# /settings tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_show_current(mock_message, test_settings):
    """'/settings' with no args sends message with 'top_n_coins'."""
    msg = mock_message("/settings")

    await settings_handlers.cmd_settings(
        msg,
        session_factory=MagicMock(),
        settings=test_settings,
    )

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "top_n_coins" in text


@pytest.mark.asyncio
async def test_settings_top_n_valid(mock_message, test_settings):
    """'/settings top_n 15' sets settings.top_n_coins = 15."""
    msg = mock_message("/settings top_n 15")
    test_settings.top_n_coins = 10  # starting value

    await settings_handlers.cmd_settings(
        msg,
        session_factory=MagicMock(),
        settings=test_settings,
    )

    assert test_settings.top_n_coins == 15
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "✅" in text


@pytest.mark.asyncio
async def test_settings_review_interval(mock_message, mock_session_factory):
    """'/settings review_interval 14' returns success message."""
    msg = mock_message("/settings review_interval 14")

    # Session needs to handle the UPDATE query for Strategy rows
    session = mock_session_factory.return_value.__aenter__.return_value
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock

    await settings_handlers.cmd_settings(
        msg,
        session_factory=mock_session_factory,
        settings=MagicMock(top_n_coins=10, coin_whitelist=[]),
    )

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "✅" in text or "14" in text
