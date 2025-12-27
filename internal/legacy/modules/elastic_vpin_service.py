"""
Elastic VPIN (Volume-Synchronized Probability of Informed Trading) Service

This service provides intelligent scaling and fallback capabilities for VPIN analysis:
- Monitors API throttling and automatically switches to fallback models
- Dynamically scales compute resources based on market conditions
- Implements circuit breaker patterns for resilient operation
- Provides cost-effective alternatives when TPU resources are constrained

Key Features:
- Multi-model fallback system (TPU → GPU → CPU)
- Intelligent resource scaling based on market volatility
- Circuit breaker protection against API failures
- Cost optimization through resource pooling
- Real-time performance monitoring and adjustment
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .circuit_breaker import CircuitBreaker
from .vertex_ai_client import VertexAIClient

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """Model performance tiers for elastic scaling"""

    TPU_OPTIMIZED = "tpu"  # Highest performance, highest cost
    GPU_ACCELERATED = "gpu"  # Medium performance, medium cost
    CPU_FALLBACK = "cpu"  # Basic performance, lowest cost


class ScalingMode(Enum):
    """Resource scaling modes"""

    CONSERVATIVE = "conservative"  # Minimal scaling, cost-focused
    BALANCED = "balanced"  # Adaptive scaling based on market
    AGGRESSIVE = "aggressive"  # Maximum performance, higher cost


@dataclass
class ResourceMetrics:
    """Real-time resource utilization metrics"""

    cpu_usage: float
    memory_usage: float
    gpu_utilization: Optional[float]
    api_call_count: int
    throttling_events: int
    average_latency: float
    cost_per_hour: float


@dataclass
class ModelPerformance:
    """Performance metrics for different model configurations"""

    tier: ModelTier
    throughput: float  # predictions per second
    latency: float  # milliseconds per prediction
    accuracy: float  # prediction accuracy score
    cost_efficiency: float  # performance per dollar


class ElasticVPINService:
    """
    Intelligent VPIN service with elastic scaling and fallback capabilities.

    Provides high-frequency volume analysis with automatic resource optimization
    and multi-tier fallback system for maximum reliability and cost efficiency.
    """

    def __init__(
        self,
        vertex_client: VertexAIClient,
        scaling_mode: ScalingMode = ScalingMode.BALANCED,
        max_concurrent_requests: int = 100,
        circuit_breaker_threshold: int = 5,
    ):
        self.vertex_client = vertex_client
        self.scaling_mode = scaling_mode
        self.max_concurrent_requests = max_concurrent_requests

        # Circuit breakers for different failure modes
        self.api_circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold,
            recovery_timeout=300,  # 5 minutes
            name="vpin_api_breaker",
        )

        self.tpu_circuit_breaker = CircuitBreaker(
            failure_threshold=3, recovery_timeout=600, name="vpin_tpu_breaker"  # 10 minutes
        )

        # Model performance tracking
        self.model_performance: Dict[ModelTier, ModelPerformance] = {
            ModelTier.TPU_OPTIMIZED: ModelPerformance(
                tier=ModelTier.TPU_OPTIMIZED,
                throughput=500,  # predictions/sec
                latency=50,  # ms
                accuracy=0.95,
                cost_efficiency=85,
            ),
            ModelTier.GPU_ACCELERATED: ModelPerformance(
                tier=ModelTier.GPU_ACCELERATED,
                throughput=150,
                latency=150,
                accuracy=0.92,
                cost_efficiency=65,
            ),
            ModelTier.CPU_FALLBACK: ModelPerformance(
                tier=ModelTier.CPU_FALLBACK,
                throughput=50,
                latency=400,
                accuracy=0.88,
                cost_efficiency=40,
            ),
        }

        # Current operational state
        self.current_tier = ModelTier.TPU_OPTIMIZED
        self.active_requests = 0
        self.resource_metrics = ResourceMetrics(
            cpu_usage=0.0,
            memory_usage=0.0,
            gpu_utilization=None,
            api_call_count=0,
            throttling_events=0,
            average_latency=0.0,
            cost_per_hour=0.0,
        )

        # Scaling parameters
        self.scale_up_threshold = 0.8  # 80% utilization
        self.scale_down_threshold = 0.3  # 30% utilization
        self.throttling_threshold = 10  # API throttling events per minute

        # Thread pool for CPU fallback operations
        self.cpu_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="vpin-cpu")

        logger.info(f"🧠 Elastic VPIN Service initialized with {scaling_mode.value} scaling mode")

    async def analyze_volume_batch(
        self, volume_data: List[Dict[str, Any]], market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze volume data with intelligent scaling and fallback.

        Automatically selects optimal compute tier based on:
        - Market volatility and data volume
        - Current resource utilization
        - API throttling status
        - Cost optimization goals
        """

        # Determine optimal tier based on market conditions and load
        optimal_tier = await self._determine_optimal_tier(market_conditions)

        # Scale to optimal tier if different from current
        if optimal_tier != self.current_tier:
            await self._scale_to_tier(optimal_tier)

        # Execute analysis with circuit breaker protection
        result = await self.api_circuit_breaker.call(
            self._execute_analysis, volume_data, market_conditions
        )

        # Update performance metrics
        await self._update_metrics(result)

        return result

    async def _determine_optimal_tier(self, market_conditions: Dict[str, Any]) -> ModelTier:
        """
        Determine the optimal model tier based on market conditions and system state.
        """

        # High volatility or large data volumes favor TPU
        volatility = market_conditions.get("volatility_index", 0.5)
        data_volume = market_conditions.get("batch_size", 100)

        # Check API throttling status
        throttling_rate = self.resource_metrics.throttling_events / max(
            1, time.time() - getattr(self, "_last_throttle_check", 0)
        )

        # Conservative mode prioritizes cost
        if self.scaling_mode == ScalingMode.CONSERVATIVE:
            if throttling_rate > self.throttling_threshold:
                return ModelTier.CPU_FALLBACK
            return ModelTier.GPU_ACCELERATED

        # Aggressive mode prioritizes performance
        elif self.scaling_mode == ScalingMode.AGGRESSIVE:
            if volatility > 0.8 or data_volume > 1000:
                return ModelTier.TPU_OPTIMIZED
            return ModelTier.GPU_ACCELERATED

        # Balanced mode (default) - adaptive scaling
        else:
            # TPU for high-demand scenarios
            if (volatility > 0.7 or data_volume > 500) and not self.tpu_circuit_breaker.is_open:
                return ModelTier.TPU_OPTIMIZED

            # GPU for moderate demand
            if volatility > 0.4 or throttling_rate < self.throttling_threshold:
                return ModelTier.GPU_ACCELERATED

            # CPU fallback for cost optimization or when other tiers are unavailable
            return ModelTier.CPU_FALLBACK

    async def _scale_to_tier(self, target_tier: ModelTier) -> None:
        """
        Scale resources to target tier with graceful transition.
        """

        logger.info(
            f"🔄 Scaling VPIN service from {self.current_tier.value} to {target_tier.value}"
        )

        # Graceful shutdown of current tier resources
        if self.current_tier == ModelTier.TPU_OPTIMIZED:
            await self._shutdown_tpu_resources()
        elif self.current_tier == ModelTier.GPU_ACCELERATED:
            await self._shutdown_gpu_resources()

        # Initialize new tier resources
        if target_tier == ModelTier.TPU_OPTIMIZED:
            await self._initialize_tpu_resources()
        elif target_tier == ModelTier.GPU_ACCELERATED:
            await self._initialize_gpu_resources()
        # CPU tier doesn't need special initialization

        self.current_tier = target_tier
        logger.info(f"✅ Successfully scaled to {target_tier.value} tier")

    async def _execute_analysis(
        self, volume_data: List[Dict[str, Any]], market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute VPIN analysis using the current tier's optimal method.
        """

        start_time = time.time()

        try:
            if self.current_tier == ModelTier.TPU_OPTIMIZED:
                result = await self._execute_tpu_analysis(volume_data, market_conditions)
            elif self.current_tier == ModelTier.GPU_ACCELERATED:
                result = await self._execute_gpu_analysis(volume_data, market_conditions)
            else:
                result = await self._execute_cpu_analysis(volume_data, market_conditions)

            # Record successful execution
            execution_time = time.time() - start_time
            await self._record_execution_metrics(execution_time, success=True)

            return result

        except Exception as e:
            # Record failed execution and trigger fallback
            execution_time = time.time() - start_time
            await self._record_execution_metrics(execution_time, success=False)

            logger.warning(f"❌ Analysis failed on {self.current_tier.value} tier: {e}")

            # Trigger automatic fallback to lower tier
            if self.current_tier == ModelTier.TPU_OPTIMIZED:
                await self._scale_to_tier(ModelTier.GPU_ACCELERATED)
                return await self._execute_analysis(volume_data, market_conditions)
            elif self.current_tier == ModelTier.GPU_ACCELERATED:
                await self._scale_to_tier(ModelTier.CPU_FALLBACK)
                return await self._execute_analysis(volume_data, market_conditions)
            else:
                # CPU tier failed - return basic analysis
                return await self._execute_basic_fallback(volume_data, market_conditions)

    async def _execute_tpu_analysis(
        self, volume_data: List[Dict[str, Any]], market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute high-performance TPU-accelerated VPIN analysis"""
        # Use Vertex AI with TPU optimization for maximum throughput
        return await self.vertex_client.predict_vpin_tpu(volume_data, market_conditions)

    async def _execute_gpu_analysis(
        self, volume_data: List[Dict[str, Any]], market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute GPU-accelerated VPIN analysis"""
        # Use Vertex AI GPU instances for balanced performance/cost
        return await self.vertex_client.predict_vpin_gpu(volume_data, market_conditions)

    async def _execute_cpu_analysis(
        self, volume_data: List[Dict[str, Any]], market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute CPU-based VPIN analysis with thread pool"""
        # Use thread pool for CPU-bound operations
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.cpu_executor, self._cpu_vpin_calculation, volume_data, market_conditions
        )

    def _cpu_vpin_calculation(
        self, volume_data: List[Dict[str, Any]], market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """CPU-based VPIN calculation (fallback method)"""
        # Implement basic VPIN calculation without ML models
        # This provides minimal functionality when ML models are unavailable

        total_volume = sum(item.get("volume", 0) for item in volume_data)
        buy_volume = sum(item.get("buy_volume", 0) for item in volume_data)
        sell_volume = sum(item.get("sell_volume", 0) for item in volume_data)

        # Simple VPIN approximation
        imbalance = abs(buy_volume - sell_volume) / max(total_volume, 1)
        vpin_score = min(imbalance * 100, 100)  # Scale to 0-100

        return {
            "vpin_score": vpin_score,
            "confidence": 0.7,  # Lower confidence for fallback method
            "method": "cpu_fallback",
            "timestamp": time.time(),
            "market_regime": "unknown",  # Cannot determine without ML
        }

    async def _execute_basic_fallback(
        self, volume_data: List[Dict[str, Any]], market_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Ultimate fallback when all ML methods fail"""
        logger.warning("🚨 All ML methods failed, using statistical fallback")

        # Return neutral/safe VPIN score
        return {
            "vpin_score": 50.0,  # Neutral score
            "confidence": 0.5,  # Low confidence
            "method": "statistical_fallback",
            "timestamp": time.time(),
            "market_regime": "neutral",
            "warning": "ML models unavailable, using statistical approximation",
        }

    async def _initialize_tpu_resources(self) -> None:
        """Initialize TPU resources and warm up models"""
        try:
            await self.vertex_client.initialize_tpu_models()
            logger.info("✅ TPU resources initialized")
        except Exception as e:
            logger.error(f"❌ TPU initialization failed: {e}")
            self.tpu_circuit_breaker.record_failure()
            raise

    async def _initialize_gpu_resources(self) -> None:
        """Initialize GPU resources"""
        try:
            await self.vertex_client.initialize_gpu_models()
            logger.info("✅ GPU resources initialized")
        except Exception as e:
            logger.error(f"❌ GPU initialization failed: {e}")
            raise

    async def _shutdown_tpu_resources(self) -> None:
        """Gracefully shutdown TPU resources"""
        try:
            await self.vertex_client.shutdown_tpu_models()
            logger.info("✅ TPU resources shut down")
        except Exception as e:
            logger.warning(f"⚠️ TPU shutdown error: {e}")

    async def _shutdown_gpu_resources(self) -> None:
        """Gracefully shutdown GPU resources"""
        try:
            await self.vertex_client.shutdown_gpu_models()
            logger.info("✅ GPU resources shut down")
        except Exception as e:
            logger.warning(f"⚠️ GPU shutdown error: {e}")

    async def _update_metrics(self, result: Dict[str, Any]) -> None:
        """Update resource utilization metrics"""
        # Update API call count
        self.resource_metrics.api_call_count += 1

        # Update average latency (exponential moving average)
        if "latency" in result:
            alpha = 0.1  # Smoothing factor
            self.resource_metrics.average_latency = (
                alpha * result["latency"] + (1 - alpha) * self.resource_metrics.average_latency
            )

        # Check for throttling indicators
        if result.get("throttled", False):
            self.resource_metrics.throttling_events += 1

    async def _record_execution_metrics(self, execution_time: float, success: bool) -> None:
        """Record execution performance metrics"""
        # Update circuit breaker state
        if success:
            self.api_circuit_breaker.record_success()
        else:
            self.api_circuit_breaker.record_failure()

    async def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive service status and metrics"""
        return {
            "current_tier": self.current_tier.value,
            "scaling_mode": self.scaling_mode.value,
            "active_requests": self.active_requests,
            "resource_metrics": {
                "cpu_usage": self.resource_metrics.cpu_usage,
                "memory_usage": self.resource_metrics.memory_usage,
                "gpu_utilization": self.resource_metrics.gpu_utilization,
                "api_call_count": self.resource_metrics.api_call_count,
                "throttling_events": self.resource_metrics.throttling_events,
                "average_latency": self.resource_metrics.average_latency,
                "cost_per_hour": self.resource_metrics.cost_per_hour,
            },
            "circuit_breakers": {
                "api_breaker": {
                    "state": self.api_circuit_breaker.state.name,
                    "failure_count": self.api_circuit_breaker.failure_count,
                    "is_open": self.api_circuit_breaker.is_open,
                },
                "tpu_breaker": {
                    "state": self.tpu_circuit_breaker.state.name,
                    "failure_count": self.tpu_circuit_breaker.failure_count,
                    "is_open": self.tpu_circuit_breaker.is_open,
                },
            },
            "model_performance": {
                tier.value: {
                    "throughput": perf.throughput,
                    "latency": perf.latency,
                    "accuracy": perf.accuracy,
                    "cost_efficiency": perf.cost_efficiency,
                }
                for tier, perf in self.model_performance.items()
            },
        }

    async def optimize_resource_allocation(self) -> None:
        """
        Continuously optimize resource allocation based on:
        - Market conditions
        - Performance metrics
        - Cost constraints
        - System load
        """
        while True:
            try:
                # Analyze current performance
                status = await self.get_service_status()

                # Determine if scaling is needed
                cpu_usage = status["resource_metrics"]["cpu_usage"]
                throttling_rate = status["resource_metrics"]["throttling_events"] / 60  # per minute

                scaling_decision = None

                if self.scaling_mode == ScalingMode.CONSERVATIVE:
                    # Scale down if utilization is low and no throttling
                    if cpu_usage < 0.2 and throttling_rate < 1:
                        scaling_decision = ModelTier.CPU_FALLBACK
                elif self.scaling_mode == ScalingMode.AGGRESSIVE:
                    # Scale up if utilization is high or throttling occurs
                    if cpu_usage > 0.7 or throttling_rate > 5:
                        scaling_decision = ModelTier.TPU_OPTIMIZED
                else:  # Balanced
                    if (
                        cpu_usage > self.scale_up_threshold
                        or throttling_rate > self.throttling_threshold
                    ):
                        scaling_decision = (
                            ModelTier.TPU_OPTIMIZED
                            if cpu_usage > 0.8
                            else ModelTier.GPU_ACCELERATED
                        )
                    elif cpu_usage < self.scale_down_threshold and throttling_rate < 1:
                        scaling_decision = ModelTier.CPU_FALLBACK

                # Execute scaling if needed
                if scaling_decision and scaling_decision != self.current_tier:
                    logger.info(
                        f"🎯 Resource optimization: scaling from {self.current_tier.value} to {scaling_decision.value}"
                    )
                    await self._scale_to_tier(scaling_decision)

            except Exception as e:
                logger.error(f"❌ Resource optimization error: {e}")

            # Check every 5 minutes
            await asyncio.sleep(300)
