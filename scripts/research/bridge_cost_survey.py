"""Live bridge fee survey for USDC L2-L2 (Arbitrum <-> Optimism).

Read-only. Quotes only — does NOT bridge anything. Pulls real-time fees
from public quote APIs and emits a markdown table + machine-readable
JSON for ingestion into the backtest cost calibration.

Providers surveyed:
- Across Protocol  -- public suggested-fees API
- Stargate         -- v1 quoteLayerZeroFee + token transfer fee
- Hop Protocol     -- public quote API (v2)
- CCTP (Circle)    -- structurally near-zero (paid in destination gas)

Usage:
    python3 scripts/research/bridge_cost_survey.py [--json out.json]

Notional buckets: $1k, $10k, $100k.
Directions: Arbitrum (42161) <-> Optimism (10).

The output table feeds the BRIDGE_COST_TIERS constant in
``lib/trading/cross_chain_arb_backtest.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# Token addresses (native USDC, not bridged USDC.e where possible)
USDC_ARBITRUM = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"  # native USDC
USDC_OPTIMISM = "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85"  # native USDC

# Notional buckets in USD (USDC has 6 decimals)
NOTIONALS_USD = (1_000, 10_000, 100_000)


@dataclass
class Quote:
    provider: str
    direction: str  # "ARB->OP" or "OP->ARB"
    notional_usd: int
    fee_usd: float | None
    fee_bps: float | None
    finality_seconds: int | None
    note: str = ""
    raw: dict = field(default_factory=dict)


def _http_get(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 SapphireBridgeSurvey/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def quote_across(direction: str, notional_usd: int) -> Quote:
    """Across suggested-fees endpoint (public, no auth required for quotes)."""
    if direction == "ARB->OP":
        origin, dest = 42161, 10
        in_tok, out_tok = USDC_ARBITRUM, USDC_OPTIMISM
    else:
        origin, dest = 10, 42161
        in_tok, out_tok = USDC_OPTIMISM, USDC_ARBITRUM

    amount_units = notional_usd * 1_000_000  # USDC = 6 decimals
    params = urllib.parse.urlencode({
        "inputToken": in_tok,
        "outputToken": out_tok,
        "originChainId": origin,
        "destinationChainId": dest,
        "amount": str(amount_units),
    })
    url = f"https://app.across.to/api/suggested-fees?{params}"
    try:
        data = _http_get(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return Quote("Across", direction, notional_usd, None, None, None,
                     note=f"error: {exc}")

    if data.get("isAmountTooLow"):
        return Quote("Across", direction, notional_usd, None, None, None,
                     note="below minDeposit", raw=data)

    output_amount_units = int(data["outputAmount"])
    fee_units = amount_units - output_amount_units
    fee_usd = fee_units / 1_000_000
    fee_bps = (fee_units / amount_units) * 10_000
    finality = int(data.get("estimatedFillTimeSec", 0))
    return Quote(
        "Across", direction, notional_usd,
        round(fee_usd, 4), round(fee_bps, 4), finality,
        note=f"output={output_amount_units / 1_000_000:.4f} USDC",
        raw={"totalRelayFee_pct": data.get("totalRelayFee", {}).get("pct"),
             "lpFee_pct": data.get("lpFee", {}).get("pct"),
             "fillDeadline": data.get("fillDeadline")},
    )


def quote_hop(direction: str, notional_usd: int) -> Quote:
    """Hop Protocol quote API (v1.x, public)."""
    if direction == "ARB->OP":
        from_chain, to_chain = "arbitrum", "optimism"
    else:
        from_chain, to_chain = "optimism", "arbitrum"

    amount_units = notional_usd * 1_000_000
    params = urllib.parse.urlencode({
        "amount": str(amount_units),
        "token": "USDC",
        "fromChain": from_chain,
        "toChain": to_chain,
        "slippage": "0.5",
    })
    url = f"https://api.hop.exchange/v1/quote?{params}"
    try:
        data = _http_get(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return Quote("Hop", direction, notional_usd, None, None, None,
                     note=f"error: {exc}")

    # Hop returns: amountIn, estimatedRecieved (sic), bonderFee, etc.
    # NB: "estimatedRecieved" is the Hop API's actual key (typo upstream).
    try:
        amount_in = int(data["amountIn"])
        # Try both spellings; current Hop API uses "estimatedRecieved"
        if "estimatedRecieved" in data:
            amount_out = int(data["estimatedRecieved"])
        elif "estimatedReceived" in data:
            amount_out = int(data["estimatedReceived"])
        elif "amountOut" in data:
            amount_out = int(data["amountOut"])
        else:
            amount_out = int(data["amountOutMin"])
        bonder_fee = int(data.get("bonderFee", 0))
        total_fee_units = amount_in - amount_out
        fee_usd = total_fee_units / 1_000_000
        fee_bps = (total_fee_units / amount_in) * 10_000
        # Hop typically settles in 1-5 minutes for L2->L2
        return Quote(
            "Hop", direction, notional_usd,
            round(fee_usd, 4), round(fee_bps, 4),
            120,  # ~2min typical hAMM settlement
            note=f"bonderFee={bonder_fee/1e6:.4f} USDC",
            raw={"amountIn": amount_in, "estimatedRecieved": amount_out,
                 "bonderFee": bonder_fee},
        )
    except (KeyError, ValueError, TypeError) as exc:
        return Quote("Hop", direction, notional_usd, None, None, None,
                     note=f"parse error: {exc}", raw=data)


def quote_stargate(direction: str, notional_usd: int) -> Quote:
    """Stargate fee structure: protocol fee (0.06% USDC pool) + LayerZero gas.

    Stargate doesn't expose a public quote-fees REST API for arbitrary
    chain pairs; their on-chain ``feeLibrary.getFees()`` returns the
    breakdown but requires a web3 call. We model their published USDC
    pool fee structure as a fixed-bps approximation (verified against
    docs.stargate.finance v1 fee schedule):

    - Protocol fee:  0.06% (6 bps) for USDC pool
    - LP reward:     0.0% (currently subsidized)
    - Equilibrium fee: variable based on pool delta; we use the typical
      observed 0-2 bps for USDC ARB<->OP balanced pools.
    - LayerZero gas: ~$0.50-2 in destination gas per transfer.

    Total estimate: ~6-8 bps for USDC L2<->L2.
    """
    # Stargate v1 USDC L2<->L2: ~6 bps protocol + small LZ gas
    base_bps = 6.0
    # LZ gas component scales weakly with notional (it's basically fixed gas)
    lz_gas_usd = 1.0  # typical observed for ARB<->OP USDC
    fee_usd_estimate = (notional_usd * base_bps / 10_000) + lz_gas_usd
    fee_bps_estimate = (fee_usd_estimate / notional_usd) * 10_000
    return Quote(
        "Stargate", direction, notional_usd,
        round(fee_usd_estimate, 4), round(fee_bps_estimate, 4),
        90,  # typical L2<->L2 settlement
        note="modeled: 6bps protocol + ~$1 LZ gas (no public REST quote API)",
        raw={"base_bps": base_bps, "lz_gas_usd_estimate": lz_gas_usd},
    )


def quote_cctp(direction: str, notional_usd: int) -> Quote:
    """Circle CCTP (Cross-Chain Transfer Protocol).

    CCTP burns USDC on origin, mints on destination. Circle charges
    NO protocol fee for v1 standard transfers (Fast Transfer v2 charges
    a small fee for sub-minute finality). Cost is purely destination
    gas to call ``receiveMessage()`` (~$0.10-0.50 on L2s).

    Standard CCTP: 13-19 minute finality (Ethereum L1 attestation).
    Fast CCTP v2: <60 seconds, ~5bps fee.
    """
    # Standard CCTP v1: gas only, ~$0.30 destination + minimal origin
    fee_usd = 0.30
    fee_bps = (fee_usd / notional_usd) * 10_000
    finality = 900  # 15 minutes typical
    return Quote(
        "CCTP-v1", direction, notional_usd,
        round(fee_usd, 4), round(fee_bps, 4), finality,
        note="standard CCTP: zero protocol fee + ~$0.30 dest gas; 13-19min finality",
        raw={"protocol": "Circle CCTP v1"},
    )


def survey() -> list[Quote]:
    quotes: list[Quote] = []
    for direction in ("ARB->OP", "OP->ARB"):
        for notional in NOTIONALS_USD:
            quotes.append(quote_across(direction, notional))
            quotes.append(quote_hop(direction, notional))
            quotes.append(quote_stargate(direction, notional))
            quotes.append(quote_cctp(direction, notional))
    return quotes


def emit_markdown(quotes: list[Quote]) -> str:
    lines = [
        "# USDC L2-L2 Bridge Fee Survey",
        "",
        f"_Surveyed: {datetime.now(timezone.utc).isoformat()}_",
        "",
        "## Live quotes (Arbitrum <-> Optimism, USDC native)",
        "",
        "| Provider | Direction | Notional USD | Fee USD | Fee bps | Finality (s) | Note |",
        "|----------|-----------|--------------|---------|---------|--------------|------|",
    ]
    for q in quotes:
        fee_usd = f"${q.fee_usd:.4f}" if q.fee_usd is not None else "-"
        fee_bps = f"{q.fee_bps:.2f}" if q.fee_bps is not None else "-"
        finality = str(q.finality_seconds) if q.finality_seconds is not None else "-"
        lines.append(
            f"| {q.provider} | {q.direction} | ${q.notional_usd:,} "
            f"| {fee_usd} | {fee_bps} | {finality} | {q.note} |"
        )
    return "\n".join(lines)


def best_per_bucket(quotes: list[Quote]) -> dict[int, Quote]:
    """Pick the median-fastest-economical quote per notional bucket.

    Strategy: for each notional, of the providers with fee data + finality
    under 10 minutes, pick the cheapest. CCTP is excluded from "fast"
    because its 15-min standard finality blocks daily rebalance.
    """
    by_notional: dict[int, list[Quote]] = {n: [] for n in NOTIONALS_USD}
    for q in quotes:
        if q.fee_usd is None or q.finality_seconds is None:
            continue
        if q.finality_seconds > 600:  # exclude slow bridges from "best"
            continue
        by_notional[q.notional_usd].append(q)

    out: dict[int, Quote] = {}
    for n, qs in by_notional.items():
        if not qs:
            continue
        # Best = lowest fee_bps (tie-break: faster finality)
        best = min(qs, key=lambda q: (q.fee_bps, q.finality_seconds))
        out[n] = best
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", help="Write machine-readable JSON to this path")
    p.add_argument("--md", help="Write markdown table to this path")
    args = p.parse_args()

    quotes = survey()
    md = emit_markdown(quotes)
    print(md)
    print()
    print("## Recommended defaults (best fast economical per bucket)")
    print()
    print("| Notional | Provider | Fee bps | Finality (s) |")
    print("|----------|----------|---------|--------------|")
    for n, q in best_per_bucket(quotes).items():
        print(f"| ${n:,} | {q.provider} | {q.fee_bps:.2f} | {q.finality_seconds} |")

    if args.json:
        with open(args.json, "w") as f:
            json.dump([asdict(q) for q in quotes], f, indent=2)
    if args.md:
        with open(args.md, "w") as f:
            f.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
