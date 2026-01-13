"""
Platform Logger - Structured logging for each trading platform.

Provides:
- Per-platform log storage with rotation
- API endpoint for retrieving logs
- Log level filtering
- Error tracking per platform
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Platform(Enum):
    ASTER = "aster"
    SYMPHONY = "symphony"
    DRIFT = "drift"
    HYPERLIQUID = "hyperliquid"
    SYSTEM = "system"
    AGENTS = "agents"


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class PlatformLogEntry:
    """A single log entry for a platform."""
    
    timestamp: float
    level: str
    message: str
    platform: str
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
            "level": self.level,
            "message": self.message,
            "platform": self.platform,
            "context": self.context,
        }


class PlatformLogger:
    """
    Centralized logger for all trading platforms.
    Stores logs in memory with rotation for API access.
    """
    
    def __init__(self, max_logs_per_platform: int = 500):
        self.max_logs = max_logs_per_platform
        self._logs: Dict[str, deque] = {
            p.value: deque(maxlen=max_logs_per_platform) for p in Platform
        }
        self._error_counts: Dict[str, int] = {p.value: 0 for p in Platform}
        self._last_activity: Dict[str, float] = {p.value: 0.0 for p in Platform}
        
    def log(
        self,
        platform: str,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a log entry for a platform."""
        platform_key = platform.lower()
        if platform_key not in self._logs:
            platform_key = Platform.SYSTEM.value
            
        entry = PlatformLogEntry(
            timestamp=time.time(),
            level=level.upper(),
            message=message,
            platform=platform_key,
            context=context or {},
        )
        
        self._logs[platform_key].append(entry)
        self._last_activity[platform_key] = time.time()
        
        if level.upper() in ("ERROR", "CRITICAL"):
            self._error_counts[platform_key] += 1
            
        # Also log to standard logger
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(f"[{platform_key.upper()}] {message}")
    
    def get_logs(
        self,
        platform: str,
        limit: int = 50,
        level_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent logs for a platform."""
        platform_key = platform.lower()
        if platform_key not in self._logs:
            return []
            
        logs = list(self._logs[platform_key])
        
        # Filter by level if specified
        if level_filter:
            level_upper = level_filter.upper()
            logs = [l for l in logs if l.level == level_upper]
        
        # Return most recent first
        logs = logs[-limit:]
        logs.reverse()
        
        return [l.to_dict() for l in logs]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get logging statistics for all platforms."""
        return {
            platform: {
                "total_logs": len(self._logs[platform]),
                "error_count": self._error_counts[platform],
                "last_activity": self._last_activity[platform],
                "last_activity_ago": time.time() - self._last_activity[platform]
                if self._last_activity[platform] > 0
                else None,
            }
            for platform in self._logs
        }
    
    def clear(self, platform: Optional[str] = None) -> None:
        """Clear logs for a platform or all platforms."""
        if platform:
            platform_key = platform.lower()
            if platform_key in self._logs:
                self._logs[platform_key].clear()
                self._error_counts[platform_key] = 0
        else:
            for p in self._logs:
                self._logs[p].clear()
                self._error_counts[p] = 0


# Singleton instance
_platform_logger: Optional[PlatformLogger] = None


def get_logger() -> PlatformLogger:
    """Get the global platform logger instance."""
    global _platform_logger
    if _platform_logger is None:
        _platform_logger = PlatformLogger()
    return _platform_logger


# Convenience functions for each platform
def log_aster(level: str, message: str, **context):
    get_logger().log(Platform.ASTER.value, level, message, context)


def log_symphony(level: str, message: str, **context):
    get_logger().log(Platform.SYMPHONY.value, level, message, context)


def log_drift(level: str, message: str, **context):
    get_logger().log(Platform.DRIFT.value, level, message, context)


def log_hyperliquid(level: str, message: str, **context):
    get_logger().log(Platform.HYPERLIQUID.value, level, message, context)


def log_agents(level: str, message: str, **context):
    get_logger().log(Platform.AGENTS.value, level, message, context)


def log_system(level: str, message: str, **context):
    get_logger().log(Platform.SYSTEM.value, level, message, context)


# API function for the endpoint
async def get_platform_logs(platform: str, limit: int = 50) -> Dict[str, Any]:
    """Get logs for a platform - used by API endpoint."""
    platform_logger = get_logger()
    
    if platform.lower() == "all":
        # Return logs from all platforms
        all_logs = []
        for p in Platform:
            logs = platform_logger.get_logs(p.value, limit=limit // len(Platform))
            all_logs.extend(logs)
        # Sort by timestamp
        all_logs.sort(key=lambda x: x["timestamp"], reverse=True)
        return {
            "platform": "all",
            "logs": all_logs[:limit],
            "stats": platform_logger.get_stats(),
        }
    else:
        return {
            "platform": platform,
            "logs": platform_logger.get_logs(platform, limit=limit),
            "stats": platform_logger.get_stats().get(platform.lower(), {}),
        }
