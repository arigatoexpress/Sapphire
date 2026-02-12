"""
Dual-Speed Cognition Pipeline - System 1 / System 2 Processing

This module implements the Kahneman-inspired dual-process architecture:
- System 1 (Flash): Fast, intuitive decisions (<50ms)
- System 2 (Pro): Deep, analytical validation (1-3s)

Key Innovation: System 1 can make provisional trades that System 2 validates.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


class CognitionSpeed(str, Enum):
    """Which cognitive system to engage."""

    SYSTEM_1 = "system_1"  # Fast/Flash - intuitive
    SYSTEM_2 = "system_2"  # Slow/Pro - analytical
    DUAL = "dual"  # Both systems coordinated


@dataclass
class CognitionRequest:
    """Request for cognitive processing."""

    prompt: str
    context: Dict[str, Any] = field(default_factory=dict)
    speed: CognitionSpeed = CognitionSpeed.DUAL
    max_latency_ms: float = 5000.0  # Max time allowed
    requires_validation: bool = True


@dataclass
class CognitionResult:
    """Result of cognitive processing."""

    decision: str
    confidence: float
    reasoning: str
    system_used: CognitionSpeed
    latency_ms: float

    # Dual-speed specific
    system1_decision: Optional[str] = None
    system2_validation: Optional[str] = None
    was_overridden: bool = False


class DualSpeedCognition:
    """
    Dual-process cognitive architecture using Gemini Flash + Pro.

    System 1 (Flash):
    - Responds in <50ms
    - Pattern matching, heuristics
    - Good for routine decisions

    System 2 (Pro):
    - Takes 1-3 seconds
    - Deep analysis, reasoning
    - Validates System 1 or handles complex cases

    Novel Mechanism:
    - System 1 can trigger "provisional" actions
    - System 2 validates and can reverse within a "cognitive window"
    """

    SYSTEM_1_MODEL = "gemini-2.0-flash"
    SYSTEM_2_MODEL = "gemini-2.0-pro-exp-02-05"

    # Thresholds
    INSTANT_ACTION_THRESHOLD = 0.85  # System 1 confidence to act immediately
    VALIDATION_REQUIRED_THRESHOLD = 0.70  # Below this, always wait for System 2
    COGNITIVE_WINDOW_MS = 2000  # Time allowed for System 2 to override

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        if api_key:
            genai.configure(api_key=api_key)
            self.system1 = genai.GenerativeModel(self.SYSTEM_1_MODEL)
            self.system2 = genai.GenerativeModel(self.SYSTEM_2_MODEL)
            logger.info(f"🧠 Dual-Speed Cognition initialized (Flash + Pro)")
        else:
            self.system1 = None
            self.system2 = None
            logger.warning("⚠️ No API key - Dual Cognition in mock mode")

        # Metrics
        self.system1_calls = 0
        self.system2_calls = 0
        self.overrides = 0
        self.avg_system1_latency_ms = 0.0
        self.avg_system2_latency_ms = 0.0

    async def process(
        self,
        request: CognitionRequest,
        on_provisional_decision: Optional[Callable] = None,
    ) -> CognitionResult:
        """
        Process a cognitive request through the dual-speed pipeline.

        Args:
            request: The cognition request
            on_provisional_decision: Callback for System 1 provisional actions

        Returns:
            CognitionResult with decision and validation status
        """
        if request.speed == CognitionSpeed.SYSTEM_1:
            return await self._process_system1_only(request)
        elif request.speed == CognitionSpeed.SYSTEM_2:
            return await self._process_system2_only(request)
        else:
            return await self._process_dual(request, on_provisional_decision)

    async def _process_system1_only(self, request: CognitionRequest) -> CognitionResult:
        """Fast path - System 1 only."""
        start = time.time()

        decision, confidence, reasoning = await self._invoke_system1(request.prompt)

        latency = (time.time() - start) * 1000
        self._update_system1_metrics(latency)

        return CognitionResult(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            system_used=CognitionSpeed.SYSTEM_1,
            latency_ms=latency,
            system1_decision=decision,
        )

    async def _process_system2_only(self, request: CognitionRequest) -> CognitionResult:
        """Deep path - System 2 only."""
        start = time.time()

        decision, confidence, reasoning = await self._invoke_system2(request.prompt)

        latency = (time.time() - start) * 1000
        self._update_system2_metrics(latency)

        return CognitionResult(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            system_used=CognitionSpeed.SYSTEM_2,
            latency_ms=latency,
            system2_validation=decision,
        )

    async def _process_dual(
        self,
        request: CognitionRequest,
        on_provisional: Optional[Callable] = None,
    ) -> CognitionResult:
        """
        Dual-process path - the core innovation.

        1. System 1 makes rapid assessment
        2. If confidence > INSTANT threshold, optionally act provisionally
        3. System 2 validates in parallel
        4. If System 2 disagrees, override
        """
        start = time.time()

        # Launch both systems in parallel
        system1_task = asyncio.create_task(self._invoke_system1(request.prompt))
        system2_task = asyncio.create_task(
            self._invoke_system2(f"{request.prompt}\n\nProvide deep analysis and validation.")
        )

        # Wait for System 1 first (should be much faster)
        s1_decision, s1_confidence, s1_reasoning = await system1_task
        s1_latency = (time.time() - start) * 1000
        self._update_system1_metrics(s1_latency)

        # Check if we should act provisionally
        provisional_action_taken = False
        if s1_confidence >= self.INSTANT_ACTION_THRESHOLD and on_provisional:
            logger.info(f"⚡ System 1 high confidence ({s1_confidence:.2f}), provisional action")
            try:
                await on_provisional(s1_decision, s1_confidence, s1_reasoning)
                provisional_action_taken = True
            except Exception as e:
                logger.error(f"Provisional action failed: {e}")

        # Wait for System 2 validation
        try:
            s2_decision, s2_confidence, s2_reasoning = await asyncio.wait_for(
                system2_task,
                timeout=request.max_latency_ms / 1000,
            )
            s2_latency = (time.time() - start) * 1000
            self._update_system2_metrics(s2_latency - s1_latency)
        except asyncio.TimeoutError:
            logger.warning("System 2 timeout - using System 1 decision")
            return CognitionResult(
                decision=s1_decision,
                confidence=s1_confidence,
                reasoning=s1_reasoning + "\n[System 2 TIMEOUT - unvalidated]",
                system_used=CognitionSpeed.SYSTEM_1,
                latency_ms=(time.time() - start) * 1000,
                system1_decision=s1_decision,
            )

        # Check for override
        was_overridden = self._should_override(s1_decision, s2_decision, s2_confidence)

        if was_overridden:
            self.overrides += 1
            logger.warning(f"🔄 System 2 OVERRIDES System 1: {s1_decision} -> {s2_decision}")

            final_decision = s2_decision
            final_confidence = s2_confidence
            final_reasoning = f"[OVERRIDE] {s2_reasoning}"
        else:
            final_decision = s1_decision
            final_confidence = (s1_confidence + s2_confidence) / 2  # Average confidence
            final_reasoning = f"System 1: {s1_reasoning}\nSystem 2 Validates: {s2_reasoning}"

        total_latency = (time.time() - start) * 1000

        return CognitionResult(
            decision=final_decision,
            confidence=final_confidence,
            reasoning=final_reasoning,
            system_used=CognitionSpeed.DUAL,
            latency_ms=total_latency,
            system1_decision=s1_decision,
            system2_validation=s2_decision,
            was_overridden=was_overridden,
        )

    async def _invoke_system1(self, prompt: str) -> tuple:
        """Invoke Gemini Flash for fast response."""
        if not self.system1:
            return ("HOLD", 0.5, "[MOCK] System 1 response")

        try:
            self.system1_calls += 1

            system1_prompt = f"""You are a fast-thinking trading intuition system.
Respond QUICKLY with:
DECISION: [BUY/SELL/HOLD]
CONFIDENCE: [0.0-1.0]
REASON: [One sentence]

{prompt}"""

            response = await asyncio.to_thread(
                lambda: self.system1.generate_content(
                    system1_prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=128,
                        temperature=0.3,
                    ),
                )
            )

            return self._parse_response(response.text)

        except Exception as e:
            logger.error(f"System 1 error: {e}")
            return ("HOLD", 0.5, f"Error: {e}")

    async def _invoke_system2(self, prompt: str) -> tuple:
        """Invoke Gemini Pro for deep analysis."""
        if not self.system2:
            return ("HOLD", 0.5, "[MOCK] System 2 response")

        try:
            self.system2_calls += 1

            system2_prompt = f"""You are a deep-thinking trading analysis system.
Take your time to analyze thoroughly.

Respond with:
DECISION: [BUY/SELL/HOLD]
CONFIDENCE: [0.0-1.0]
ANALYSIS: [Detailed reasoning with risk factors]

{prompt}"""

            response = await asyncio.to_thread(
                lambda: self.system2.generate_content(
                    system2_prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=512,
                        temperature=0.5,
                    ),
                )
            )

            return self._parse_response(response.text)

        except Exception as e:
            logger.error(f"System 2 error: {e}")
            return ("HOLD", 0.5, f"Error: {e}")

    def _parse_response(self, text: str) -> tuple:
        """Parse LLM response into structured output."""
        decision = "HOLD"
        confidence = 0.5
        reasoning = text

        if "DECISION:" in text:
            decision_line = text.split("DECISION:")[1].split("\n")[0].strip().upper()
            if "BUY" in decision_line:
                decision = "BUY"
            elif "SELL" in decision_line:
                decision = "SELL"

        if "CONFIDENCE:" in text:
            try:
                conf_line = text.split("CONFIDENCE:")[1].split("\n")[0].strip()
                confidence = float(conf_line)
            except:
                pass

        return (decision, confidence, reasoning)

    def _should_override(
        self,
        s1_decision: str,
        s2_decision: str,
        s2_confidence: float,
    ) -> bool:
        """Determine if System 2 should override System 1."""
        # Different decisions with high System 2 confidence = override
        if s1_decision != s2_decision and s2_confidence >= 0.7:
            return True

        # System 2 says HOLD but System 1 wants to trade = override (safety)
        if s2_decision == "HOLD" and s1_decision in ("BUY", "SELL") and s2_confidence >= 0.6:
            return True

        return False

    def _update_system1_metrics(self, latency_ms: float):
        """Update System 1 performance metrics."""
        if self.system1_calls == 1:
            self.avg_system1_latency_ms = latency_ms
        else:
            self.avg_system1_latency_ms = (self.avg_system1_latency_ms + latency_ms) / 2

    def _update_system2_metrics(self, latency_ms: float):
        """Update System 2 performance metrics."""
        if self.system2_calls == 1:
            self.avg_system2_latency_ms = latency_ms
        else:
            self.avg_system2_latency_ms = (self.avg_system2_latency_ms + latency_ms) / 2

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return {
            "system1_calls": self.system1_calls,
            "system2_calls": self.system2_calls,
            "overrides": self.overrides,
            "override_rate": self.overrides / max(1, self.system2_calls),
            "avg_system1_latency_ms": self.avg_system1_latency_ms,
            "avg_system2_latency_ms": self.avg_system2_latency_ms,
        }


# Global instance
_cognition_instance: Optional[DualSpeedCognition] = None


def get_dual_cognition() -> DualSpeedCognition:
    """Get or create the global dual-speed cognition instance."""
    global _cognition_instance
    if _cognition_instance is None:
        _cognition_instance = DualSpeedCognition()
    return _cognition_instance


async def demo_dual_cognition():
    """Demo the dual-speed cognition system."""
    cognition = get_dual_cognition()

    request = CognitionRequest(
        prompt="""Market Data:
- SOL is up 5% in 1H
- Volume spike detected (3x average)
- Funding rate turning positive
- Order book shows more bids than asks

Should we BUY, SELL, or HOLD SOL?""",
        speed=CognitionSpeed.DUAL,
    )

    print("🧠 Processing through Dual-Speed Cognition...")

    async def provisional_action(decision, confidence, reasoning):
        print(f"⚡ PROVISIONAL: {decision} (conf: {confidence:.2f})")

    result = await cognition.process(request, on_provisional=provisional_action)

    print(f"\n📊 RESULT:")
    print(f"  Decision: {result.decision}")
    print(f"  Confidence: {result.confidence:.2f}")
    print(f"  System Used: {result.system_used.value}")
    print(f"  Latency: {result.latency_ms:.0f}ms")
    print(f"  Override: {result.was_overridden}")
    print(f"\n  Reasoning: {result.reasoning[:300]}...")

    print(f"\n📈 Metrics: {cognition.get_metrics()}")


if __name__ == "__main__":
    asyncio.run(demo_dual_cognition())
