import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from cloud_trader.fallback_strategies import FallbackStrategySelector

@pytest.fixture
def fallback_selector():
    return FallbackStrategySelector()

@pytest.mark.asyncio
async def test_select_and_execute_position_holding(fallback_selector):
    # Test when there's an open position
    position = {"symbol": "BTCUSDT", "notional": 1000}
    with patch.object(fallback_selector, '_position_holding', new_callable=AsyncMock) as mock_position_holding:
        mock_position_holding.return_value = "HOLD"
        result = await fallback_selector.select_and_execute("BTCUSDT", position)
        mock_position_holding.assert_called_once_with("BTCUSDT", position)
        assert result == "HOLD"

@pytest.mark.asyncio
async def test_select_and_execute_no_position(fallback_selector):
    # Test when there's no open position, should randomly pick other strategies
    position = {"symbol": "BTCUSDT", "notional": 0}
    
    # Patch random.choice to control which strategy is picked
    with patch('random.choice', return_value="low_frequency_momentum") as mock_choice, \
         patch.object(fallback_selector, '_low_frequency_momentum', new_callable=AsyncMock) as mock_low_freq:
        mock_low_freq.return_value = "HOLD"
        result = await fallback_selector.select_and_execute("BTCUSDT", position)
        mock_choice.assert_called_once_with(["low_frequency_momentum", "reduced_symbol_scanning"])
        mock_low_freq.assert_called_once_with("BTCUSDT", position)
        assert result == "HOLD"

    with patch('random.choice', return_value="reduced_symbol_scanning") as mock_choice, \
         patch.object(fallback_selector, '_reduced_symbol_scanning', new_callable=AsyncMock) as mock_reduced_scan:
        mock_reduced_scan.return_value = "HOLD"
        result = await fallback_selector.select_and_execute("BTCUSDT", position)
        mock_choice.assert_called_once_with(["low_frequency_momentum", "reduced_symbol_scanning"])
        mock_reduced_scan.assert_called_once_with("BTCUSDT", position)
        assert result == "HOLD"

@pytest.mark.asyncio
async def test_low_frequency_momentum_strategy(fallback_selector):
    result = await fallback_selector._low_frequency_momentum("BTCUSDT", None)
    assert result == "HOLD"

@pytest.mark.asyncio
async def test_position_holding_strategy(fallback_selector):
    position = {"symbol": "BTCUSDT", "notional": 1000}
    result = await fallback_selector._position_holding("BTCUSDT", position)
    assert result == "HOLD"

    # Test with no position
    result = await fallback_selector._position_holding("BTCUSDT", None)
    assert result == "HOLD"

@pytest.mark.asyncio
async def test_reduced_symbol_scanning_strategy(fallback_selector):
    result = await fallback_selector._reduced_symbol_scanning("BTCUSDT", None)
    assert result == "HOLD"
