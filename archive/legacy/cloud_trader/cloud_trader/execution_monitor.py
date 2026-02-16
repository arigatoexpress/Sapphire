"""
V2.3 Execution Speed Monitor - Track and optimize for < 100ms execution times.

Monitors:
- Signal to execution latency
- Platform API response times
- Circuit breaker overhead
- End-to-end trade execution speed

Target: < 100ms for autonomous HFT trading
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    """Metrics for a single execution."""
    platform: str
    symbol: str
    total_latency_ms: float
    api_latency_ms: float
    preprocessing_ms: float
    success: bool
    timestamp: float


class ExecutionSpeedMonitor:
    """
    Monitor and optimize execution speed for independent platform traders.

    V2.3 targets:
    - Aster: < 100ms (VPIN HFT)
    - Lighter: < 100ms (Momentum)
    - Aster: < 50ms (Shield HFT strategy)
    - Aster: < 200ms (Treasury operations)
    - Lighter: < 150ms (L2 execution)
    """

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.executions: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))

        # Platform-specific latency targets (ms)
        self.targets = {
            "aster": 100,
            "lighter": 100,
            "aster": 50,  # HFT Shield strategy needs speed
            "aster": 200,
            "lighter": 150
        }

        # Real-time stats
        self.stats = defaultdict(lambda: {
            "count": 0,
            "avg_latency": 0.0,
            "min_latency": float('inf'),
            "max_latency": 0.0,
            "success_rate": 0.0,
            "within_target": 0.0
        })

    def record_execution(
        self,
        platform: str,
        symbol: str,
        total_latency_ms: float,
        api_latency_ms: float = 0.0,
        preprocessing_ms: float = 0.0,
        success: bool = True
    ):
        """Record an execution and update statistics."""

        execution = ExecutionMetrics(
            platform=platform.lower(),
            symbol=symbol,
            total_latency_ms=total_latency_ms,
            api_latency_ms=api_latency_ms,
            preprocessing_ms=preprocessing_ms,
            success=success,
            timestamp=time.time()
        )

        self.executions[platform.lower()].append(execution)
        self._update_stats(platform.lower())

        # Log performance warnings
        target = self.targets.get(platform.lower(), 100)
        if total_latency_ms > target:
            logger.warning(
                f"⚠️ [SPEED] {platform} execution slow: {total_latency_ms:.1f}ms "
                f"(target: {target}ms) - Symbol: {symbol}"
            )
        else:
            logger.debug(
                f"⚡ [SPEED] {platform} fast execution: {total_latency_ms:.1f}ms - {symbol}"
            )

    def _update_stats(self, platform: str):
        """Update real-time statistics for a platform."""
        executions = list(self.executions[platform])
        if not executions:
            return

        latencies = [e.total_latency_ms for e in executions]
        successes = [e.success for e in executions]
        target = self.targets.get(platform, 100)
        within_target = sum(1 for lat in latencies if lat <= target)

        self.stats[platform] = {
            "count": len(executions),
            "avg_latency": sum(latencies) / len(latencies),
            "min_latency": min(latencies),
            "max_latency": max(latencies),
            "success_rate": sum(successes) / len(successes),
            "within_target": within_target / len(latencies),
            "target_ms": target
        }

    def get_platform_stats(self, platform: str) -> dict:
        """Get statistics for a specific platform."""
        return self.stats.get(platform.lower(), {})

    def get_all_stats(self) -> dict:
        """Get statistics for all platforms."""
        return dict(self.stats)

    def get_slow_executions(self, platform: str, threshold_ms: Optional[float] = None) -> list:
        """Get executions that exceeded the threshold."""
        if threshold_ms is None:
            threshold_ms = self.targets.get(platform.lower(), 100)

        executions = self.executions.get(platform.lower(), [])
        return [
            {
                "symbol": e.symbol,
                "latency_ms": e.total_latency_ms,
                "api_latency_ms": e.api_latency_ms,
                "preprocessing_ms": e.preprocessing_ms,
                "timestamp": e.timestamp
            }
            for e in executions
            if e.total_latency_ms > threshold_ms
        ]

    def get_performance_summary(self) -> str:
        """Get a formatted performance summary for all platforms."""
        lines = ["⚡ EXECUTION SPEED SUMMARY (V2.3 Independent Traders)"]
        lines.append("=" * 70)

        for platform, stats in sorted(self.stats.items()):
            if stats["count"] == 0:
                continue

            target = stats.get("target_ms", 100)
            avg = stats["avg_latency"]
            within = stats["within_target"] * 100

            status = "✅" if avg <= target and within >= 80 else "⚠️"

            lines.append(
                f"{status} {platform.upper():12} | "
                f"Avg: {avg:6.1f}ms | "
                f"Target: {target:3.0f}ms | "
                f"Within: {within:5.1f}% | "
                f"Success: {stats['success_rate']*100:5.1f}% | "
                f"Trades: {stats['count']}"
            )

        return "\n".join(lines)

    def is_platform_fast_enough(self, platform: str) -> bool:
        """Check if platform is meeting speed targets."""
        stats = self.stats.get(platform.lower())
        if not stats or stats["count"] < 5:
            return True  # Not enough data yet

        # Must have 80%+ executions within target
        return stats["within_target"] >= 0.80


# Global instance for monitoring
_monitor = None


def get_execution_monitor() -> ExecutionSpeedMonitor:
    """Get the global execution speed monitor."""
    global _monitor
    if _monitor is None:
        _monitor = ExecutionSpeedMonitor()
    return _monitor
