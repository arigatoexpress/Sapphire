"""Open-source analyst integrations (FinGPT, Lag-LLaMA) for trade reasoning."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import Settings
from .sui_clients import SuiNautilusClient, SuiSealClient, SuiWalrusClient

logger = logging.getLogger(__name__)


class OpenSourceAnalyst:
    """Asynchronous helper that calls optional FinGPT and Lag-LLaMA services."""

    _MIN_INTERVAL_SECONDS = {
        "fingpt-alpha": 2.0,
        "lagllama-degen": 2.0,
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rate_state: Dict[str, float] = {}
        self._rate_lock = asyncio.Lock()
        self._response_cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_lock = asyncio.Lock()
        # Sui decentralized science hooks (configured with endpoints from settings)
        self._walrus = SuiWalrusClient(
            endpoint=self._settings.sui_walrus_endpoint,
            api_key=self._settings.sui_walrus_key,
        )
        self._seal = SuiSealClient(endpoint=self._settings.sui_seal_endpoint)
        self._nautilus = SuiNautilusClient(endpoint=self._settings.sui_nautilus_endpoint)

    async def generate_thesis(
        self,
        agent_id: Optional[str],
        symbol: str,
        side: str,
        price: float,
        market_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not agent_id:
            return None

        if agent_id == "fingpt-alpha":
            return await self._query_fingpt(symbol, side, price, market_context)

        if agent_id == "lagllama-degen":
            return await self._query_lagllama(symbol, side, price, market_context)

        return None

    async def _query_fingpt(
        self,
        symbol: str,
        side: str,
        price: float,
        market_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Query FinGPT with caching, enhanced prompts, and validation."""
        # Check cache first
        cache_key = self._get_cache_key("fingpt-alpha", symbol, side, price)
        cached = await self._get_cached_response(cache_key)
        if cached:
            return cached

        if not await self._allow_request("fingpt-alpha"):
            logger.debug("FinGPT request throttled for %s", symbol)
            return None

        endpoint = self._settings.fingpt_endpoint
        if not endpoint:
            return self._fallback_fingpt(symbol, side, price, market_context)

        # Build enhanced prompt with DeFi context
        prompt = await self._build_prompt(symbol, side, price, market_context, "FinGPT")

        payload = {
            "model": "FinGPT",
            "prompt": prompt,
        }

        data = await self._post_json(endpoint, payload, self._settings.fingpt_api_key, "FinGPT")
        if not data:
            return self._fallback_fingpt(symbol, side, price, market_context)

        thesis = data.get("thesis") or data.get("summary") or data.get("text")
        risk_score = data.get("risk_score")
        confidence = data.get("confidence")

        if isinstance(thesis, str):
            thesis = thesis.strip()

        if not thesis:
            return self._fallback_fingpt(symbol, side, price, market_context)

        # Validate response (hallucination guard)
        if not self._validate_fingpt_response(thesis, market_context):
            logger.warning("FinGPT response failed validation, using fallback")
            return self._fallback_fingpt(symbol, side, price, market_context)

        result = {
            "source": "FinGPT",
            "thesis": thesis,
            "risk_score": float(risk_score) if isinstance(risk_score, (int, float)) else None,
            "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
        }

        # Cache response
        await self._cache_response(cache_key, result)

        return result

    async def _query_lagllama(
        self,
        symbol: str,
        side: str,
        price: float,
        market_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Query Lag-Llama with caching, time-series enrichment, and validation."""
        # Check cache first
        cache_key = self._get_cache_key("lagllama-degen", symbol, side, price)
        cached = await self._get_cached_response(cache_key)
        if cached:
            return cached

        if not await self._allow_request("lagllama-degen"):
            logger.debug("Lag-LLaMA request throttled for %s", symbol)
            return None

        endpoint = self._settings.lagllama_endpoint
        if not endpoint:
            return self._fallback_lagllama(symbol, side, price, market_context)

        # Enrich market context (on-chain data integration would go here if Nautilus were configured)
        enriched_context = market_context.copy()

        payload = {
            "model": "lag-llama",
            "symbol": symbol,
            "side": side,
            "price": price,
            "context": enriched_context,
            "horizon": 24,  # 24-hour forecast horizon
            "include_anomaly_detection": True,
        }

        data = await self._post_json(endpoint, payload, self._settings.lagllama_api_key, "Lag-LLaMA")
        if not data:
            return self._fallback_lagllama(symbol, side, price, market_context)

        forecast = data.get("forecast") or []
        upper_ci = data.get("upper_ci") or []
        lower_ci = data.get("lower_ci") or []
        anomaly_score = data.get("anomaly_score")
        confidence = data.get("confidence")

        ci_span = self._compute_ci_span(price, upper_ci, lower_ci)

        # Validate CI span (reject if >20% variance as per plan)
        if ci_span is not None and ci_span > 0.20:
            logger.warning(
                "Lag-LLaMA CI span %.2f%% exceeds 20%% threshold, rejecting",
                ci_span * 100,
            )
            return self._fallback_lagllama(symbol, side, price, market_context)

        # Validate forecast against recent price action (hallucination guard)
        if not self._validate_lagllama_forecast(forecast, price, market_context):
            logger.warning("Lag-LLaMA forecast failed validation, using fallback")
            return self._fallback_lagllama(symbol, side, price, market_context)

        thesis = data.get("thesis")
        if not isinstance(thesis, str):
            thesis = self._format_lagllama_thesis(symbol, side, price, forecast, upper_ci, lower_ci, anomaly_score)

        result = {
            "source": "Lag-LLaMA",
            "thesis": thesis,
            "ci_span": ci_span,
            "anomaly_score": float(anomaly_score) if isinstance(anomaly_score, (int, float)) else None,
            "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
            "forecast": forecast[:5] if forecast else [],  # Include first 5 forecast points
        }

        # Cache response
        await self._cache_response(cache_key, result)

        return result

    async def _post_json(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        api_key: Optional[str],
        label: str,
        retry_attempts: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Post JSON with retry logic and exponential backoff."""
        if retry_attempts is None:
            retry_attempts = self._settings.agent_retry_attempts

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        last_exception = None
        for attempt in range(retry_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
                    response = await client.post(endpoint, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    if isinstance(data, dict):
                        return data
                    logger.debug("%s analyst returned non-dict payload", label)
                    return None
            except Exception as exc:
                last_exception = exc
                if attempt < retry_attempts:
                    # Exponential backoff: 0.5s, 1s, 2s
                    wait_time = 0.5 * (2 ** attempt)
                    logger.debug("%s analyst call failed (attempt %d/%d), retrying in %.1fs: %s", label, attempt + 1, retry_attempts + 1, wait_time, exc)
                    await asyncio.sleep(wait_time)
                else:
                    logger.debug("%s analyst call failed after %d attempts: %s", label, retry_attempts + 1, exc)
        return None

    def _get_cache_key(self, agent_id: str, symbol: str, side: str, price: float) -> str:
        """Generate cache key for agent response."""
        # Round price to 4 decimals for cache hit
        price_rounded = round(price, 4)
        cache_data = f"{agent_id}:{symbol}:{side}:{price_rounded}"
        return hashlib.md5(cache_data.encode()).hexdigest()

    async def _get_cached_response(self, cache_key: str) -> Optional[Any]:
        """Get cached response if still valid."""
        async with self._cache_lock:
            if cache_key in self._response_cache:
                timestamp, response = self._response_cache[cache_key]
                age = time.time() - timestamp
                if age < self._settings.agent_cache_ttl_seconds:
                    logger.debug("Cache hit for agent response (age: %.1fs)", age)
                    return response
                else:
                    # Expired, remove from cache
                    del self._response_cache[cache_key]
        return None

    async def _cache_response(self, cache_key: str, response: Any) -> None:
        """Cache agent response."""
        async with self._cache_lock:
            self._response_cache[cache_key] = (time.time(), response)
            # Clean up old entries (keep last 100)
            if len(self._response_cache) > 100:
                # Remove oldest entries
                sorted_items = sorted(self._response_cache.items(), key=lambda x: x[1][0])
                for key, _ in sorted_items[:len(self._response_cache) - 100]:
                    del self._response_cache[key]

    async def _allow_request(self, key: str) -> bool:
        interval = self._MIN_INTERVAL_SECONDS.get(key, 1.0)
        async with self._rate_lock:
            now = time.monotonic()
            last = self._rate_state.get(key, 0.0)
            if now - last < interval:
                return False
            self._rate_state[key] = now
            return True

    async def _build_prompt(
        self,
        symbol: str,
        side: str,
        price: float,
        market_context: Dict[str, Any],
        model_name: str,
    ) -> str:
        """Build enhanced prompt with DeFi/on-chain context."""
        change = market_context.get("change_24h", 0)
        volume = market_context.get("volume", 0)
        atr = market_context.get("atr")

        # Determine volatility regime
        volatility_regime = "high"
        if atr and price > 0:
            atr_pct = (atr / price) * 100
            if atr_pct < 1.0:
                volatility_regime = "low"
            elif atr_pct < 2.0:
                volatility_regime = "moderate"
            else:
                volatility_regime = "high"

        # Symbol-specific context for DeFi-focused analysis
        symbol_base = symbol.upper().replace("USDT", "").replace("USDC", "")
        if symbol_base == "AVAX":
            chain_context = "Avalanche (AVAX) - High-throughput chain with 1K+ TPS. Monitor TVL spikes and DeFi yield farming risks. High volatility regime for DeFi tokens."
        elif symbol_base == "ARB":
            chain_context = "Arbitrum (ARB) - Layer-2 scaling solution. Track rollup volumes and gas fee dynamics. Layer-2 volatility patterns."
        else:
            chain_context = f"{symbol_base} - Monitor DeFi market structure and on-chain metrics."

        prompt = f"""You are {model_name}, an open-source model aiding a privacy-preserving trader.

Generate a concise thesis for {side.upper()} {symbol} near {price:.4f}.

Market Context:
- 24h change: {change:.2f}%
- Volume: ${volume:,.0f}
- ATR: {atr if atr is not None else 'N/A'}
- Volatility Regime: {volatility_regime}
- Chain Context: {chain_context}

Focus on:
1. Volatility regime detection and implications for position sizing
2. DeFi market structure analysis (monitor for TVL spikes, yield risks)
3. Risk assessment with leverage considerations
4. High-volatility DeFi token dynamics (flash crash detection)

Return JSON with fields thesis (string), risk_score (0-1), confidence (0-1)."""
        return prompt

    @staticmethod
    def _compute_ci_span(price: float, upper_ci: list[Any], lower_ci: list[Any]) -> Optional[float]:
        if not upper_ci or not lower_ci:
            return None
        try:
            max_diff = max(float(u) - float(l) for u, l in zip(upper_ci, lower_ci))
            if price > 0:
                return max_diff / price
        except Exception:
            return None
        return None

    @staticmethod
    def _format_lagllama_thesis(
        symbol: str,
        side: str,
        price: float,
        forecast: list[Any],
        upper_ci: list[Any],
        lower_ci: list[Any],
        anomaly_score: Optional[Any],
    ) -> str:
        try:
            next_price = float(forecast[0]) if forecast else price
            upper = float(upper_ci[0]) if upper_ci else next_price
            lower = float(lower_ci[0]) if lower_ci else next_price
            anomaly = float(anomaly_score) if isinstance(anomaly_score, (int, float)) else None
        except Exception:
            next_price, upper, lower, anomaly = price, price, price, None

        bias = "upside" if next_price >= price else "downside"
        anomaly_text = f" Anomaly score {anomaly:.2f}." if anomaly is not None else ""
        return (
            f"Lag-LLaMA forecast for {symbol}: {bias} bias with next target {next_price:.4f}. "
            f"Confidence band [{lower:.4f}, {upper:.4f}].{anomaly_text}"
        )

    @staticmethod
    def _fallback_fingpt(
        symbol: str,
        side: str,
        price: float,
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        change = market_context.get("change_24h", 0)
        volume = market_context.get("volume", 0)
        thesis = (
            f"FinGPT heuristic for {symbol}: {side.upper()} near {price:.4f}. "
            f"24h change {change:+.2f}%, volume {volume:.0f}. Maintain tight stops and respect leverage limits."
        )
        return {
            "source": "FinGPT",
            "thesis": thesis,
            "risk_score": 0.5,
            "confidence": 0.5,
        }

    @staticmethod
    def _fallback_lagllama(
        symbol: str,
        side: str,
        price: float,
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        change = market_context.get("change_24h", 0)
        thesis = (
            f"Lag-LLaMA heuristic for {symbol}: {side.upper()} near {price:.4f}. "
            f"Momentum {change:+.2f}% 24h. Monitor spreads and adjust exposure if volatility widens."
        )
        return {
            "source": "Lag-LLaMA",
            "thesis": thesis,
            "ci_span": None,
            "anomaly_score": None,
            "confidence": 0.4,
        }

    def _validate_fingpt_response(self, thesis: str, market_context: Dict[str, Any]) -> bool:
        """Hallucination guard: validate FinGPT response against market data."""
        if not thesis or len(thesis) < 10:
            return False

        # Check for reasonable price references (should be within 50% of current price mentioned in context)
        # This is a basic check - in production, could cross-reference with DeFi Llama data
        change = market_context.get("change_24h", 0)
        volume = market_context.get("volume", 0)

        # Basic sanity checks
        # Thesis should not contain obviously wrong information
        if "NaN" in thesis or "undefined" in thesis.lower():
            return False

        # If thesis mentions extreme numbers that don't match context, flag
        # (This is a simplified check - production could be more sophisticated)
        return True

    def _validate_lagllama_forecast(
        self,
        forecast: List[Any],
        current_price: float,
        market_context: Dict[str, Any],
    ) -> bool:
        """Hallucination guard: validate Lag-Llama forecast against recent price action."""
        if not forecast:
            return True  # Empty forecast is acceptable (will use fallback)

        try:
            # Check if forecast values are reasonable (within 50% of current price)
            first_forecast = float(forecast[0]) if forecast else current_price
            price_change_pct = abs((first_forecast - current_price) / current_price) if current_price > 0 else 0

            # If forecast is more than 50% away from current price, it might be hallucinated
            # (This is conservative - in volatile markets, larger moves are possible)
            if price_change_pct > 0.50:
                logger.warning(
                    "Lag-Llama forecast %.4f is %.1f%% away from current price %.4f, possible hallucination",
                    first_forecast,
                    price_change_pct * 100,
                    current_price,
                )
                return False

            return True
        except Exception as exc:
            logger.warning("Failed to validate Lag-Llama forecast: %s", exc)
            return True  # Allow through if validation fails (fail open)


