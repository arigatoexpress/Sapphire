"""Vertex AI client for model inference and management."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Union
import time

from google.api_core.exceptions import GoogleAPIError
from google.cloud import aiplatform
from vertexai.preview.generative_models import GenerativeModel
import httpx

from .config import get_settings

logger = logging.getLogger(__name__)


class VertexAIClient:
    """Client for interacting with Vertex AI endpoints and models."""

    def __init__(self):
        self._settings = get_settings()
        self._project_id = self._settings.vertex_ai_project or self._settings.gcp_project_id
        self._region = self._settings.vertex_ai_region
        self._clients: Dict[str, Any] = {}
        self._endpoints: Dict[str, str] = {}
        self._health_cache: Dict[str, Dict[str, Any]] = {}
        self._health_cache_ttl = 300  # 5 minutes

        # Circuit breaker state for each agent
        self._circuit_breakers: Dict[str, Dict[str, Any]] = {}
        self._failure_threshold = 3  # Failures before opening circuit
        self._recovery_timeout = 300  # 5 minutes before trying again

        # Performance metrics
        self._performance_metrics: Dict[str, List[float]] = {}
        self._max_metrics_history = 100

        if self._settings.enable_vertex_ai and self._project_id:
            try:
                aiplatform.init(project=self._project_id, location=self._region)
                logger.info("Vertex AI initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI: {e}")
                raise

        # Initialize endpoint mappings
        self._initialize_endpoints()

    def _initialize_endpoints(self) -> None:
        """Initialize Vertex AI endpoint mappings for each agent."""
        settings = self._settings
        self._endpoints = {
            "deepseek-v3": settings.deepseek_vertex_endpoint,
            "qwen-adaptive": settings.qwen_vertex_endpoint,
            "fingpt-alpha": settings.fingpt_vertex_endpoint,
            "lagllama-degen": settings.lagllama_vertex_endpoint,
            "profit-maximizer": settings.profit_maximizer_vertex_endpoint,
        }

        # Filter out None endpoints
        self._endpoints = {k: v for k, v in self._endpoints.items() if v is not None}

    async def predict(self, agent_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Make prediction using specified agent model with circuit breaker protection."""
        if not self._settings.enable_vertex_ai:
            raise ValueError("Vertex AI is disabled in configuration")

        endpoint_url = self._endpoints.get(agent_id)
        if not endpoint_url:
            raise ValueError(f"No Vertex AI endpoint configured for agent: {agent_id}")

        # Check circuit breaker
        if self._is_circuit_open(agent_id):
            raise RuntimeError(f"Circuit breaker open for {agent_id} - too many failures")

        # Check health cache
        if not await self._is_endpoint_healthy(agent_id):
            self._record_failure(agent_id)
            raise RuntimeError(f"Vertex AI endpoint for {agent_id} is unhealthy")

        try:
            # Prepare prediction payload
            payload = {
                "instances": [{
                    "prompt": prompt,
                    "max_tokens": kwargs.get("max_tokens", 512),
                    "temperature": kwargs.get("temperature", 0.7),
                    "top_p": kwargs.get("top_p", 0.9),
                    "top_k": kwargs.get("top_k", 40),
                }]
            }

            # Extract endpoint ID from URL
            endpoint_id = endpoint_url.split("/")[-1]

            # Use Vertex AI SDK for prediction
            endpoint = aiplatform.Endpoint(endpoint_name=endpoint_id)

            start_time = time.time()
            response = endpoint.predict(instances=payload["instances"])
            inference_time = time.time() - start_time

            # Record success and performance
            self._record_success(agent_id)
            self._record_performance_metric(agent_id, inference_time)

            # Parse response
            if response.predictions:
                prediction = response.predictions[0]
                result = {
                    "response": prediction.get("generated_text", ""),
                    "confidence": prediction.get("confidence", 0.5),
                    "metadata": {
                        "inference_time": inference_time,
                        "model": agent_id,
                        "endpoint": endpoint_id,
                        "circuit_breaker": "healthy",
                    }
                }

                # Validate response quality
                if self._validate_response_quality(result):
                    return result
                else:
                    logger.warning(f"Low quality response from {agent_id}, but returning anyway")
                    return result

            return {
                "response": "",
                "confidence": 0.0,
                "metadata": {
                    "inference_time": inference_time,
                    "error": "No predictions returned",
                    "circuit_breaker": "healthy"
                }
            }

        except GoogleAPIError as e:
            self._record_failure(agent_id)
            logger.error(f"Vertex AI prediction error for {agent_id}: {e}")
            raise RuntimeError(f"Vertex AI prediction failed: {e}")

        except Exception as e:
            self._record_failure(agent_id)
            logger.error(f"Unexpected error in Vertex AI prediction for {agent_id}: {e}")
            raise RuntimeError(f"Vertex AI prediction failed: {e}")

    async def predict_with_fallback(self, agent_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Make prediction with LLM fallback if Vertex AI fails."""
        try:
            return await self.predict(agent_id, prompt, **kwargs)
        except Exception as e:
            logger.warning(f"Vertex AI failed for {agent_id}, falling back to LLM: {e}")

            # Fallback to LLM endpoint if configured
            if self._settings.llm_endpoint and self._settings.enable_llm_trading:
                return await self._predict_llm_fallback(prompt, **kwargs)

            raise e

    async def _predict_llm_fallback(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Fallback prediction using LLM endpoint."""
        try:
            payload = {
                "model": "fallback-llm",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get("max_tokens", 512),
                "temperature": kwargs.get("temperature", 0.7),
            }

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self._settings.llm_endpoint, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "response": data.get("choices", [{}])[0].get("message", {}).get("content", ""),
                        "confidence": 0.5,  # Default confidence for fallback
                        "metadata": {
                            "fallback": True,
                            "model": "llm-fallback",
                        }
                    }

                raise RuntimeError(f"LLM fallback failed with status {response.status_code}")

        except Exception as e:
            logger.error(f"LLM fallback failed: {e}")
            raise RuntimeError(f"All prediction methods failed: {e}")

    async def _is_endpoint_healthy(self, agent_id: str) -> bool:
        """Check if Vertex AI endpoint is healthy."""
        cache_key = f"{agent_id}_health"
        now = time.time()

        # Check cache
        if cache_key in self._health_cache:
            cached = self._health_cache[cache_key]
            if now - cached["timestamp"] < self._health_cache_ttl:
                return cached["healthy"]

        # Perform health check
        try:
            endpoint_url = self._endpoints.get(agent_id)
            if not endpoint_url:
                return False

            # Simple health check - try to get endpoint info
            endpoint_id = endpoint_url.split("/")[-1]
            endpoint = aiplatform.Endpoint(endpoint_name=endpoint_id)

            # Try to get endpoint info (this will fail if endpoint doesn't exist)
            endpoint.display_name  # This property access will trigger API call

            healthy = True

        except Exception as e:
            logger.warning(f"Health check failed for {agent_id}: {e}")
            healthy = False

        # Cache result
        self._health_cache[cache_key] = {
            "healthy": healthy,
            "timestamp": now
        }

        return healthy

    async def get_model_info(self, agent_id: str) -> Dict[str, Any]:
        """Get information about a deployed model."""
        try:
            endpoint_url = self._endpoints.get(agent_id)
            if not endpoint_url:
                return {"error": f"No endpoint configured for {agent_id}"}

            endpoint_id = endpoint_url.split("/")[-1]
            endpoint = aiplatform.Endpoint(endpoint_name=endpoint_id)

            return {
                "model_id": agent_id,
                "endpoint_id": endpoint_id,
                "display_name": endpoint.display_name,
                "deployed_models": [
                    {
                        "model": model.model,
                        "model_version": model.model_version_id,
                        "display_name": model.display_name,
                    }
                    for model in endpoint.list_models()
                ],
                "traffic_split": endpoint.traffic_split,
                "healthy": await self._is_endpoint_healthy(agent_id),
            }

        except Exception as e:
            logger.error(f"Failed to get model info for {agent_id}: {e}")
            return {"error": str(e), "model_id": agent_id}

    async def list_all_models(self) -> Dict[str, Any]:
        """List all Vertex AI models and their status."""
        result = {}
        for agent_id in self._endpoints.keys():
            result[agent_id] = await self.get_model_info(agent_id)
        return result

    def _is_circuit_open(self, agent_id: str) -> bool:
        """Check if circuit breaker is open for an agent."""
        breaker = self._circuit_breakers.get(agent_id, {})
        if not breaker:
            return False

        if breaker.get("state") == "open":
            # Check if recovery timeout has passed
            if time.time() - breaker.get("last_failure", 0) > self._recovery_timeout:
                # Try to close circuit (half-open state)
                breaker["state"] = "half-open"
                breaker["half_open_successes"] = 0
                logger.info(f"Circuit breaker for {agent_id} entering half-open state")
                return False
            return True

        return False

    def _record_success(self, agent_id: str) -> None:
        """Record successful prediction."""
        breaker = self._circuit_breakers.setdefault(agent_id, {
            "state": "closed",
            "failures": 0,
            "half_open_successes": 0,
            "last_failure": 0
        })

        if breaker["state"] == "half-open":
            breaker["half_open_successes"] += 1
            if breaker["half_open_successes"] >= 2:  # Require 2 successes to close
                breaker["state"] = "closed"
                breaker["failures"] = 0
                logger.info(f"Circuit breaker for {agent_id} closed - recovered")
        elif breaker["state"] == "closed":
            # Reset failure count on success
            breaker["failures"] = 0

    def _record_failure(self, agent_id: str) -> None:
        """Record failed prediction."""
        breaker = self._circuit_breakers.setdefault(agent_id, {
            "state": "closed",
            "failures": 0,
            "half_open_successes": 0,
            "last_failure": 0
        })

        breaker["failures"] += 1
        breaker["last_failure"] = time.time()

        if breaker["state"] == "half-open":
            # Any failure in half-open state immediately opens circuit
            breaker["state"] = "open"
            logger.warning(f"Circuit breaker for {agent_id} opened due to half-open failure")
        elif breaker["failures"] >= self._failure_threshold:
            breaker["state"] = "open"
            logger.warning(f"Circuit breaker for {agent_id} opened after {breaker['failures']} failures")

    def _record_performance_metric(self, agent_id: str, inference_time: float) -> None:
        """Record performance metric for monitoring."""
        if agent_id not in self._performance_metrics:
            self._performance_metrics[agent_id] = []

        metrics = self._performance_metrics[agent_id]
        metrics.append(inference_time)

        # Keep only recent metrics
        if len(metrics) > self._max_metrics_history:
            metrics.pop(0)

    def _validate_response_quality(self, result: Dict[str, Any]) -> bool:
        """Validate response quality and coherence."""
        response = result.get("response", "").strip()

        # Basic quality checks
        if not response:
            return False

        if len(response) < 10:  # Too short
            return False

        confidence = result.get("confidence", 0.0)
        if confidence < 0.1:  # Too low confidence
            return False

        # Check for error indicators
        error_indicators = ["error", "failed", "unable", "sorry", "apologize"]
        response_lower = response.lower()
        if any(indicator in response_lower for indicator in error_indicators):
            return False

        return True

    def get_circuit_breaker_status(self, agent_id: str) -> Dict[str, Any]:
        """Get circuit breaker status for an agent."""
        breaker = self._circuit_breakers.get(agent_id, {
            "state": "closed",
            "failures": 0,
            "half_open_successes": 0,
            "last_failure": 0
        })

        return {
            "agent_id": agent_id,
            "state": breaker["state"],
            "failures": breaker["failures"],
            "half_open_successes": breaker.get("half_open_successes", 0),
            "last_failure": time.time() - breaker.get("last_failure", 0),
            "failure_threshold": self._failure_threshold,
            "recovery_timeout": self._recovery_timeout
        }

    def get_performance_metrics(self, agent_id: str) -> Dict[str, Any]:
        """Get performance metrics for an agent."""
        metrics = self._performance_metrics.get(agent_id, [])

        if not metrics:
            return {"agent_id": agent_id, "metrics": "no_data"}

        import statistics
        return {
            "agent_id": agent_id,
            "count": len(metrics),
            "mean": statistics.mean(metrics),
            "median": statistics.median(metrics),
            "min": min(metrics),
            "max": max(metrics),
            "p95": sorted(metrics)[int(len(metrics) * 0.95)] if len(metrics) > 1 else max(metrics),
            "latest": metrics[-1] if metrics else None
        }

    def reset_circuit_breaker(self, agent_id: str) -> bool:
        """Manually reset circuit breaker for an agent."""
        if agent_id in self._circuit_breakers:
            self._circuit_breakers[agent_id] = {
                "state": "closed",
                "failures": 0,
                "half_open_successes": 0,
                "last_failure": 0
            }
            logger.info(f"Circuit breaker reset for {agent_id}")
            return True
        return False

    def get_all_circuit_breakers(self) -> Dict[str, Dict[str, Any]]:
        """Get circuit breaker status for all agents."""
        result = {}
        for agent_id in self._endpoints.keys():
            result[agent_id] = self.get_circuit_breaker_status(agent_id)
        return result

    def get_all_performance_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get performance metrics for all agents."""
        result = {}
        for agent_id in self._endpoints.keys():
            result[agent_id] = self.get_performance_metrics(agent_id)
        return result


# Global client instance
_vertex_client: Optional[VertexAIClient] = None


def get_vertex_client() -> VertexAIClient:
    """Get or create global Vertex AI client instance."""
    global _vertex_client
    if _vertex_client is None:
        _vertex_client = VertexAIClient()
    return _vertex_client
