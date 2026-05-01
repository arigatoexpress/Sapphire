"""Tests for the signal envelope used by og_publish."""

from __future__ import annotations

import hashlib
import json

import pytest

from lib.og.envelope import (
    ENVELOPE_VERSION,
    InferenceAttestation,
    build_envelope,
    confidence_to_bp,
    direction_from_action,
)


class TestDirectionMapping:
    @pytest.mark.parametrize(
        "action,expected",
        [
            ("buy", 1),
            ("BUY", 1),
            ("long", 1),
            ("open_long", 1),
            ("bull", 1),
            ("sell", 2),
            ("SELL", 2),
            ("short", 2),
            ("open_short", 2),
            ("bear", 2),
            ("hold", 0),
            ("", 0),
            ("garbage", 0),
        ],
    )
    def test_direction_from_action(self, action: str, expected: int) -> None:
        assert direction_from_action(action) == expected


class TestConfidenceMapping:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (None, 0),
            (-5, 0),
            (0, 0),
            (50, 5000),
            (50.0, 5000),
            (100, 10000),
            (101, 10000),
            (0.5, 5000),  # fractional inputs scaled
            (1.0, 10000),
        ],
    )
    def test_confidence_to_bp(self, score: float | int | None, expected: int) -> None:
        assert confidence_to_bp(score) == expected


class TestEnvelope:
    def test_canonical_json_is_deterministic(self) -> None:
        e1 = build_envelope(
            strategy="kronos_btc_24h",
            symbol="BTC-USD",
            direction=1,
            confidence_bp=8300,
            signal={"price": 65000, "score": 83},
            inputs={"ohlcv_window": "24h"},
        )
        e2 = build_envelope(
            strategy="kronos_btc_24h",
            symbol="BTC-USD",
            direction=1,
            confidence_bp=8300,
            signal={"score": 83, "price": 65000},  # different key order
            inputs={"ohlcv_window": "24h"},
        )
        # Note: published_at differs across calls — we only assert keys/values are stable
        d1 = json.loads(e1.canonical_json())
        d2 = json.loads(e2.canonical_json())
        d1.pop("published_at")
        d2.pop("published_at")
        assert d1 == d2

    def test_inputs_fingerprint_is_stable(self) -> None:
        a = build_envelope(
            strategy="s",
            symbol="BTC",
            direction=1,
            confidence_bp=5000,
            inputs={"a": 1, "b": 2},
        )
        b = build_envelope(
            strategy="s",
            symbol="BTC",
            direction=1,
            confidence_bp=5000,
            inputs={"b": 2, "a": 1},
        )
        assert a.inputs_fingerprint == b.inputs_fingerprint

    def test_content_hash_is_sha256_of_canonical_json(self) -> None:
        e = build_envelope(
            strategy="s",
            symbol="ETH",
            direction=2,
            confidence_bp=7100,
            signal={"x": 1},
        )
        expected = "0x" + hashlib.sha256(e.canonical_json().encode()).hexdigest()
        assert e.content_hash() == expected

    def test_attestation_carries_chat_id(self) -> None:
        att = InferenceAttestation(
            provider_address="0xabc",
            model="qwen3:14b",
            chat_id="chatcmpl-xyz",
            base_url="https://provider.example/v1/proxy",
        )
        e = build_envelope(
            strategy="s", symbol="BTC", direction=1, confidence_bp=5000, inference=att
        )
        loaded = json.loads(e.canonical_json())
        assert loaded["inference"]["chat_id"] == "chatcmpl-xyz"
        assert loaded["inference"]["provider_address"] == "0xabc"

    def test_envelope_version_is_pinned(self) -> None:
        e = build_envelope(
            strategy="s", symbol="BTC", direction=0, confidence_bp=0
        )
        assert e.version == ENVELOPE_VERSION
