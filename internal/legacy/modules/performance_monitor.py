"""
Performance monitoring and optimization for high-frequency trading.
"""

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import psutil

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Real-time performance metrics."""

    timestamp: datetime = field(default_factory=datetime.now)

    # System metrics
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_io: float = 0.0
    network_io: float = 0.0

    # Application metrics
    active_connections: int = 0
    queue_depth: int = 0
    request_rate: float = 0.0
    error_rate: float = 0.0

    # Trading metrics
    trades_per_second: float = 0.0
    latency_p95: float = 0.0
    throughput: float = 0.0

    # AI metrics
    inference_time: float = 0.0
    model_accuracy: float = 0.0


@dataclass
class PerformanceThresholds:
    """Performance threshold configurations."""

    max_cpu_usage: float = 80.0
    max_memory_usage: float = 85.0
    max_latency_p95: float = 100.0  # ms
    min_throughput: float = 100.0  # trades/second
    max_error_rate: float = 5.0  # percentage
    max_queue_depth: int = 1000


class PerformanceMonitor:
    """Real-time performance monitoring and optimization."""

    def __init__(self, thresholds: Optional[PerformanceThresholds] = None):
        self.thresholds = thresholds or PerformanceThresholds()
        self.metrics_history: deque = deque(maxlen=1000)
        self.alerts: List[Dict[str, Any]] = []
        self.monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None

        # Performance counters
        self.request_count = 0
        self.error_count = 0
        self.trade_count = 0
        self.latency_samples: deque = deque(maxlen=1000)

        # Lock for thread safety
        self._lock = threading.Lock()

    def start_monitoring(self):
        """Start performance monitoring."""
        if self.monitoring_active:
            logger.warning("Performance monitoring already active")
            return

        self.monitoring_active = True
        self._monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Performance monitoring started")

    def stop_monitoring(self):
        """Stop performance monitoring."""
        self.monitoring_active = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Performance monitoring stopped")

    def record_request(self, latency_ms: Optional[float] = None):
        """Record an API request."""
        with self._lock:
            self.request_count += 1
            if latency_ms is not None:
                self.latency_samples.append(latency_ms)

    def record_error(self):
        """Record an error."""
        with self._lock:
            self.error_count += 1

    def record_trade(self):
        """Record a trade execution."""
        with self._lock:
            self.trade_count += 1

    def _monitoring_loop(self):
        """Main monitoring loop."""
        last_check = time.time()
        last_request_count = 0
        last_error_count = 0
        last_trade_count = 0

        while self.monitoring_active:
            try:
                current_time = time.time()

                # Collect metrics every second
                if current_time - last_check >= 1.0:
                    metrics = self._collect_metrics()

                    # Calculate rates
                    time_diff = current_time - last_check
                    with self._lock:
                        metrics.request_rate = (self.request_count - last_request_count) / time_diff
                        metrics.error_rate = (
                            (self.error_count - last_error_count)
                            / max(self.request_count - last_request_count, 1)
                        ) * 100
                        metrics.trades_per_second = (
                            self.trade_count - last_trade_count
                        ) / time_diff

                        # Calculate latency percentiles
                        if self.latency_samples:
                            sorted_latencies = sorted(self.latency_samples)
                            p95_index = int(len(sorted_latencies) * 0.95)
                            metrics.latency_p95 = sorted_latencies[
                                min(p95_index, len(sorted_latencies) - 1)
                            ]

                        last_request_count = self.request_count
                        last_error_count = self.error_count
                        last_trade_count = self.trade_count

                    # Store metrics
                    self.metrics_history.append(metrics)

                    # Check thresholds and alert
                    self._check_thresholds(metrics)

                    last_check = current_time

                time.sleep(0.1)  # 100ms sleep to reduce CPU usage

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(1)

    def _collect_metrics(self) -> PerformanceMetrics:
        """Collect current system and application metrics."""
        metrics = PerformanceMetrics()

        try:
            # System metrics
            metrics.cpu_usage = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            metrics.memory_usage = memory.percent

            # Disk I/O (simplified)
            disk_io = psutil.disk_io_counters()
            if disk_io:
                metrics.disk_io = disk_io.read_bytes + disk_io.write_bytes

            # Network I/O (simplified)
            net_io = psutil.net_io_counters()
            if net_io:
                metrics.network_io = net_io.bytes_sent + net_io.bytes_recv

        except Exception as e:
            logger.warning(f"Error collecting system metrics: {e}")

        return metrics

    def _check_thresholds(self, metrics: PerformanceMetrics):
        """Check if metrics exceed thresholds and generate alerts."""
        alerts = []

        if metrics.cpu_usage > self.thresholds.max_cpu_usage:
            alerts.append(
                {
                    "type": "cpu_usage",
                    "severity": "high",
                    "message": f"CPU usage {metrics.cpu_usage:.1f}% exceeds threshold {self.thresholds.max_cpu_usage}%",
                    "value": metrics.cpu_usage,
                    "threshold": self.thresholds.max_cpu_usage,
                }
            )

        if metrics.memory_usage > self.thresholds.max_memory_usage:
            alerts.append(
                {
                    "type": "memory_usage",
                    "severity": "high",
                    "message": f"Memory usage {metrics.memory_usage:.1f}% exceeds threshold {self.thresholds.max_memory_usage}%",
                    "value": metrics.memory_usage,
                    "threshold": self.thresholds.max_memory_usage,
                }
            )

        if metrics.latency_p95 > self.thresholds.max_latency_p95:
            alerts.append(
                {
                    "type": "latency",
                    "severity": "medium",
                    "message": f"P95 latency {metrics.latency_p95:.1f}ms exceeds threshold {self.thresholds.max_latency_p95}ms",
                    "value": metrics.latency_p95,
                    "threshold": self.thresholds.max_latency_p95,
                }
            )

        if metrics.trades_per_second < self.thresholds.min_throughput:
            alerts.append(
                {
                    "type": "throughput",
                    "severity": "medium",
                    "message": f"Trading throughput {metrics.trades_per_second:.1f} TPS below minimum {self.thresholds.min_throughput} TPS",
                    "value": metrics.trades_per_second,
                    "threshold": self.thresholds.min_throughput,
                }
            )

        if metrics.error_rate > self.thresholds.max_error_rate:
            alerts.append(
                {
                    "type": "error_rate",
                    "severity": "high",
                    "message": f"Error rate {metrics.error_rate:.1f}% exceeds threshold {self.thresholds.max_error_rate}%",
                    "value": metrics.error_rate,
                    "threshold": self.thresholds.max_error_rate,
                }
            )

        # Store alerts
        for alert in alerts:
            alert["timestamp"] = datetime.now()
            self.alerts.append(alert)
            logger.warning(f"Performance Alert: {alert['message']}")

            # Keep only recent alerts
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-50:]

    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """Get the most recent performance metrics."""
        return self.metrics_history[-1] if self.metrics_history else None

    def get_metrics_history(self, limit: int = 100) -> List[PerformanceMetrics]:
        """Get recent performance metrics history."""
        return list(self.metrics_history)[-limit:]

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get currently active performance alerts."""
        # Return alerts from the last 5 minutes
        cutoff = datetime.now() - timedelta(minutes=5)
        return [alert for alert in self.alerts if alert["timestamp"] > cutoff]

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of performance statistics."""
        if not self.metrics_history:
            return {}

        recent_metrics = list(self.metrics_history)[-100:]  # Last 100 samples

        summary = {
            "avg_cpu_usage": sum(m.cpu_usage for m in recent_metrics) / len(recent_metrics),
            "avg_memory_usage": sum(m.memory_usage for m in recent_metrics) / len(recent_metrics),
            "avg_latency_p95": sum(m.latency_p95 for m in recent_metrics) / len(recent_metrics),
            "avg_request_rate": sum(m.request_rate for m in recent_metrics) / len(recent_metrics),
            "avg_trades_per_second": sum(m.trades_per_second for m in recent_metrics)
            / len(recent_metrics),
            "avg_error_rate": sum(m.error_rate for m in recent_metrics) / len(recent_metrics),
            "total_requests": self.request_count,
            "total_trades": self.trade_count,
            "total_errors": self.error_count,
            "active_alerts": len(self.get_active_alerts()),
        }

        return summary

    def optimize_performance(self) -> Dict[str, Any]:
        """Generate performance optimization recommendations."""
        summary = self.get_performance_summary()
        recommendations = []

        if summary.get("avg_cpu_usage", 0) > 70:
            recommendations.append(
                {
                    "type": "cpu_optimization",
                    "priority": "high",
                    "action": "Consider increasing CPU allocation or optimizing compute-intensive operations",
                    "impact": "Reduce CPU bottlenecks",
                }
            )

        if summary.get("avg_memory_usage", 0) > 80:
            recommendations.append(
                {
                    "type": "memory_optimization",
                    "priority": "high",
                    "action": "Implement memory pooling or reduce data retention periods",
                    "impact": "Prevent out-of-memory errors",
                }
            )

        if summary.get("avg_latency_p95", 0) > 50:
            recommendations.append(
                {
                    "type": "latency_optimization",
                    "priority": "medium",
                    "action": "Optimize database queries and implement caching strategies",
                    "impact": "Improve response times",
                }
            )

        if summary.get("avg_error_rate", 0) > 2:
            recommendations.append(
                {
                    "type": "error_handling",
                    "priority": "high",
                    "action": "Review error handling and implement circuit breakers",
                    "impact": "Increase system reliability",
                }
            )

        return {"recommendations": recommendations, "summary": summary}


# Global performance monitor instance
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


# Convenience functions
def record_api_request(latency_ms: Optional[float] = None):
    """Record an API request with optional latency."""
    monitor = get_performance_monitor()
    monitor.record_request(latency_ms)


def record_api_error():
    """Record an API error."""
    monitor = get_performance_monitor()
    monitor.record_error()


def record_trade_execution():
    """Record a successful trade execution."""
    monitor = get_performance_monitor()
    monitor.record_trade()


def start_performance_monitoring():
    """Start the global performance monitoring system."""
    monitor = get_performance_monitor()
    monitor.start_monitoring()


def stop_performance_monitoring():
    """Stop the global performance monitoring system."""
    monitor = get_performance_monitor()
    monitor.stop_monitoring()


def get_performance_status() -> Dict[str, Any]:
    """Get current performance status and recommendations."""
    monitor = get_performance_monitor()
    return monitor.optimize_performance()
