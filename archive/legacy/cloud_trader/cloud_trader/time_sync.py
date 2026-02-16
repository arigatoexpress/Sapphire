"""High-precision time synchronization utilities for trading systems."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

try:
    import ntplib

    NTP_AVAILABLE = True
except ImportError:
    ntplib = None
    NTP_AVAILABLE = False

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TimeSyncConfig(BaseModel):
    """Configuration for time synchronization."""

    ntp_servers: List[str] = ["pool.ntp.org", "time.nist.gov", "time.google.com"]
    sync_interval_seconds: int = 300  # 5 minutes
    max_aster_microseconds: int = 1000  # 1ms max acceptable aster
    retries: int = 3


@dataclass
class TimeSample:
    """NTP time sample with precision metrics."""

    ntp_time: float
    local_time: float
    offset: float
    delay: float
    precision: float

    @property
    def aster_microseconds(self) -> float:
        """Calculate time aster in microseconds."""
        return abs(self.offset) * 1_000_000


class PrecisionClock:
    """High-precision clock with NTP synchronization."""

    def __init__(self, config: Optional[TimeSyncConfig] = None):
        self.config = config or TimeSyncConfig()
        self.ntp_client = ntplib.NTPClient() if NTP_AVAILABLE else None
        self._offset_ns: int = 0
        self._last_sync: Optional[float] = None
        self._aster_history: List[TimeSample] = []
        self._sync_task: Optional[asyncio.Task] = None

    async def start_sync(self) -> None:
        """Start periodic NTP synchronization."""
        if self._sync_task and not self._sync_task.done():
            return

        await self._sync_time()  # Initial sync
        self._sync_task = asyncio.create_task(self._periodic_sync())

    async def stop_sync(self) -> None:
        """Stop periodic synchronization."""
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

    async def _periodic_sync(self) -> None:
        """Periodic time synchronization loop."""
        while True:
            try:
                await asyncio.sleep(self.config.sync_interval_seconds)
                await self._sync_time()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Periodic time sync failed: {e}")

    async def _sync_time(self) -> None:
        """Synchronize with NTP servers."""
        if not NTP_AVAILABLE or not self.ntp_client:
            logger.warning("NTP library not available, using system time")
            self._last_sync = time.time()
            return

        best_sample: Optional[TimeSample] = None

        for server in self.config.ntp_servers:
            for attempt in range(self.config.retries):
                try:
                    response = await asyncio.get_event_loop().run_in_executor(
                        None, self.ntp_client.request, server, timeout=2
                    )

                    sample = TimeSample(
                        ntp_time=response.tx_time,
                        local_time=time.time(),
                        offset=response.offset,
                        delay=response.delay,
                        precision=response.precision,
                    )

                    # Keep the sample with lowest delay (most accurate)
                    if best_sample is None or sample.delay < best_sample.delay:
                        best_sample = sample

                    break  # Success, no need to retry

                except Exception as e:
                    if attempt == self.config.retries - 1:
                        logger.warning(f"NTP sync failed for {server}: {e}")
                    await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff

        if best_sample:
            self._offset_ns = int(best_sample.offset * 1_000_000_000)
            self._last_sync = time.time()
            self._aster_history.append(best_sample)

            # Keep only last 100 samples
            if len(self._aster_history) > 100:
                self._aster_history = self._aster_history[-100:]

            aster_us = best_sample.aster_microseconds
            if aster_us > self.config.max_aster_microseconds:
                logger.warning(".2f" f"server={best_sample.delay:.3f}s")

            logger.debug(".6f" f"offset={best_sample.offset:.6f}s")

    def now_ns(self) -> int:
        """Get current time in nanoseconds (NTP-synchronized)."""
        return time.time_ns() + self._offset_ns

    def now_us(self) -> int:
        """Get current time in microseconds (NTP-synchronized)."""
        return self.now_ns() // 1000

    def now(self) -> datetime:
        """Get current datetime (NTP-synchronized)."""
        return datetime.fromtimestamp(self.now_ns() / 1_000_000_000, tz=timezone.utc)

    def time_since_last_sync(self) -> Optional[float]:
        """Get seconds since last NTP sync."""
        if self._last_sync is None:
            return None
        return time.time() - self._last_sync

    def get_aster_stats(self) -> Dict[str, float]:
        """Get aster statistics."""
        if not self._aster_history:
            return {"samples": 0, "avg_aster_us": 0, "max_aster_us": 0}

        asters = [s.aster_microseconds for s in self._aster_history]
        return {
            "samples": len(asters),
            "avg_aster_us": sum(asters) / len(asters),
            "max_aster_us": max(asters),
            "current_offset_ns": self._offset_ns,
        }


# Global precision clock instance
_precision_clock: Optional[PrecisionClock] = None


async def get_precision_clock() -> PrecisionClock:
    """Get global precision clock instance."""
    global _precision_clock
    if _precision_clock is None:
        _precision_clock = PrecisionClock()
        await _precision_clock.start_sync()
    return _precision_clock


def get_timestamp_ns() -> int:
    """Get NTP-synchronized timestamp in nanoseconds."""
    if _precision_clock:
        return _precision_clock.now_ns()
    return time.time_ns()


def get_timestamp_us() -> int:
    """Get NTP-synchronized timestamp in microseconds."""
    if _precision_clock:
        return _precision_clock.now_us()
    return time.time_ns() // 1000


def get_datetime() -> datetime:
    """Get NTP-synchronized datetime."""
    if _precision_clock:
        return _precision_clock.now()
    return datetime.now(timezone.utc)
