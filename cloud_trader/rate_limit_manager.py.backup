import asyncio
import time
from collections import defaultdict
from typing import Dict, Any

class RateLimitManager:
    """
    Manages API rate limits for different agents and endpoints.
    Tracks requests, detects throttling, and coordinates agent activity.
    """

    def __init__(self, default_rps: int = 10, default_rpm: int = 600):
        self.default_rps = default_rps  # Default requests per second
        self.default_rpm = default_rpm  # Default requests per minute

        self._request_timestamps: Dict[str, list[float]] = defaultdict(list)
        self._rate_limits: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"rps": self.default_rps, "rpm": self.default_rpm, "last_reset": time.time()}
        )
        self._throttled_agents: Dict[str, float] = {}  # agent_id: throttle_until_timestamp

    def _clean_old_timestamps(self, agent_id: str):
        """Removes timestamps older than 60 seconds to keep the list relevant for RPM."""
        now = time.time()
        self._request_timestamps[agent_id] = [
            ts for ts in self._request_timestamps[agent_id] if now - ts <= 60
        ]

    def record_request(self, agent_id: str, endpoint: str = "default"):
        """Records an API request for a given agent."""
        now = time.time()
        self._request_timestamps[agent_id].append(now)
        # Optionally, update rate limits based on response headers if available
        # For now, we'll stick to predefined/default limits

    def update_rate_limits(self, agent_id: str, rps: int = None, rpm: int = None, reset_time: float = None):
        """Updates the known rate limits for an agent, typically from API response headers."""
        if rps is not None:
            self._rate_limits[agent_id]["rps"] = rps
        if rpm is not None:
            self._rate_limits[agent_id]["rpm"] = rpm
        if reset_time is not None:
            self._rate_limits[agent_id]["last_reset"] = reset_time

    def check_rate_limit(self, agent_id: str) -> bool:
        """
        Checks if an agent can make a request based on its rate limits.
        Returns True if allowed, False otherwise.
        """
        self._clean_old_timestamps(agent_id)
        now = time.time()

        agent_limits = self._rate_limits[agent_id]
        current_rps = sum(1 for ts in self._request_timestamps[agent_id] if now - ts <= 1)
        current_rpm = len(self._request_timestamps[agent_id])

        if current_rps >= agent_limits["rps"]:
            return False
        if current_rpm >= agent_limits["rpm"]:
            return False

        return True

    def should_throttle_agent(self, agent_id: str) -> bool:
        """
        Determines if an agent should be throttled.
        This can be due to hitting rate limits or explicit throttling by the manager.
        """
        now = time.time()
        if agent_id in self._throttled_agents and self._throttled_agents[agent_id] > now:
            return True  # Still throttled

        if not self.check_rate_limit(agent_id):
            # If rate limit is hit, throttle for a short period
            self._throttled_agents[agent_id] = now + 5  # Throttle for 5 seconds
            return True
        return False

    def throttle_agent_for(self, agent_id: str, duration_seconds: float):
        """Explicitly throttles an agent for a given duration."""
        self._throttled_agents[agent_id] = time.time() + duration_seconds

    def get_available_capacity(self, agent_id: str) -> Dict[str, int]:
        """Returns the remaining request capacity for an agent."""
        self._clean_old_timestamps(agent_id)
        now = time.time()

        agent_limits = self._rate_limits[agent_id]
        current_rps = sum(1 for ts in self._request_timestamps[agent_id] if now - ts <= 1)
        current_rpm = len(self._request_timestamps[agent_id])

        return {
            "remaining_rps": max(0, agent_limits["rps"] - current_rps),
            "remaining_rpm": max(0, agent_limits["rpm"] - current_rpm),
        }

    def is_rate_limited(self) -> bool:
        """
        Checks if any agent is currently being rate-limited or throttled.
        This can be used to determine if a global fallback is needed.
        """
        now = time.time()
        for agent_id in self._rate_limits:
            if self.should_throttle_agent(agent_id):
                return True
        return False

    async def wait_for_capacity(self, agent_id: str, timeout: float = 10.0):
        """
        Waits asynchronously until an agent has capacity to make a request.
        Raises TimeoutError if capacity is not available within the timeout.
        """
        start_time = time.time()
        while not self.check_rate_limit(agent_id):
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Timeout waiting for rate limit capacity for agent {agent_id}")
            await asyncio.sleep(0.1)  # Wait a short period before re-checking