"""Robinhood Trading API client — portfolio + holdings.

Authentication: ED25519-signed requests (Robinhood Credentials API, 2024+).
Credentials loaded from ~/.config/sapphire-secrets/:
  - robinhood_api_key               (e.g. rh-api-{uuid})
  - robinhood_ed25519_private.b64   (base64-encoded 32-byte ED25519 seed)

Endpoints used:
  GET /api/v1/portfolios/   → portfolio value, equity
  GET /api/v1/positions/?nonzero=true  → open positions
  GET /api/v1/accounts/     → account info (cash, buying power)

All calls degrade gracefully — if the API is unavailable this returns
a stub dict with a `source: "unavailable"` key so callers can detect it.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

_SECRETS = Path.home() / ".config" / "sapphire-secrets"
_BASE = "https://trading.robinhood.com"

# Instrument symbol cache to avoid repeated calls
_INSTRUMENT_CACHE: dict[str, str] = {}


def _load_credentials() -> tuple[str, bytes]:
    """Load API key + ED25519 private key bytes from secrets dir."""
    api_key = (_SECRETS / "robinhood_api_key").read_text().strip()
    private_b64 = (_SECRETS / "robinhood_ed25519_private.b64").read_text().strip()
    private_bytes = base64.b64decode(private_b64)
    return api_key, private_bytes


def _sign_request(api_key: str, private_bytes: bytes, path: str, body: str = "") -> dict[str, str]:
    """Return auth headers for a Robinhood API request.

    Message format: {api_key}{timestamp}{path}{body}
    """
    timestamp = str(int(time.time()))
    message = f"{api_key}{timestamp}{path}{body}".encode()

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        signature = private_key.sign(message)
        sig_b64 = base64.b64encode(signature).decode()
    except ImportError:
        # PyNaCl fallback
        try:
            import nacl.signing
            signing_key = nacl.signing.SigningKey(private_bytes)
            signed = signing_key.sign(message)
            sig_b64 = base64.b64encode(signed.signature).decode()
        except ImportError:
            raise RuntimeError(
                "No ED25519 signing library available. "
                "Install 'cryptography' or 'PyNaCl': pip install cryptography"
            )

    return {
        "x-api-key": api_key,
        "x-timestamp": timestamp,
        "x-signature": sig_b64,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(path: str, api_key: str, private_bytes: bytes, timeout: int = 15) -> Any:
    """Authenticated GET request to Robinhood API."""
    headers = _sign_request(api_key, private_bytes, path)
    url = _BASE + path
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"Robinhood GET {path} → HTTP {e.code}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"Robinhood GET {path} → {type(e).__name__}: {e}") from e


class RobinhoodReader:
    """Read-only Robinhood portfolio data."""

    def __init__(self):
        try:
            self._api_key, self._private_bytes = _load_credentials()
            self._available = True
        except (FileNotFoundError, KeyError, ValueError) as e:
            log.warning("Robinhood credentials unavailable: %s", e)
            self._api_key = ""
            self._private_bytes = b""
            self._available = False

    def is_configured(self) -> bool:
        """True if credentials are loaded and non-empty."""
        return self._available and bool(self._api_key)

    def _get(self, path: str) -> Any:
        return _get(path, self._api_key, self._private_bytes)

    def get_portfolio_value(self) -> dict:
        """Return equity, cash, and return metrics."""
        if not self._available:
            return {"source": "unavailable", "error": "credentials not loaded"}
        try:
            portfolios = self._get("/api/v1/portfolios/")
            results = portfolios.get("results") or []
            if not results:
                return {"source": "unavailable", "error": "no portfolio found"}
            p = results[0]
            equity = float(p.get("equity") or p.get("extended_hours_equity") or 0)
            prev_equity = float(p.get("equity_previous_close") or equity)
            day_pnl = equity - prev_equity
            day_pnl_pct = (day_pnl / prev_equity * 100.0) if prev_equity else 0.0
            adj_prev = float(p.get("adjusted_equity_previous_close") or prev_equity)
            total_return = equity - adj_prev
            total_return_pct = (total_return / adj_prev * 100.0) if adj_prev else 0.0
            return {
                "source": "robinhood",
                "equity": equity,
                "day_pnl": day_pnl,
                "day_pnl_pct": day_pnl_pct,
                "total_return": total_return,
                "total_return_pct": total_return_pct,
            }
        except Exception as e:
            log.warning("get_portfolio_value failed: %s", e)
            return {"source": "unavailable", "error": str(e)}

    def get_account(self) -> dict:
        """Return cash, buying power from account endpoint."""
        if not self._available:
            return {"source": "unavailable", "error": "credentials not loaded"}
        try:
            accounts = self._get("/api/v1/accounts/")
            results = accounts.get("results") or []
            if not results:
                return {"source": "unavailable", "error": "no account found"}
            a = results[0]
            cash = float(a.get("cash") or a.get("portfolio_cash") or 0)
            buying_power = float(a.get("buying_power") or cash)
            return {
                "source": "robinhood",
                "cash": cash,
                "buying_power": buying_power,
                "account_number": a.get("account_number", ""),
            }
        except Exception as e:
            log.warning("get_account failed: %s", e)
            return {"source": "unavailable", "error": str(e)}

    def get_holdings(self) -> list[dict]:
        """Return list of non-zero positions with current price data."""
        if not self._available:
            return []
        try:
            # Positions
            positions_data = self._get("/api/v1/positions/?nonzero=true")
            positions = positions_data.get("results") or []
            if not positions:
                return []

            # Collect instrument URLs to resolve symbols
            instrument_urls = list({p.get("instrument") for p in positions if p.get("instrument")})
            symbol_map = self._resolve_symbols(instrument_urls)

            holdings = []
            total_equity = sum(
                float(p.get("quantity", 0)) * float(p.get("average_buy_price", 0))
                for p in positions
            )
            total_equity = total_equity or 1.0  # avoid division by zero

            for p in positions:
                qty = float(p.get("quantity") or 0)
                avg_cost = float(p.get("average_buy_price") or 0)
                if qty == 0:
                    continue

                instrument_url = p.get("instrument", "")
                sym = symbol_map.get(instrument_url, "UNKNOWN")

                # Current price via quote endpoint
                current_price, day_chg_pct = self._fetch_quote(sym)
                if current_price is None:
                    current_price = avg_cost
                    day_chg_pct = 0.0

                total_return = (current_price - avg_cost) * qty
                market_value = current_price * qty
                weight = market_value / total_equity * 100.0

                holdings.append({
                    "symbol": sym,
                    "name": sym,  # Robinhood API gives name via instrument detail
                    "qty": qty,
                    "avg_cost": avg_cost,
                    "price": current_price,
                    "day_chg_pct": day_chg_pct,
                    "total_return": total_return,
                    "weight": weight,
                })

            return holdings
        except Exception as e:
            log.warning("get_holdings failed: %s", e)
            return []

    def _resolve_symbols(self, instrument_urls: list[str]) -> dict[str, str]:
        """Batch-resolve instrument URLs to ticker symbols."""
        result: dict[str, str] = {}
        for url in instrument_urls:
            if url in _INSTRUMENT_CACHE:
                result[url] = _INSTRUMENT_CACHE[url]
                continue
            try:
                req = urllib.request.Request(
                    url,
                    headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                sym = data.get("symbol", "UNKNOWN")
                _INSTRUMENT_CACHE[url] = sym
                result[url] = sym
            except Exception:
                result[url] = "UNKNOWN"
        return result

    def _fetch_quote(self, symbol: str) -> tuple[float | None, float]:
        """Fetch current price + day change % for a symbol."""
        try:
            data = self._get(f"/api/v1/quotes/{symbol}/")
            price = float(data.get("last_trade_price") or data.get("bid_price") or 0)
            prev_close = float(data.get("previous_close") or price)
            day_chg = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
            return price, day_chg
        except Exception:
            return None, 0.0

    def get_snapshot(self) -> dict:
        """Full portfolio snapshot matching dashboard template data shape."""
        pv = self.get_portfolio_value()
        acc = self.get_account()
        holdings = self.get_holdings()

        # Build sector + asset class summaries from holdings
        # (Robinhood API has instrument types we can use for this)
        equity_val = pv.get("equity", 0.0)
        cash = acc.get("cash", 0.0)
        total_val = equity_val + cash

        # Simple sector allocation (all stocks for now — crypto separate)
        sectors = [{"name": "Equities", "pct": (equity_val / total_val * 100) if total_val else 0}]
        if cash:
            sectors.append({"name": "Cash & Equivalents", "pct": (cash / total_val * 100) if total_val else 0})

        asset_classes = [
            {"name": "Stocks", "pct": (equity_val / total_val * 100) if total_val else 0, "color": "#62ff40"},
            {"name": "Cash", "pct": (cash / total_val * 100) if total_val else 0, "color": "#6a8e67"},
        ]

        is_live = pv.get("source") == "robinhood"
        return {
            "source": "robinhood" if is_live else "unavailable",
            "total_value": total_val,
            "day_pnl": pv.get("day_pnl", 0.0),
            "day_pnl_pct": pv.get("day_pnl_pct", 0.0),
            "total_return": pv.get("total_return", 0.0),
            "total_return_pct": pv.get("total_return_pct", 0.0),
            "cash": cash,
            "buying_power": acc.get("buying_power", cash),
            "holdings": holdings,
            "sectors": sectors,
            "asset_classes": asset_classes,
            "last_updated": time.time(),
            "error": pv.get("error") or acc.get("error"),
        }

    def get_daily_snapshot(self) -> dict:
        """Snapshot shaped for the morning brief (unrealized P&L focus)."""
        if not self._available:
            return {}
        try:
            holdings = self.get_holdings()
            pv = self.get_portfolio_value()
            if pv.get("source") != "robinhood":
                return {}
            total_pnl_usd = sum(h.get("total_return", 0.0) for h in holdings)
            total_cost = sum(h.get("qty", 0) * h.get("avg_cost", 0) for h in holdings) or 1.0
            pnl_pct = total_pnl_usd / total_cost
            positions = [
                {
                    "asset": h["symbol"],
                    "market_value_usd": h["qty"] * h["price"],
                    "unrealized_pnl_usd": h["total_return"],
                    "unrealized_pnl_pct": h["total_return"] / (h["qty"] * h["avg_cost"]) if h["avg_cost"] else 0,
                }
                for h in sorted(holdings, key=lambda x: abs(x.get("total_return", 0)), reverse=True)
            ]
            return {
                "portfolio_value_usd": pv.get("equity", 0.0),
                "unrealized_pnl_usd": total_pnl_usd,
                "unrealized_pnl_pct": pnl_pct,
                "position_count": len(holdings),
                "positions": positions,
            }
        except Exception as e:
            log.warning("get_daily_snapshot failed: %s", e)
            return {}


def get_reader() -> RobinhoodReader:
    """Factory function — returns a RobinhoodReader (credentials loaded from secrets dir)."""
    return RobinhoodReader()
