"""Unified multi-venue portfolio aggregation (Robinhood + OKX).

Combines every configured venue reader into one snapshot that keeps the exact
top-level key contract ``/api/portfolio`` already serves, so
``templates/pages/portfolio.html`` and ``overview.html`` keep working unchanged
while gaining per-venue attribution.

Two views of the same positions are emitted, because a trading desk needs both:

``holdings``
    One row **per venue per asset**, tagged with ``venue``. This is the
    actionable view — you can only trade SOL-on-Robinhood with Robinhood.

``by_asset``
    One row **per asset**, summed across venues, with a ``venues`` breakdown.
    This is the risk view — true exposure to SOL is the sum, regardless of
    where it sits.

Degradation is per-venue, never global: an unconfigured or failing venue
contributes an entry in ``sources`` with its status and zero holdings, and the
rest of the portfolio still renders.
"""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# Assets treated as USD cash rather than a position.
_CASH_ASSETS = frozenset({"USD", "USDT", "USDC", "DAI", "TUSD", "USDK"})


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class PortfolioAggregator:
    """Aggregate holdings and valuation across all configured venues."""

    def __init__(self, readers: dict[str, Any] | None = None) -> None:
        """Build the aggregator.

        Args:
            readers: Optional ``{venue_name: reader}`` override. Each reader
                must expose ``is_configured()``, ``get_holdings()`` and
                ``get_portfolio_value()``. Defaults to the live Robinhood and
                OKX readers. Injectable so tests never touch the network.
        """
        if readers is None:
            from lib.portfolio.okx import OKXReader
            from lib.portfolio.robinhood import RobinhoodReader

            readers = {"robinhood": RobinhoodReader(), "okx": OKXReader()}
        self._readers = readers

    # -- price backfill ---------------------------------------------------

    def _fallback_prices(self) -> dict[str, float]:
        """Public spot prices used to value holdings a venue won't quote.

        Robinhood lists assets in ``/holdings/`` that its own
        ``/marketdata/best_bid_ask/`` endpoint rejects as invalid symbols, so
        those positions arrive with ``price=None`` and silently drop out of the
        total. OKX's public ticker feed needs no credentials and covers most of
        them, so it doubles as a price oracle for the whole portfolio.
        """
        okx = self._readers.get("okx")
        if okx is None or not hasattr(okx, "get_spot_prices"):
            return {}
        try:
            return okx.get_spot_prices()
        except Exception as exc:
            log.warning("fallback price lookup failed: %s", exc)
            return {}

    @staticmethod
    def _backfill(row: dict[str, Any], prices: dict[str, float]) -> dict[str, Any]:
        """Value a holding off fallback prices when its venue returned none."""
        if row.get("market_value") is not None:
            return row
        symbol = str(row.get("symbol") or row.get("asset_code") or "").upper()
        price = prices.get(symbol)
        qty = _safe_float(row.get("qty"))
        if price is None or qty <= 0:
            return row
        row["price"] = price
        row["market_value"] = qty * price
        row["price_source"] = "okx_public"
        if row.get("avg_cost"):
            row["total_return"] = (price - row["avg_cost"]) * qty
        return row

    # -- collection -------------------------------------------------------

    def _collect(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return ``(holdings, sources)`` across every venue."""
        prices = self._fallback_prices()
        holdings: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []

        for venue, reader in self._readers.items():
            try:
                configured = bool(reader.is_configured())
            except Exception as exc:
                log.warning("%s is_configured failed: %s", venue, exc)
                configured = False

            if not configured:
                sources.append(
                    {
                        "venue": venue,
                        "status": "not_configured",
                        "configured": False,
                        "total_value": 0.0,
                        "cash": 0.0,
                        "holdings_value": 0.0,
                        "position_count": 0,
                        "error": "credentials not configured",
                    }
                )
                continue

            try:
                venue_rows = [dict(r) for r in reader.get_holdings()]
                value = reader.get_portfolio_value()
            except Exception as exc:
                log.warning("%s holdings fetch failed: %s", venue, exc)
                sources.append(
                    {
                        "venue": venue,
                        "status": "error",
                        "configured": True,
                        "total_value": 0.0,
                        "cash": 0.0,
                        "holdings_value": 0.0,
                        "position_count": 0,
                        "error": str(exc),
                    }
                )
                continue

            for row in venue_rows:
                row["venue"] = venue
                self._backfill(row, prices)
            holdings.extend(venue_rows)

            venue_holdings_value = sum(_safe_float(r.get("market_value")) for r in venue_rows)
            cash = _safe_float(value.get("cash"))
            # Recompute from backfilled rows — the reader's own total predates
            # the cross-venue price fill and would understate the venue.
            sources.append(
                {
                    "venue": venue,
                    "status": "live"
                    if value.get("source") not in {None, "unavailable"}
                    else "error",
                    "configured": True,
                    "total_value": venue_holdings_value + cash,
                    "cash": cash,
                    "holdings_value": venue_holdings_value,
                    "position_count": len(venue_rows),
                    "total_return": value.get("total_return"),
                    "unpriced_count": sum(1 for r in venue_rows if r.get("market_value") is None),
                    "error": value.get("error"),
                }
            )

        # Recompute weights across the combined book. Each reader sets a weight
        # relative to its own venue and *before* the cross-venue price backfill,
        # so inheriting those would both understate the denominator and imply
        # every venue is 100% of the portfolio.
        combined_value = sum(_safe_float(r.get("market_value")) for r in holdings)
        for row in holdings:
            mv = row.get("market_value")
            row["weight"] = (
                (mv / combined_value * 100.0) if mv is not None and combined_value > 0 else None
            )

        holdings.sort(
            key=lambda r: r.get("market_value") if r.get("market_value") is not None else -1.0,
            reverse=True,
        )
        return holdings, sources

    @staticmethod
    def _consolidate(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Collapse per-venue rows into one row per asset (the risk view)."""
        by_asset: dict[str, dict[str, Any]] = {}
        for row in holdings:
            symbol = str(row.get("symbol") or row.get("asset_code") or "").upper()
            if not symbol:
                continue
            entry = by_asset.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "qty": 0.0,
                    "market_value": 0.0,
                    "price": row.get("price"),
                    "venues": [],
                },
            )
            entry["qty"] += _safe_float(row.get("qty"))
            entry["market_value"] += _safe_float(row.get("market_value"))
            if entry["price"] is None and row.get("price") is not None:
                entry["price"] = row.get("price")
            entry["venues"].append(
                {
                    "venue": row.get("venue"),
                    "qty": _safe_float(row.get("qty")),
                    "market_value": row.get("market_value"),
                }
            )

        rows = list(by_asset.values())
        total = sum(r["market_value"] for r in rows)
        for row in rows:
            row["weight"] = (row["market_value"] / total * 100.0) if total > 0 else None
            row["venue_count"] = len(row["venues"])
        rows.sort(key=lambda r: r["market_value"], reverse=True)
        return rows

    # -- public API -------------------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        """Unified snapshot across all venues.

        The top-level keys match ``RobinhoodReader.get_snapshot`` exactly so
        existing dashboard consumers need no changes; ``sources``, ``by_asset``
        and per-row ``venue`` are additive.
        """
        holdings, sources = self._collect()

        live_sources = [s for s in sources if s["status"] == "live"]
        holdings_value = sum(_safe_float(r.get("market_value")) for r in holdings)
        cash = sum(_safe_float(s.get("cash")) for s in sources)
        total_value = holdings_value + cash

        returns = [s["total_return"] for s in sources if s.get("total_return") is not None]
        total_return = sum(returns) if returns else None
        cost_basis = sum(
            _safe_float(r.get("avg_cost")) * _safe_float(r.get("qty"))
            for r in holdings
            if r.get("avg_cost")
        )
        total_return_pct = (
            (total_return / cost_basis * 100.0)
            if total_return is not None and cost_basis > 0
            else None
        )

        # Asset-class split treats stables + venue buying power as cash.
        stable_value = sum(
            _safe_float(r.get("market_value"))
            for r in holdings
            if str(r.get("symbol") or "").upper() in _CASH_ASSETS
        )
        crypto_value = holdings_value - stable_value
        cash_total = cash + stable_value

        def _pct(part: float) -> float:
            return (part / total_value * 100.0) if total_value > 0 else 0.0

        sectors: list[dict[str, Any]] = []
        asset_classes: list[dict[str, Any]] = []
        if crypto_value:
            sectors.append({"name": "Crypto", "pct": _pct(crypto_value)})
            asset_classes.append({"name": "Crypto", "pct": _pct(crypto_value), "color": "#62ff40"})
        if cash_total:
            sectors.append({"name": "Cash & Equivalents", "pct": _pct(cash_total)})
            asset_classes.append({"name": "Cash", "pct": _pct(cash_total), "color": "#6a8e67"})

        errors = [f"{s['venue']}: {s['error']}" for s in sources if s.get("error")]

        return {
            "source": "aggregate" if live_sources else "unavailable",
            "total_value": total_value,
            "day_pnl": None,
            "day_pnl_pct": None,
            "total_return": total_return,
            "total_return_pct": total_return_pct,
            "cash": cash_total,
            "buying_power": cash,
            "holdings": holdings,
            "by_asset": self._consolidate(holdings),
            "sources": sources,
            "venue_count": len(live_sources),
            "sectors": sectors,
            "asset_classes": asset_classes,
            "last_updated": time.time(),
            "error": "; ".join(errors) if errors else None,
        }


def get_aggregator() -> PortfolioAggregator:
    """Factory function — returns a PortfolioAggregator over live readers."""
    return PortfolioAggregator()
