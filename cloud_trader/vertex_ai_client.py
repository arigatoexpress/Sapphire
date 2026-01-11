"""Vertex AI client for model inference and management with Gemini API fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Union

import httpx

try:
    from google.api_core.exceptions import GoogleAPIError
    from google.cloud import aiplatform
    from google.protobuf import json_format
    from google.protobuf.struct_pb2 import Value
except ImportError:
    GoogleAPIError = Exception
    aiplatform = None
    json_format = None
    Value = None
    print("⚠️ Vertex AI not found. AI predictions disabled.")
try:
    from vertexai.preview.generative_models import GenerativeModel
except ImportError:
    GenerativeModel = None

# Try to import Google Generative AI (for API key mode)
try:
    import google.generativeai as genai

    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

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
        self._initialized = False

        # Circuit breaker state for each agent
        self._circuit_breakers: Dict[str, Dict[str, Any]] = {}
        self._failure_threshold = 3  # Failures before opening circuit
        self._recovery_timeout = 300  # 5 minutes before trying again

        # Performance metrics
        self._performance_metrics: Dict[str, List[float]] = {}
        self._max_metrics_history = 100

        # Mode detection
        self._use_api_key = False

        if self._settings.gemini_api_key:
            if HAS_GENAI:
                logger.info("Initializing Gemini API client with provided API key")
                genai.configure(api_key=self._settings.gemini_api_key)
                self._use_api_key = True
            else:
                logger.warning(
                    "GEMINI_API_KEY present but google-generativeai package not installed"
                )

        # Defer Vertex AI initialization to initialize() method or first use
        self._initialize_endpoints()

        # Model mapping for Direct API Mode
        self._model_map = {
            "trend-momentum-agent": "gemini-2.5-flash",
            "strategy-optimization-agent": "gemini-2.5-flash",
            "financial-sentiment-agent": "gemini-2.5-flash",
            "market-prediction-agent": "gemini-2.5-flash",
            "volume-microstructure-agent": "gemini-2.5-flash",
            "vpin-hft": "gemini-2.5-flash",
            "deep-logic-special-ops": "gemini-2.5-flash",
            "market-analysis": "gemini-2.5-flash",
        }

        # Dynamic model override map: agent_id -> "gemini-3.0-flash-001"
        self._dynamic_model_overrides = {}

        # Prediction Cache (Elite Optimization)
        # Key: hash(agent_id + prompt), Value: (timestamp, result_dict)
        self._prediction_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._cache_ttl = 60.0  # 60 seconds

    def set_agent_model_override(self, agent_id: str, model_name: str) -> None:
        """Dynamically override an agent's model (e.g. from definitions.py)."""
        self._dynamic_model_overrides[agent_id] = model_name
        # Also update legacy map for fallback compatibility
        self._model_map[agent_id] = model_name

    async def initialize(self) -> None:
        """Initialize Vertex AI connection asynchronously."""
        if self._initialized:
            return

        if not self._use_api_key and self._settings.enable_vertex_ai and self._project_id:
            try:
                # Run blocking init in executor
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: aiplatform.init(project=self._project_id, location=self._region)
                )
                logger.info("Vertex AI initialized successfully")
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI: {e}")
                if not self._use_api_key:
                    # Don't raise here, allow fallback to other methods or graceful degradation
                    pass
        else:
            self._initialized = True

    def _initialize_endpoints(self) -> None:
        """Initialize Vertex AI endpoint mappings for each agent."""
        # In API Key mode, we don't need endpoints, but we keep this structure compatible
        self._endpoints = {}

        # In a real Vertex AI setup, we would fetch these or load from config
        # For now, if using API key, we rely on _model_map

    async def predict(self, agent_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Make prediction using specified agent model with circuit breaker protection."""
        if not self._initialized:
            await self.initialize()

        if not self._settings.enable_vertex_ai and not self._use_api_key:
            raise ValueError("Both Vertex AI and Gemini API Key modes are disabled")

        # Check circuit breaker
        if self._is_circuit_open(agent_id):
            raise RuntimeError(f"Circuit breaker open for {agent_id} - too many failures")

        # Elite Optimization: Check Cache
        import hashlib

        cache_key = hashlib.md5(f"{agent_id}:{prompt}".encode()).hexdigest()

        if cache_key in self._prediction_cache:
            timestamp, cached_result = self._prediction_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                # Add cache metadata
                cached_result["metadata"]["cached"] = True
                cached_result["metadata"]["cache_age"] = time.time() - timestamp
                return cached_result

        # Dispatch based on mode
        # Dispatch based on mode
        try:
            result = None
            if self._use_api_key:
                result = await self._predict_with_api_key(agent_id, prompt, **kwargs)
            else:
                result = await self._predict_with_vertex(agent_id, prompt, **kwargs)

            # Elite Optimization: Save to Cache
            if result and result.get("confidence", 0) > 0:
                self._prediction_cache[cache_key] = (time.time(), result)

            return result

        except Exception as e:
            # Detailed error logging
            import traceback

            logger.error(f"Prediction error for {agent_id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")

            # Check for specific Google API errors
            if hasattr(e, "code"):
                logger.error(f"Google API Error Code: {e.code}")
            if hasattr(e, "message"):
                logger.error(f"Google API Error Message: {e.message}")
            if hasattr(e, "details"):
                logger.error(f"Google API Error Details: {e.details}")

            self._record_failure(agent_id)
            raise RuntimeError(f"Prediction failed: {e}")

    async def _predict_with_api_key(self, agent_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Make prediction using Google AI Studio API Key."""
        model_name = self._model_map.get(agent_id, "gemini-flash-latest")

        try:
            model = genai.GenerativeModel(model_name)

            generation_config = genai.types.GenerationConfig(
                max_output_tokens=kwargs.get("max_tokens", 512),
                temperature=kwargs.get("temperature", 0.7),
                top_p=kwargs.get("top_p", 0.9),
                top_k=kwargs.get("top_k", 40),
            )

            start_time = time.time()
            # Run in executor to avoid blocking async loop
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: model.generate_content(prompt, generation_config=generation_config)
            )
            inference_time = time.time() - start_time

            self._record_success(agent_id)
            self._record_performance_metric(agent_id, inference_time)

            text_response = response.text if response.parts else ""

            return {
                "response": text_response,
                "confidence": 0.9,  # API doesn't strictly return confidence in this mode
                "metadata": {
                    "inference_time": inference_time,
                    "model": model_name,
                    "mode": "api_key",
                    "circuit_breaker": "healthy",
                },
            }

        except Exception as e:
            logger.error(f"Gemini API Key prediction failed for {agent_id}: {e}")
            raise

    async def _predict_with_vertex(self, agent_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Make prediction using Vertex AI (GenerativeModel or Endpoint)."""
        start_time = time.time()

        # 1. Check if it's a Generative Model (Gemini)
        # Check for dynamic override first, then static map
        model_name = self._dynamic_model_overrides.get(agent_id) or self._model_map.get(agent_id)
        if model_name:
            try:
                # Initialize model
                model = GenerativeModel(model_name)

                # Config
                generation_config = {
                    "max_output_tokens": kwargs.get("max_tokens", 1024),
                    "temperature": kwargs.get("temperature", 0.7),
                    "top_p": kwargs.get("top_p", 0.95),
                    "top_k": kwargs.get("top_k", 40),
                }

                # Run prediction (in executor to be async-friendly)
                # Note: stream=False by default
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: model.generate_content(prompt, generation_config=generation_config),
                )

                inference_time = time.time() - start_time

                # Safe response extraction
                try:
                    text_response = response.text
                except Exception:
                    # Fallback if .text property fails (e.g. safety blocks)
                    if response.candidates and response.candidates[0].content.parts:
                        text_response = response.candidates[0].content.parts[0].text
                    else:
                        # Log safety ratings if available
                        logger.warning(
                            f"Empty response from Vertex AI for {agent_id}. Safety attributes: {getattr(response, 'prompt_feedback', 'N/A')}"
                        )
                        raise ValueError("Vertex AI returned empty response (possibly blocked)")

                self._record_success(agent_id)
                self._record_performance_metric(agent_id, inference_time)

                return {
                    "response": text_response,
                    "confidence": 0.9,
                    "metadata": {
                        "inference_time": inference_time,
                        "model": model_name,
                        "mode": "vertex_generative",
                        "circuit_breaker": "healthy",
                    },
                }
            except Exception as e:
                # FALLBACK LOGIC: Gemini 3 -> Gemini 2.5
                if "404" in str(e) and "gemini-3" in model_name:
                    logger.warning(
                        f"⚠️ {model_name} not found for {agent_id}. Fallback to gemini-2.5-flash-001..."
                    )
                    fallback_model = "gemini-2.5-flash-001"
                    try:
                        # Retry with fallback model
                        model = GenerativeModel(fallback_model)
                        response = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: model.generate_content(
                                prompt, generation_config=generation_config
                            ),
                        )

                        # ... (Process response same as above) ...
                        inference_time = time.time() - start_time
                        try:
                            text_response = response.text
                        except Exception:
                            if response.candidates and response.candidates[0].content.parts:
                                text_response = response.candidates[0].content.parts[0].text
                            else:
                                raise ValueError("Fallback empty response")

                        self._record_success(agent_id)
                        return {
                            "response": text_response,
                            "confidence": 0.9,
                            "metadata": {
                                "inference_time": inference_time,
                                "model": fallback_model,
                                "mode": "vertex_generative_fallback",
                                "circuit_breaker": "healthy",
                            },
                        }

                    except Exception as fallback_error:
                        logger.error(f"Fallback failed too: {fallback_error}")
                        # Continue to existing error handling
                        pass

                # If it fails, we log it.
                # We ONLY fall back to endpoint if one is explicitly configured.
                logger.error(
                    f"GenerativeModel prediction failed for {agent_id} ({model_name}): {e}"
                )
                if not self._endpoints.get(agent_id):
                    raise e

        # 2. Fallback to Custom Endpoint (if configured)
        endpoint_url = self._endpoints.get(agent_id)
        if not endpoint_url:
            # This is where the previous error came from.
            # If we had a model_name but failed, and have no endpoint, we should have raised e above.
            if not model_name:
                raise ValueError(f"No Vertex AI endpoint or model configured for agent: {agent_id}")
            # If we are here, it means model_name existed, failed, and we fell through.
            # But the updated logic above raises e if no endpoint, so we shouldn't reach here in that case.
            return {
                "response": "",
                "confidence": 0.0,
                "metadata": {"error": f"Prediction failed and no fallback endpoint for {agent_id}"},
            }

        # Extract endpoint ID from URL
        endpoint_id = endpoint_url.split("/")[-1]

        # Use Vertex AI SDK for prediction
        endpoint = aiplatform.Endpoint(endpoint_name=endpoint_id)

        payload = {
            "instances": [
                {
                    "prompt": prompt,
                    "max_tokens": kwargs.get("max_tokens", 512),
                    "temperature": kwargs.get("temperature", 0.7),
                    "top_p": kwargs.get("top_p", 0.9),
                    "top_k": kwargs.get("top_k", 40),
                }
            ]
        }

        response = endpoint.predict(instances=payload["instances"])
        inference_time = time.time() - start_time

        self._record_success(agent_id)
        self._record_performance_metric(agent_id, inference_time)

        if response.predictions:
            prediction = response.predictions[0]
            return {
                "response": prediction.get("generated_text", ""),
                "confidence": prediction.get("confidence", 0.5),
                "metadata": {
                    "inference_time": inference_time,
                    "model": agent_id,
                    "endpoint": endpoint_id,
                    "circuit_breaker": "healthy",
                },
            }

        return {"response": "", "confidence": 0.0, "metadata": {"error": "No predictions"}}

    async def predict_with_fallback(self, agent_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Make prediction with LLM fallback if Vertex AI/Gemini fails."""
        try:
            return await self.predict(agent_id, prompt, **kwargs)
        except Exception as e:
            logger.warning(f"Primary inference failed for {agent_id}, falling back to LLM: {e}")

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
                        "response": data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", ""),
                        "confidence": 0.5,  # Default confidence for fallback
                        "metadata": {
                            "fallback": True,
                            "model": "llm-fallback",
                        },
                    }

                raise RuntimeError(f"LLM fallback failed with status {response.status_code}")

        except Exception as e:
            logger.error(f"LLM fallback failed: {e}")
            raise RuntimeError(f"All prediction methods failed: {e}")

    async def _is_endpoint_healthy(self, agent_id: str) -> bool:
        """Check if Vertex AI endpoint is healthy."""
        if self._use_api_key:
            return True  # Assume healthy if using API key (could check list_models but simple is better)

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
            endpoint.display_name  # Trigger API call
            healthy = True

        except Exception as e:
            logger.warning(f"Health check failed for {agent_id}: {e}")
            healthy = False

        # Cache result
        self._health_cache[cache_key] = {"healthy": healthy, "timestamp": now}

        return healthy

    async def health_check(self) -> bool:
        """Perform a basic health check of Vertex AI connectivity."""
        if self._use_api_key:
            try:
                # Check if we can list models
                await asyncio.get_event_loop().run_in_executor(None, genai.list_models)
                return True
            except Exception as e:
                logger.error(f"Gemini API health check failed: {e}")
                return False

        try:
            # Try to list available models as a basic connectivity test
            aiplatform.init(project=self._project_id, location=self._region)
            return True
        except Exception as e:
            logger.error(f"Vertex AI health check failed: {e}")
            return False

    async def get_model_info(self, agent_id: str) -> Dict[str, Any]:
        """Get information about a deployed model."""
        if self._use_api_key:
            model_name = self._model_map.get(agent_id, "unknown")
            return {
                "model_id": agent_id,
                "endpoint_id": "api_key",
                "display_name": model_name,
                "deployed_models": [{"model": model_name, "display_name": model_name}],
                "traffic_split": {"100": 1},
                "healthy": True,
            }

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
        if self._use_api_key:
            for agent_id in self._model_map.keys():
                result[agent_id] = await self.get_model_info(agent_id)
        else:
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
        breaker = self._circuit_breakers.setdefault(
            agent_id,
            {"state": "closed", "failures": 0, "half_open_successes": 0, "last_failure": 0},
        )

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
        breaker = self._circuit_breakers.setdefault(
            agent_id,
            {"state": "closed", "failures": 0, "half_open_successes": 0, "last_failure": 0},
        )

        breaker["failures"] += 1
        breaker["last_failure"] = time.time()

        if breaker["state"] == "half-open":
            # Any failure in half-open state immediately opens circuit
            breaker["state"] = "open"
            logger.warning(f"Circuit breaker for {agent_id} opened due to half-open failure")
        elif breaker["failures"] >= self._failure_threshold:
            breaker["state"] = "open"
            logger.warning(
                f"Circuit breaker for {agent_id} opened after {breaker['failures']} failures"
            )

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
        breaker = self._circuit_breakers.get(
            agent_id,
            {"state": "closed", "failures": 0, "half_open_successes": 0, "last_failure": 0},
        )

        return {
            "agent_id": agent_id,
            "state": breaker["state"],
            "failures": breaker["failures"],
            "half_open_successes": breaker.get("half_open_successes", 0),
            "last_failure": time.time() - breaker.get("last_failure", 0),
            "failure_threshold": self._failure_threshold,
            "recovery_timeout": self._recovery_timeout,
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
            "latest": metrics[-1] if metrics else None,
        }

    def reset_circuit_breaker(self, agent_id: str) -> bool:
        """Manually reset circuit breaker for an agent."""
        if agent_id in self._circuit_breakers:
            self._circuit_breakers[agent_id] = {
                "state": "closed",
                "failures": 0,
                "half_open_successes": 0,
                "last_failure": 0,
            }
            logger.info(f"Circuit breaker reset for {agent_id}")
            return True
        return False

    def get_all_circuit_breakers(self) -> Dict[str, Dict[str, Any]]:
        """Get circuit breaker status for all agents."""
        result = {}
        if self._use_api_key:
            for agent_id in self._model_map.keys():
                result[agent_id] = self.get_circuit_breaker_status(agent_id)
        else:
            for agent_id in self._endpoints.keys():
                result[agent_id] = self.get_circuit_breaker_status(agent_id)
        return result

    def get_all_performance_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get performance metrics for all agents."""
        result = {}
        if self._use_api_key:
            for agent_id in self._model_map.keys():
                result[agent_id] = self.get_performance_metrics(agent_id)
        else:
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
