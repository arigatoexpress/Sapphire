"""Tests for ``lib.portfolio.aggregate``.

The aggregator is constructed with injected fake readers, so nothing here
touches the network or a real credential. Each fake implements the same three
methods the real readers expose: ``is_configured`` / ``get_holdings`` /
``get_portfolio_value``.
"""

from __future__ import annotations

from typing import Any

import pytest

from lib.portfolio.aggregate import PortfolioAggregator


class FakeReader:
    """Minimal stand-in for a venue reader."""

    def __init__(
        self,
        holdings: list[dict[str, Any]] | None = None,
        value: dict[str, Any] | None = None,
        configured: bool = True,
        prices: dict[str, float] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._holdings = holdings or []
        self._value = value or {"source": "fake", "cash": 0.0, "total_return": None}
        self._configured = configured
        self._prices = prices
        self._raises = raises

    def is_configured(self) -> bool:
        return self._configured

    def get_holdings(self) -> list[dict[str, Any]]:
        if self._raises:
            raise self._raises
        return [dict(h) for h in self._holdings]

    def get_portfolio_value(self) -> dict[str, Any]:
        if self._raises:
            raise self._raises
        return dict(self._value)

    def get_spot_prices(self) -> dict[str, float]:
        return dict(self._prices or {})


def _holding(symbol: str, qty: float, mv: float | None, **extra: Any) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "asset_code": symbol,
        "qty": qty,
        "price": (mv / qty) if mv is not None and qty else None,
        "market_value": mv,
        "avg_cost": None,
        "total_return": None,
        **extra,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_totals_sum_across_both_venues():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader(
                [_holding("BTC", 0.01, 640.0)], {"source": "robinhood", "cash": 0.01}
            ),
            "okx": FakeReader([_holding("SOL", 10.0, 700.0)], {"source": "okx", "cash": 100.0}),
        }
    )
    snap = agg.get_snapshot()
    assert snap["source"] == "aggregate"
    assert snap["venue_count"] == 2
    # 640 + 700 holdings + 100.01 venue cash
    assert snap["total_value"] == pytest.approx(1440.01)
    assert snap["buying_power"] == pytest.approx(100.01)


def test_holdings_are_tagged_with_their_venue():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("BTC", 0.01, 640.0)]),
            "okx": FakeReader([_holding("SOL", 10.0, 700.0)]),
        }
    )
    venues = {h["symbol"]: h["venue"] for h in agg.get_snapshot()["holdings"]}
    assert venues == {"BTC": "robinhood", "SOL": "okx"}


def test_holdings_sorted_by_value_across_venues():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("SMALL", 1.0, 5.0)]),
            "okx": FakeReader([_holding("BIG", 1.0, 5000.0)]),
        }
    )
    assert [h["symbol"] for h in agg.get_snapshot()["holdings"]][0] == "BIG"


def test_same_asset_on_two_venues_stays_split_in_holdings():
    """``holdings`` is the actionable view — venue-specific rows are preserved."""
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("SOL", 1.0, 70.0)]),
            "okx": FakeReader([_holding("SOL", 9.0, 630.0)]),
        }
    )
    rows = [h for h in agg.get_snapshot()["holdings"] if h["symbol"] == "SOL"]
    assert len(rows) == 2


def test_by_asset_consolidates_the_same_asset_across_venues():
    """``by_asset`` is the risk view — total SOL exposure regardless of venue."""
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("SOL", 1.0, 70.0)]),
            "okx": FakeReader([_holding("SOL", 9.0, 630.0)]),
        }
    )
    by_asset = agg.get_snapshot()["by_asset"]
    assert len(by_asset) == 1
    sol = by_asset[0]
    assert sol["qty"] == pytest.approx(10.0)
    assert sol["market_value"] == pytest.approx(700.0)
    assert sol["venue_count"] == 2
    assert {v["venue"] for v in sol["venues"]} == {"robinhood", "okx"}


def test_by_asset_weights_sum_to_one_hundred():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("A", 1.0, 250.0)]),
            "okx": FakeReader([_holding("B", 1.0, 750.0)]),
        }
    )
    weights = [r["weight"] for r in agg.get_snapshot()["by_asset"]]
    assert sum(weights) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Per-venue degradation
# ---------------------------------------------------------------------------


def test_unconfigured_venue_does_not_blank_the_portfolio():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader(
                [_holding("BTC", 0.01, 640.0)], {"source": "robinhood", "cash": 0.0}
            ),
            "okx": FakeReader(configured=False),
        }
    )
    snap = agg.get_snapshot()
    assert snap["source"] == "aggregate"
    assert snap["total_value"] == pytest.approx(640.0)
    statuses = {s["venue"]: s["status"] for s in snap["sources"]}
    assert statuses == {"robinhood": "live", "okx": "not_configured"}


def test_failing_venue_is_isolated_from_the_healthy_one():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader(
                [_holding("BTC", 0.01, 640.0)], {"source": "robinhood", "cash": 0.0}
            ),
            "okx": FakeReader(raises=RuntimeError("OKX 503")),
        }
    )
    snap = agg.get_snapshot()
    assert snap["total_value"] == pytest.approx(640.0)
    okx_src = next(s for s in snap["sources"] if s["venue"] == "okx")
    assert okx_src["status"] == "error"
    assert "OKX 503" in okx_src["error"]
    assert "okx" in snap["error"]


def test_all_venues_down_reports_unavailable():
    agg = PortfolioAggregator(
        {"robinhood": FakeReader(configured=False), "okx": FakeReader(configured=False)}
    )
    snap = agg.get_snapshot()
    assert snap["source"] == "unavailable"
    assert snap["venue_count"] == 0
    assert snap["total_value"] == 0.0
    assert snap["holdings"] == []


def test_is_configured_raising_is_treated_as_unconfigured():
    class Exploding(FakeReader):
        def is_configured(self):
            raise RuntimeError("keychain locked")

    agg = PortfolioAggregator({"okx": Exploding()})
    src = agg.get_snapshot()["sources"][0]
    assert src["status"] == "not_configured"


def test_source_rows_report_position_counts():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("A", 1.0, 1.0), _holding("B", 1.0, 2.0)]),
            "okx": FakeReader([_holding("C", 1.0, 3.0)]),
        }
    )
    counts = {s["venue"]: s["position_count"] for s in agg.get_snapshot()["sources"]}
    assert counts == {"robinhood": 2, "okx": 1}


# ---------------------------------------------------------------------------
# Cross-venue price backfill
# ---------------------------------------------------------------------------


def test_unpriced_holding_is_backfilled_from_okx_public_prices():
    """Robinhood lists tokens its own marketdata endpoint won't quote."""
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("JTO", 37.0, None)]),
            "okx": FakeReader(configured=False, prices={"JTO": 0.6}),
        }
    )
    row = agg.get_snapshot()["holdings"][0]
    assert row["market_value"] == pytest.approx(22.2)
    assert row["price"] == pytest.approx(0.6)
    assert row["price_source"] == "okx_public"


def test_backfill_lifts_the_portfolio_total():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader(
                [_holding("BTC", 0.01, 640.0), _holding("JTO", 37.0, None)],
                {"source": "robinhood", "cash": 0.0},
            ),
            "okx": FakeReader(configured=False, prices={"JTO": 0.6}),
        }
    )
    assert agg.get_snapshot()["total_value"] == pytest.approx(662.2)


def test_backfill_does_not_override_a_venue_quote():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("BTC", 1.0, 64000.0)]),
            "okx": FakeReader(configured=False, prices={"BTC": 1.0}),
        }
    )
    row = agg.get_snapshot()["holdings"][0]
    assert row["market_value"] == pytest.approx(64000.0)
    assert "price_source" not in row


def test_backfill_computes_return_when_cost_basis_known():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("JTO", 10.0, None, avg_cost=0.4)]),
            "okx": FakeReader(configured=False, prices={"JTO": 0.6}),
        }
    )
    assert agg.get_snapshot()["holdings"][0]["total_return"] == pytest.approx(2.0)


def test_holding_with_no_price_anywhere_stays_unpriced_not_zero():
    """Silently valuing an unquotable asset at $0 would understate the book."""
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader([_holding("VVV", 13.238, None)]),
            "okx": FakeReader(configured=False, prices={}),
        }
    )
    snap = agg.get_snapshot()
    row = snap["holdings"][0]
    assert row["market_value"] is None
    assert row["weight"] is None
    rh_src = next(s for s in snap["sources"] if s["venue"] == "robinhood")
    assert rh_src["unpriced_count"] == 1


def test_price_backfill_failure_is_non_fatal():
    class BadPrices(FakeReader):
        def get_spot_prices(self):
            raise RuntimeError("cloudflare")

    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader(
                [_holding("BTC", 0.01, 640.0)], {"source": "robinhood", "cash": 0.0}
            ),
            "okx": BadPrices(configured=False),
        }
    )
    assert agg.get_snapshot()["total_value"] == pytest.approx(640.0)


def test_reader_without_price_oracle_is_tolerated():
    class NoPrices:
        def is_configured(self):
            return True

        def get_holdings(self):
            return [_holding("BTC", 0.01, 640.0)]

        def get_portfolio_value(self):
            return {"source": "x", "cash": 0.0}

    assert PortfolioAggregator({"x": NoPrices()}).get_snapshot()["total_value"] == pytest.approx(
        640.0
    )


# ---------------------------------------------------------------------------
# Dashboard contract
# ---------------------------------------------------------------------------


def test_snapshot_keeps_the_legacy_dashboard_keys():
    """``portfolio.html`` and ``overview.html`` read these — they must not vanish."""
    snap = PortfolioAggregator(
        {"robinhood": FakeReader([_holding("BTC", 0.01, 640.0)])}
    ).get_snapshot()
    for key in (
        "source",
        "total_value",
        "day_pnl",
        "day_pnl_pct",
        "total_return",
        "total_return_pct",
        "cash",
        "buying_power",
        "holdings",
        "sectors",
        "asset_classes",
        "last_updated",
        "error",
    ):
        assert key in snap, f"missing legacy key {key}"


def test_stablecoins_count_as_cash_not_crypto():
    agg = PortfolioAggregator(
        {
            "okx": FakeReader(
                [_holding("USDT", 100.0, 100.0), _holding("SOL", 10.0, 700.0)],
                {"source": "okx", "cash": 0.0},
            )
        }
    )
    snap = agg.get_snapshot()
    assert snap["cash"] == pytest.approx(100.0)
    classes = {c["name"]: c["pct"] for c in snap["asset_classes"]}
    assert classes["Crypto"] == pytest.approx(87.5)
    assert classes["Cash"] == pytest.approx(12.5)


def test_stablecoins_are_not_double_counted_in_the_total():
    """``cash`` includes stables *and* they are holdings rows — the total must
    count them exactly once. ``overview.html`` previously recomputed equity as
    ``cash + sum(holdings)``, which double-counted them."""
    agg = PortfolioAggregator(
        {
            "okx": FakeReader(
                [_holding("USDT", 100.0, 100.0), _holding("SOL", 10.0, 700.0)],
                {"source": "okx", "cash": 0.0},
            )
        }
    )
    snap = agg.get_snapshot()
    assert snap["total_value"] == pytest.approx(800.0)
    # The naive recomputation would give 900 — assert the payload can't be read
    # that way without the discrepancy being visible.
    naive = snap["cash"] + sum(h["market_value"] for h in snap["holdings"])
    assert naive == pytest.approx(900.0)
    assert snap["total_value"] != pytest.approx(naive)


def test_venue_cash_and_stables_both_reach_the_total_once():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader(
                [_holding("BTC", 1.0, 640.0)], {"source": "robinhood", "cash": 0.01}
            ),
            "okx": FakeReader([_holding("USDC", 50.0, 50.0)], {"source": "okx", "cash": 25.0}),
        }
    )
    snap = agg.get_snapshot()
    # 640 BTC + 50 USDC holdings + 25.01 venue cash
    assert snap["total_value"] == pytest.approx(715.01)
    assert snap["cash"] == pytest.approx(75.01)  # 25.01 venue cash + 50 stables
    assert snap["buying_power"] == pytest.approx(25.01)


def test_asset_class_percentages_sum_to_one_hundred():
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader(
                [_holding("BTC", 1.0, 900.0)], {"source": "robinhood", "cash": 100.0}
            )
        }
    )
    assert sum(c["pct"] for c in agg.get_snapshot()["asset_classes"]) == pytest.approx(100.0)


def test_empty_portfolio_does_not_divide_by_zero():
    snap = PortfolioAggregator(
        {"robinhood": FakeReader([], {"source": "rh", "cash": 0.0})}
    ).get_snapshot()
    assert snap["total_value"] == 0.0
    assert snap["sectors"] == []
    assert snap["asset_classes"] == []


def test_total_return_aggregates_only_reporting_venues():
    """OKX has no cost basis; its ``None`` must not zero out Robinhood's P&L."""
    agg = PortfolioAggregator(
        {
            "robinhood": FakeReader(
                [_holding("BTC", 1.0, 640.0, avg_cost=600.0)],
                {"source": "robinhood", "cash": 0.0, "total_return": 40.0},
            ),
            "okx": FakeReader(
                [_holding("SOL", 10.0, 700.0)],
                {"source": "okx", "cash": 0.0, "total_return": None},
            ),
        }
    )
    snap = agg.get_snapshot()
    assert snap["total_return"] == pytest.approx(40.0)
    # Percentage is against known cost basis only (600), not the whole book.
    assert snap["total_return_pct"] == pytest.approx(40.0 / 600.0 * 100.0)


def test_snapshot_does_not_mutate_reader_rows():
    """The aggregator tags rows with ``venue`` — that must not leak into caches."""
    original = _holding("BTC", 1.0, 640.0)
    reader = FakeReader([original])
    PortfolioAggregator({"robinhood": reader}).get_snapshot()
    assert "venue" not in original
