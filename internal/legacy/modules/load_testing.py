"""
Load testing framework for high-frequency trading performance validation.
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class LoadTestConfig:
    """Configuration for load testing."""

    duration_seconds: int = 60
    concurrent_users: int = 10
    requests_per_second: int = 100
    ramp_up_seconds: int = 10
    target_url: str = "http://localhost:8080"
    test_endpoints: List[str] = field(
        default_factory=lambda: ["/healthz", "/market-data", "/portfolio"]
    )


@dataclass
class LoadTestResult:
    """Results from a load test."""

    test_start: datetime
    test_end: datetime
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    response_times: List[float] = field(default_factory=list)
    error_types: Dict[str, int] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return (self.test_end - self.test_start).total_seconds()

    @property
    def requests_per_second(self) -> float:
        return self.total_requests / self.duration if self.duration > 0 else 0

    @property
    def success_rate(self) -> float:
        return self.successful_requests / self.total_requests if self.total_requests > 0 else 0

    @property
    def avg_response_time(self) -> float:
        return statistics.mean(self.response_times) if self.response_times else 0

    @property
    def p95_response_time(self) -> float:
        return np.percentile(self.response_times, 95) if self.response_times else 0

    @property
    def p99_response_time(self) -> float:
        return np.percentile(self.response_times, 99) if self.response_times else 0


class LoadTester:
    """Load testing framework for trading system validation."""

    def __init__(self, config: Optional[LoadTestConfig] = None):
        self.config = config or LoadTestConfig()
        self.session: Optional[aiohttp.ClientSession] = None
        self.results = LoadTestResult(datetime.now(), datetime.now())

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30, connect=5))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def run_load_test(self) -> LoadTestResult:
        """Run the complete load test."""
        logger.info(
            f"Starting load test: {self.config.concurrent_users} users, {self.config.requests_per_second} RPS for {self.config.duration_seconds}s"
        )

        self.results = LoadTestResult(datetime.now(), datetime.now())

        # Create worker tasks
        tasks = []
        for i in range(self.config.concurrent_users):
            task = asyncio.create_task(self._user_worker(i))
            tasks.append(task)

        # Run all workers concurrently
        start_time = time.time()
        await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        self.results.test_end = datetime.now()
        self.results.total_requests = len(self.results.response_times)

        logger.info(f"Load test completed in {end_time - start_time:.2f}s")
        logger.info(
            f"Results: {self.results.total_requests} requests, {self.results.success_rate:.1%} success rate"
        )

        return self.results

    async def _user_worker(self, worker_id: int):
        """Individual user worker for load testing."""
        await asyncio.sleep(worker_id * 0.1)  # Stagger worker starts

        end_time = time.time() + self.config.duration_seconds

        while time.time() < end_time:
            # Select random endpoint
            endpoint = np.random.choice(self.config.test_endpoints)

            # Make request
            await self._make_request(endpoint)

            # Rate limiting - calculate delay to achieve target RPS
            delay = 1.0 / (self.config.requests_per_second / self.config.concurrent_users)
            await asyncio.sleep(delay)

    async def _make_request(self, endpoint: str) -> bool:
        """Make a single request and record results."""
        url = f"{self.config.target_url}{endpoint}"
        start_time = time.time()

        try:
            async with self.session.get(url) as response:
                response_time = time.time() - start_time

                self.results.response_times.append(response_time * 1000)  # Convert to ms

                if response.status == 200:
                    self.results.successful_requests += 1
                    return True
                else:
                    self.results.failed_requests += 1
                    error_type = f"http_{response.status}"
                    self.results.error_types[error_type] = (
                        self.results.error_types.get(error_type, 0) + 1
                    )
                    return False

        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            self.results.response_times.append(response_time * 1000)
            self.results.failed_requests += 1
            self.results.error_types["timeout"] = self.results.error_types.get("timeout", 0) + 1
            return False

        except Exception as e:
            response_time = time.time() - start_time
            self.results.response_times.append(response_time * 1000)
            self.results.failed_requests += 1
            error_type = type(e).__name__
            self.results.error_types[error_type] = self.results.error_types.get(error_type, 0) + 1
            return False

    def generate_report(self, results: LoadTestResult) -> Dict[str, Any]:
        """Generate a comprehensive load test report."""
        report = {
            "test_summary": {
                "duration": results.duration,
                "total_requests": results.total_requests,
                "successful_requests": results.successful_requests,
                "failed_requests": results.failed_requests,
                "requests_per_second": results.requests_per_second,
                "success_rate": results.success_rate,
            },
            "performance_metrics": {
                "avg_response_time_ms": results.avg_response_time,
                "p95_response_time_ms": results.p95_response_time,
                "p99_response_time_ms": results.p99_response_time,
                "min_response_time_ms": (
                    min(results.response_times) if results.response_times else 0
                ),
                "max_response_time_ms": (
                    max(results.response_times) if results.response_times else 0
                ),
            },
            "error_analysis": {
                "error_types": results.error_types,
                "total_errors": results.failed_requests,
            },
            "assessment": self._assess_performance(results),
            "recommendations": self._generate_recommendations(results),
        }

        return report

    def _assess_performance(self, results: LoadTestResult) -> Dict[str, Any]:
        """Assess the performance results."""
        assessment = {
            "overall_rating": "unknown",
            "throughput_status": "unknown",
            "latency_status": "unknown",
            "reliability_status": "unknown",
        }

        # Throughput assessment
        target_rps = self.config.requests_per_second
        actual_rps = results.requests_per_second

        if actual_rps >= target_rps * 0.95:
            assessment["throughput_status"] = "excellent"
        elif actual_rps >= target_rps * 0.80:
            assessment["throughput_status"] = "good"
        elif actual_rps >= target_rps * 0.60:
            assessment["throughput_status"] = "acceptable"
        else:
            assessment["throughput_status"] = "poor"

        # Latency assessment
        avg_latency = results.avg_response_time
        p95_latency = results.p95_response_time

        if p95_latency < 100:  # ms
            assessment["latency_status"] = "excellent"
        elif p95_latency < 500:
            assessment["latency_status"] = "good"
        elif p95_latency < 2000:
            assessment["latency_status"] = "acceptable"
        else:
            assessment["latency_status"] = "poor"

        # Reliability assessment
        success_rate = results.success_rate

        if success_rate >= 0.999:
            assessment["reliability_status"] = "excellent"
        elif success_rate >= 0.995:
            assessment["reliability_status"] = "good"
        elif success_rate >= 0.98:
            assessment["reliability_status"] = "acceptable"
        else:
            assessment["reliability_status"] = "poor"

        # Overall rating
        statuses = [
            assessment["throughput_status"],
            assessment["latency_status"],
            assessment["reliability_status"],
        ]
        if all(s == "excellent" for s in statuses):
            assessment["overall_rating"] = "excellent"
        elif all(s in ["excellent", "good"] for s in statuses):
            assessment["overall_rating"] = "good"
        elif any(s == "poor" for s in statuses):
            assessment["overall_rating"] = "poor"
        else:
            assessment["overall_rating"] = "acceptable"

        return assessment

    def _generate_recommendations(self, results: LoadTestResult) -> List[str]:
        """Generate performance improvement recommendations."""
        recommendations = []

        if results.requests_per_second < self.config.requests_per_second * 0.8:
            recommendations.append("Increase server capacity or optimize request processing")
            recommendations.append("Consider implementing request queuing or rate limiting")

        if results.p95_response_time > 1000:  # 1 second
            recommendations.append("Optimize database queries and implement caching")
            recommendations.append("Consider using async/await patterns for I/O operations")

        if results.success_rate < 0.95:
            recommendations.append("Implement circuit breakers and retry logic")
            recommendations.append("Review error handling and add graceful degradation")

        if results.avg_response_time > 500:
            recommendations.append("Implement response compression and optimize payload sizes")
            recommendations.append("Consider using CDN for static content")

        # Resource-specific recommendations
        timeout_errors = results.error_types.get("timeout", 0)
        if timeout_errors > results.total_requests * 0.01:
            recommendations.append("Increase timeout values or optimize slow endpoints")

        connection_errors = results.error_types.get("ClientConnectorError", 0)
        if connection_errors > 0:
            recommendations.append("Review network configuration and connection pooling")

        return recommendations


# Pre-configured load test scenarios
TRADING_LOAD_TEST = LoadTestConfig(
    duration_seconds=300,  # 5 minutes
    concurrent_users=50,
    requests_per_second=500,
    target_url="http://trading-system-cloud-trader.trading.svc.cluster.local:8080",
    test_endpoints=["/healthz", "/market-data", "/portfolio", "/risk-assessment"],
)

STRESS_TEST = LoadTestConfig(
    duration_seconds=120,  # 2 minutes
    concurrent_users=100,
    requests_per_second=1000,
    target_url="http://trading-system-cloud-trader.trading.svc.cluster.local:8080",
    test_endpoints=["/healthz", "/market-data"],
)


async def run_trading_load_test() -> Dict[str, Any]:
    """Run a comprehensive trading load test."""
    config = TRADING_LOAD_TEST

    async with LoadTester(config) as tester:
        results = await tester.run_load_test()
        report = tester.generate_report(results)

        return report


async def run_stress_test() -> Dict[str, Any]:
    """Run a stress test to find system limits."""
    config = STRESS_TEST

    async with LoadTester(config) as tester:
        results = await tester.run_load_test()
        report = tester.generate_report(results)

        return report


# Utility function for quick load testing
async def quick_load_test(url: str, duration: int = 30, rps: int = 50) -> Dict[str, Any]:
    """Run a quick load test with custom parameters."""
    config = LoadTestConfig(
        duration_seconds=duration, concurrent_users=10, requests_per_second=rps, target_url=url
    )

    async with LoadTester(config) as tester:
        results = await tester.run_load_test()
        return tester.generate_report(results)
