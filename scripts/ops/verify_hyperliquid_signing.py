#!/usr/bin/env python3
"""Verify Hyperliquid EIP-712 signing — operator-driven gate before mainnet.

Three escalating modes (default is the safest):

1. Local round-trip (default, no network). Sign a test order action with the
   configured wallet, recover the signer from the signature, assert the
   recovered address matches the wallet. Proves the typed-data scheme is
   structurally correct. Does NOT verify that Hyperliquid will accept the
   signature — that requires a real call.

2. ``--info``. After (1), call ``/info clearinghouseState`` on the
   Hyperliquid testnet REST endpoint with the wallet's address. Confirms
   network reachability and that Hyperliquid recognizes the account. Still
   does not exercise authenticated paths.

3. ``--testnet-order``. After (1) and (2), place a real testnet limit order
   priced far from market (so it cannot fill) then immediately cancel it.
   This is the full sign → submit → auth → cancel round-trip. Requires
   testnet HYPE balance for fees. Still uses the in-policy size cap.

Pass criteria for flipping ``HyperliquidLivePolicy.signing_verified=True``
(in code, not env): mode 1 must pass AND, ideally, mode 3 succeeded with
the testnet account at least once. The ``signing_verified`` field is the
only gate that lets the executor run on mainnet.

Usage:
    python3 scripts/ops/verify_hyperliquid_signing.py
    python3 scripts/ops/verify_hyperliquid_signing.py --info
    python3 scripts/ops/verify_hyperliquid_signing.py --testnet-order
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_SRC = ROOT / "services" / "hyperliquid" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eth_account import Account  # noqa: E402
from hyperliquid_bot.client import HyperliquidClient  # noqa: E402
from hyperliquid_bot.risk import HyperliquidLivePolicy, load_private_key  # noqa: E402
from hyperliquid_bot.signing import recover_l1_signer, sign_l1_action  # noqa: E402


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}", file=sys.stderr)


def local_roundtrip(private_key: str) -> bool:
    print("[1/3] local round-trip (no network)")
    wallet = Account.from_key(private_key)
    action = {
        "type": "order",
        "orders": [
            {
                "a": 0,
                "b": True,
                "p": "1",
                "s": "0.0001",
                "r": False,
                "t": {"limit": {"tif": "Gtc"}},
            }
        ],
        "grouping": "na",
    }
    nonce = int(time.time() * 1000)
    sig = sign_l1_action(wallet, action, nonce=nonce, is_mainnet=False)
    recovered = recover_l1_signer(action, sig, nonce=nonce, is_mainnet=False)
    if recovered.lower() != wallet.address.lower():
        _fail(f"recovered {recovered} != wallet {wallet.address}")
        return False
    _ok(f"signer={wallet.address}  testnet round-trip OK")
    return True


async def info_probe(private_key: str) -> bool:
    print("[2/3] testnet /info clearinghouseState probe")
    async with HyperliquidClient(private_key, testnet=True) as client:
        try:
            state = await client.get_user_state()
        except Exception as exc:
            _fail(f"info call failed: {exc!r}")
            return False
    margin = state.get("marginSummary", {}) if isinstance(state, dict) else {}
    print(json.dumps({"marginSummary": margin}, indent=2))
    _ok("testnet recognizes the wallet account")
    return True


async def testnet_order_roundtrip(private_key: str) -> bool:
    print("[3/3] testnet limit order place + cancel")
    policy = HyperliquidLivePolicy()
    async with HyperliquidClient(private_key, testnet=True) as client:
        mids = await client.get_all_mids()
        btc_mid = float(mids.get("BTC", 0) or 0)
        if not btc_mid:
            _fail("no BTC mid price returned from testnet")
            return False
        # Limit price far below mid so the order cannot fill.
        far_px = round(btc_mid * 0.10, 2)
        sz = round(policy.max_order_notional_usd / far_px, 6)
        print(f"  placing limit BTC buy size={sz} @ {far_px} (mid={btc_mid})")
        try:
            place_resp = await client.limit_order("BTC", True, sz, far_px, tif="Gtc")
        except Exception as exc:
            _fail(f"place failed: {exc!r}")
            return False
        print(json.dumps(place_resp, indent=2))
        oid = _extract_oid(place_resp)
        if oid is None:
            _fail("no order id returned — auth may have failed")
            return False
        try:
            cancel_resp = await client.cancel_order("BTC", oid)
        except Exception as exc:
            _fail(f"cancel failed: {exc!r}")
            return False
        print(json.dumps(cancel_resp, indent=2))
    _ok("testnet sign → submit → cancel round-trip OK")
    return True


def _extract_oid(resp: dict) -> int | None:
    try:
        statuses = resp["response"]["data"]["statuses"]
        for s in statuses:
            if isinstance(s, dict):
                if "resting" in s and isinstance(s["resting"], dict):
                    return int(s["resting"].get("oid"))
                if "filled" in s and isinstance(s["filled"], dict):
                    return int(s["filled"].get("oid"))
    except (KeyError, TypeError, ValueError):
        return None
    return None


async def _run(args: argparse.Namespace) -> int:
    policy = HyperliquidLivePolicy()
    private_key = load_private_key(policy)
    if not private_key:
        _fail(
            "no private key — store one in macOS keychain "
            f"(account={policy.keychain_account!r} service={policy.keychain_service!r}) "
            "or export HYPERLIQUID_PRIVATE_KEY"
        )
        return 2

    if not local_roundtrip(private_key):
        return 1

    if args.info or args.testnet_order:
        if not await info_probe(private_key):
            return 1

    if args.testnet_order:
        if not await testnet_order_roundtrip(private_key):
            return 1

    print()
    print("All requested checks passed.")
    print(
        "Once you're satisfied, set HyperliquidLivePolicy.signing_verified=True "
        "in services/hyperliquid/src/hyperliquid_bot/risk.py to unblock mainnet."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--info",
        action="store_true",
        help="Also call testnet /info to verify network reachability + account recognition.",
    )
    parser.add_argument(
        "--testnet-order",
        action="store_true",
        help="Also place + cancel a far-from-market testnet limit order (full auth round-trip).",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
