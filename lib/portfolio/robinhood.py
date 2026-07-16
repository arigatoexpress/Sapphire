"""Robinhood Crypto Trading API client — portfolio + holdings.

Uses Robinhood's current crypto trading API and authentication contract:

  - Base URL: ``https://trading.robinhood.com``
  - Read endpoints:
      ``/api/v2/crypto/trading/accounts/``
      ``/api/v2/crypto/trading/holdings/``
      ``/api/v2/crypto/marketdata/best_bid_ask/``
      ``/api/v2/crypto/trading/orders/``
  - Signature message:
      ``{api_key}{timestamp}{path}{method}{body}``

Credentials are loaded from ``~/.config/sapphire-secrets/``:
  - ``robinhood_api_key``
  - ``robinhood_ed25519_private.b64`` (base64-encoded 32-byte Ed25519 seed)

The API does not expose cost basis directly in holdings, so this module
reconstructs a weighted-average cost basis from filled order history when
possible. If order history is incomplete, the reader still returns current
holdings and valuation data, but unrealized P&L may be unavailable.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import certifi

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

_SECRETS = Path.home() / ".config" / "sapphire-secrets"
_BASE = "https://trading.robinhood.com"
_DEFAULT_ORDER_LOOKBACK_DAYS = 365 * 5


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote_midpoint(item: dict[str, Any]) -> float | None:
    """Return the midpoint from Robinhood's current v2 quote shape."""
    bid = _as_float(item.get("bid_inclusive_of_sell_spread"))
    ask = _as_float(item.get("ask_inclusive_of_buy_spread"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    if bid is not None:
        return bid
    if ask is not None:
        return ask

    price = _as_float(item.get("price"))
    if price is not None:
        return price

    legacy_bid = _as_float(item.get("bid"))
    legacy_ask = _as_float(item.get("ask"))
    if legacy_bid is not None and legacy_ask is not None:
        return (legacy_bid + legacy_ask) / 2.0
    if legacy_bid is not None:
        return legacy_bid
    if legacy_ask is not None:
        return legacy_ask
    return None


def _load_credentials() -> tuple[str, bytes]:
    """Load API key + Ed25519 private key bytes from the secrets dir."""
    api_key = (_SECRETS / "robinhood_api_key").read_text().strip()
    private_b64 = (_SECRETS / "robinhood_ed25519_private.b64").read_text().strip()
    private_bytes = base64.b64decode(private_b64)
    return api_key, private_bytes


def _encode_query(params: dict[str, Any] | None = None) -> str:
    if not params:
        return ""
    items: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            items.extend((key, str(v)) for v in value if v is not None)
        else:
            items.append((key, str(value)))
    if not items:
        return ""
    return "?" + urllib.parse.urlencode(items, doseq=True)


def _sign_request(
    api_key: str,
    private_bytes: bytes,
    method: str,
    path: str,
    body: str = "",
) -> dict[str, str]:
    """Return auth headers for a Robinhood API request."""
    timestamp = str(int(time.time()))
    method = method.upper()
    message = f"{api_key}{timestamp}{path}{method}{body}".encode()

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        signature = private_key.sign(message)
        sig_b64 = base64.b64encode(signature).decode("utf-8")
    except ImportError:
        try:
            import nacl.signing

            signing_key = nacl.signing.SigningKey(private_bytes)
            signed = signing_key.sign(message)
            sig_b64 = base64.b64encode(signed.signature).decode("utf-8")
        except ImportError as exc:
            raise RuntimeError(
                "No Ed25519 signing library available. Install 'cryptography' or 'PyNaCl'."
            ) from exc

    return {
        "x-api-key": api_key,
        "x-signature": sig_b64,
        "x-timestamp": timestamp,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _request(
    method: str,
    path: str,
    api_key: str,
    private_bytes: bytes,
    body: dict[str, Any] | None = None,
    timeout: int = 15,
) -> Any:
    """Authenticated Robinhood API request with retry on 5xx / network errors."""
    body_json = json.dumps(body, separators=(",", ":")) if body is not None else ""
    last_exc: RuntimeError | None = None
    for attempt in range(3):
        # Re-sign each attempt — timestamp is part of the signature message.
        headers = _sign_request(api_key, private_bytes, method, path, body_json)
        req = urllib.request.Request(
            _BASE + path,
            data=body_json.encode("utf-8") if body_json else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(req, context=_SSL_CTX, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode(errors="replace")[:300]
            if exc.code >= 500 and attempt < 2:
                last_exc = RuntimeError(
                    f"Robinhood {method.upper()} {path} -> HTTP {exc.code}: {err_body}"
                )
                time.sleep(2**attempt)
                continue
            raise RuntimeError(
                f"Robinhood {method.upper()} {path} -> HTTP {exc.code}: {err_body}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < 2:
                last_exc = RuntimeError(
                    f"Robinhood {method.upper()} {path} -> {type(exc).__name__}: {exc}"
                )
                time.sleep(2**attempt)
                continue
            raise RuntimeError(
                f"Robinhood {method.upper()} {path} -> {type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Robinhood {method.upper()} {path} -> {type(exc).__name__}: {exc}"
            ) from exc
    raise last_exc or RuntimeError(f"Robinhood {method.upper()} {path} -> failed after 3 attempts")


class RobinhoodReader:
    """Read-only Robinhood crypto portfolio data."""

    def __init__(self):
        try:
            self._api_key, self._private_bytes = _load_credentials()
            self._available = True
        except (FileNotFoundError, ValueError) as exc:
            log.warning("Robinhood credentials unavailable: %s", exc)
            self._api_key = ""
            self._private_bytes = b""
            self._available = False
        self._account_cache: dict[str, Any] | None = None
        self._cost_basis_cache: dict[str, dict[str, float]] | None = None

    def is_configured(self) -> bool:
        """True if credentials are loaded and non-empty."""
        return self._available and bool(self._api_key)

    def _request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: int = 15,
    ) -> Any:
        return _request(
            method, path, self._api_key, self._private_bytes, body=body, timeout=timeout
        )

    def _get_results(
        self, base_path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if not self._available:
            return []

        path = f"{base_path}{_encode_query(params)}"
        results: list[dict[str, Any]] = []
        seen_paths: set[str] = set()

        while path and path not in seen_paths:
            seen_paths.add(path)
            payload = self._request_json("GET", path)
            page_results = payload.get("results") if isinstance(payload, dict) else None
            if isinstance(page_results, list):
                results.extend(r for r in page_results if isinstance(r, dict))
            next_url = payload.get("next") if isinstance(payload, dict) else None
            if next_url:
                path = next_url.replace(_BASE, "")
            else:
                break
        return results

    def _get_account_record(self) -> dict[str, Any] | None:
        if self._account_cache is not None:
            return self._account_cache
        if not self._available:
            return None
        try:
            accounts = self._get_results("/api/v2/crypto/trading/accounts/")
            if not accounts:
                return None
            tradable = [a for a in accounts if a.get("is_api_tradable") is True]
            self._account_cache = tradable[0] if tradable else accounts[0]
            return self._account_cache
        except Exception as exc:
            log.warning("get_accounts failed: %s", exc)
            return None

    def _get_account_number(self) -> str | None:
        account = self._get_account_record()
        if not account:
            return None
        account_number = account.get("account_number")
        return str(account_number) if account_number else None

    def _get_best_bid_ask(self, symbols: list[str]) -> dict[str, float]:
        if not symbols:
            return {}

        remaining = list(dict.fromkeys(s.upper() for s in symbols if s))
        prices: dict[str, float] = {}

        while remaining:
            try:
                results = self._get_results(
                    "/api/v2/crypto/marketdata/best_bid_ask/",
                    params={"symbol": remaining},
                )
            except RuntimeError as exc:
                err = str(exc)
                # Robinhood rejects the whole batch if any symbol is invalid.
                # Parse the offender, drop it, and retry the rest.
                invalid_match = re.search(r"Invalid symbol:\s*([A-Z0-9._-]+)", err, re.IGNORECASE)
                if invalid_match:
                    invalid = invalid_match.group(1).upper()
                    remaining = [s for s in remaining if s != invalid]
                    log.debug("dropped invalid RH symbol %s", invalid)
                    continue
                log.warning("get_best_bid_ask failed: %s", exc)
                return prices
            except Exception as exc:
                log.warning("get_best_bid_ask failed: %s", exc)
                return prices

            for item in results:
                symbol = str(item.get("symbol") or "").upper()
                price = _quote_midpoint(item)
                if symbol and price is not None:
                    prices[symbol] = price
            break

        return prices

    def _reconstruct_cost_basis(self, account_number: str) -> dict[str, dict[str, float]]:
        if self._cost_basis_cache is not None:
            return self._cost_basis_cache

        created_at_start = (
            datetime.now(UTC) - timedelta(days=_DEFAULT_ORDER_LOOKBACK_DAYS)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            orders = self._get_results(
                "/api/v2/crypto/trading/orders/",
                params={
                    "account_number": account_number,
                    "created_at_start": created_at_start,
                },
            )
        except Exception as exc:
            log.warning("get_orders failed: %s", exc)
            self._cost_basis_cache = {}
            return self._cost_basis_cache

        positions: dict[str, dict[str, float]] = {}
        orders.sort(key=lambda order: str(order.get("created_at") or ""))

        for order in orders:
            state = str(order.get("state") or "").lower()
            if state not in {"filled", "partially_filled"}:
                continue

            symbol = str(order.get("symbol") or "")
            asset_code = symbol.split("-", 1)[0].upper() if "-" in symbol else ""
            if not asset_code:
                continue

            quantity = _as_float(order.get("filled_asset_quantity")) or 0.0
            average_price = _as_float(order.get("average_price"))
            side = str(order.get("side") or "").lower()
            if quantity <= 0 or average_price is None or side not in {"buy", "sell"}:
                continue

            pos = positions.setdefault(asset_code, {"qty": 0.0, "cost": 0.0})
            if side == "buy":
                pos["qty"] += quantity
                pos["cost"] += quantity * average_price
                continue

            current_qty = pos["qty"]
            if current_qty <= 0:
                pos["qty"] = 0.0
                pos["cost"] = 0.0
                continue

            avg_cost = pos["cost"] / current_qty if current_qty else 0.0
            quantity_to_remove = min(current_qty, quantity)
            pos["qty"] = max(0.0, current_qty - quantity)
            pos["cost"] = max(0.0, pos["cost"] - quantity_to_remove * avg_cost)

        self._cost_basis_cache = {
            asset: {
                "qty": round(pos["qty"], 12),
                "avg_cost": (pos["cost"] / pos["qty"]) if pos["qty"] > 0 else 0.0,
            }
            for asset, pos in positions.items()
        }
        return self._cost_basis_cache

    def get_account(self) -> dict[str, Any]:
        """Return the default crypto account's buying power and status."""
        if not self._available:
            return {"source": "unavailable", "error": "credentials not loaded"}
        try:
            account = self._get_account_record()
            if not account:
                return {"source": "unavailable", "error": "no crypto account found"}
            buying_power = _as_float(account.get("buying_power")) or 0.0
            return {
                "source": "robinhood",
                "account_number": account.get("account_number", ""),
                "status": account.get("status", ""),
                "account_type": account.get("account_type", ""),
                "buying_power": buying_power,
                "buying_power_currency": account.get("buying_power_currency", "USD"),
                "is_api_tradable": bool(account.get("is_api_tradable")),
                "fee_ratio": _as_float((account.get("fee_tier_status") or {}).get("fee_ratio")),
            }
        except Exception as exc:
            log.warning("get_account failed: %s", exc)
            return {"source": "unavailable", "error": str(exc)}

    def get_holdings(self) -> list[dict[str, Any]]:
        """Return Robinhood crypto holdings with live prices and cost basis if available."""
        if not self._available:
            return []

        account_number = self._get_account_number()
        if not account_number:
            return []

        try:
            raw_holdings = self._get_results(
                "/api/v2/crypto/trading/holdings/",
                params={"account_number": account_number},
            )
        except Exception as exc:
            log.warning("get_holdings failed: %s", exc)
            return []

        live_rows: list[dict[str, Any]] = []
        symbols: list[str] = []
        for row in raw_holdings:
            asset_code = str(row.get("asset_code") or "").upper()
            quantity = _as_float(row.get("total_quantity")) or 0.0
            if not asset_code or quantity <= 0:
                continue
            symbol = f"{asset_code}-USD"
            symbols.append(symbol)
            live_rows.append(
                {
                    "asset_code": asset_code,
                    "symbol": asset_code,
                    "trading_pair": symbol,
                    "qty": quantity,
                    "available_qty": _as_float(row.get("quantity_available_for_trading"))
                    or quantity,
                    "account_number": row.get("account_number", ""),
                }
            )

        if not live_rows:
            return []

        prices = self._get_best_bid_ask(symbols)
        cost_basis = self._reconstruct_cost_basis(account_number)

        total_market_value = 0.0
        for row in live_rows:
            price = prices.get(row["trading_pair"])
            avg_cost = cost_basis.get(row["asset_code"], {}).get("avg_cost")
            market_value = price * row["qty"] if price is not None else None
            total_return = (
                (price - avg_cost) * row["qty"]
                if price is not None and avg_cost not in {None, 0.0}
                else None
            )
            row["price"] = price
            row["avg_cost"] = avg_cost if avg_cost not in {None, 0.0} else None
            row["market_value"] = market_value
            row["total_return"] = total_return
            if market_value is not None:
                total_market_value += market_value

        for row in live_rows:
            if row.get("market_value") is None or total_market_value <= 0:
                row["weight"] = None
            else:
                row["weight"] = row["market_value"] / total_market_value * 100.0

        live_rows.sort(
            key=lambda row: (
                row.get("market_value") if row.get("market_value") is not None else -1.0
            ),
            reverse=True,
        )
        total_val = sum(h.get("market_value") or 0.0 for h in live_rows)
        log.info("robinhood: %d holdings, total value $%s", len(live_rows), f"{total_val:,.2f}")
        return live_rows

    def get_portfolio_value(self) -> dict[str, Any]:
        """Return current crypto account value from holdings + buying power."""
        if not self._available:
            return {"source": "unavailable", "error": "credentials not loaded"}

        account = self.get_account()
        if account.get("source") != "robinhood":
            return account

        holdings = self.get_holdings()
        holdings_value = sum(h.get("market_value") or 0.0 for h in holdings)
        buying_power = account.get("buying_power", 0.0) or 0.0
        equity = holdings_value + buying_power

        pnl_rows = [h["total_return"] for h in holdings if h.get("total_return") is not None]
        cost_basis_total = sum(
            (h.get("avg_cost") or 0.0) * (h.get("qty") or 0.0)
            for h in holdings
            if h.get("avg_cost") is not None
        )
        total_return = sum(pnl_rows) if pnl_rows else None
        total_return_pct = (
            (total_return / cost_basis_total * 100.0)
            if total_return is not None and cost_basis_total > 0
            else None
        )

        return {
            "source": "robinhood",
            "equity": equity,
            "cash": buying_power,
            "buying_power": buying_power,
            "holdings_value": holdings_value,
            "day_pnl": None,
            "day_pnl_pct": None,
            "total_return": total_return,
            "total_return_pct": total_return_pct,
            "position_count": len(holdings),
        }

    def get_snapshot(self) -> dict[str, Any]:
        """Full portfolio snapshot matching dashboard template data shape."""
        pv = self.get_portfolio_value()
        account = self.get_account()
        holdings = self.get_holdings()

        total_val = pv.get("equity", 0.0) or 0.0
        holdings_value = pv.get("holdings_value", 0.0) or 0.0
        cash = account.get("buying_power", 0.0) or 0.0

        sectors = []
        if holdings_value:
            sectors.append(
                {"name": "Crypto", "pct": (holdings_value / total_val * 100) if total_val else 0}
            )
        if cash:
            sectors.append(
                {"name": "Cash & Equivalents", "pct": (cash / total_val * 100) if total_val else 0}
            )

        asset_classes = []
        if holdings_value:
            asset_classes.append(
                {
                    "name": "Crypto",
                    "pct": (holdings_value / total_val * 100) if total_val else 0,
                    "color": "#62ff40",
                }
            )
        if cash:
            asset_classes.append(
                {
                    "name": "Cash",
                    "pct": (cash / total_val * 100) if total_val else 0,
                    "color": "#6a8e67",
                }
            )

        is_live = pv.get("source") == "robinhood"
        return {
            "source": "robinhood" if is_live else "unavailable",
            "total_value": total_val,
            "day_pnl": pv.get("day_pnl"),
            "day_pnl_pct": pv.get("day_pnl_pct"),
            "total_return": pv.get("total_return"),
            "total_return_pct": pv.get("total_return_pct"),
            "cash": cash,
            "buying_power": cash,
            "holdings": holdings,
            "sectors": sectors,
            "asset_classes": asset_classes,
            "last_updated": time.time(),
            "error": pv.get("error") or account.get("error"),
        }

    def get_daily_snapshot(self) -> dict[str, Any]:
        """Snapshot shaped for the morning brief."""
        if not self._available:
            return {}
        try:
            holdings = self.get_holdings()
            portfolio = self.get_portfolio_value()
            if portfolio.get("source") != "robinhood":
                return {}

            pnl_rows = [h["total_return"] for h in holdings if h.get("total_return") is not None]
            cost_basis_total = sum(
                (h.get("avg_cost") or 0.0) * (h.get("qty") or 0.0)
                for h in holdings
                if h.get("avg_cost") is not None
            )
            total_pnl_usd = sum(pnl_rows) if pnl_rows else None
            pnl_pct = (
                (total_pnl_usd / cost_basis_total)
                if total_pnl_usd is not None and cost_basis_total > 0
                else None
            )

            positions = []
            for holding in holdings:
                market_value = holding.get("market_value")
                position = {
                    "asset": holding["symbol"],
                    "market_value_usd": market_value,
                    "current_price_usd": holding.get("price"),
                    "unrealized_pnl_usd": holding.get("total_return"),
                    "unrealized_pnl_pct": (
                        (
                            holding["total_return"]
                            / ((holding.get("avg_cost") or 0.0) * holding["qty"])
                        )
                        if holding.get("total_return") is not None
                        and holding.get("avg_cost") not in {None, 0.0}
                        and holding["qty"] > 0
                        else None
                    ),
                }
                positions.append(position)

            return {
                "portfolio_value_usd": portfolio.get("equity", 0.0),
                "cash_usd": portfolio.get("cash", 0.0),
                "holdings_value_usd": portfolio.get("holdings_value", 0.0),
                "unrealized_pnl_usd": total_pnl_usd,
                "unrealized_pnl_pct": pnl_pct,
                "pnl_available": total_pnl_usd is not None,
                "position_count": len(holdings),
                "positions": positions,
            }
        except Exception as exc:
            log.warning("get_daily_snapshot failed: %s", exc)
            return {}


def get_reader() -> RobinhoodReader:
    """Factory function — returns a RobinhoodReader."""
    return RobinhoodReader()
