#!/usr/bin/env python3
"""Sapphire Solana paper wallet — simulated SPL balances + swaps.

NO real transactions. NO keys. Balances live in data/solana_paper_wallet.json.
Prices fetched from CoinGecko (read-only, public API). Swap simulation applies
a configurable spread + slippage so backtested results don't look unrealistically
clean.

Actions:
    balance   — current balances + USD values
    deposit   — add tokens to the paper wallet
    swap      — simulate a token swap (A → B) at live price with slippage
    history   — recent swap history
    pnl       — realized + unrealized PnL since inception
    reset     — reset wallet to initial state (requires confirm=true)

Usage:
    echo '{"action":"balance"}' | python3 solana_wallet.py
    echo '{"action":"deposit","token":"SOL","amount":10}' | python3 solana_wallet.py
    echo '{"action":"swap","from":"SOL","to":"USDC","amount":2.5}' | python3 solana_wallet.py
    echo '{"action":"pnl"}' | python3 solana_wallet.py
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
WALLET_FILE = SAPPHIRE_DIR / "data" / "solana_paper_wallet.json"

# Known tokens — extend as needed. CoinGecko IDs for price lookup.
TOKENS = {
    "SOL": {"coingecko": "solana", "decimals": 9},
    "USDC": {"coingecko": "usd-coin", "decimals": 6},
    "USDT": {"coingecko": "tether", "decimals": 6},
    "JUP": {"coingecko": "jupiter-exchange-solana", "decimals": 6},
    "BONK": {"coingecko": "bonk", "decimals": 5},
    "JITOSOL": {"coingecko": "jito-staked-sol", "decimals": 9},
    "PYTH": {"coingecko": "pyth-network", "decimals": 6},
}

# Swap simulation params
DEFAULT_SPREAD_BPS = 20  # 0.20% — typical Jupiter spread for liquid pairs
DEFAULT_SLIPPAGE_BPS = 30  # 0.30% — conservative estimate
STARTING_USDC = 10_000.0  # $10K seed in paper wallet


def _ssl_ctx() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch USD prices from CoinGecko. Returns {} on failure."""
    ids = ",".join(TOKENS[s]["coingecko"] for s in symbols if s in TOKENS)
    if not ids:
        return {}
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
    try:
        with urllib.request.urlopen(url, timeout=10, context=_ssl_ctx()) as r:
            data = json.loads(r.read())
    except Exception:
        return {}
    out: dict[str, float] = {}
    for sym, meta in TOKENS.items():
        if sym in symbols:
            px = data.get(meta["coingecko"], {}).get("usd")
            if px is not None:
                out[sym] = float(px)
    # Hard-code stablecoin to $1.00 if CoinGecko returns None (rare, but happens)
    for stable in ("USDC", "USDT"):
        out.setdefault(stable, 1.0)
    return out


def _load() -> dict:
    if WALLET_FILE.exists():
        return json.loads(WALLET_FILE.read_text(encoding="utf-8"))
    return {
        "balances": {"USDC": STARTING_USDC},
        "history": [],
        "created_at": datetime.now(UTC).isoformat(),
        "initial_usd_value": STARTING_USDC,
    }


def _save(w: dict) -> None:
    WALLET_FILE.parent.mkdir(parents=True, exist_ok=True)
    WALLET_FILE.write_text(json.dumps(w, indent=2, default=str))


def _round_qty(token: str, amount: float) -> float:
    decimals = TOKENS.get(token, {}).get("decimals", 6)
    return round(amount, decimals)


def action_balance() -> dict:
    w = _load()
    balances = w["balances"]
    prices = _fetch_prices(list(balances.keys()))
    rows = []
    total = 0.0
    for token, qty in balances.items():
        px = prices.get(token, 0.0)
        value = qty * px
        total += value
        rows.append(
            {
                "token": token,
                "qty": _round_qty(token, qty),
                "price_usd": round(px, 6) if px < 1 else round(px, 4),
                "value_usd": round(value, 2),
            }
        )
    rows.sort(key=lambda r: r["value_usd"], reverse=True)
    return {
        "total_usd": round(total, 2),
        "initial_usd": w.get("initial_usd_value", STARTING_USDC),
        "balances": rows,
        "last_update": datetime.now(UTC).isoformat(),
    }


def action_deposit(token: str, amount: float) -> dict:
    token = token.upper()
    if token not in TOKENS:
        return {"error": f"unknown token {token}. Supported: {sorted(TOKENS)}"}
    if amount <= 0:
        return {"error": "amount must be positive"}
    w = _load()
    w["balances"][token] = _round_qty(token, w["balances"].get(token, 0.0) + amount)
    w["history"].append(
        {
            "action": "deposit",
            "token": token,
            "amount": amount,
            "ts": datetime.now(UTC).isoformat(),
        }
    )
    _save(w)
    return {"success": True, "token": token, "new_balance": w["balances"][token]}


def action_swap(
    from_token: str,
    to_token: str,
    amount: float,
    spread_bps: float = DEFAULT_SPREAD_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> dict:
    from_token = from_token.upper()
    to_token = to_token.upper()
    if from_token == to_token:
        return {"error": "from and to must differ"}
    if from_token not in TOKENS or to_token not in TOKENS:
        return {"error": f"unknown tokens. Supported: {sorted(TOKENS)}"}
    if amount <= 0:
        return {"error": "amount must be positive"}

    w = _load()
    have = w["balances"].get(from_token, 0.0)
    if have < amount:
        return {"error": f"insufficient {from_token}: have {have}, need {amount}"}

    prices = _fetch_prices([from_token, to_token])
    from_px = prices.get(from_token)
    to_px = prices.get(to_token)
    if not from_px or not to_px:
        return {"error": "price unavailable — cannot simulate swap"}

    notional_usd = amount * from_px
    # Apply spread + slippage on the *output* side (common AMM convention).
    cost_factor = 1 - (spread_bps + slippage_bps) / 10_000
    gross_out = notional_usd / to_px
    net_out = gross_out * cost_factor
    fee_usd = notional_usd * (spread_bps + slippage_bps) / 10_000

    w["balances"][from_token] = _round_qty(from_token, have - amount)
    if w["balances"][from_token] <= 0:
        w["balances"].pop(from_token, None)
    w["balances"][to_token] = _round_qty(
        to_token,
        w["balances"].get(to_token, 0.0) + net_out,
    )

    record = {
        "action": "swap",
        "from": from_token,
        "from_amount": amount,
        "to": to_token,
        "to_amount": _round_qty(to_token, net_out),
        "from_price_usd": from_px,
        "to_price_usd": to_px,
        "notional_usd": round(notional_usd, 2),
        "fee_usd": round(fee_usd, 4),
        "spread_bps": spread_bps,
        "slippage_bps": slippage_bps,
        "ts": datetime.now(UTC).isoformat(),
    }
    w["history"].append(record)
    _save(w)

    # Event bus publish — decision engine + dashboard consumers.
    try:
        import sys as _sys

        repo_root = Path.home() / "Code" / "Sapphire"
        if str(repo_root) not in _sys.path:
            _sys.path.insert(0, str(repo_root))
        from lib.core.event_bus import get_bus

        get_bus().publish("wallet.swap", record, source="solana_paper_wallet")
    except Exception:
        pass

    return {
        "success": True,
        "swap": f"{amount} {from_token} → {record['to_amount']} {to_token}",
        "fee_usd": record["fee_usd"],
        "new_balances": {
            from_token: w["balances"].get(from_token, 0.0),
            to_token: w["balances"][to_token],
        },
    }


def action_history(limit: int = 20) -> dict:
    w = _load()
    return {"history": w["history"][-limit:]}


def action_pnl() -> dict:
    w = _load()
    bal = action_balance()
    initial = w.get("initial_usd_value", STARTING_USDC)
    current = bal["total_usd"]
    pnl = current - initial
    pnl_pct = (pnl / initial * 100) if initial > 0 else 0.0
    fees = sum(h.get("fee_usd", 0) for h in w.get("history", []) if h.get("action") == "swap")
    return {
        "initial_usd": initial,
        "current_usd": current,
        "realized_fees_usd": round(fees, 4),
        "pnl_usd": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 3),
        "trades": sum(1 for h in w.get("history", []) if h.get("action") == "swap"),
    }


def action_reset(confirm: bool = False) -> dict:
    if not confirm:
        return {"error": "reset requires confirm=true"}
    if WALLET_FILE.exists():
        WALLET_FILE.unlink()
    w = _load()
    _save(w)
    return {"success": True, "balances": w["balances"]}


def main() -> None:
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "balance"}
    action = params.get("action", "balance")

    if action == "balance":
        result = action_balance()
    elif action == "deposit":
        result = action_deposit(params.get("token", ""), float(params.get("amount", 0)))
    elif action == "swap":
        result = action_swap(
            params.get("from", ""),
            params.get("to", ""),
            float(params.get("amount", 0)),
            spread_bps=float(params.get("spread_bps", DEFAULT_SPREAD_BPS)),
            slippage_bps=float(params.get("slippage_bps", DEFAULT_SLIPPAGE_BPS)),
        )
    elif action == "history":
        result = action_history(int(params.get("limit", 20)))
    elif action == "pnl":
        result = action_pnl()
    elif action == "reset":
        result = action_reset(bool(params.get("confirm", False)))
    else:
        result = {"error": f"unknown action {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
