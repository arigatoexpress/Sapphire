"""ChainIntelligence aggregator — synthesizes on-chain data into a market regime.

The `get_regime()` method is the crown jewel: it combines BTC dominance,
funding extremes, TVL direction, and stablecoin supply deltas into a single
RISK_ON / RISK_OFF / TRANSITION call with a numeric confidence.

Historical state is persisted to `data/chain/history.jsonl` so 24h/7d deltas
are meaningful across process restarts.
"""

from __future__ import annotations

import json
import statistics
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .sources import (
    CoinGeckoClient,
    DefiLlamaClient,
    HyperliquidClient,
    SourceError,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "chain"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.jsonl"

# Funding thresholds (per 8h on Hyperliquid — equivalent to ~0.15%/day at extreme)
FUNDING_EXTREME_POS = 0.00050   # 0.05%/8h → crowded longs
FUNDING_EXTREME_NEG = -0.00050  # 0.05%/8h → crowded shorts
FUNDING_ELEVATED = 0.00020

MAJOR_PERPS = ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOGE", "ARB", "OP", "SUI", "APT"]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MarketOverview:
    timestamp: str
    total_market_cap_usd: float
    total_volume_24h_usd: float
    btc_dominance: float
    eth_dominance: float
    market_cap_change_24h_pct: float
    btc_price_usd: float
    eth_price_usd: float
    stablecoin_total_usd: float
    stablecoin_24h_change_pct: float | None


@dataclass
class PerpFunding:
    coin: str
    mark_price: float
    funding_rate_8h: float
    funding_annualized_pct: float  # APR-equivalent (×3×365)
    open_interest_usd: float
    day_volume_usd: float
    extreme_flag: str  # "", "crowded_long", "crowded_short", "elevated_long", "elevated_short"


@dataclass
class FundingSnapshot:
    timestamp: str
    perps: list[PerpFunding]
    extreme_count: int
    avg_funding_pct: float  # mean across majors
    majors_skew: str  # "long", "short", "neutral"


@dataclass
class OISnapshot:
    timestamp: str
    total_oi_usd: float
    delta_24h_pct: float | None  # None on cold start
    top_gainers: list[tuple[str, float]]  # [(coin, pct_change), ...]
    top_losers: list[tuple[str, float]]


@dataclass
class TVLTrend:
    timestamp: str
    total_tvl_usd: float
    tvl_7d_ago_usd: float | None
    delta_7d_pct: float | None
    top_chains: list[tuple[str, float]]  # [(chain, tvl), ...] top 10
    direction: str  # "rising", "falling", "flat"


@dataclass
class StablecoinFlows:
    timestamp: str
    total_usd: float
    tether_usd: float
    usdc_usd: float
    delta_24h_usd: float | None
    delta_7d_usd: float | None
    flow_direction: str  # "inflow" (minting), "outflow" (burning), "neutral"


@dataclass
class MarketRegime:
    timestamp: str
    state: str  # "RISK_ON", "RISK_OFF", "TRANSITION"
    confidence: float  # 0.0 – 1.0
    score: float  # -1.0 (max risk-off) to +1.0 (max risk-on)
    signals: dict[str, float] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# History persistence
# ---------------------------------------------------------------------------


_history_lock = threading.Lock()


def _append_history(snapshot: dict) -> None:
    with _history_lock, HISTORY_FILE.open("a") as f:
        f.write(json.dumps(snapshot) + "\n")


def _read_history(kind: str, max_age_secs: float) -> list[dict]:
    """Load history entries of a given kind newer than `max_age_secs`."""
    if not HISTORY_FILE.exists():
        return []
    cutoff = time.time() - max_age_secs
    out: list[dict] = []
    with _history_lock, HISTORY_FILE.open() as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("kind") != kind:
                continue
            ts = e.get("unix_ts")
            if ts is None or ts < cutoff:
                continue
            out.append(e)
    return out


# ---------------------------------------------------------------------------
# ChainIntelligence
# ---------------------------------------------------------------------------


class ChainIntelligence:
    """Aggregator that turns raw on-chain data into decision-grade signals."""

    def __init__(
        self,
        llama: DefiLlamaClient | None = None,
        hyperliquid: HyperliquidClient | None = None,
        coingecko: CoinGeckoClient | None = None,
    ):
        self.llama = llama or DefiLlamaClient()
        self.hyperliquid = hyperliquid or HyperliquidClient()
        self.coingecko = coingecko or CoinGeckoClient()

    # ------------------------------------------------------------------
    # Primitive collectors
    # ------------------------------------------------------------------

    def get_market_overview(self) -> MarketOverview:
        gm = self.coingecko.global_market()
        prices = self.llama.prices(["coingecko:bitcoin", "coingecko:ethereum"])
        btc = float(prices.get("coingecko:bitcoin", {}).get("price", 0.0))
        eth = float(prices.get("coingecko:ethereum", {}).get("price", 0.0))
        sc = self.llama.stablecoins()

        # Look up 24h-ago stablecoin supply from history
        prev = _read_history("stablecoins", 30 * 3600)
        prev_total = None
        if prev:
            # Find closest to 24h ago
            target = time.time() - 24 * 3600
            closest = min(prev, key=lambda e: abs(e.get("unix_ts", 0) - target))
            if abs(closest.get("unix_ts", 0) - target) < 6 * 3600:
                prev_total = closest.get("total_usd")

        delta_pct = None
        if prev_total and prev_total > 0:
            delta_pct = (sc.total_usd - prev_total) / prev_total * 100.0

        now = datetime.now(UTC)
        overview = MarketOverview(
            timestamp=now.isoformat(),
            total_market_cap_usd=gm.total_market_cap_usd,
            total_volume_24h_usd=gm.total_volume_24h_usd,
            btc_dominance=gm.btc_dominance,
            eth_dominance=gm.eth_dominance,
            market_cap_change_24h_pct=gm.market_cap_change_pct_24h,
            btc_price_usd=btc,
            eth_price_usd=eth,
            stablecoin_total_usd=sc.total_usd,
            stablecoin_24h_change_pct=delta_pct,
        )
        _append_history({
            "kind": "stablecoins",
            "unix_ts": now.timestamp(),
            "total_usd": sc.total_usd,
            "tether_usd": sc.tether_usd,
            "usdc_usd": sc.usdc_usd,
        })
        _append_history({
            "kind": "market_overview",
            "unix_ts": now.timestamp(),
            "btc_dominance": gm.btc_dominance,
            "total_mcap": gm.total_market_cap_usd,
            "btc": btc,
            "eth": eth,
        })
        return overview

    def get_funding_rates(self) -> FundingSnapshot:
        ctxs = self.hyperliquid.meta_and_asset_ctxs()
        by_coin = {c.coin: c for c in ctxs}
        perps: list[PerpFunding] = []
        for coin in MAJOR_PERPS:
            c = by_coin.get(coin)
            if not c:
                continue
            flag = ""
            if c.funding_rate >= FUNDING_EXTREME_POS:
                flag = "crowded_long"
            elif c.funding_rate <= FUNDING_EXTREME_NEG:
                flag = "crowded_short"
            elif c.funding_rate >= FUNDING_ELEVATED:
                flag = "elevated_long"
            elif c.funding_rate <= -FUNDING_ELEVATED:
                flag = "elevated_short"
            perps.append(
                PerpFunding(
                    coin=c.coin,
                    mark_price=c.mark_px,
                    funding_rate_8h=c.funding_rate,
                    funding_annualized_pct=c.funding_rate * 3 * 365 * 100,
                    open_interest_usd=c.open_interest * c.mark_px,
                    day_volume_usd=c.day_volume,
                    extreme_flag=flag,
                )
            )
        extreme_count = sum(1 for p in perps if p.extreme_flag.startswith("crowded"))
        avg = statistics.mean(p.funding_rate_8h for p in perps) if perps else 0.0
        if avg > FUNDING_ELEVATED:
            skew = "long"
        elif avg < -FUNDING_ELEVATED:
            skew = "short"
        else:
            skew = "neutral"
        now = datetime.now(UTC)
        _append_history({
            "kind": "funding",
            "unix_ts": now.timestamp(),
            "avg_funding": avg,
            "extreme_count": extreme_count,
            "perps": {p.coin: p.funding_rate_8h for p in perps},
        })
        return FundingSnapshot(
            timestamp=now.isoformat(),
            perps=perps,
            extreme_count=extreme_count,
            avg_funding_pct=avg * 100,
            majors_skew=skew,
        )

    def get_open_interest_delta(self, hours: int = 24) -> OISnapshot:
        ctxs = self.hyperliquid.meta_and_asset_ctxs()
        by_coin = {c.coin: c for c in ctxs}
        majors = [by_coin[c] for c in MAJOR_PERPS if c in by_coin]
        total_oi_usd = sum(c.open_interest * c.mark_px for c in majors)

        now = datetime.now(UTC)
        # Record current OI in history
        _append_history({
            "kind": "open_interest",
            "unix_ts": now.timestamp(),
            "total_usd": total_oi_usd,
            "per_coin": {c.coin: c.open_interest * c.mark_px for c in majors},
        })

        # Retrieve historical OI
        window = hours * 3600
        hist = _read_history("open_interest", window + 6 * 3600)
        prev_total: float | None = None
        prev_per_coin: dict[str, float] = {}
        if hist:
            target = now.timestamp() - window
            hist_filtered = [e for e in hist if e.get("unix_ts", 0) < now.timestamp() - 1800]
            if hist_filtered:
                closest = min(hist_filtered, key=lambda e: abs(e.get("unix_ts", 0) - target))
                if abs(closest.get("unix_ts", 0) - target) < hours * 3600 * 0.5:
                    prev_total = closest.get("total_usd")
                    prev_per_coin = closest.get("per_coin") or {}

        delta_pct = None
        if prev_total and prev_total > 0:
            delta_pct = (total_oi_usd - prev_total) / prev_total * 100.0

        gainers: list[tuple[str, float]] = []
        losers: list[tuple[str, float]] = []
        if prev_per_coin:
            for c in majors:
                curr = c.open_interest * c.mark_px
                prev = prev_per_coin.get(c.coin)
                if prev and prev > 0:
                    pct = (curr - prev) / prev * 100
                    if pct > 0:
                        gainers.append((c.coin, pct))
                    elif pct < 0:
                        losers.append((c.coin, pct))
            gainers.sort(key=lambda x: -x[1])
            losers.sort(key=lambda x: x[1])

        return OISnapshot(
            timestamp=now.isoformat(),
            total_oi_usd=total_oi_usd,
            delta_24h_pct=delta_pct,
            top_gainers=gainers[:5],
            top_losers=losers[:5],
        )

    def get_defi_tvl_trend(self, days: int = 7) -> TVLTrend:
        chains = self.llama.chains()
        total_tvl = sum(c.tvl for c in chains)
        top = sorted(chains, key=lambda c: -c.tvl)[:10]

        # Pull historical TVL
        history = self.llama.chart_tvl()
        prev_tvl: float | None = None
        if history:
            target_ts = int(time.time()) - days * 86400
            # history is sorted ascending by date
            closest = min(history, key=lambda p: abs(p[0] - target_ts))
            if abs(closest[0] - target_ts) < 2 * 86400:
                prev_tvl = closest[1]

        delta_pct = None
        direction = "flat"
        if prev_tvl and prev_tvl > 0:
            delta_pct = (total_tvl - prev_tvl) / prev_tvl * 100.0
            if delta_pct > 1.5:
                direction = "rising"
            elif delta_pct < -1.5:
                direction = "falling"

        now = datetime.now(UTC)
        return TVLTrend(
            timestamp=now.isoformat(),
            total_tvl_usd=total_tvl,
            tvl_7d_ago_usd=prev_tvl,
            delta_7d_pct=delta_pct,
            top_chains=[(c.name, c.tvl) for c in top],
            direction=direction,
        )

    def get_stablecoin_flows(self) -> StablecoinFlows:
        sc = self.llama.stablecoins()
        now = datetime.now(UTC)

        hist = _read_history("stablecoins", 8 * 86400)
        delta_24h: float | None = None
        delta_7d: float | None = None
        if hist:
            t24 = now.timestamp() - 86400
            t7 = now.timestamp() - 7 * 86400
            h24 = min(hist, key=lambda e: abs(e.get("unix_ts", 0) - t24))
            h7 = min(hist, key=lambda e: abs(e.get("unix_ts", 0) - t7))
            if abs(h24.get("unix_ts", 0) - t24) < 6 * 3600:
                delta_24h = sc.total_usd - float(h24.get("total_usd") or 0)
            if abs(h7.get("unix_ts", 0) - t7) < 36 * 3600:
                delta_7d = sc.total_usd - float(h7.get("total_usd") or 0)

        # Classify on 24h
        flow = "neutral"
        if delta_24h is not None:
            pct = delta_24h / sc.total_usd * 100 if sc.total_usd else 0
            if pct > 0.3:
                flow = "inflow"
            elif pct < -0.3:
                flow = "outflow"

        return StablecoinFlows(
            timestamp=now.isoformat(),
            total_usd=sc.total_usd,
            tether_usd=sc.tether_usd,
            usdc_usd=sc.usdc_usd,
            delta_24h_usd=delta_24h,
            delta_7d_usd=delta_7d,
            flow_direction=flow,
        )

    # ------------------------------------------------------------------
    # Regime synthesizer (the crown jewel)
    # ------------------------------------------------------------------

    def get_regime(self) -> MarketRegime:
        """Synthesize a market regime from all inputs.

        Each input contributes a sub-score in [-1, +1]. The final score is
        a weighted average; >0.2 = RISK_ON, <-0.2 = RISK_OFF, else TRANSITION.
        Confidence is derived from the magnitude of the score and the
        agreement between inputs.
        """
        now = datetime.now(UTC)
        signals: dict[str, float] = {}
        reasoning: list[str] = []
        weights: dict[str, float] = {}
        failures: list[str] = []

        # ── BTC dominance direction ──
        try:
            overview = self.get_market_overview()
            dom = overview.btc_dominance
            mcap_change = overview.market_cap_change_24h_pct
            # Rising dominance + falling total mcap = risk-off (flight to BTC)
            dom_score = 0.0
            if mcap_change > 1.5:
                dom_score += 0.3
                reasoning.append(f"Total mcap +{mcap_change:.1f}% 24h → risk-on")
            elif mcap_change < -1.5:
                dom_score -= 0.3
                reasoning.append(f"Total mcap {mcap_change:.1f}% 24h → risk-off")
            if dom > 58:
                dom_score -= 0.2
                reasoning.append(f"BTC.D {dom:.1f}% elevated (alt weakness)")
            elif dom < 50:
                dom_score += 0.2
                reasoning.append(f"BTC.D {dom:.1f}% low (alt strength)")
            signals["market"] = max(-1.0, min(1.0, dom_score))
            weights["market"] = 0.25
        except SourceError as e:
            failures.append(f"market_overview: {e}")

        # ── Funding rates ──
        try:
            funding = self.get_funding_rates()
            avg = funding.avg_funding_pct / 100
            # Moderately positive funding = healthy; extreme = crowded = inversion risk
            f_score = 0.0
            if avg > FUNDING_EXTREME_POS:
                f_score -= 0.4  # Crowded long = contrarian bearish
                reasoning.append(f"Funding extreme long ({avg*100*3*365:.1f}% APR) → overheated")
            elif avg > FUNDING_ELEVATED:
                f_score += 0.2  # Healthy long bias
                reasoning.append(f"Funding healthy long ({avg*100*3*365:.1f}% APR)")
            elif avg < FUNDING_EXTREME_NEG:
                f_score += 0.4  # Crowded short = contrarian bullish
                reasoning.append("Funding extreme short → squeeze potential")
            elif avg < -FUNDING_ELEVATED:
                f_score -= 0.2
                reasoning.append(f"Funding bearish ({avg*100*3*365:.1f}% APR)")
            else:
                reasoning.append(f"Funding neutral ({avg*100*3*365:+.1f}% APR)")
            signals["funding"] = max(-1.0, min(1.0, f_score))
            weights["funding"] = 0.25
        except SourceError as e:
            failures.append(f"funding: {e}")

        # ── Open interest ──
        try:
            oi = self.get_open_interest_delta()
            oi_score = 0.0
            if oi.delta_24h_pct is not None:
                if oi.delta_24h_pct > 3:
                    oi_score += 0.3
                    reasoning.append(f"OI +{oi.delta_24h_pct:.1f}% 24h — fresh longs")
                elif oi.delta_24h_pct < -3:
                    oi_score -= 0.3
                    reasoning.append(f"OI {oi.delta_24h_pct:.1f}% 24h — deleveraging")
            signals["oi"] = max(-1.0, min(1.0, oi_score))
            weights["oi"] = 0.15
        except SourceError as e:
            failures.append(f"oi: {e}")

        # ── DeFi TVL ──
        try:
            tvl = self.get_defi_tvl_trend(days=7)
            t_score = 0.0
            if tvl.delta_7d_pct is not None:
                if tvl.direction == "rising":
                    t_score = min(0.5, tvl.delta_7d_pct / 10)
                    reasoning.append(f"TVL +{tvl.delta_7d_pct:.1f}% 7d → DeFi expanding")
                elif tvl.direction == "falling":
                    t_score = max(-0.5, tvl.delta_7d_pct / 10)
                    reasoning.append(f"TVL {tvl.delta_7d_pct:.1f}% 7d → DeFi contracting")
            signals["tvl"] = max(-1.0, min(1.0, t_score))
            weights["tvl"] = 0.15
        except SourceError as e:
            failures.append(f"tvl: {e}")

        # ── Stablecoin flows ──
        try:
            sc = self.get_stablecoin_flows()
            s_score = 0.0
            if sc.delta_7d_usd is not None:
                if sc.flow_direction == "inflow":
                    s_score = 0.3
                    reasoning.append(f"Stablecoins +${sc.delta_7d_usd/1e9:+.1f}B 7d → fiat entering")
                elif sc.flow_direction == "outflow":
                    s_score = -0.3
                    reasoning.append(f"Stablecoins ${sc.delta_7d_usd/1e9:+.1f}B 7d → fiat exiting")
            signals["stablecoins"] = max(-1.0, min(1.0, s_score))
            weights["stablecoins"] = 0.20
        except SourceError as e:
            failures.append(f"stablecoins: {e}")

        # ── Weighted score ──
        if not signals:
            return MarketRegime(
                timestamp=now.isoformat(),
                state="TRANSITION",
                confidence=0.0,
                score=0.0,
                signals={},
                reasoning=["All data sources failed"] + failures,
            )
        total_weight = sum(weights[k] for k in signals)
        score = sum(signals[k] * weights[k] for k in signals) / total_weight

        if score >= 0.2:
            state = "RISK_ON"
        elif score <= -0.2:
            state = "RISK_OFF"
        else:
            state = "TRANSITION"

        # Confidence: magnitude × agreement (how many signals agree with final call)
        if score > 0:
            agreement = sum(1 for v in signals.values() if v > 0) / len(signals)
        elif score < 0:
            agreement = sum(1 for v in signals.values() if v < 0) / len(signals)
        else:
            agreement = 0.5
        confidence = min(1.0, abs(score) * agreement * 2)

        if failures:
            reasoning.extend(f"⚠ {f}" for f in failures)

        # Persist regime row so correlation.regime_adjusted_matrices can
        # bucket historical returns by RISK_ON / RISK_OFF days.
        _append_history({
            "kind": "regime",
            "unix_ts": now.timestamp(),
            "state": state,
            "score": round(score, 3),
            "confidence": round(confidence, 3),
        })

        return MarketRegime(
            timestamp=now.isoformat(),
            state=state,
            confidence=round(confidence, 3),
            score=round(score, 3),
            signals={k: round(v, 3) for k, v in signals.items()},
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # Unified dict for API
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Unified dict of every metric — used by /api/chain/overview."""
        out: dict = {"generated_at": datetime.now(UTC).isoformat()}
        try:
            out["overview"] = asdict(self.get_market_overview())
        except SourceError as e:
            out["overview_error"] = str(e)
        try:
            out["funding"] = asdict(self.get_funding_rates())
        except SourceError as e:
            out["funding_error"] = str(e)
        try:
            out["open_interest"] = asdict(self.get_open_interest_delta())
        except SourceError as e:
            out["open_interest_error"] = str(e)
        try:
            out["tvl"] = asdict(self.get_defi_tvl_trend())
        except SourceError as e:
            out["tvl_error"] = str(e)
        try:
            out["stablecoins"] = asdict(self.get_stablecoin_flows())
        except SourceError as e:
            out["stablecoins_error"] = str(e)
        try:
            out["regime"] = asdict(self.get_regime())
        except SourceError as e:
            out["regime_error"] = str(e)
        return out


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    ci = ChainIntelligence()

    print("=== Market Overview ===")
    ov = ci.get_market_overview()
    print(f"BTC.D: {ov.btc_dominance:.2f}% | total mcap: ${ov.total_market_cap_usd:,.0f} | 24h: {ov.market_cap_change_24h_pct:+.2f}%")
    print(f"Stablecoins: ${ov.stablecoin_total_usd:,.0f}")

    print("\n=== Funding ===")
    f = ci.get_funding_rates()
    print(f"Avg: {f.avg_funding_pct:+.4f}% per 8h | skew: {f.majors_skew} | extremes: {f.extreme_count}")
    for p in f.perps[:5]:
        print(f"  {p.coin:6} {p.funding_rate_8h*100:+.4f}%/8h  OI=${p.open_interest_usd/1e6:.1f}M  flag={p.extreme_flag}")

    print("\n=== Open Interest ===")
    oi = ci.get_open_interest_delta()
    print(f"Total OI: ${oi.total_oi_usd/1e9:.2f}B | 24h: {oi.delta_24h_pct}")

    print("\n=== TVL ===")
    tvl = ci.get_defi_tvl_trend()
    print(f"Total: ${tvl.total_tvl_usd/1e9:.1f}B | 7d: {tvl.delta_7d_pct}  direction={tvl.direction}")
    for name, v in tvl.top_chains[:5]:
        print(f"  {name:12} ${v/1e9:.1f}B")

    print("\n=== Stablecoin Flows ===")
    sc = ci.get_stablecoin_flows()
    print(f"Total: ${sc.total_usd/1e9:.1f}B | 24h: {sc.delta_24h_usd} | 7d: {sc.delta_7d_usd} | flow={sc.flow_direction}")

    print("\n=== REGIME ===")
    r = ci.get_regime()
    print(f"STATE: {r.state} (score={r.score:+.3f}, conf={r.confidence:.2f})")
    print(f"Signals: {r.signals}")
    for reason in r.reasoning:
        print(f"  • {reason}")
