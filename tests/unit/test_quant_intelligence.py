from __future__ import annotations

import json

from lib.autonomy import quant_intelligence as qi


def test_quant_flywheel_is_read_only_and_paper_safe() -> None:
    payload = qi.build_quant_intelligence_flywheel(fetch_live=False)

    assert payload["mode"] == "quant_intelligence_flywheel"
    assert payload["execution_enabled"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["telegram_sends_enabled"] is False
    assert payload["writes_by_default"] is False
    assert "no_order_submission" in payload["safety"]["guards"]
    assert "no_tradingview_mutation" in payload["safety"]["guards"]
    assert "paper_forward_only" in payload["safety"]["guards"]


def test_quant_flywheel_names_universes_sources_and_validation_gates() -> None:
    payload = qi.build_quant_intelligence_flywheel(fetch_live=False)

    universes = {row["id"]: row for row in payload["watch_universes"]}
    signals = {row["id"]: row for row in payload["signal_families"]}
    validation = {row["id"]: row for row in payload["validation_stack"]}
    sources = {row["id"]: row for row in payload["data_source_roadmap"]}

    assert {"core_crypto_liquidity", "macro_risk_sensors", "eth_defi_rwa_agentic"} <= set(universes)
    assert {"BTC", "ETH", "SOL"} <= set(universes["core_crypto_liquidity"]["symbols"])
    assert "VIX" in universes["macro_risk_sensors"]["symbols"]
    assert {"multi_horizon_trend", "volatility_and_risk_regime"} <= set(signals)
    assert {"walk_forward_oos", "cpcv_embargo", "deflated_sharpe"} <= set(validation)
    assert {"defillama_defi_fundamentals", "fred_macro_regime", "sec_edgar_events"} <= set(sources)
    assert payload["totals"]["unique_watch_symbols"] >= 30
    assert payload["source_docs"]


def test_quant_work_orders_are_safe_sorted_and_dispatchable() -> None:
    payload = qi.build_quant_intelligence_flywheel(fetch_live=False)
    work_orders = payload["work_orders"]
    ids = [row["id"] for row in work_orders]
    priorities = [row["priority"] for row in work_orders]

    assert len(ids) == len(set(ids))
    assert priorities == sorted(priorities, key=lambda value: qi.PRIORITY_ORDER[value])
    assert {row["safe_mode"] for row in work_orders} <= qi.SAFE_MODES
    assert payload["dispatch_now"]
    assert all(row["priority"] == "P1" for row in payload["dispatch_now"])
    assert any(row["id"] == "tradingview-readback-alert-replay" for row in payload["dispatch_now"])
    assert all("order submission" not in row["description"].lower() for row in work_orders)


def test_quant_flywheel_cli_emits_json(capsys) -> None:
    exit_code = qi.cli(["--pretty"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "quant_intelligence_flywheel"
    assert payload["live_requested"] is False
