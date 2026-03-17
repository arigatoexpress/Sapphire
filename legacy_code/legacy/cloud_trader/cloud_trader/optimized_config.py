"""Optimized configuration for cloud native AI upgrades."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OptimizedSettings(BaseSettings):
    """Optimized runtime configuration with performance enhancements."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )

    # GPU & AI Inference Optimization
    model_quantization: str = Field(
        default="4bit", description="Model quantization level (none, 8bit, 4bit)"
    )
    gpu_memory_fraction: float = Field(
        default=0.7, ge=0.1, le=1.0, description="Fraction of GPU memory to use"
    )
    inference_batch_size: int = Field(
        default=8, ge=1, le=64, description="Batch size for inference operations"
    )
    cuda_launch_blocking: bool = Field(
        default=False, description="Enable synchronous CUDA operations"
    )

    # CPU & Compute Optimization
    numba_threading_layer: str = Field(
        default="omp", description="Numba threading layer (omp, tbb, workqueue)"
    )
    omp_num_threads: int = Field(default=4, ge=1, le=16, description="OpenMP thread count")
    python_optimize: bool = Field(default=True, description="Enable Python bytecode optimization")
    vectorize_operations: bool = Field(default=True, description="Enable SIMD vectorization")

    # Memory Management Optimization
    memory_cache_enabled: bool = Field(default=True, description="Enable in-memory caching")
    memory_cache_size: str = Field(default="512MB", description="Memory cache size limit")
    redis_maxmemory: str = Field(default="512mb", description="Redis max memory limit")
    redis_maxmemory_policy: str = Field(default="allkeys-lru", description="Redis eviction policy")

    # Network & Communication Optimization
    message_compression: bool = Field(default=True, description="Enable message compression")
    connection_pool_size: int = Field(default=50, ge=10, le=200, description="Connection pool size")
    message_batch_size: int = Field(default=100, ge=10, le=1000, description="Message batch size")
    network_timeout: float = Field(
        default=5.0, ge=1.0, le=30.0, description="Network timeout in seconds"
    )

    # Async & Concurrency Optimization
    async_workers: int = Field(default=16, ge=4, le=64, description="Number of async workers")
    async_io_workers: int = Field(default=8, ge=2, le=32, description="Async I/O worker count")

    # BigQuery Optimization
    bigquery_batch_size: int = Field(
        default=500, ge=100, le=1000, description="BigQuery batch insert size"
    )
    bigquery_compression: str = Field(default="LZ4", description="BigQuery data compression")
    bigquery_partitioning: str = Field(default="DAY", description="BigQuery partitioning strategy")

    # Caching Strategy
    cache_hierarchy_enabled: bool = Field(default=True, description="Enable multi-level caching")
    l1_cache_ttl: int = Field(default=60, ge=10, le=3600, description="L1 cache TTL in seconds")
    l2_cache_ttl: int = Field(default=300, ge=60, le=7200, description="L2 cache TTL in seconds")

    # Resource Optimization
    resource_optimization_enabled: bool = Field(
        default=True, description="Enable resource optimization"
    )
    adaptive_scaling_enabled: bool = Field(default=True, description="Enable adaptive scaling")
    cost_optimization_enabled: bool = Field(
        default=True, description="Enable cost optimization features"
    )

    @field_validator("gpu_memory_fraction")
    @classmethod
    def validate_gpu_memory_fraction(cls, v: float) -> float:
        """Validate GPU memory fraction is reasonable."""
        if v > 0.9:
            raise ValueError("GPU memory fraction should not exceed 90%")
        return v

    @field_validator("omp_num_threads")
    @classmethod
    def validate_omp_threads(cls, v: int) -> int:
        """Validate OpenMP thread count based on CPU cores."""
        import multiprocessing

        max_threads = multiprocessing.cpu_count()
        if v > max_threads:
            raise ValueError(f"OMP threads ({v}) exceeds CPU cores ({max_threads})")
        return v

    def get_cache_config(self) -> Dict[str, Any]:
        """Get optimized cache configuration."""
        return {
            "enabled": self.cache_hierarchy_enabled,
            "l1_ttl": self.l1_cache_ttl,
            "l2_ttl": self.l2_cache_ttl,
            "memory_size": self.memory_cache_size,
            "redis_config": {
                "maxmemory": self.redis_maxmemory,
                "maxmemory_policy": self.redis_maxmemory_policy,
            },
        }

    def get_inference_config(self) -> Dict[str, Any]:
        """Get optimized inference configuration."""
        return {
            "quantization": self.model_quantization,
            "gpu_memory_fraction": self.gpu_memory_fraction,
            "batch_size": self.inference_batch_size,
            "cuda_launch_blocking": self.cuda_launch_blocking,
        }

    def get_network_config(self) -> Dict[str, Any]:
        """Get optimized network configuration."""
        return {
            "compression": self.message_compression,
            "connection_pool_size": self.connection_pool_size,
            "batch_size": self.message_batch_size,
            "timeout": self.network_timeout,
        }

    def get_performance_config(self) -> Dict[str, Any]:
        """Get comprehensive performance configuration."""
        try:
            return {
                "cpu": {
                    "numba_threading": self.numba_threading_layer,
                    "omp_threads": self.omp_num_threads,
                    "python_optimize": self.python_optimize,
                    "vectorize": self.vectorize_operations,
                },
                "memory": {
                    "cache_enabled": self.memory_cache_enabled,
                    "cache_size": self.memory_cache_size,
                },
                "async": {
                    "workers": self.async_workers,
                    "io_workers": self.async_io_workers,
                },
                "bigquery": {
                    "batch_size": self.bigquery_batch_size,
                    "compression": self.bigquery_compression,
                    "partitioning": self.bigquery_partitioning,
                },
            }
        except Exception as e:
            logger.warning(f"Failed to get performance config: {e}")
            return {}


# Global optimized settings instance
_optimized_settings: Optional[OptimizedSettings] = None


def get_optimized_settings() -> OptimizedSettings:
    """Get or create optimized settings instance."""
    global _optimized_settings
    if _optimized_settings is None:
        _optimized_settings = OptimizedSettings()
    return _optimized_settings


def apply_performance_optimizations():
    """Apply all performance optimizations globally."""
    try:
        settings = get_optimized_settings()

        # Validate settings before applying
        if not settings:
            logger.error("❌ Failed to load optimized settings")
            return False

        # Set environment variables for optimizations
        env_updates = {
            "NUMBA_THREADING_LAYER": settings.numba_threading_layer,
            "OMP_NUM_THREADS": str(settings.omp_num_threads),
            "PYTHONOPTIMIZE": "1" if settings.python_optimize else "0",
        }

        # Safely update environment variables
        for key, value in env_updates.items():
            try:
                os.environ[key] = value
            except (OSError, ValueError) as e:
                logger.warning(f"Failed to set environment variable {key}: {e}")

        # Configure GPU memory fraction
        try:
            if settings.gpu_memory_fraction < 1.0:
                os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Ensure GPU is available
                os.environ["PYTORCH_CUDA_ALLOC_CONF"] = f"max_split_size_mb:512"
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to configure GPU settings: {e}")

        logger.info("🚀 Applied performance optimizations:")
        logger.info(f"  • GPU Memory: {settings.gpu_memory_fraction * 100}%")
        logger.info(f"  • OMP Threads: {settings.omp_num_threads}")
        logger.info(f"  • Batch Size: {settings.inference_batch_size}")
        logger.info(f"  • Connection Pool: {settings.connection_pool_size}")
        logger.info(f"  • Async Workers: {settings.async_workers}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to apply performance optimizations: {e}")
        return False


if __name__ == "__main__":
    # Test configuration loading
    settings = get_optimized_settings()
    print("✅ Optimized settings loaded successfully")
    print(f"GPU Memory Fraction: {settings.gpu_memory_fraction}")
    print(f"Inference Batch Size: {settings.inference_batch_size}")
    print(f"Connection Pool Size: {settings.connection_pool_size}")
