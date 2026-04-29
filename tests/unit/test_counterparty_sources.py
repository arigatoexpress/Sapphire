from __future__ import annotations

import json

import pytest

from lib.counterparty.sources import HyperliquidCounterpartyClient, HyperliquidCounterpartyConfig


def test_client_defaults_to_dry_run(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_HYPERLIQUID_LIVE", raising=False)
    assert HyperliquidCounterpartyClient().live_enabled is False


def test_status_reports_public_data_only(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_HYPERLIQUID_LIVE", raising=False)
    assert HyperliquidCounterpartyClient().status()["public_data_only"] is True


def test_dry_run_leaderboard_returns_ranked_mock(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_HYPERLIQUID_LIVE", raising=False)
    traders = HyperliquidCounterpartyClient().leaderboard(top_n=2)
    assert len(traders) == 2
    assert traders[0].realized_pnl_30d_usd >= traders[1].realized_pnl_30d_usd


def test_dry_run_positions_return_mock(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_HYPERLIQUID_LIVE", raising=False)
    positions = HyperliquidCounterpartyClient().positions("0xaaa")
    assert positions[0].asset == "BTC"


def test_live_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_LIVE", "1")
    assert HyperliquidCounterpartyClient().live_enabled is True


def test_config_to_dict():
    assert (
        HyperliquidCounterpartyConfig(api_url="https://example.com").to_dict()["api_url"]
        == "https://example.com"
    )


def test_live_leaderboard_posts_public_payload(monkeypatch, tmp_path):
    import lib.counterparty.sources as sources

    monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_LIVE", "1")
    monkeypatch.setattr(sources, "COUNTER_PATH", tmp_path / "leaderboard.json")
    monkeypatch.setattr(sources, "CACHE_DIR", tmp_path)
    client = HyperliquidCounterpartyClient(
        HyperliquidCounterpartyConfig(api_url="https://example.com")
    )
    captured = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "leaderboard": [
                        {"address": "0x1", "realized_pnl_30d_usd": 100000, "sharpe_30d": 1}
                    ]
                }
            ).encode()

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode())
        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert client.leaderboard()[0].address == "0x1"
    assert captured["body"] == {"type": "leaderboard"}


def test_live_positions_posts_public_payload(monkeypatch, tmp_path):
    import lib.counterparty.sources as sources

    monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_LIVE", "1")
    monkeypatch.setattr(sources, "COUNTER_PATH", tmp_path / "positions.json")
    monkeypatch.setattr(sources, "CACHE_DIR", tmp_path)
    client = HyperliquidCounterpartyClient()

    def fake_post(payload):
        assert payload["type"] == "clearinghouseState"
        return {
            "assetPositions": [{"position": {"coin": "BTC", "szi": "1", "signed_size_usd": 100}}]
        }

    monkeypatch.setattr(client, "_post", fake_post)
    assert client.positions("0x1")[0].asset == "BTC"


def test_post_failure_returns_empty(monkeypatch):
    client = HyperliquidCounterpartyClient()

    def boom(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert client._post({}) == {}


def test_rate_limit_raises(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_LIVE", "1")
    client = HyperliquidCounterpartyClient(HyperliquidCounterpartyConfig(max_refresh_per_hour=0))
    with pytest.raises(RuntimeError, match="rate_limit"):
        client.leaderboard()


def test_live_positions_ignores_bad_rows(monkeypatch, tmp_path):
    import lib.counterparty.sources as sources

    monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_LIVE", "1")
    monkeypatch.setattr(sources, "COUNTER_PATH", tmp_path / "bad-rows.json")
    monkeypatch.setattr(sources, "CACHE_DIR", tmp_path)
    client = HyperliquidCounterpartyClient()
    monkeypatch.setattr(client, "_post", lambda payload: {"assetPositions": [1, {"bad": "row"}]})
    assert client.positions("0x1") == []


def test_status_counts_calls(monkeypatch, tmp_path):
    import lib.counterparty.sources as sources

    monkeypatch.setattr(sources, "COUNTER_PATH", tmp_path / "counters.json")
    monkeypatch.setattr(sources, "CACHE_DIR", tmp_path)
    (tmp_path / "counters.json").write_text(json.dumps({"calls": [9999999999]}), encoding="utf-8")
    assert HyperliquidCounterpartyClient().status()["calls_last_hour"] == 1
