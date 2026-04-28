from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from lib.sources.defillama import DeFiLlamaSource


def test_defillama_dry_run_reads_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_DEFILLAMA_LIVE", raising=False)
    cache = tmp_path / "defillama.json"
    cache.write_text(
        json.dumps(
            {
                "protocols": {
                    "ETH": {
                        "slug": "ethereum",
                        "retrieved_at": datetime.now(UTC).isoformat(),
                        "protocol": {
                            "tvl": [{"date": 1, "totalLiquidityUSD": 1000}],
                            "change_1d": 0.80,
                        },
                        "fees": {"total24h": 25, "change_1d": 0.70},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    sig = DeFiLlamaSource(cache_path=cache).latest_for("ETH-USD", "1d")

    assert sig is not None
    assert sig.source == "defillama"
    assert sig.direction == "bull"
    assert sig.raw["tvl_usd"] == pytest.approx(1000)
    assert sig.raw["daily_revenue_usd"] == pytest.approx(25)
    assert sig.raw["live_operator_flag"] is False


def test_defillama_live_gate_fetches_and_caches(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_DEFILLAMA_LIVE", "1")
    seen: list[str] = []

    def fake_fetch(url, _headers):
        seen.append(url)
        if "/summary/fees/" in url:
            return {"total24h": 50, "change_1d": 0.2}
        return {"tvl": [{"totalLiquidityUSD": 2000}], "change_1d": 0.8}

    cache = tmp_path / "live.json"
    src = DeFiLlamaSource(protocol_map={"BTC": "bitcoin"}, cache_path=cache, fetcher=fake_fetch)

    sig = src.latest_for("BTC", "1h")

    assert sig is not None
    assert len(seen) == 2
    assert cache.exists()
    assert sig.raw["live_operator_flag"] is True
