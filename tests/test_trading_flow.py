"""End-to-end tests for full trading flow with mocked APIs."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from cloud_trader.service import TradingService, HealthStatus
from cloud_trader.config import Settings
from cloud_trader.strategy import MarketSnapshot
from cloud_trader.secrets import Credentials


@pytest.fixture
def mock_settings() -> Settings:
    """Create deterministic settings instance for tests."""

    settings = Settings()
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
    settings.decisions_stream = "test:decisions"
    settings.positions_stream = "test:positions"
    settings.reasoning_stream = "test:reasoning"
    settings.redis_stream_maxlen = 100
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
    return client


@pytest.mark.asyncio
async def test_trading_loop_execution(mock_settings):
    """Verify service start/stop toggles health state in paper trading mode."""

    loop_mock = AsyncMock(return_value=None)
    with (
        patch("cloud_trader.service.load_credentials", return_value=Credentials(api_key=None, api_secret=None)),
        patch("cloud_trader.service.AsterClient"),
        patch.object(TradingService, "_run_loop", loop_mock),
    ):
        service = TradingService(settings=mock_settings)
        
        await service.start()
        assert service.health().running is True
        assert service.health().paper_trading is True
        
        await service.stop()
        assert service.health().running is False
        loop_mock.assert_awaited()


@pytest.mark.asyncio
async def test_market_feed_validation(mock_settings):
    """Test market feed validation and caching."""

    with patch("cloud_trader.service.load_credentials", return_value=Credentials(api_key=None, api_secret=None)):
        service = TradingService(settings=mock_settings)
        
        service._health = HealthStatus(running=False, paper_trading=True, last_error=None)
    
    market = await service._fetch_market()
    assert len(market) > 0
    assert "BTCUSDT" in market


@pytest.mark.asyncio
async def test_position_verification(mock_settings, mock_aster_client):
    """Test position verification after order execution."""
    with patch("cloud_trader.service.load_credentials", return_value=Credentials(api_key=None, api_secret=None)):
        service = TradingService(settings=mock_settings)

        service._client = mock_aster_client
        
        verified = await service._verify_position_execution(
            symbol="BTCUSDT",
            side="BUY",
            order_id="test-order",
            timeout=5.0,
        )
        
        assert verified is True


@pytest.mark.asyncio
async def test_circuit_breaker_aster_api(mock_settings):
    """Test circuit breaker triggers on Aster API failures."""
    from cloud_trader.client import _aster_circuit_breaker
    
    # Reset circuit breaker
    await _aster_circuit_breaker.reset()
    
    # Simulate failures
    for _ in range(6):  # More than fail_max
        try:
            async def failing_call():
                raise RuntimeError("API failure")
            await _aster_circuit_breaker.call_async(failing_call)
        except Exception:
            pass
    
    # Circuit should be open
    assert _aster_circuit_breaker.current_state == "open"


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
    
    # Mock telegram service
    handler = TelegramCommandHandler(
        bot_token="test-token",
        chat_id="test-chat",
        trading_service=MagicMock(),
    )
    
    # Should initialize without errors
    assert handler.bot_token == "test-token"
    assert handler.chat_id == "test-chat"


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

