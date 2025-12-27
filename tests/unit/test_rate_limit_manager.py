import asyncio
import time

import pytest

from cloud_trader.rate_limit_manager import RateLimitManager


@pytest.fixture
def rate_limit_manager():
    return RateLimitManager(default_rps=5, default_rpm=100)


def test_initial_state(rate_limit_manager):
    assert rate_limit_manager.check_rate_limit("agent1") is True
    assert rate_limit_manager.should_throttle_agent("agent1") is False
    assert rate_limit_manager.is_rate_limited() is False


def test_record_request(rate_limit_manager):
    rate_limit_manager.record_request("agent1")
    assert len(rate_limit_manager._request_timestamps["agent1"]) == 1


def test_check_rate_limit_rps(rate_limit_manager):
    for _ in range(5):
        rate_limit_manager.record_request("agent1")
    assert rate_limit_manager.check_rate_limit("agent1") is True
    rate_limit_manager.record_request("agent1")  # 6th request
    assert rate_limit_manager.check_rate_limit("agent1") is False


def test_check_rate_limit_rpm(rate_limit_manager):
    # Simulate 100 requests spread over 30 seconds (to avoid RPS limit)
    now = time.time()
    for i in range(100):
        # Spread requests over 30s, so RPS check (~3 per second) doesn't trigger
        rate_limit_manager._request_timestamps["agent1"].append(now - 30 + (i * 0.3))
    assert rate_limit_manager.check_rate_limit("agent1") is True
    rate_limit_manager.record_request("agent1")  # 101st request
    assert rate_limit_manager.check_rate_limit("agent1") is False


def test_should_throttle_agent_rps(rate_limit_manager):
    for _ in range(5):
        rate_limit_manager.record_request("agent1")
    assert rate_limit_manager.should_throttle_agent("agent1") is False
    rate_limit_manager.record_request("agent1")  # 6th request
    assert rate_limit_manager.should_throttle_agent("agent1") is True  # Should be throttled now


@pytest.mark.asyncio
async def test_should_throttle_agent_duration(rate_limit_manager):
    rate_limit_manager.throttle_agent_for("agent1", 0.1)  # Throttle for 0.1 seconds
    assert rate_limit_manager.should_throttle_agent("agent1") is True
    await asyncio.sleep(0.15)  # Wait for throttle to expire
    assert rate_limit_manager.should_throttle_agent("agent1") is False


def test_get_available_capacity(rate_limit_manager):
    rate_limit_manager.record_request("agent1")
    capacity = rate_limit_manager.get_available_capacity("agent1")
    assert capacity["remaining_rps"] == 4
    assert capacity["remaining_rpm"] == 99


def test_is_rate_limited(rate_limit_manager):
    assert rate_limit_manager.is_rate_limited() is False
    # Record 6 requests to exceed RPS limit of 5
    for _ in range(6):
        rate_limit_manager.record_request("agent1")
    assert rate_limit_manager.is_rate_limited() is True


@pytest.mark.asyncio
async def test_wait_for_capacity(rate_limit_manager):
    for _ in range(5):
        rate_limit_manager.record_request("agent1")
    rate_limit_manager.record_request("agent1")  # Exceed RPS

    start_time = time.time()
    # This should raise TimeoutError if it doesn't get capacity
    with pytest.raises(TimeoutError):
        await rate_limit_manager.wait_for_capacity("agent1", timeout=0.1)
    end_time = time.time()
    assert (end_time - start_time) >= 0.1

    # Test successful wait (by clearing requests)
    rate_limit_manager._request_timestamps["agent1"].clear()
    await rate_limit_manager.wait_for_capacity("agent1", timeout=0.1)  # Should not raise
    assert True  # If we reach here, it means it waited successfully


def test_update_rate_limits(rate_limit_manager):
    rate_limit_manager.update_rate_limits("agent1", rps=10, rpm=200)
    assert rate_limit_manager._rate_limits["agent1"]["rps"] == 10
    assert rate_limit_manager._rate_limits["agent1"]["rpm"] == 200
