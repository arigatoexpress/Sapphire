"""Tests for live-gated on-chain provider clients."""

from __future__ import annotations

import pytest

from lib.chain.providers import eth_node as eth_mod
from lib.chain.providers import glassnode as glassnode_mod
from lib.chain.providers import sol_node as sol_mod
from lib.chain.providers.eth_node import EthNodeClient
from lib.chain.providers.glassnode import GlassnodeClient
from lib.chain.providers.sol_node import SolNodeClient
from lib.chain.sources import SourceError


def test_glassnode_fixture_mode_does_not_call_http(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_GLASSNODE_LIVE", raising=False)
    monkeypatch.delenv("GLASSNODE_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(glassnode_mod, "http_get", boom)
    snap = GlassnodeClient().asset_snapshot("ETH", days=9999)

    assert snap["mode"] == "fixture"
    assert snap["backfill_days"] == 730
    assert snap["active_addresses"] == 520000
    assert snap["nupl"] == 0.31
    assert snap["mvrv_z"] == 1.8
    assert snap["hodl_waves_1y_plus_pct"] == 0.47
    assert snap["lth_supply"] == 78000000
    assert snap["etf_balance_proxies"]["proxy_source"]


def test_glassnode_live_uses_header_and_usage_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_GLASSNODE_LIVE", "1")
    monkeypatch.setenv("GLASSNODE_API_KEY", "g-key")
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))
    captured = {}

    def fake(url, *, headers=None, params=None, **_kwargs):
        captured.update(url=url, headers=dict(headers or {}), params=dict(params or {}))
        return [{"t": "2026-04-28T00:00:00Z", "v": 123}]

    monkeypatch.setattr(glassnode_mod, "http_get", fake)
    out = GlassnodeClient().active_addresses("BTC", days=7)

    assert out[-1]["v"] == 123
    assert captured["headers"]["X-Api-Key"] == "g-key"
    assert captured["params"]["a"] == "btc"
    assert (tmp_path / "usage.json").exists()


def test_glassnode_named_metrics_use_known_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_GLASSNODE_LIVE", "1")
    monkeypatch.setenv("GLASSNODE_API_KEY", "g-key")
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))
    seen: list[str] = []

    def fake(url, *, headers=None, params=None, **_kwargs):
        del headers, params
        seen.append(url)
        return [{"t": "2026-04-28T00:00:00Z", "v": 1}]

    monkeypatch.setattr(glassnode_mod, "http_get", fake)
    client = GlassnodeClient()
    client.nupl("BTC")
    client.mvrv_z("BTC")
    client.hodl_waves("BTC")
    client.lth_supply("BTC")

    assert any(url.endswith("/indicators/net_unrealized_profit_loss") for url in seen)
    assert any(url.endswith("/market/mvrv_z_score") for url in seen)
    assert any(url.endswith("/supply/hodl_waves") for url in seen)
    assert any(url.endswith("/supply/long_term_holder") for url in seen)


def test_eth_node_rejects_transaction_submission(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_ETH_NODE_LIVE", raising=False)

    with pytest.raises(SourceError):
        EthNodeClient().rpc("eth_sendRawTransaction", ["0xdead"])


def test_eth_node_live_rpc_posts_only_when_gated(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_ETH_NODE_LIVE", "1")
    monkeypatch.setenv("ETH_RPC_URL", "https://eth.example.test")
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))
    captured = {}

    def fake(url, payload, **_kwargs):
        captured.update(url=url, payload=payload)
        return {"jsonrpc": "2.0", "id": 1, "result": "0x1"}

    monkeypatch.setattr(eth_mod, "http_post_json", fake)

    assert EthNodeClient().chain_id() == 1
    assert captured["payload"]["method"] == "eth_chainId"


def test_sol_node_rejects_mutating_methods(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_SOL_NODE_LIVE", raising=False)

    with pytest.raises(SourceError):
        SolNodeClient().rpc("sendTransaction", ["deadbeef"])


def test_sol_node_fixture_snapshot_is_read_only(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_SOL_NODE_LIVE", raising=False)
    monkeypatch.delenv("SOL_RPC_URL", raising=False)

    snap = SolNodeClient().network_snapshot()

    assert snap["mode"] == "fixture"
    assert snap["read_only"] is True
    assert snap["wallet_keys_required"] is False
    assert snap["latest_blockhash"].startswith("DryRun")


def test_sol_node_live_rpc_posts_when_gated(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_SOL_NODE_LIVE", "1")
    monkeypatch.setenv("SOL_RPC_URL", "https://sol.example.test")
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))
    captured = {}

    def fake(url, payload, **_kwargs):
        captured.update(url=url, payload=payload)
        return {"jsonrpc": "2.0", "id": 1, "result": 123}

    monkeypatch.setattr(sol_mod, "http_post_json", fake)

    assert SolNodeClient().slot() == 123
    assert captured["payload"]["method"] == "getSlot"
