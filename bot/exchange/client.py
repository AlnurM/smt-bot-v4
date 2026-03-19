"""Binance async client factory — testnet/production toggle via settings."""
from binance import AsyncClient
from loguru import logger

from bot.config import Settings


async def create_binance_client(settings: Settings) -> AsyncClient:
    """
    Create and return an authenticated AsyncClient.

    When settings.binance_env == "testnet"  → testnet=True  (connects to testnet.binancefuture.com)
    When settings.binance_env == "production" → testnet=False (connects to live endpoints)

    NEVER log .get_secret_value() — pass the SecretStr object to the logger so pydantic renders it
    as *** in any log output.
    """
    is_testnet = settings.binance_env == "testnet"
    # Log SecretStr objects (not their raw values) so pydantic masks them automatically
    logger.info(
        f"Creating Binance client | env={settings.binance_env} | testnet={is_testnet}"
    )
    client = await AsyncClient.create(
        api_key=settings.binance_api_key.get_secret_value(),
        api_secret=settings.binance_api_secret.get_secret_value(),
        testnet=is_testnet,
    )
    return client
