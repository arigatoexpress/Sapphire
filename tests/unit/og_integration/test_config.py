"""Tests for lib.og.config — feature flag + network resolution."""

from __future__ import annotations

import pytest

from lib.og import config


class TestFeatureFlag:
    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(config.ENV_FLAG, raising=False)
        assert config.is_enabled() is False

    def test_enabled_when_set_to_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(config.ENV_FLAG, "1")
        assert config.is_enabled() is True

    def test_other_truthy_values_do_not_enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Strict opt-in. "true" / "yes" don't count, only "1".
        for v in ("true", "yes", "on", "TRUE"):
            monkeypatch.setenv(config.ENV_FLAG, v)
            assert config.is_enabled() is False, f"unexpectedly enabled by {v!r}"


class TestNetworkConfig:
    def test_testnet_chain_id(self) -> None:
        cfg = config.network_config("testnet")
        assert cfg.chain_id == 16602
        assert cfg.rpc_url == "https://evmrpc-testnet.0g.ai"
        assert cfg.indexer_url == "https://indexer-storage-testnet-turbo.0g.ai"

    def test_mainnet_chain_id(self) -> None:
        cfg = config.network_config("mainnet")
        assert cfg.chain_id == 16661
        assert cfg.rpc_url == "https://evmrpc.0g.ai"
        assert cfg.indexer_url == "https://indexer-storage-mainnet-turbo.0g.ai"

    def test_default_is_testnet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(config.ENV_NETWORK, raising=False)
        assert config.network_config().name == "testnet"

    def test_env_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(config.ENV_NETWORK, "mainnet")
        assert config.network_config().name == "mainnet"

    def test_explicit_arg_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(config.ENV_NETWORK, "mainnet")
        assert config.network_config("testnet").name == "testnet"

    def test_unknown_network_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown 0G network"):
            config.network_config("rinkeby")

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(config.ENV_NETWORK, "MAINNET")
        assert config.network_config().name == "mainnet"
