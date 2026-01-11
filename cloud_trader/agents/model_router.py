"""
Sapphire V2 Model Router
AI model integration using Gemini.

Currently configured for:
- Gemini 2.0 Flash (primary AI for all analysis)

Architecture supports future expansion to:
- OpenAI GPT-4
- Anthropic Claude
- Local Llama
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """Supported AI model providers."""

    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass
class ModelResponse:
    """Response from an AI model."""

    text: str
    model: str
    latency_ms: int
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None


class MultiModelRouter:
    """
    Routes queries to the optimal AI model with intelligent fallback.

    Strategy:
    1. Try primary model first
    2. Fall back to secondary on error
    3. Use local model if all APIs fail
    """

    def __init__(self):
        self._clients: Dict[ModelProvider, Any] = {}
        self._stats: Dict[ModelProvider, Dict] = {
            p: {"calls": 0, "errors": 0, "avg_latency": 0} for p in ModelProvider
        }
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize Gemini client using existing GCloud secrets."""
        from ..api_secrets import GcpSecretManager
        from ..config import get_settings

        settings = get_settings()
        secret_manager = GcpSecretManager()
        gcp_project = settings.gcp_project_id

        # Gemini (primary and only AI provider)
        gemini_key = settings.gemini_api_key or os.getenv("GEMINI_API_KEY")
        if not gemini_key and gcp_project:
            gemini_key = secret_manager.get_secret("GEMINI_API_KEY", gcp_project)

        if gemini_key:
            try:
                # Using stable google.generativeai (compatible with httpx 0.23.1)
                # Suppress deprecation warning until we can upgrade httpx
                import warnings

                warnings.filterwarnings(
                    "ignore", category=FutureWarning, module="google.generativeai"
                )

                import google.generativeai as genai

                genai.configure(api_key=gemini_key)
                self._clients[ModelProvider.GEMINI] = genai.GenerativeModel("gemini-2.0-flash-exp")
                logger.info("✅ Gemini 2.0 Flash initialized (primary AI)")
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")

        if not self._clients:
            logger.warning("⚠️ No AI models available - using fallback responses")

    async def query(
        self,
        prompt: str,
        primary: ModelProvider = ModelProvider.GEMINI,
        fallback: ModelProvider = ModelProvider.OPENAI,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """
        Query an AI model with fallback.

        Returns:
            Dict with 'text', 'model', 'latency_ms' keys
        """
        # Try primary
        if primary in self._clients:
            try:
                response = await asyncio.wait_for(
                    self._query_model(primary, prompt), timeout=timeout
                )
                if response.success:
                    return {
                        "text": response.text,
                        "model": response.model,
                        "latency_ms": response.latency_ms,
                    }
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ {primary.value} timeout")
            except Exception as e:
                logger.warning(f"❌ {primary.value} error: {e}")

        # Try fallback
        if fallback in self._clients and fallback != primary:
            try:
                response = await asyncio.wait_for(
                    self._query_model(fallback, prompt), timeout=timeout
                )
                if response.success:
                    return {
                        "text": response.text,
                        "model": response.model,
                        "latency_ms": response.latency_ms,
                    }
            except Exception as e:
                logger.warning(f"❌ {fallback.value} error: {e}")

        # All failed - return fallback response
        return self._fallback_response(prompt)

    async def _query_model(self, provider: ModelProvider, prompt: str) -> ModelResponse:
        """Query a specific model provider."""
        start_time = time.time()
        client = self._clients.get(provider)

        if not client:
            return ModelResponse(
                text="",
                model=provider.value,
                latency_ms=0,
                success=False,
                error="Client not initialized",
            )

        try:
            if provider == ModelProvider.GEMINI:
                response = await client.generate_content_async(prompt)
                text = response.text

            elif provider == ModelProvider.OPENAI:
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=256,
                )
                text = response.choices[0].message.content

            elif provider == ModelProvider.ANTHROPIC:
                response = await client.messages.create(
                    model="claude-3-5-sonnet-latest",
                    max_tokens=256,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text
            else:
                text = ""

            latency_ms = int((time.time() - start_time) * 1000)

            # Update stats
            self._update_stats(provider, latency_ms, success=True)

            return ModelResponse(
                text=text, model=provider.value, latency_ms=latency_ms, success=True
            )

        except Exception as e:
            self._update_stats(provider, 0, success=False)
            return ModelResponse(
                text="", model=provider.value, latency_ms=0, success=False, error=str(e)
            )

    def _fallback_response(self, prompt: str) -> Dict[str, Any]:
        """Generate a safe fallback response when all models fail."""
        # Simple rule-based fallback
        return {
            "text": "SIGNAL: HOLD\nCONFIDENCE: 0.3\nREASONING: Unable to perform full analysis - holding position.",
            "model": "fallback",
            "latency_ms": 0,
        }

    def _update_stats(self, provider: ModelProvider, latency_ms: int, success: bool):
        """Update usage statistics."""
        stats = self._stats[provider]
        stats["calls"] += 1
        if not success:
            stats["errors"] += 1
        if latency_ms > 0:
            # Running average
            prev_avg = stats["avg_latency"]
            stats["avg_latency"] = (prev_avg * (stats["calls"] - 1) + latency_ms) / stats["calls"]

    def get_stats(self) -> Dict[str, Dict]:
        """Get usage statistics for all models."""
        return {p.value: {**self._stats[p], "available": p in self._clients} for p in ModelProvider}
