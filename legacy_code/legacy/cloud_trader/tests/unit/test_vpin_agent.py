import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud_trader.agents.vpin_hft_agent import VpinHFTAgent


@pytest.fixture
def mock_exchange_client():
    return AsyncMock()


@pytest.fixture
def mock_pubsub_client():
    return AsyncMock()


@pytest.fixture
def vpin_agent(mock_exchange_client, mock_pubsub_client):
    return VpinHFTAgent(mock_exchange_client, mock_pubsub_client, "sapphire-vpin-positions")


def generate_mock_ticks(num_ticks: int, base_price: float, volume: float, direction: str = "buy"):
    ticks = []
    prev_price = base_price
    for i in range(num_ticks):
        price_change = 0.01 if direction == "buy" else -0.01
        price = base_price + (i * price_change)
        ticks.append(
            {
                "price": price,
                "prev_price": prev_price,
                "volume": volume,
            }
        )
        prev_price = price
    return ticks


@pytest.mark.asyncio
async def test_vpin_calculation_basic(vpin_agent):
    # Test with a simple batch of buy ticks
    buy_ticks = generate_mock_ticks(50, 100.0, 10.0, "buy")
    vpin_result = vpin_agent.calculate_vpin(buy_ticks)
    assert vpin_result["vpin"] > 0.0  # Expect a positive VPIN for buy pressure

    # Test with a simple batch of sell ticks
    sell_ticks = generate_mock_ticks(50, 100.0, 10.0, "sell")
    vpin_result = vpin_agent.calculate_vpin(sell_ticks)
    assert vpin_result["vpin"] > 0.0  # VPIN is absolute/imbalance based on code

    # Test with mixed ticks (should be close to zero)
    mixed_ticks = generate_mock_ticks(25, 100.0, 10.0, "buy") + generate_mock_ticks(
        25, 100.0, 10.0, "sell"
    )
    vpin_result = vpin_agent.calculate_vpin(mixed_ticks)
    assert vpin_result["vpin"] < 0.1  # Should be close to zero


@pytest.mark.asyncio
async def test_vpin_calculation_insufficient_data(vpin_agent):
    # Test with less than 10 ticks
    ticks = generate_mock_ticks(5, 100.0, 10.0)
    vpin_result = vpin_agent.calculate_vpin(ticks)
    assert vpin_result["vpin"] == 0.0


@pytest.mark.asyncio
async def test_vpin_calculation_zero_volume(vpin_agent):
    # Test with zero volume ticks
    ticks = generate_mock_ticks(50, 100.0, 0.0)
    vpin_result = vpin_agent.calculate_vpin(ticks)
    assert vpin_result["vpin"] == 0.0


@pytest.mark.asyncio
async def test_execute_trade_buy_signal(vpin_agent, mock_exchange_client, mock_pubsub_client):
    mock_exchange_client.get_ticker_price.return_value = {"price": 100.0}
    mock_exchange_client.place_order.return_value = {"orderId": "test_order_buy"}

    await vpin_agent.execute_trade(0.5, "BTCUSDT")  # Positive VPIN signal

    mock_exchange_client.get_ticker_price.assert_called_once_with("BTCUSDT")
    mock_exchange_client.place_order.assert_called_once()
    args, kwargs = mock_exchange_client.place_order.call_args
    assert kwargs["side"] == "BUY"
    assert kwargs["symbol"] == "BTCUSDT"
    mock_pubsub_client.publish.assert_called_once()
    args, kwargs = mock_pubsub_client.publish.call_args
    assert args[0] == "sapphire-vpin-positions"
    assert args[1]["side"] == "BUY"


@pytest.mark.asyncio
async def test_execute_trade_high_vpin_signal(vpin_agent, mock_exchange_client, mock_pubsub_client):
    mock_exchange_client.get_ticker_price.return_value = {"price": 100.0}
    mock_exchange_client.place_order.return_value = {"orderId": "test_order_buy"}

    await vpin_agent.execute_trade(0.8, "BTCUSDT")  # High VPIN signal (> 0.6)

    mock_exchange_client.get_ticker_price.assert_called_once_with("BTCUSDT")
    mock_exchange_client.place_order.assert_called_once()
    args, kwargs = mock_exchange_client.place_order.call_args
    assert kwargs["side"] == "BUY"
    assert kwargs["symbol"] == "BTCUSDT"
    mock_pubsub_client.publish.assert_called_once()
    args, kwargs = mock_pubsub_client.publish.call_args
    assert args[0] == "sapphire-vpin-positions"
    assert args[1]["side"] == "BUY"


@pytest.mark.asyncio
async def test_execute_trade_neutral_signal(vpin_agent, mock_exchange_client, mock_pubsub_client):
    mock_exchange_client.get_ticker_price.return_value = {"price": 100.0}

    await vpin_agent.execute_trade(0.05, "BTCUSDT")  # Neutral VPIN signal (below threshold)

    mock_exchange_client.get_ticker_price.assert_not_called()
    mock_exchange_client.place_order.assert_not_called()
    mock_pubsub_client.publish.assert_not_called()


@pytest.mark.asyncio
async def test_execute_trade_exchange_error(vpin_agent, mock_exchange_client, mock_pubsub_client):
    mock_exchange_client.get_ticker_price.return_value = {"price": 100.0}
    mock_exchange_client.place_order.side_effect = Exception("Exchange error")

    await vpin_agent.execute_trade(0.5, "BTCUSDT")

    mock_exchange_client.get_ticker_price.assert_called_once()
    mock_exchange_client.place_order.assert_called_once()
    mock_pubsub_client.publish.assert_not_called()  # Should not publish if order fails
