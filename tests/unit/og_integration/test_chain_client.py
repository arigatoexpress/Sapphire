"""Tests for lib.og.chain — strategy hashing + input validation.

Live chain calls are out of scope for unit tests; we cover the input
validation surface and the deterministic helpers.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from lib.og import chain


class TestStrategyIdHashing:
    def test_deterministic(self) -> None:
        assert chain.strategy_id_from_name("kronos_btc_24h") == hashlib.sha256(
            b"kronos_btc_24h"
        ).digest()

    def test_different_strategies_different_ids(self) -> None:
        a = chain.strategy_id_from_name("rsi_cross")
        b = chain.strategy_id_from_name("macd_cross")
        assert a != b

    def test_returns_bytes32(self) -> None:
        out = chain.strategy_id_from_name("anything")
        assert isinstance(out, bytes)
        assert len(out) == 32


class TestPublishSignalValidation:
    """Validation runs before any web3 / network call, so we can test it
    without mocking the chain. We just need OG_PRIVATE_KEY set and the
    deployments/ABI files to be missing → we expect the chain client to
    bail with OGChainError before the validation kicks in."""

    def test_missing_deployments_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("OG_PRIVATE_KEY", "0x" + "33" * 32)
        monkeypatch.setattr(chain, "DEPLOYMENTS_FILE", tmp_path / "deployments.json")
        with pytest.raises(chain.OGChainError, match="deployments file missing"):
            chain.publish_signal(
                strategy="s",
                symbol="BTC",
                direction=1,
                confidence_bp=5000,
                proof_root_hash="0x" + "ab" * 32,
                network="testnet",
            )
