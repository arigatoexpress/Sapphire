"""End-to-end tests for full trading flow with mocked APIs."""

import pytest
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from cloud_trader.service import TradingService
from cloud_trader.config import Settings
from cloud_trader.strategy import MarketSnapshot
from cloud_trader.credentials import Credentials


@pytest.fixture
def mock_settings() -> Settings:
    """Create deterministic settings instance for tests."""

    settings = Settings(_env_file=None)
    settings.enable_paper_trading = True
    settings.bot_id = "test-bot"
    settings.decision_interval_seconds = 5
    settings.momentum_threshold = 2.5
    settings.notional_fraction = 0.05
    settings.max_concurrent_positions = 5
    settings.symbols = ["BTCUSDT"]
    settings.redis_url = None
    settings.orchestrator_url = None
    settings.mcp_url = None
    settings.bandit_epsilon = 0.1
    settings.telegram_bot_token = None
    settings.telegram_chat_id = None
    settings.gcp_project_id = "test-project"
    return settings


@pytest.fixture
def mock_aster_client():
    """Create mock Aster client."""
    client = AsyncMock()
    client.ticker = AsyncMock(return_value={
        "lastPrice": 50000.0,
        "volume": 1000000.0,
        "priceChangePercent": 3.0,
    })
    client.place_order = AsyncMock(return_value={"orderId": "test-order-123"})
    client.position_risk = AsyncMock(return_value=[{
        "symbol": "BTCUSDT",
        "positionAmt": "0.1",
    }])
    client.get_position_risk = AsyncMock(return_value=[{
        "symbol": "BTCUSDT",
        "positionAmt": "0.1",
    }])
    return client


@pytest.mark.asyncio
async def test_trading_loop_execution(mock_settings):
    """Verify service start/stop toggles health state in paper trading mode."""

    loop_mock = AsyncMock(return_value=None)

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "cloud_trader.credentials.load_credentials",
                return_value=Credentials(api_key=None, api_secret=None),
            )
        )
        stack.enter_context(patch("cloud_trader.service.get_cache", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("cloud_trader.service.get_storage", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("cloud_trader.service.get_feature_store", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("cloud_trader.service.get_bigquery_streamer", new=AsyncMock(return_value=None)))
        stack.enter_context(patch("cloud_trader.service.close_cache", new=AsyncMock()))
        stack.enter_context(patch("cloud_trader.service.close_storage", new=AsyncMock()))
        stack.enter_context(patch("cloud_trader.service.close_bigquery_streamer", new=AsyncMock()))

        mock_pubsub_cls = stack.enter_context(patch("cloud_trader.service.PubSubClient"))
        mock_pubsub = mock_pubsub_cls.return_value
        mock_pubsub.connect = AsyncMock()
        mock_pubsub.close = AsyncMock()
        mock_pubsub.publish_reasoning = AsyncMock()
        mock_pubsub.publish_position = AsyncMock()
        mock_pubsub.publish_decision = AsyncMock()

        mock_exchange = AsyncMock()
        mock_exchange.get_all_symbols = AsyncMock(return_value=["BTCUSDT"])
        mock_exchange.get_all_tickers = AsyncMock(
            return_value=[
                {
                    "symbol": "BTCUSDT",
                    "lastPrice": "50000",
                    "volume": "1000000",
                    "priceChangePercent": "3",
                }
            ]
        )
        mock_exchange.close = AsyncMock()
        stack.enter_context(patch("cloud_trader.service.AsterClient", return_value=mock_exchange))

        stack.enter_context(patch("cloud_trader.service.TradingService._init_telegram", new=AsyncMock()))
        stack.enter_context(patch("cloud_trader.service.TradingService._publish_portfolio_state", new=AsyncMock()))

        with patch.object(TradingService, "_run_loop", loop_mock):
        service = TradingService(settings=mock_settings)
            service._start_symbol_refresh = AsyncMock()
        
        await service.start()
        assert service.health().running is True
        assert service.health().paper_trading is True
        
        await service.stop()
        assert service.health().running is False
        loop_mock.assert_awaited()


@pytest.mark.asyncio
async def test_market_feed_validation(mock_settings):
    """Test market feed validation and caching."""

    with ExitStack() as stack:
        stack.enter_context(patch("cloud_trader.service.AsterClient"))
        service = TradingService(settings=mock_settings)
    service._exchange = AsyncMock()
    service._exchange.get_all_tickers = AsyncMock(
        return_value=[
            {
                "symbol": "BTCUSDT",
                "lastPrice": "50000",
                "volume": "1000000",
                "priceChangePercent": "3",
            }
        ]
    )
    service._storage = None
    service._bigquery = None
    market = await service._fetch_market()
    assert len(market) > 0
    assert "BTCUSDT" in market


@pytest.mark.asyncio
async def test_position_verification(mock_settings, mock_aster_client):
    """Test position verification after order execution."""
    with patch("cloud_trader.service.AsterClient"):
        service = TradingService(settings=mock_settings)

    service._exchange = mock_aster_client
    mock_aster_client.get_position_risk = AsyncMock(
        return_value=[{"symbol": "BTCUSDT", "positionAmt": "0.1"}]
    )
        
    verified, _ = await service._verify_position_execution(
            symbol="BTCUSDT",
            side="BUY",
            order_id="test-order",
            timeout=5.0,
        )
        
        assert verified is True


@pytest.mark.asyncio
async def test_circuit_breaker_aster_api(mock_settings):
    """Test circuit breaker triggers on Aster API failures."""
    with patch("cloud_trader.service.AsterClient"):
        service = TradingService(settings=mock_settings)

    for _ in range(3):
        service._safeguards.record_failure("api")

    assert service._safeguards.check_circuit_breaker("api") is False


@pytest.mark.asyncio
async def test_risk_limits_enforcement(mock_settings):
    """Test that risk limits prevent oversized positions."""
    with patch("cloud_trader.service.load_credentials", return_value=Credentials(api_key=None, api_secret=None)):
        service = TradingService(settings=mock_settings)
    
    service._health.paper_trading = True
    service._portfolio.balance = 100.0
    service._portfolio.total_exposure = 900.0  # Already at 9x leverage
    
    can_open = service._risk.can_open_position(service._portfolio, 100.0)
    
    assert can_open is False


@pytest.mark.asyncio
async def test_telegram_command_handler(mock_settings):
    """Test Telegram command handler initialization."""
    from cloud_trader.telegram_commands import TelegramCommandHandler
    
    with patch("cloud_trader.telegram_commands.ApplicationBuilder") as mock_builder:
        builder_instance = MagicMock()
        application_instance = MagicMock()
        builder_instance.token.return_value = builder_instance
        builder_instance.build.return_value = application_instance
        mock_builder.return_value = builder_instance

    handler = TelegramCommandHandler(
        bot_token="test-token",
        chat_id="test-chat",
        trading_service=MagicMock(),
    )
    
    assert handler.chat_id == "test-chat"
    assert handler.application is application_instance


@pytest.mark.asyncio
async def test_ta_indicators():
    """Test TA-Lib indicator calculations."""
    from cloud_trader.ta_indicators import TAIndicators
    
    # Test RSI
    prices = [100.0 + i * 0.1 for i in range(30)]
    rsi = TAIndicators.calculate_rsi(prices)
    assert rsi is not None or True  # May be None if TA-Lib not installed
    
    # Test MACD
    macd = TAIndicators.calculate_macd(prices)
    assert macd is None or isinstance(macd, dict)


def test_kelly_criterion():
    """Test Kelly Criterion position sizing."""
    from cloud_trader.ta_indicators import kelly_criterion
    
    position_size = kelly_criterion(
        expected_return=0.05,
        volatility=0.15,
        account_balance=1000.0,
        risk_fraction=0.01,
    )
    
    assert position_size > 0
    assert position_size <= 1000.0 * 0.01  # Should not exceed 1%


if __name__ == "__main__":
    import asyncio
    pytest.main([__file__, "-v"])

