"""Sensitivity classifier — guards Kimi Cloud and other external routes.

Fast keyword + pattern engine, no LLM required. Runs in microseconds.
Used by inference-proxy (Tier 4 gate) and router.py (cloud task gate).

Usage:
    from .sensitivity_classifier import is_sensitive, SensitivityResult

    result = is_sensitive("explain the RSI indicator")
    if result.safe:
        # OK to route to Kimi Cloud
        ...

    result = is_sensitive("customer PIN is 4832")
    assert result.sensitive
    assert result.reason   # "personal: PIN"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union


# ─── Pattern groups ───────────────────────────────────────────────────────────

_GROUPS: list[tuple[str, list[str]]] = [
    # Auth / credentials
    ("credentials", [
        r"\bapi[_\-]?key\b",
        r"\bpassword\b",
        r"\bsecret\b",
        r"\btoken[=:\s\"']",
        r"bearer\s+\S",
        r"private[_\-\s]?key",
        r"ssh[_\-]?key",
        r"auth[_\-]?key",
        r"hmac[_\-]?secret",
        r"\bsign(?:ing)?[_\-]?secret\b",
    ]),

    # Financial / trading (internal)
    ("financial", [
        r"\bportfolio\b",
        r"\bposition[s]?\b",
        r"\bpnl\b",
        r"p&l\b",
        r"trading signal",
        r"wallet.{0,10}address",
        r"seed phrase",
        r"private.{0,10}wallet",
        r"\bbalance[=:\s]\s*\$",
        r"\$\s*\d[\d,]+[kKmM]?\b",  # dollar amounts
        r"\bdrawdown\b.*\d",
        r"account.{0,20}balance",
    ]),

    # Personal / customer data (THO + general)
    ("personal", [
        r"\bpin\b.{0,10}\d{4}",
        r"social security",
        r"ssn\b",
        r"\bcustomer.{0,20}name\b",
        r"\baccount.{0,20}id\b",
        r"tho.{0,10}customer",
        r"tho.{0,10}lead",
        r"firestore.{0,10}customer",
        r"enrolled.{0,20}customer",
        r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",   # US phone pattern
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",  # email
    ]),

    # System internals (Tailscale mesh, API endpoints, service configs)
    ("system_internals", [
        r"100\.\d{1,3}\.\d{1,3}\.\d{1,3}",   # Tailscale CGNAT range
        r"MOONSHOT_API_KEY",
        r"OPENAI_API_KEY",
        r"TELEGRAM_BOT_TOKEN",
        r"OPENROUTER_API_KEY",
        r"com\.sapphire\.",                    # LaunchAgent identifiers
        r"launchagents",
        r"tailscale\s+(?:up|down|status)",
    ]),
]

# Compile each group into a single pattern
_COMPILED: list[tuple[str, re.Pattern]] = [
    (group, re.compile("|".join(patterns), re.IGNORECASE))
    for group, patterns in _GROUPS
]


# ─── Public API ───────────────────────────────────────────────────────────────

@dataclass
class SensitivityResult:
    """Result of a sensitivity classification."""

    safe: bool
    reason: str = ""          # non-empty if sensitive, e.g. "credentials: api_key"
    matched_group: str = ""   # group name that triggered, e.g. "credentials"

    @property
    def sensitive(self) -> bool:
        return not self.safe


def classify(text: str) -> SensitivityResult:
    """Classify a single text string.

    Returns SENSITIVE on first match (fail-safe — err toward blocking).
    """
    for group, pattern in _COMPILED:
        m = pattern.search(text)
        if m:
            snippet = m.group(0)[:40].strip()
            return SensitivityResult(safe=False, reason=f"{group}: {snippet!r}", matched_group=group)
    return SensitivityResult(safe=True)


def is_sensitive(text_or_messages: Union[str, list]) -> SensitivityResult:
    """Classify a string or a list of OpenAI-format messages.

    Args:
        text_or_messages: Plain string, or list of {"role": ..., "content": ...} dicts.

    Returns:
        SensitivityResult — check .safe / .sensitive, .reason.
    """
    if isinstance(text_or_messages, str):
        return classify(text_or_messages)

    # OpenAI message list
    for msg in text_or_messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            result = classify(content)
            if result.sensitive:
                return result
        elif isinstance(content, list):
            # Vision/multipart content blocks
            for block in content:
                if isinstance(block, dict):
                    result = classify(block.get("text", ""))
                    if result.sensitive:
                        return result
    return SensitivityResult(safe=True)


# ─── Convenience helpers ──────────────────────────────────────────────────────

def safe_for_cloud(messages: list) -> bool:
    """Return True if messages are safe to route to Kimi Cloud / any external API."""
    return is_sensitive(messages).safe


def block_reason(messages: list) -> str:
    """Return the block reason string, or empty string if safe."""
    return is_sensitive(messages).reason


# ─── CLI self-test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        # Should be SAFE
        ("Explain the RSI indicator", True),
        ("What is a moving average?", True),
        ("Summarize the Sapphire architecture", True),
        ("Write a function to parse JSON in Python", True),

        # Should be SENSITIVE
        ("My MOONSHOT_API_KEY is sk-abc123", False),
        ("The customer PIN is 4832", False),
        ("Customer balance is $12,500", False),
        ("trading signal: BUY BTC at 95000", False),
        ("token=eyJhbGciOiJIUzI1NiJ9", False),
        ("Private key: 0xabcdef123456", False),
        ("bearer abc123token", False),
        ("Tailscale IP is 100.67.171.79", False),
        ("THO customer John enrolled", False),
        ("email me at user@example.com", False),
        ("Call 555-867-5309 for support", False),
    ]

    passed = failed = 0
    for text, expected_safe in test_cases:
        result = is_sensitive(text)
        ok = result.safe == expected_safe
        status = "✓" if ok else "✗"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"{status} {'SAFE' if result.safe else f'SENSITIVE ({result.reason})':<50}  {text[:60]}")

    print(f"\n{passed}/{passed+failed} passed")
