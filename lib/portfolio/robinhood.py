"""Read-only Robinhood Crypto API integration.

Reads positions, portfolio value, and order history from the Robinhood
Crypto Trading API.  Never executes trades — Phase 1 is read-only.

Auth: API key + secret signed headers (HMAC-SHA256).

Robinhood Crypto Trading API signing scheme:
  message  = f"{timestamp}\\n{api_key}\\n{path}\\n{body}"
  signature = HMAC-SHA256(secret_bytes, message.encode("utf-8"))
  header    = base64.b64encode(signature).decode()

Required env vars:
  ROBINHOOD_API_KEY    — API key from Robinhood developer portal
  ROBINHOOD_API_SECRET — Base64-encoded secret key

If env vars are not set, all methods return None / empty lists gracefully
(no crash, no exception — the module is simply disabled).

References:
  https://docs.robinhood.com/crypto/trading/
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

BASE_URL = "https://trading.robinhood.com"
USER_AGENT = "sapphire-os/0.4 (+portfolio-reader)"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RHPosition:
    asset_code: str           # e.g. "BTC"
    quantity: float           # units held
    cost_basis_usd: float     # average cost basis per unit × quantity
    mark_price_usd: float     # current mark price
    unrealized_pnl_usd: float
    unrealized_pnl_pct: float
    market_value_usd: float


@dataclass
class RHOrder:
    order_id: str
    asset_code: str
    side: str                 # "buy" | "sell"
    quantity: float
    average_price_usd: float | None
    state: str                # "filled" | "canceled" | "pending" | ...
    created_at: str           # ISO-8601
    filled_at: str | None


@dataclass
class RHSnapshot:
    portfolio_value_usd: float
    positions: list[RHPosition] = field(default_factory=list)
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0
    position_count: int = 0
    timestamp: str = ""


# ---------------------------------------------------------------------------
# RobinhoodReader
# ---------------------------------------------------------------------------


class RobinhoodReader:
    """Read-only integration with Robinhood Crypto API.

    All methods return None or empty collections when credentials are missing
    or when the API call fails — callers should always check is_configured()
    before relying on the data.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("ROBINHOOD_API_KEY") or ""
        raw_secret = api_secret or os.environ.get("ROBINHOOD_API_SECRET") or ""
        # Secret may be base64-encoded or raw bytes — store as bytes
        try:
            self._secret_bytes = base64.b64decode(raw_secret) if raw_secret else b""
        except Exception:
            self._secret_bytes = raw_secret.encode()

    def is_configured(self) -> bool:
        """Returns True if API credentials are present."""
        return bool(self._api_key and self._secret_bytes)

    # ------------------------------------------------------------------
    # Public read methods
    # ------------------------------------------------------------------

    def get_positions(self) -> list[RHPosition]:
        """Current crypto positions with cost basis and unrealised P&L."""
        if not self.is_configured():
            return []
        try:
            data = self._get("/api/v1/crypto/trading/holdings/")
        except Exception as e:
            log.warning("robinhood get_positions failed: %s", e)
            return []

        results = data.get("results") or [] if isinstance(data, dict) else []
        positions: list[RHPosition] = []
        for item in results:
            try:
                qty = float(item.get("quantity") or 0.0)
                if qty <= 0:
                    continue
                mark = float(item.get("mark_price") or 0.0)
                cost_per_unit = float(item.get("average_buy_price") or 0.0)
                cost_basis = cost_per_unit * qty
                market_value = mark * qty
                pnl_usd = market_value - cost_basis
                pnl_pct = (pnl_usd / cost_basis) if cost_basis > 0 else 0.0
                positions.append(
                    RHPosition(
                        asset_code=str(item.get("asset_code") or ""),
                        quantity=qty,
                        cost_basis_usd=round(cost_basis, 4),
                        mark_price_usd=round(mark, 4),
                        unrealized_pnl_usd=round(pnl_usd, 4),
                        unrealized_pnl_pct=round(pnl_pct, 6),
                        market_value_usd=round(market_value, 4),
                    )
                )
            except (TypeError, ValueError, KeyError) as e:
                log.debug("skipping position item: %s — %s", item, e)
        return positions

    def get_portfolio_value(self) -> float | None:
        """Total crypto portfolio value in USD (sum of all positions)."""
        if not self.is_configured():
            return None
        try:
            data = self._get("/api/v1/crypto/trading/accounts/")
        except Exception as e:
            log.warning("robinhood get_portfolio_value failed: %s", e)
            return None

        # Primary: portfolio buying_power + equity fields
        if isinstance(data, dict):
            equity = data.get("equity") or data.get("portfolio_value")
            if equity is not None:
                return round(float(equity), 2)

        # Fallback: sum positions
        positions = self.get_positions()
        if positions:
            return round(sum(p.market_value_usd for p in positions), 2)
        return None

    def get_order_history(self, limit: int = 50) -> list[RHOrder]:
        """Recent order history for tracking DCA patterns."""
        if not self.is_configured():
            return []
        try:
            data = self._get(f"/api/v1/crypto/trading/orders/?page_size={min(limit, 200)}")
        except Exception as e:
            log.warning("robinhood get_order_history failed: %s", e)
            return []

        results = data.get("results") or [] if isinstance(data, dict) else []
        orders: list[RHOrder] = []
        for item in results[:limit]:
            try:
                avg_price = item.get("average_price") or item.get("price")
                orders.append(
                    RHOrder(
                        order_id=str(item.get("id") or ""),
                        asset_code=str(item.get("asset_code") or ""),
                        side=str(item.get("side") or ""),
                        quantity=float(item.get("quantity") or 0.0),
                        average_price_usd=float(avg_price) if avg_price is not None else None,
                        state=str(item.get("state") or ""),
                        created_at=str(item.get("created_at") or ""),
                        filled_at=item.get("filled_at"),
                    )
                )
            except (TypeError, ValueError, KeyError) as e:
                log.debug("skipping order item: %s — %s", item, e)
        return orders

    def get_daily_snapshot(self) -> dict | None:
        """Complete portfolio snapshot for morning brief and dashboard."""
        if not self.is_configured():
            return None

        positions = self.get_positions()
        portfolio_value = self.get_portfolio_value()

        if portfolio_value is None:
            portfolio_value = sum(p.market_value_usd for p in positions)

        total_cost = sum(p.cost_basis_usd for p in positions)
        total_pnl = sum(p.unrealized_pnl_usd for p in positions)
        total_pnl_pct = (total_pnl / total_cost) if total_cost > 0 else 0.0

        from datetime import datetime, timezone
        return {
            "portfolio_value_usd": round(portfolio_value, 2),
            "position_count": len(positions),
            "unrealized_pnl_usd": round(total_pnl, 2),
            "unrealized_pnl_pct": round(total_pnl_pct, 6),
            "positions": [
                {
                    "asset": p.asset_code,
                    "quantity": p.quantity,
                    "mark_price_usd": p.mark_price_usd,
                    "market_value_usd": p.market_value_usd,
                    "cost_basis_usd": p.cost_basis_usd,
                    "unrealized_pnl_usd": p.unrealized_pnl_usd,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                }
                for p in sorted(positions, key=lambda p: -p.market_value_usd)
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _sign(self, method: str, path: str, body: str, timestamp: str) -> str:
        """Compute HMAC-SHA256 signature.

        Robinhood Crypto API signing scheme:
          message = f"{timestamp}\\n{api_key}\\n{path}\\n{body}"
          signature = HMAC-SHA256(secret_bytes, message.encode())
          header value = base64.b64encode(signature).decode()

        TODO: Verify exact signing scheme against
              https://docs.robinhood.com/crypto/trading/ when credentials
              are available for end-to-end testing.  The scheme above follows
              the Robinhood Crypto API documentation published in 2024.
        """
        message = f"{timestamp}\n{self._api_key}\n{path}\n{body}"
        sig = hmac.new(self._secret_bytes, message.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(sig).decode("ascii")

    def _get(self, path: str, timeout: int = 15) -> Any:
        """Signed GET request. Raises on HTTP error or bad JSON."""
        timestamp = str(int(time.time()))
        signature = self._sign("GET", path, "", timestamp)
        url = BASE_URL + path
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "x-api-key": self._api_key,
                "x-timestamp": timestamp,
                "x-signature": signature,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"GET {path} → HTTP {e.code}: {e.reason}") from e
        except Exception as e:
            raise RuntimeError(f"GET {path} → {type(e).__name__}: {e}") from e
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"GET {path} → invalid JSON: {e}") from e


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_reader: RobinhoodReader | None = None


def get_reader() -> RobinhoodReader:
    global _reader
    if _reader is None:
        _reader = RobinhoodReader()
    return _reader


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    reader = RobinhoodReader()
    if not reader.is_configured():
        print("ROBINHOOD_API_KEY / ROBINHOOD_API_SECRET not set — module disabled.")
        sys.exit(0)

    snap = reader.get_daily_snapshot()
    if snap:
        print(f"Portfolio: ${snap['portfolio_value_usd']:,.2f}  "
              f"({snap['position_count']} positions)")
        print(f"Unrealised P&L: ${snap['unrealized_pnl_usd']:+,.2f} "
              f"({snap['unrealized_pnl_pct']*100:+.2f}%)")
        for pos in snap["positions"][:5]:
            print(f"  {pos['asset']:6}  {pos['quantity']:.6f}  "
                  f"${pos['market_value_usd']:,.2f}  "
                  f"P&L {pos['unrealized_pnl_pct']*100:+.1f}%")
    else:
        print("No snapshot returned.")
