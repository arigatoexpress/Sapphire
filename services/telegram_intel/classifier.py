"""Optional local inference classifier for Telegram intel messages."""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.telegram_intel.models import ClassificationResult
from services.telegram_intel.quality_filter import infer_tags

DEFAULT_PROXY_URL = "http://127.0.0.1:11435/v1/chat/completions"
DEFAULT_MODEL = "balanced"
DEFAULT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class ClassifierModelInfo:
    name: str
    endpoint: str
    timeout_seconds: int
    enabled_by_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "endpoint": self.endpoint,
            "timeout_seconds": self.timeout_seconds,
            "enabled_by_default": self.enabled_by_default,
        }


def available_models() -> dict[str, Any]:
    return {
        "default": DEFAULT_MODEL,
        "optional_classifier": ClassifierModelInfo(
            name=DEFAULT_MODEL,
            endpoint=DEFAULT_PROXY_URL,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        ).to_dict(),
        "fallback": "heuristic-fallback",
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    candidate = match.group(0) if match else cleaned
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def heuristic_classification(text: str) -> ClassificationResult:
    tags = infer_tags(text)
    label = tags[0] if tags else "general-intel"
    confidence = 0.55 if tags else 0.35
    return ClassificationResult(
        label=label,
        confidence=confidence,
        topics=tags,
        model="heuristic",
        source="heuristic-fallback",
        rationale="local classifier disabled or unavailable",
    )


class LocalClassifier:
    """OpenAI-compatible classifier over the local Sapphire inference proxy."""

    def __init__(
        self,
        *,
        enabled: bool,
        model: str = DEFAULT_MODEL,
        proxy_url: str = DEFAULT_PROXY_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        call: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.enabled = enabled
        self.model = model or DEFAULT_MODEL
        self.proxy_url = proxy_url
        self.timeout_seconds = timeout_seconds
        self._call = call

    def classify(self, text: str, *, channel_id: str | None = None) -> ClassificationResult:
        if not self.enabled:
            return heuristic_classification(text)
        prompt = (
            "Classify this Telegram channel intel item for Sapphire. Return strict JSON "
            "with keys label, confidence, topics, rationale. Labels should be one of "
            "security, markets, ai, policy, infra, onchain, general-intel. Do not include "
            "PII or quote the message.\n\n"
            f"Channel: {channel_id or 'unknown'}\nMessage:\n{text[:2000]}"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0.0,
            "max_tokens": 180,
        }
        try:
            data = self._call(payload) if self._call else self._post(payload)
            content = (
                data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if isinstance(data, dict)
                else ""
            )
            parsed = _extract_json(content)
            if not parsed:
                raise ValueError("classifier returned non-json")
            label = str(parsed.get("label") or "general-intel").strip()[:80]
            confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
            topics_raw = parsed.get("topics") or ()
            topics = (
                tuple(str(topic).strip()[:40] for topic in topics_raw if str(topic).strip())
                if isinstance(topics_raw, list)
                else ()
            )
            return ClassificationResult(
                label=label or "general-intel",
                confidence=confidence,
                topics=topics,
                model=self.model,
                source="local-inference-proxy",
                rationale=str(parsed.get("rationale") or "")[:500],
            )
        except Exception as exc:
            fallback = heuristic_classification(text)
            return ClassificationResult(
                label=fallback.label,
                confidence=fallback.confidence,
                topics=fallback.topics,
                model=self.model,
                source="heuristic-fallback",
                rationale="classifier fallback after local proxy error",
                error=exc.__class__.__name__,
            )

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.proxy_url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
