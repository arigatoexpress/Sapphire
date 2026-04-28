from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.sources.dune import DuneNamedQuerySource


def test_dune_dry_run_uses_cached_named_query(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_DUNE_LIVE", raising=False)
    cache = tmp_path / "dune.json"
    cache.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "name": "btc_flow",
                        "query_id": 123,
                        "symbol": "BTC",
                        "retrieved_at": datetime.now(UTC).isoformat(),
                        "result": {
                            "result": {
                                "rows": [
                                    {
                                        "timestamp": datetime.now(UTC).isoformat(),
                                        "direction": "bull",
                                        "confidence": 0.77,
                                    }
                                ]
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    sig = DuneNamedQuerySource(cache_path=cache).latest_for("BTC", "1h")

    assert sig is not None
    assert sig.direction == "bull"
    assert sig.confidence == 0.77
    assert sig.raw["query_name"] == "btc_flow"


def test_dune_live_gate_runs_operator_config_and_writes_one_hour_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_DUNE_LIVE", "1")
    config = tmp_path / "dune_named_queries.json"
    config.write_text(
        json.dumps({"queries": [{"name": "eth_flow", "id": 456, "symbol": "ETH"}]}),
        encoding="utf-8",
    )
    calls: list[int] = []

    def fake_runner(query_id, params):
        calls.append(query_id)
        return {"result": {"rows": [{"score": -0.4}]}}

    cache = tmp_path / "cache.json"
    src = DuneNamedQuerySource(config_path=config, cache_path=cache, runner=fake_runner)

    first = src.latest_for("ETH", "1h")
    second = src.latest_for("ETH", "1h")

    assert first is not None
    assert second is not None
    assert first.direction == "bear"
    assert calls == [456]
    assert cache.exists()
