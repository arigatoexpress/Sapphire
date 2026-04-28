#!/usr/bin/env python3
"""
Performance Monitor for Kimi-Claw Telegram Bot
Tracks response times, CPU, memory, and system health
"""

import asyncio
import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import psutil


@dataclass
class MetricSnapshot:
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    disk_percent: float
    load_avg: list[float]
    kimi_response_time: float | None = None
    telegram_latency: float | None = None


class PerformanceMonitor:
    """Monitor system and application performance."""

    def __init__(self, history_size: int = 1000):
        self.metrics_history: deque = deque(maxlen=history_size)
        self.alert_thresholds = {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0,
            'kimi_response_time': 30.0,  # seconds
        }
        self.alerts: list[dict] = []
        self.log_file = Path("performance.log")

    def get_system_metrics(self) -> dict:
        """Get current system metrics."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load_avg = list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else [0, 0, 0]

        return {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_mb': memory.used / (1024 * 1024),
            'disk_percent': disk.percent,
            'load_avg': load_avg,
        }

    async def test_kimi_response_time(self) -> float | None:
        """Test Kimi CLI response time."""
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "kimi", "--yes", "--prompt", "Say OK",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            elapsed = time.time() - start
            return elapsed if proc.returncode == 0 else None
        except TimeoutError:
            return None
        except Exception as e:
            print(f"Error testing Kimi: {e}")
            return None

    def check_alerts(self, metrics: MetricSnapshot):
        """Check if any metrics exceed thresholds."""
        alerts_triggered = []

        if metrics.cpu_percent > self.alert_thresholds['cpu_percent']:
            alerts_triggered.append(f"High CPU: {metrics.cpu_percent:.1f}%")

        if metrics.memory_percent > self.alert_thresholds['memory_percent']:
            alerts_triggered.append(f"High Memory: {metrics.memory_percent:.1f}%")

        if metrics.disk_percent > self.alert_thresholds['disk_percent']:
            alerts_triggered.append(f"High Disk: {metrics.disk_percent:.1f}%")

        if metrics.kimi_response_time and metrics.kimi_response_time > self.alert_thresholds['kimi_response_time']:
            alerts_triggered.append(f"Slow Kimi: {metrics.kimi_response_time:.1f}s")

        if alerts_triggered:
            alert = {
                'timestamp': datetime.now().isoformat(),
                'alerts': alerts_triggered,
                'metrics': asdict(metrics)
            }
            self.alerts.append(alert)
            return alert
        return None

    def log_metrics(self, metrics: MetricSnapshot):
        """Log metrics to file."""
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(asdict(metrics)) + '\n')

    def get_stats(self, minutes: int = 10) -> dict:
        """Get statistics for the last N minutes."""
        cutoff = time.time() - (minutes * 60)
        recent = [m for m in self.metrics_history if m.timestamp > cutoff]

        if not recent:
            return {'error': 'No data available'}

        cpu_values = [m.cpu_percent for m in recent]
        memory_values = [m.memory_percent for m in recent]
        kimi_times = [m.kimi_response_time for m in recent if m.kimi_response_time]

        stats = {
            'period_minutes': minutes,
            'samples': len(recent),
            'cpu': {
                'avg': sum(cpu_values) / len(cpu_values),
                'max': max(cpu_values),
                'min': min(cpu_values),
            },
            'memory': {
                'avg': sum(memory_values) / len(memory_values),
                'max': max(memory_values),
                'min': min(memory_values),
            },
            'alerts': len([a for a in self.alerts if datetime.fromisoformat(a['timestamp']).timestamp() > cutoff])
        }

        if kimi_times:
            stats['kimi_response_time'] = {
                'avg': sum(kimi_times) / len(kimi_times),
                'max': max(kimi_times),
                'min': min(kimi_times),
            }

        return stats

    async def monitor_loop(self, interval: int = 30):
        """Main monitoring loop."""
        print(f"🔍 Performance monitor started (interval: {interval}s)")

        while True:
            try:
                # Get system metrics
                sys_metrics = self.get_system_metrics()

                # Test Kimi response time
                kimi_time = await self.test_kimi_response_time()

                # Create snapshot
                snapshot = MetricSnapshot(
                    timestamp=time.time(),
                    kimi_response_time=kimi_time,
                    **sys_metrics
                )

                # Store and log
                self.metrics_history.append(snapshot)
                self.log_metrics(snapshot)

                # Check alerts
                alert = self.check_alerts(snapshot)
                if alert:
                    print(f"⚠️  ALERT: {', '.join(alert['alerts'])}")

                # Print status every 2 minutes
                if len(self.metrics_history) % 4 == 0:
                    stats = self.get_stats(minutes=2)
                    print(f"📊 CPU: {stats['cpu']['avg']:.1f}% | "
                          f"Mem: {stats['memory']['avg']:.1f}% | "
                          f"Kimi: {stats.get('kimi_response_time', {}).get('avg', 0):.1f}s")

                await asyncio.sleep(interval)

            except Exception as e:
                print(f"Monitor error: {e}")
                await asyncio.sleep(interval)


def print_report(monitor: PerformanceMonitor):
    """Print performance report."""
    print("\n" + "=" * 60)
    print("📈 PERFORMANCE REPORT")
    print("=" * 60)

    # Last 10 minutes
    stats = monitor.get_stats(minutes=10)
    if 'error' in stats:
        print("No data yet...")
        return

    print(f"\n📊 Last {stats['period_minutes']} minutes:")
    print(f"  Samples: {stats['samples']}")
    print("\n  CPU Usage:")
    print(f"    Average: {stats['cpu']['avg']:.1f}%")
    print(f"    Peak:    {stats['cpu']['max']:.1f}%")
    print("\n  Memory Usage:")
    print(f"    Average: {stats['memory']['avg']:.1f}%")
    print(f"    Peak:    {stats['memory']['max']:.1f}%")

    if 'kimi_response_time' in stats:
        print("\n  Kimi Response Time:")
        print(f"    Average: {stats['kimi_response_time']['avg']:.2f}s")
        print(f"    Peak:    {stats['kimi_response_time']['max']:.2f}s")
        print(f"    Best:    {stats['kimi_response_time']['min']:.2f}s")

    print(f"\n  Alerts: {stats['alerts']}")

    # Recent alerts
    if monitor.alerts:
        print("\n⚠️  Recent Alerts:")
        for alert in monitor.alerts[-5:]:
            print(f"    {alert['timestamp']}: {', '.join(alert['alerts'])}")

    # Recommendations
    print("\n💡 Recommendations:")
    if stats['cpu']['avg'] > 70:
        print("  - High CPU usage detected. Consider offloading tasks to slave nodes.")
    if stats['memory']['avg'] > 75:
        print("  - High memory usage. Check for memory leaks or increase RAM.")
    if 'kimi_response_time' in stats and stats['kimi_response_time']['avg'] > 20:
        print("  - Slow Kimi responses. Check network or restart Kimi CLI.")
    if stats['alerts'] == 0:
        print("  - System running smoothly! No action needed.")

    print("=" * 60)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Performance Monitor for Kimi-Claw')
    parser.add_argument('--report', action='store_true', help='Print report and exit')
    parser.add_argument('--interval', type=int, default=30, help='Monitoring interval (seconds)')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')

    args = parser.parse_args()

    monitor = PerformanceMonitor()

    if args.report:
        print_report(monitor)
        return

    if args.daemon or True:  # Default to daemon mode
        try:
            await monitor.monitor_loop(interval=args.interval)
        except KeyboardInterrupt:
            print("\n\n📊 Final Report:")
            print_report(monitor)


if __name__ == '__main__':
    asyncio.run(main())
