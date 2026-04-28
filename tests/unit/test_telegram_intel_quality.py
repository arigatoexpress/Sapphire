from __future__ import annotations

from services.telegram_intel.models import MAX_MESSAGE_CHARS, TRUNCATION_SUFFIX
from services.telegram_intel.quality_filter import (
    defang_urls,
    quality_filter,
    redact_pii,
    sanitize_text,
    truncate_text,
)

QUALITY_CASES = [
    (
        "CVE-2026-1111 exploit confirmed against edge VPN devices; patch guidance published.",
        True,
        "security",
    ),
    ("BTC funding flipped negative while spot demand rose 4.2% across majors.", True, "markets"),
    ("New open model inference benchmark shows GPU latency down 18% in agent workloads.", True, "ai"),
    ("Fed policy minutes mention liquidity stress and treasury issuance timing.", True, "policy"),
    ("Cloud DNS outage investigation published with mitigation steps.", True, "infra"),
    ("Validator bridge exploit drained token liquidity from a DeFi pool.", True, "onchain"),
    ("gm", False, None),
    ("hello", False, None),
    ("Claim now free tokens airdrop guaranteed profit", False, None),
    ("DM for promo paid post limited spots", False, None),
    ("Seed phrase private key wallet drain connect wallet", False, None),
    ("Casino jackpot guaranteed profit binary options", False, None),
    ("FORWARD THIS FORWARD THIS FORWARD THIS FORWARD THIS", False, None),
    ("Photo", False, None),
    ("Video", False, None),
    ("ok", False, None),
    ("Security team published IOC list at https://example.com/iocs for CVE-2026-2222.", True, "security"),
    ("ETH validators saw 3.1% participation drop after client release.", True, "markets"),
    ("Kubernetes incident: latency above 900ms after DNS cache regression.", True, "infra"),
    ("SEC court filing changes token policy posture for exchanges.", True, "policy"),
    ("AI agent framework patched prompt injection vulnerability with sandboxing.", True, "security"),
    ("Ransomware group exploited zero-day; mitigation playbook released.", True, "security"),
    ("Treasury yield curve steepened as inflation swaps repriced.", True, "markets"),
    ("Smart contract bridge monitor detected suspicious wallet movement.", True, "onchain"),
    ("Short note", False, None),
    ("Model training outage resolved after GPU driver rollback and queue drain.", True, "ai"),
]


def test_quality_filter_cases() -> None:
    for text, expected_keep, expected_tag in QUALITY_CASES:
        decision = quality_filter(text, channel_id="test")
        assert decision.keep is expected_keep, text
        if expected_tag:
            assert expected_tag in decision.tags


def test_defang_urls_rewrites_http_and_https() -> None:
    out = defang_urls("see https://example.com and http://example.org")
    assert "hxxps://example.com" in out
    assert "hxxp://example.org" in out


def test_defang_urls_rewrites_www() -> None:
    assert "hxxp://www.example.com" in defang_urls("visit www.example.com now")


def test_redact_pii_removes_email_phone_handle_and_wallet() -> None:
    out = redact_pii(
        "mail ari@example.com call +1 303-555-1212 ping @someuser 0x1234567890abcdef1234567890abcdef12345678"
    )
    assert "ari@example.com" not in out
    assert "303-555-1212" not in out
    assert "@someuser" not in out
    assert "0x1234" not in out
    assert "[redacted-email]" in out
    assert "[redacted-phone]" in out
    assert "[redacted-handle]" in out
    assert "[redacted-wallet]" in out


def test_sanitize_normalizes_whitespace_and_defangs() -> None:
    out = sanitize_text("  Security\n\nupdate https://example.com  ")
    assert out == "Security update hxxps://example.com"


def test_truncate_text_uses_requested_suffix() -> None:
    out = truncate_text("a" * (MAX_MESSAGE_CHARS + 20))
    assert len(out) == MAX_MESSAGE_CHARS
    assert out.endswith(TRUNCATION_SUFFIX)


def test_quality_decision_serializes_without_text() -> None:
    decision = quality_filter("CVE-2026-3333 patch released with mitigation guidance.", channel_id="c")
    payload = decision.to_dict()
    assert payload["keep"] is True
    assert "sanitized_text" not in payload


def test_spam_pattern_overrides_domain_signal() -> None:
    decision = quality_filter("CVE-2026-3333 free tokens airdrop claim now.", channel_id="c")
    assert decision.keep is False
    assert "spam-pattern" in decision.reasons


def test_repetitive_text_is_penalized() -> None:
    decision = quality_filter("market " * 30, channel_id="c")
    assert decision.keep is False
    assert "repetitive" in decision.reasons


def test_channel_attribution_adds_reason() -> None:
    decision = quality_filter("CVE-2026-4444 exploit detected and mitigation published.", channel_id="c")
    assert "attributed-channel" in decision.reasons
