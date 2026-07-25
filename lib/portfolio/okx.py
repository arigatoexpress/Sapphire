"""OKX V5 REST client — read-only portfolio + holdings.

Mirrors the ``lib.portfolio.robinhood.RobinhoodReader`` contract so both venues
can be aggregated by ``lib.portfolio.aggregate`` without special-casing.

Authentication (OKX V5):
  - Base URL: ``https://www.okx.com``
  - Headers: ``OK-ACCESS-KEY`` / ``OK-ACCESS-SIGN`` / ``OK-ACCESS-TIMESTAMP``
    / ``OK-ACCESS-PASSPHRASE``
  - Signature: ``base64(hmac_sha256(timestamp + method + path + body, secret))``
    where ``timestamp`` is ISO-8601 with milliseconds, e.g.
    ``2026-07-25T09:08:57.715Z``.

Credentials are loaded from ``~/.config/sapphire-secrets/`` (preferred) with an
environment-variable fallback:

  ==============================  =====================
  Secret file                     Env fallback
  ==============================  =====================
  ``okx_api_key``                 ``OKX_API_KEY``
  ``okx_api_secret``              ``OKX_API_SECRET``
  ``okx_passphrase``              ``OKX_PASSPHRASE``
  ==============================  =====================

Optional ``okx_simulated`` (``1``/``true``) routes to OKX demo trading via the
``x-simulated-trading`` header.

OKX splits a user's assets across a **trading** account
(``/api/v5/account/balance``) and a **funding** account
(``/api/v5/asset/balances``). A complete portfolio view requires both, so this
reader queries each and merges by currency, tagging the sub-account of origin.

This module is READ-ONLY by construction: no order, transfer, or withdrawal
endpoint is implemented or reachable from here.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import certifi

log = logging.getLogger(__name__)

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())
_SECRETS = Path.home() / ".config" / "sapphire-secrets"
_BASE = "https://www.okx.com"

# OKX fronts its API with Cloudflare, which rejects the default
# ``Python-urllib/3.x`` User-Agent with HTTP 403 "error 1010: browser signature".
# A conventional browser UA clears the check; without it every call fails,
# including the unauthenticated public market-data endpoints.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Currencies quoted 1:1 against USD. OKX has no USD spot pair for most assets,
# so valuation routes through USDT and these are pinned rather than round-tripped.
_USD_STABLES = frozenset({"USDT", "USDC", "USD", "DAI", "TUSD", "USDK"})

# Dust filter — OKX reports long-tail residue (airdrop dust, fee rebates) that
# would otherwise clutter the holdings table with sub-cent rows.
_MIN_HOLDING_USD = 0.01


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_secret(filename: str, env_var: str) -> str:
    """Read a secret from the secrets dir, falling back to an env var."""
    path = _SECRETS / filename
    try:
        value = path.read_text().strip()
        if value:
            return value
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return os.environ.get(env_var, "").strip()


def _load_credentials() -> tuple[str, str, str]:
    """Return ``(api_key, api_secret, passphrase)``; empty strings when absent."""
    return (
        _read_secret("okx_api_key", "OKX_API_KEY"),
        _read_secret("okx_api_secret", "OKX_API_SECRET"),
        _read_secret("okx_passphrase", "OKX_PASSPHRASE"),
    )


def _simulated_enabled() -> bool:
    raw = _read_secret("okx_simulated", "OKX_SIMULATED").lower()
    return raw in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    """OKX requires ISO-8601 UTC with exactly milliseconds and a ``Z`` suffix."""
    # Single ``now()`` read — sampling twice can straddle a second boundary and
    # produce a timestamp whose milliseconds belong to the previous second.
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _sign_request(
    api_secret: str,
    timestamp: str,
    method: str,
    request_path: str,
    body: str = "",
) -> str:
    """Return the base64 HMAC-SHA256 signature for an OKX V5 request.

    ``request_path`` must include the query string, and ``body`` must be the
    exact serialized payload sent on the wire — OKX signs the literal bytes.
    """
    message = f"{timestamp}{method.upper()}{request_path}{body}".encode()
    digest = hmac.new(api_secret.encode(), message, sha256).digest()
    return base64.b64encode(digest).decode()


def _encode_query(params: dict[str, Any] | None = None) -> str:
    if not params:
        return ""
    items = {k: str(v) for k, v in params.items() if v is not None}
    if not items:
        return ""
    return "?" + urllib.parse.urlencode(items)


def _request(
    method: str,
    path: str,
    *,
    api_key: str = "",
    api_secret: str = "",
    passphrase: str = "",
    simulated: bool = False,
    timeout: int = 15,
) -> dict[str, Any]:
    """Perform an OKX V5 request with retry on 5xx / transport errors.

    When ``api_secret`` is empty the request is sent unauthenticated, which is
    correct for OKX public market-data endpoints.
    """
    method = method.upper()
    last_exc: RuntimeError | None = None

    for attempt in range(3):
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if api_secret:
            # Re-sign per attempt — the timestamp is part of the signed message
            # and OKX rejects anything skewed more than 30s from server time.
            timestamp = _timestamp()
            headers.update(
                {
                    "OK-ACCESS-KEY": api_key,
                    "OK-ACCESS-SIGN": _sign_request(api_secret, timestamp, method, path),
                    "OK-ACCESS-TIMESTAMP": timestamp,
                    "OK-ACCESS-PASSPHRASE": passphrase,
                }
            )
        if simulated:
            headers["x-simulated-trading"] = "1"

        req = urllib.request.Request(_BASE + path, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=_SSL_CTX, timeout=timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode(errors="replace")[:300]
            if exc.code >= 500 and attempt < 2:
                last_exc = RuntimeError(f"OKX {method} {path} -> HTTP {exc.code}: {err_body}")
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"OKX {method} {path} -> HTTP {exc.code}: {err_body}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < 2:
                last_exc = RuntimeError(f"OKX {method} {path} -> {type(exc).__name__}: {exc}")
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"OKX {method} {path} -> {type(exc).__name__}: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"OKX {method} {path} -> {type(exc).__name__}: {exc}") from exc

        # OKX returns HTTP 200 with an application-level error code.
        if not isinstance(payload, dict):
            raise RuntimeError(f"OKX {method} {path} -> non-object response")
        code = str(payload.get("code", ""))
        if code not in {"0", ""}:
            raise RuntimeError(
                f"OKX {method} {path} -> code {code}: {payload.get('msg', '')}"[:300]
            )
        return payload

    raise last_exc or RuntimeError(f"OKX {method} {path} -> failed after 3 attempts")


class OKXReader:
    """Read-only OKX portfolio data across trading + funding accounts."""

    def __init__(self) -> None:
        self._api_key, self._api_secret, self._passphrase = _load_credentials()
        self._simulated = _simulated_enabled()
        self._available = bool(self._api_key and self._api_secret and self._passphrase)
        if not self._available:
            log.warning(
                "OKX credentials unavailable — expected okx_api_key / okx_api_secret / "
                "okx_passphrase in %s (or OKX_API_KEY / OKX_API_SECRET / OKX_PASSPHRASE)",
                _SECRETS,
            )
        self._ticker_cache: dict[str, float] | None = None

    def is_configured(self) -> bool:
        """True if all three OKX credential components are present."""
        return self._available

    # -- requests ---------------------------------------------------------

    def _private_get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = _request(
            "GET",
            f"{path}{_encode_query(params)}",
            api_key=self._api_key,
            api_secret=self._api_secret,
            passphrase=self._passphrase,
            simulated=self._simulated,
        )
        data = payload.get("data")
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    def _public_get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = _request("GET", f"{path}{_encode_query(params)}")
        data = payload.get("data")
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    # -- pricing ----------------------------------------------------------

    def get_spot_prices(self) -> dict[str, float]:
        """Return ``{CCY: usd_price}`` from OKX public SPOT tickers.

        Public endpoint — works without credentials, which is what lets the
        aggregator use OKX as a price oracle for Robinhood holdings that
        Robinhood's own marketdata endpoint refuses to quote.
        """
        if self._ticker_cache is not None:
            return self._ticker_cache

        prices: dict[str, float] = {c: 1.0 for c in _USD_STABLES}
        try:
            tickers = self._public_get("/api/v5/market/tickers", {"instType": "SPOT"})
        except Exception as exc:
            log.warning("OKX get_spot_prices failed: %s", exc)
            self._ticker_cache = prices
            return prices

        # Prefer USDT pairs (deepest books), then USDC, then USD.
        for quote in ("USD", "USDC", "USDT"):
            for row in tickers:
                inst_id = str(row.get("instId") or "")
                base, _, row_quote = inst_id.partition("-")
                if row_quote != quote or not base:
                    continue
                price = _as_float(row.get("last")) or _as_float(row.get("idxPx"))
                if price is not None and price > 0:
                    prices[base.upper()] = price

        self._ticker_cache = prices
        return prices

    # -- account ----------------------------------------------------------

    def get_account(self) -> dict[str, Any]:
        """Return OKX trading-account equity and margin status."""
        if not self._available:
            return {"source": "unavailable", "error": "credentials not loaded"}
        try:
            rows = self._private_get("/api/v5/account/balance")
            if not rows:
                return {"source": "unavailable", "error": "no OKX account data"}
            account = rows[0]
            return {
                "source": "okx",
                "total_equity_usd": _as_float(account.get("totalEq")) or 0.0,
                "account_equity_usd": _as_float(account.get("adjEq")),
                "isolated_equity_usd": _as_float(account.get("isoEq")),
                "ord_frozen_usd": _as_float(account.get("ordFroz")),
                "margin_ratio": _as_float(account.get("mgnRatio")),
                "simulated": self._simulated,
            }
        except Exception as exc:
            log.warning("OKX get_account failed: %s", exc)
            return {"source": "unavailable", "error": str(exc)}

    def _trading_balances(self) -> dict[str, dict[str, float]]:
        """Currency -> balance from the OKX trading (unified) account."""
        out: dict[str, dict[str, float]] = {}
        rows = self._private_get("/api/v5/account/balance")
        for account in rows:
            details = account.get("details")
            if not isinstance(details, list):
                continue
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                ccy = str(detail.get("ccy") or "").upper()
                qty = _as_float(detail.get("eq")) or _as_float(detail.get("cashBal")) or 0.0
                if not ccy or qty <= 0:
                    continue
                bucket = out.setdefault(ccy, {"qty": 0.0, "usd": 0.0})
                bucket["qty"] += qty
                # OKX gives per-currency USD valuation directly — trust it over
                # our own ticker math when present.
                eq_usd = _as_float(detail.get("eqUsd"))
                if eq_usd is not None:
                    bucket["usd"] += eq_usd
        return out

    def _funding_balances(self) -> dict[str, dict[str, float]]:
        """Currency -> balance from the OKX funding account."""
        out: dict[str, dict[str, float]] = {}
        rows = self._private_get("/api/v5/asset/balances")
        for row in rows:
            ccy = str(row.get("ccy") or "").upper()
            qty = _as_float(row.get("bal")) or 0.0
            if not ccy or qty <= 0:
                continue
            bucket = out.setdefault(ccy, {"qty": 0.0, "usd": 0.0})
            bucket["qty"] += qty
        return out

    def get_holdings(self) -> list[dict[str, Any]]:
        """Return OKX holdings merged across trading + funding accounts.

        Rows use the same key contract as ``RobinhoodReader.get_holdings`` so
        the aggregator can concatenate them without translation:
        ``symbol`` / ``qty`` / ``price`` / ``market_value`` / ``weight``.
        """
        if not self._available:
            return []

        merged: dict[str, dict[str, float]] = {}
        sub_accounts: dict[str, set[str]] = {}

        for label, loader in (
            ("trading", self._trading_balances),
            ("funding", self._funding_balances),
        ):
            try:
                balances = loader()
            except Exception as exc:
                log.warning("OKX %s balances failed: %s", label, exc)
                continue
            for ccy, bucket in balances.items():
                target = merged.setdefault(ccy, {"qty": 0.0, "usd": 0.0})
                target["qty"] += bucket["qty"]
                target["usd"] += bucket["usd"]
                sub_accounts.setdefault(ccy, set()).add(label)

        if not merged:
            return []

        prices = self.get_spot_prices()
        rows: list[dict[str, Any]] = []
        for ccy, bucket in merged.items():
            qty = bucket["qty"]
            price = prices.get(ccy)
            # OKX's own eqUsd is authoritative when it covers the whole position;
            # otherwise value the full quantity off the ticker.
            market_value = bucket["usd"] if bucket["usd"] > 0 else None
            if market_value is None and price is not None:
                market_value = qty * price
            if price is None and market_value is not None and qty > 0:
                price = market_value / qty
            if market_value is not None and market_value < _MIN_HOLDING_USD:
                continue
            rows.append(
                {
                    "asset_code": ccy,
                    "symbol": ccy,
                    "trading_pair": f"{ccy}-USDT",
                    "qty": qty,
                    "available_qty": qty,
                    "price": price,
                    # OKX does not expose cost basis on balance endpoints.
                    "avg_cost": None,
                    "market_value": market_value,
                    "total_return": None,
                    "sub_accounts": sorted(sub_accounts.get(ccy, set())),
                }
            )

        total = sum(r["market_value"] or 0.0 for r in rows)
        for row in rows:
            mv = row.get("market_value")
            row["weight"] = (mv / total * 100.0) if mv is not None and total > 0 else None

        rows.sort(
            key=lambda r: r.get("market_value") if r.get("market_value") is not None else -1.0,
            reverse=True,
        )
        log.info("okx: %d holdings, total value $%s", len(rows), f"{total:,.2f}")
        return rows

    def get_portfolio_value(self) -> dict[str, Any]:
        """Return OKX account value derived from merged holdings."""
        if not self._available:
            return {"source": "unavailable", "error": "credentials not loaded"}

        account = self.get_account()
        if account.get("source") != "okx":
            return account

        holdings = self.get_holdings()
        holdings_value = sum(h.get("market_value") or 0.0 for h in holdings)
        cash = sum(h.get("market_value") or 0.0 for h in holdings if h["symbol"] in _USD_STABLES)

        return {
            "source": "okx",
            "equity": holdings_value,
            "cash": cash,
            "buying_power": cash,
            "holdings_value": holdings_value - cash,
            "day_pnl": None,
            "day_pnl_pct": None,
            # OKX balance endpoints carry no cost basis, so unrealized P&L is
            # genuinely unknowable here rather than zero.
            "total_return": None,
            "total_return_pct": None,
            "position_count": len(holdings),
            "reported_total_equity_usd": account.get("total_equity_usd"),
            "simulated": self._simulated,
        }

    def get_snapshot(self) -> dict[str, Any]:
        """Full OKX snapshot in the same shape as ``RobinhoodReader.get_snapshot``."""
        pv = self.get_portfolio_value()
        holdings = self.get_holdings() if self._available else []
        is_live = pv.get("source") == "okx"

        return {
            "source": "okx" if is_live else "unavailable",
            "total_value": pv.get("equity", 0.0) or 0.0,
            "day_pnl": pv.get("day_pnl"),
            "day_pnl_pct": pv.get("day_pnl_pct"),
            "total_return": pv.get("total_return"),
            "total_return_pct": pv.get("total_return_pct"),
            "cash": pv.get("cash", 0.0) or 0.0,
            "buying_power": pv.get("buying_power", 0.0) or 0.0,
            "holdings": holdings,
            "last_updated": time.time(),
            "simulated": self._simulated,
            "error": pv.get("error"),
        }


def get_reader() -> OKXReader:
    """Factory function — returns an OKXReader."""
    return OKXReader()
