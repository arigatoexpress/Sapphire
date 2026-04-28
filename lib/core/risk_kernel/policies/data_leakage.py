"""Data-leakage and bypass-attempt guard policy."""

from __future__ import annotations

import re
from typing import Any

from lib.core.risk_kernel.types import DecisionEnvelope, PolicyResult

_SECRETISH_RE = re.compile(
    r"(?i)(api[_-]?key|password|secret|private[_-]?key|bearer\s+[a-z0-9._~+/=-]+|"
    r"sk_live_[a-z0-9_]+|ghp_[a-z0-9_]{20,}|akia[0-9a-z]{12,}|"
    r"\b\d{8,12}:AA[a-z0-9_-]{20,}|\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\."
    r"\d{1,3}\.\d{1,3}\b|\bcustomer\s+pin\b|\bbalance\s+is\s+\$[0-9,]+)"
)
_BYPASS_KEYS = {
    "bypass_kill_switch",
    "ignore_risk_kernel",
    "ignore_risk_limits",
    "force_execute",
    "disable_confirmation_firewall",
}
_LOOKAHEAD_KEYS = {
    "lookahead_bias",
    "uses_future_data",
    "future_data",
    "future_timestamp",
    "label_leakage",
}


class DataLeakagePolicy:
    """Reject lookahead, secret-bearing, or explicit safety-bypass evidence."""

    name = "data_leakage_guard"
    version = "1.0.0"

    def __init__(self) -> None:
        self.params: dict[str, Any] = {
            "lookahead_keys": sorted(_LOOKAHEAD_KEYS),
            "bypass_keys": sorted(_BYPASS_KEYS),
        }

    def check(self, envelope: DecisionEnvelope) -> PolicyResult:
        reasons: list[str] = []
        metrics: dict[str, Any] = {}
        all_maps = {
            "risk_metrics": envelope.risk_metrics,
            "metadata": envelope.metadata,
            "market_data": envelope.market_data,
        }

        for source, mapping in all_maps.items():
            for key, value in mapping.items():
                key_norm = str(key).strip().lower()
                if key_norm in _LOOKAHEAD_KEYS and _truthy(value):
                    reasons.append(f"{source}.{key_norm} indicates lookahead")
                if key_norm in _BYPASS_KEYS and _truthy(value):
                    reasons.append(f"{source}.{key_norm} attempts safety bypass")

        feature_ts = _as_float(envelope.metadata.get("feature_timestamp"))
        decision_ts = _as_float(envelope.metadata.get("decision_timestamp"))
        if feature_ts is not None and decision_ts is not None and feature_ts > decision_ts:
            reasons.append("feature_timestamp is after decision_timestamp")
            metrics["feature_timestamp_delta_sec"] = feature_ts - decision_ts

        text_fields = []
        for key in ("prompt", "prompt_excerpt", "rationale", "model_context"):
            value = envelope.metadata.get(key)
            if value:
                text_fields.append(str(value))
        combined = "\n".join(text_fields)
        if combined and _SECRETISH_RE.search(combined):
            reasons.append("metadata text contains secret-shaped material")
            metrics["metadata_text_chars"] = len(combined)

        if reasons:
            return PolicyResult(
                policy=self.name,
                version=self.version,
                passed=False,
                reason="; ".join(reasons),
                metrics=metrics,
                params=dict(self.params),
            )
        return PolicyResult(
            policy=self.name,
            version=self.version,
            passed=True,
            reason="no lookahead, secret-shaped prompt, or bypass evidence",
            metrics=metrics,
            params=dict(self.params),
        )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "active", "enabled"}


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
