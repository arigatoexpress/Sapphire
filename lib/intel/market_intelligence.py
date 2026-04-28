"""Market intelligence data feeds — collected every 30 minutes via LaunchAgent.

Five feeds:
  1. Stablecoin issuance tracker   — DeFiLlama (mint/burn signals)
  2. Economic calendar             — ForexFactory JSON + hardcoded FOMC dates
  3. Political signal monitor      — RSS: WhiteHouse, SEC, CFTC (keyword-scored)
  4. Liquidation level estimator   — Hyperliquid OI + funding as leverage proxy
  5. Order flow proxy              — Hyperliquid funding rate velocity per coin

Saves snapshot to data/intelligence/latest/market_intel.json.

Usage:
    python3 -m lib.intel.market_intelligence          # collect + save
    python3 -m lib.intel.market_intelligence --test   # test each feed
"""

from __future__ import annotations

import json
import logging
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.chain.sources import DefiLlamaClient, HyperliquidClient, SourceError

log = logging.getLogger(__name__)

DATA_DIR = ROOT / "data" / "intelligence" / "latest"
SNAPSHOT_FILE = DATA_DIR / "market_intel.json"

# ---------------------------------------------------------------------------
# Minimal HTTP helper for XML/text (sources.py only handles JSON)
# ---------------------------------------------------------------------------

try:
    import certifi

    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

_UA = "sapphire-os/0.4 (+market-intel)"


def _http_get_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/xml, text/xml, */*"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise SourceError(f"GET {url} → HTTP {e.code}: {e.reason}") from e
    except Exception as e:
        raise SourceError(f"GET {url} → {type(e).__name__}: {e}") from e


def _http_get_json(url: str, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SourceError(f"GET {url} → HTTP {e.code}: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise SourceError(f"GET {url} → invalid JSON: {e}") from e
    except Exception as e:
        raise SourceError(f"GET {url} → {type(e).__name__}: {e}") from e


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StablecoinIssuance:
    timestamp: str
    total_usd: float
    usdt_usd: float
    usdc_usd: float
    delta_24h_usd: float | None
    delta_24h_pct: float | None
    # mint_large | mint_moderate | burn_large | burn_moderate | neutral
    signal: str
    detail: str


@dataclass
class EconEvent:
    date: str
    time: str
    title: str
    country: str
    impact: str  # High | Medium | Low
    days_until: int


@dataclass
class EconCalendar:
    timestamp: str
    events: list[EconEvent]
    upcoming_high: list[EconEvent]  # High impact, next 7 days
    next_fomc_days: int | None


@dataclass
class PoliticalSignal:
    timestamp: str
    source: str  # whitehouse | sec | cftc
    title: str
    published: str
    relevance_score: float  # 0–1
    keywords: list[str]
    url: str


@dataclass
class PoliticalMonitor:
    timestamp: str
    signals: list[PoliticalSignal]
    high_relevance_count: int  # score >= 0.5
    crypto_flag: bool


@dataclass
class LiquidationBand:
    coin: str
    mark_price: float
    open_interest_usd: float
    long_liq_estimate: float
    short_liq_estimate: float
    funding_rate_8h: float
    long_proximity_pct: float  # fraction from mark to long liq zone
    short_proximity_pct: float
    # cascade_risk_long | cascade_risk_short | monitor_long | monitor_short | neutral
    flag: str
    detail: str


@dataclass
class LiquidationEstimator:
    timestamp: str
    bands: list[LiquidationBand]
    alerts: list[str]  # coins with cascade_risk flag


@dataclass
class FundingVelocity:
    coin: str
    current_rate_8h: float
    velocity: float  # change per hour
    # accelerating_long | accelerating_short | decelerating | stable
    direction: str
    # extreme_positioning | crowding | normalizing | neutral
    signal: str


@dataclass
class OrderFlowProxy:
    timestamp: str
    velocities: list[FundingVelocity]
    crowding_alerts: list[str]


@dataclass
class MarketIntelSnapshot:
    timestamp: str
    stablecoins: StablecoinIssuance | None = None
    econ_calendar: EconCalendar | None = None
    political: PoliticalMonitor | None = None
    liquidation: LiquidationEstimator | None = None
    order_flow: OrderFlowProxy | None = None
    errors: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ForexFactory free JSON (cached weekly files)
FF_THISWEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_NEXTWEEK = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

# Hardcoded FOMC announcement dates (end of 2-day meeting).
# Update annually from https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_DATES = [
    # 2025
    "2025-01-29",
    "2025-03-19",
    "2025-05-07",
    "2025-06-18",
    "2025-07-30",
    "2025-09-17",
    "2025-10-29",
    "2025-12-10",
    # 2026 — UPDATE WHEN PUBLISHED by Fed
    "2026-01-28",
    "2026-03-18",
    "2026-05-06",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-11-04",
    "2026-12-09",
]

RSS_FEEDS: dict[str, str] = {
    "whitehouse": "https://www.whitehouse.gov/briefing-room/statements-releases/feed/",
    "sec": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&dateb=&owner=include&count=20&search_text=&output=atom",
    "cftc": "https://www.cftc.gov/rss/pressrelease.xml",
}

CRYPTO_KEYWORDS = {
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "crypto",
    "cryptocurrency",
    "digital asset",
    "stablecoin",
    "defi",
    "blockchain",
    "token",
    "nft",
    "cbdc",
    "digital currency",
    "virtual currency",
    "exchange",
    "binance",
    "coinbase",
    "kraken",
    "solana",
    "ripple",
    "xrp",
}

MARKET_KEYWORDS = {
    "tariff",
    "interest rate",
    "federal reserve",
    "inflation",
    "cpi",
    "gdp",
    "employment",
    "monetary policy",
    "sanctions",
    "trade war",
    "executive order",
    "treasury",
    "tax",
    "regulation",
    "enforcement",
    "securities",
    "commodity",
    "derivatives",
    "margin",
    "leverage",
}

# Liquidation estimator
TRACKED_COINS = [
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "AVAX",
    "DOGE",
    "XRP",
    "ARB",
    "OP",
    "LINK",
    "ONDO",
    "ASTER",
    "LIT",
]
# Funding history lookback for velocity: 6 hours
VELOCITY_LOOKBACK_MS = 6 * 60 * 60 * 1000

# Stablecoin signal thresholds
MINT_LARGE_USD = 2_000_000_000  # $2B
MINT_MOD_USD = 500_000_000  # $500M

# Liquidation proximity thresholds
CASCADE_PROXIMITY = 0.08  # flag cascade if within 8% of estimated liquidation
MONITOR_PROXIMITY = 0.15  # flag monitor if within 15%


# ---------------------------------------------------------------------------
# Feed 1: Stablecoin Issuance Tracker
# ---------------------------------------------------------------------------


def _fetch_stablecoins(prev_snapshot: dict | None) -> StablecoinIssuance:
    sc = DefiLlamaClient().stablecoins()

    prev_total: float | None = None
    if prev_snapshot:
        prev_data = prev_snapshot.get("stablecoins") or {}
        pt = prev_data.get("total_usd")
        prev_ts = prev_data.get("timestamp")
        if pt and prev_ts:
            try:
                prev_dt = datetime.fromisoformat(prev_ts)
                if prev_dt.tzinfo is None:
                    prev_dt = prev_dt.replace(tzinfo=UTC)
                age_h = (datetime.now(UTC) - prev_dt).total_seconds() / 3600
                if age_h <= 26:
                    prev_total = float(pt)
            except Exception:
                pass

    delta: float | None = None
    delta_pct: float | None = None
    if prev_total and prev_total > 0:
        delta = sc.total_usd - prev_total
        delta_pct = delta / prev_total

    signal = "neutral"
    detail = (
        f"Total ${sc.total_usd / 1e9:.2f}B "
        f"(USDT ${sc.tether_usd / 1e9:.2f}B · USDC ${sc.usdc_usd / 1e9:.2f}B)"
    )
    if delta is not None:
        abs_d = abs(delta)
        if delta >= MINT_LARGE_USD:
            signal = "mint_large"
            detail += f" | +${abs_d / 1e9:.2f}B minted (large inflow)"
        elif delta >= MINT_MOD_USD:
            signal = "mint_moderate"
            detail += f" | +${abs_d / 1e6:.0f}M minted"
        elif delta <= -MINT_LARGE_USD:
            signal = "burn_large"
            detail += f" | -${abs_d / 1e9:.2f}B burned (large outflow)"
        elif delta <= -MINT_MOD_USD:
            signal = "burn_moderate"
            detail += f" | -${abs_d / 1e6:.0f}M burned"

    return StablecoinIssuance(
        timestamp=datetime.now(UTC).isoformat(),
        total_usd=round(sc.total_usd, 0),
        usdt_usd=round(sc.tether_usd, 0),
        usdc_usd=round(sc.usdc_usd, 0),
        delta_24h_usd=round(delta, 0) if delta is not None else None,
        delta_24h_pct=round(delta_pct, 6) if delta_pct is not None else None,
        signal=signal,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Feed 2: Economic Calendar
# ---------------------------------------------------------------------------


def _parse_ff_date(date_str: str, time_str: str) -> datetime | None:
    """Parse ForexFactory 'Apr 04, 2025' / '8:30am' into a datetime."""
    try:
        dt = datetime.strptime(date_str.strip(), "%b %d, %Y")
    except ValueError:
        return None
    t = time_str.strip().lower()
    if t and t not in ("all day", "tentative", ""):
        try:
            # Normalise "8:30am" → "8:30 AM"
            t = t.replace("am", " AM").replace("pm", " PM")
            if ":" not in t:
                t = t.replace(" AM", ":00 AM").replace(" PM", ":00 PM")
            parsed = datetime.strptime(t.strip(), "%I:%M %p")
            dt = dt.replace(hour=parsed.hour, minute=parsed.minute)
        except ValueError:
            pass
    return dt


def _fetch_econ_calendar() -> EconCalendar:
    now_date = datetime.now(UTC).date()
    events: list[EconEvent] = []
    seen: set[tuple[str, str]] = set()

    for url in [FF_THISWEEK, FF_NEXTWEEK]:
        try:
            data = _http_get_json(url)
            if not isinstance(data, list):
                continue
            for item in data:
                if item.get("country") != "USD":
                    continue
                impact = item.get("impact", "")
                if impact not in ("High", "Medium"):
                    continue
                title = item.get("title", "").strip()
                dt = _parse_ff_date(item.get("date", ""), item.get("time", ""))
                if dt is None:
                    continue
                days_until = (dt.date() - now_date).days
                if not (-1 <= days_until <= 14):
                    continue
                key = (dt.strftime("%Y-%m-%d"), title)
                if key in seen:
                    continue
                seen.add(key)
                events.append(
                    EconEvent(
                        date=dt.strftime("%Y-%m-%d"),
                        time=dt.strftime("%H:%M") if dt.hour or dt.minute else "TBD",
                        title=title,
                        country="USD",
                        impact=impact,
                        days_until=days_until,
                    )
                )
        except Exception as e:
            log.debug("ForexFactory %s failed: %s", url, e)

    # Merge hardcoded FOMC dates (ForexFactory may lag or be unavailable)
    next_fomc_days: int | None = None
    for fomc_date in sorted(FOMC_DATES):
        fomc_dt = datetime.strptime(fomc_date, "%Y-%m-%d").date()
        days = (fomc_dt - now_date).days
        if days < 0:
            continue
        if next_fomc_days is None:
            next_fomc_days = days
        key = (fomc_date, "FOMC Rate Decision")
        if key not in seen and days <= 14:
            seen.add(key)
            events.append(
                EconEvent(
                    date=fomc_date,
                    time="14:00",  # FOMC announcement typically 2 PM ET
                    title="FOMC Rate Decision",
                    country="USD",
                    impact="High",
                    days_until=days,
                )
            )
        break  # only need the next one

    events.sort(key=lambda e: (e.days_until, e.date, e.title))
    upcoming_high = [e for e in events if e.impact == "High" and 0 <= e.days_until <= 7]

    return EconCalendar(
        timestamp=datetime.now(UTC).isoformat(),
        events=events,
        upcoming_high=upcoming_high,
        next_fomc_days=next_fomc_days,
    )


# ---------------------------------------------------------------------------
# Feed 3: Political Signal Monitor
# ---------------------------------------------------------------------------


def _ns_strip(tag: str) -> str:
    """Remove XML namespace prefix from a tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_rss_items(xml_text: str, source: str) -> list[dict]:
    """Parse RSS 2.0 or Atom feed, return flat list of {title, description, link, pubdate}."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise SourceError(f"RSS parse error for {source}: {e}") from e

    items: list[dict] = []
    tag = _ns_strip(root.tag)

    if tag == "rss":
        for item in root.iter("item"):
            items.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "description": (item.findtext("description") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "pubdate": (item.findtext("pubDate") or "").strip(),
                }
            )
    elif tag == "feed":
        # Atom — strip namespace prefixes
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            link_el = entry.find("a:link", ns)
            items.append(
                {
                    "title": (entry.findtext("a:title", "", ns) or "").strip(),
                    "description": (entry.findtext("a:summary", "", ns) or "").strip(),
                    "link": link_el.get("href", "") if link_el is not None else "",
                    "pubdate": (entry.findtext("a:updated", "", ns) or "").strip(),
                }
            )

    return items


def _score_text(text: str) -> tuple[float, list[str]]:
    """Score text for market/political relevance, return (0–1, matched_keywords)."""
    lower = text.lower()
    matched: list[str] = []

    crypto_hits = sum(1 for kw in CRYPTO_KEYWORDS if kw in lower)
    market_hits = sum(1 for kw in MARKET_KEYWORDS if kw in lower)
    matched = [kw for kw in CRYPTO_KEYWORDS if kw in lower]
    matched += [kw for kw in MARKET_KEYWORDS if kw in lower]

    # Crypto keywords are higher signal
    score = min(1.0, crypto_hits * 0.35 + market_hits * 0.12)
    return round(score, 3), matched[:10]


def _fetch_political() -> PoliticalMonitor:
    now_ts = datetime.now(UTC).isoformat()
    signals: list[PoliticalSignal] = []

    for source, url in RSS_FEEDS.items():
        try:
            xml_text = _http_get_text(url)
            items = _parse_rss_items(xml_text, source)
            for item in items[:20]:  # cap per feed
                combined = f"{item['title']} {item['description']}"
                score, keywords = _score_text(combined)
                if score < 0.05:
                    continue  # below noise floor
                signals.append(
                    PoliticalSignal(
                        timestamp=now_ts,
                        source=source,
                        title=item["title"][:120],
                        published=item["pubdate"][:30],
                        relevance_score=score,
                        keywords=keywords,
                        url=item["link"][:200],
                    )
                )
        except Exception as e:
            log.debug("Political RSS %s failed: %s", source, e)

    signals.sort(key=lambda s: -s.relevance_score)
    high_rel = [s for s in signals if s.relevance_score >= 0.5]
    crypto_flag = any(
        kw in s.keywords for s in signals for kw in CRYPTO_KEYWORDS if s.relevance_score >= 0.3
    )

    return PoliticalMonitor(
        timestamp=now_ts,
        signals=signals[:30],  # keep top 30
        high_relevance_count=len(high_rel),
        crypto_flag=crypto_flag,
    )


# ---------------------------------------------------------------------------
# Feed 4: Liquidation Level Estimator
# ---------------------------------------------------------------------------


def _estimate_liq_band(coin: str, mark: float, oi_coins: float, funding: float) -> LiquidationBand:
    """Estimate long/short liquidation zones from funding rate magnitude.

    Higher absolute funding → more leveraged positioning → tighter liquidation zone.
    """
    oi_usd = oi_coins * mark
    abs_rate = abs(funding)

    if abs_rate >= 0.001:  # >0.1%/8h — very crowded, high leverage
        liq_dist = 0.06
    elif abs_rate >= 0.0003:  # 0.03–0.1%/8h — crowded
        liq_dist = 0.10
    elif abs_rate >= 0.0001:  # 0.01–0.03%/8h — moderate
        liq_dist = 0.15
    else:  # low funding, low leverage
        liq_dist = 0.22

    long_liq = mark * (1 - liq_dist)
    short_liq = mark * (1 + liq_dist)
    long_prox = (mark - long_liq) / mark  # > 0 when price above liq zone
    short_prox = (short_liq - mark) / mark  # > 0 when price below liq zone

    flag = "neutral"
    detail = f"OI ${oi_usd / 1e6:.0f}M | funding {funding * 100:+.4f}%/8h"

    if funding > 0.0001:  # longs dominant
        if long_prox <= CASCADE_PROXIMITY:
            flag = "cascade_risk_long"
            detail += f" | ⚠ LONG LIQ ~${long_liq:,.0f} ({long_prox:.1%} away)"
        elif long_prox <= MONITOR_PROXIMITY:
            flag = "monitor_long"
            detail += f" | Long liq est. ~${long_liq:,.0f} ({long_prox:.1%})"
    elif funding < -0.0001:  # shorts dominant
        if short_prox <= CASCADE_PROXIMITY:
            flag = "cascade_risk_short"
            detail += f" | ⚠ SHORT LIQ ~${short_liq:,.0f} ({short_prox:.1%} away)"
        elif short_prox <= MONITOR_PROXIMITY:
            flag = "monitor_short"
            detail += f" | Short liq est. ~${short_liq:,.0f} ({short_prox:.1%})"

    return LiquidationBand(
        coin=coin,
        mark_price=round(mark, 4),
        open_interest_usd=round(oi_usd, 0),
        long_liq_estimate=round(long_liq, 4),
        short_liq_estimate=round(short_liq, 4),
        funding_rate_8h=round(funding, 8),
        long_proximity_pct=round(long_prox, 4),
        short_proximity_pct=round(short_prox, 4),
        flag=flag,
        detail=detail,
    )


def _fetch_liquidation() -> LiquidationEstimator:
    ctxs = HyperliquidClient().meta_and_asset_ctxs()
    relevant = [c for c in ctxs if c.coin in TRACKED_COINS and c.mark_px > 0]

    bands: list[LiquidationBand] = []
    for ctx in relevant:
        try:
            band = _estimate_liq_band(ctx.coin, ctx.mark_px, ctx.open_interest, ctx.funding_rate)
            bands.append(band)
        except Exception as e:
            log.debug("liq estimate failed for %s: %s", ctx.coin, e)

    bands.sort(key=lambda b: b.open_interest_usd, reverse=True)
    alerts = [b.coin for b in bands if "cascade_risk" in b.flag]

    return LiquidationEstimator(
        timestamp=datetime.now(UTC).isoformat(),
        bands=bands,
        alerts=alerts,
    )


# ---------------------------------------------------------------------------
# Feed 5: Order Flow Proxy (Funding Rate Velocity)
# ---------------------------------------------------------------------------


def _fetch_order_flow(current_ctxs: list | None = None) -> OrderFlowProxy:
    hl = HyperliquidClient()

    # Current rates snapshot (reuse if provided to avoid double call)
    if current_ctxs is None:
        current_ctxs = hl.meta_and_asset_ctxs()
    current_rates = {c.coin: c.funding_rate for c in current_ctxs if c.coin in TRACKED_COINS}

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - VELOCITY_LOOKBACK_MS

    velocities: list[FundingVelocity] = []
    for coin in TRACKED_COINS:
        try:
            history = hl.funding_history(coin, start_ms)
            if len(history) < 2:
                continue
            rates = [float(h.get("fundingRate", 0)) for h in history if "fundingRate" in h]
            if len(rates) < 2:
                continue

            # Velocity: change over the lookback window, normalised to per-hour
            elapsed_h = VELOCITY_LOOKBACK_MS / (1000 * 3600)  # 6.0
            velocity = (rates[-1] - rates[0]) / elapsed_h

            curr = current_rates.get(coin, rates[-1])
            abs_rate = abs(curr)
            abs_vel = abs(velocity)

            if abs_rate >= 0.001:
                direction = "accelerating_long" if curr > 0 else "accelerating_short"
                signal = "extreme_positioning"
            elif abs_vel >= 0.00005 and abs_rate >= 0.0003:
                direction = "accelerating_long" if velocity > 0 else "accelerating_short"
                signal = "crowding"
            elif abs_vel >= 0.00002 and abs_rate < 0.0001:
                direction = "decelerating"
                signal = "normalizing"
            else:
                direction = "stable"
                signal = "neutral"

            velocities.append(
                FundingVelocity(
                    coin=coin,
                    current_rate_8h=round(curr, 8),
                    velocity=round(velocity, 10),
                    direction=direction,
                    signal=signal,
                )
            )
        except Exception as e:
            log.debug("funding velocity failed for %s: %s", coin, e)

    crowding_alerts = [v.coin for v in velocities if v.signal == "extreme_positioning"]

    return OrderFlowProxy(
        timestamp=datetime.now(UTC).isoformat(),
        velocities=velocities,
        crowding_alerts=crowding_alerts,
    )


# ---------------------------------------------------------------------------
# Collection orchestrator
# ---------------------------------------------------------------------------


class MarketIntelligence:
    """Orchestrates all five market intelligence feeds with parallel fetching."""

    def collect(self) -> MarketIntelSnapshot:
        """Fetch all feeds in parallel threads, return snapshot."""
        prev = _load_raw_snapshot()
        now_ts = datetime.now(UTC).isoformat()

        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        lock = threading.Lock()

        # Fetch Hyperliquid assets once (reused by liquidation + order_flow)
        hl_ctxs: list | None = None
        try:
            hl_ctxs = HyperliquidClient().meta_and_asset_ctxs()
        except Exception as e:
            log.warning("Hyperliquid asset fetch failed: %s", e)

        def _previous_feed(name: str) -> Any | None:
            if not isinstance(prev, dict):
                return None
            data = prev.get(name)
            return data if data else None

        def run(name: str, fn, *, fallback_to_previous: bool = False):
            try:
                result = fn()
                with lock:
                    results[name] = result
            except Exception as e:
                fallback = _previous_feed(name) if fallback_to_previous else None
                if fallback is not None:
                    log.warning("Feed %s failed; using previous snapshot: %s", name, e)
                    with lock:
                        results[name] = fallback
                        errors[name] = f"{e}; using previous snapshot"
                    return
                log.warning("Feed %s failed: %s", name, e)
                with lock:
                    errors[name] = str(e)

        threads = [
            threading.Thread(target=run, args=("stablecoins", lambda: _fetch_stablecoins(prev))),
            threading.Thread(target=run, args=("econ_calendar", _fetch_econ_calendar)),
            threading.Thread(target=run, args=("political", _fetch_political)),
            threading.Thread(
                target=run,
                args=(
                    "liquidation",
                    lambda ctxs=hl_ctxs: (
                        _fetch_liquidation() if ctxs is None else _fetch_liquidation_from_ctxs(ctxs)
                    ),
                ),
                kwargs={"fallback_to_previous": True},
            ),
            threading.Thread(
                target=run,
                args=("order_flow", lambda ctxs=hl_ctxs: _fetch_order_flow(ctxs)),
                kwargs={"fallback_to_previous": True},
            ),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        if errors:
            log.warning("Market intel partial failures: %s", list(errors))

        return MarketIntelSnapshot(
            timestamp=now_ts,
            stablecoins=results.get("stablecoins"),
            econ_calendar=results.get("econ_calendar"),
            political=results.get("political"),
            liquidation=results.get("liquidation"),
            order_flow=results.get("order_flow"),
            errors=errors,
        )

    def save(self, snap: MarketIntelSnapshot) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_FILE.write_text(json.dumps(_snap_to_dict(snap), indent=2))
        return SNAPSHOT_FILE


def _fetch_liquidation_from_ctxs(ctxs: list) -> LiquidationEstimator:
    """Like _fetch_liquidation but using already-fetched asset contexts."""
    relevant = [c for c in ctxs if c.coin in TRACKED_COINS and c.mark_px > 0]
    bands: list[LiquidationBand] = []
    for ctx in relevant:
        try:
            bands.append(
                _estimate_liq_band(ctx.coin, ctx.mark_px, ctx.open_interest, ctx.funding_rate)
            )
        except Exception as e:
            log.debug("liq estimate failed for %s: %s", ctx.coin, e)

    bands.sort(key=lambda b: b.open_interest_usd, reverse=True)
    return LiquidationEstimator(
        timestamp=datetime.now(UTC).isoformat(),
        bands=bands,
        alerts=[b.coin for b in bands if "cascade_risk" in b.flag],
    )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _snap_to_dict(snap: MarketIntelSnapshot) -> dict:
    """Convert snapshot to JSON-serialisable dict."""

    def _conv(obj):
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, list):
            return [_conv(i) for i in obj]
        if isinstance(obj, dict):
            return {k: _conv(v) for k, v in obj.items()}
        # dataclass
        return {k: _conv(v) for k, v in asdict(obj).items()}

    return _conv(asdict(snap))


def _load_raw_snapshot() -> dict | None:
    if not SNAPSHOT_FILE.exists():
        return None
    try:
        return json.loads(SNAPSHOT_FILE.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API consumed by signal_enhancer and daily_brief
# ---------------------------------------------------------------------------


def load_latest_snapshot() -> dict | None:
    """Return a flat fact dict from the latest snapshot for signal enhancer use.

    Returns None if snapshot is missing or stale (>45 min).
    """
    raw = _load_raw_snapshot()
    if not raw:
        return None

    ts = raw.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            age_min = (datetime.now(UTC) - dt).total_seconds() / 60
            if age_min > 45:
                log.debug("market_intel snapshot stale (%.0f min old)", age_min)
                return None
        except Exception:
            pass

    result: dict[str, Any] = {}

    # Stablecoin signal
    stable = raw.get("stablecoins") or {}
    result["stablecoin_signal"] = stable.get("signal")
    result["stablecoin_total_usd"] = stable.get("total_usd")
    result["stablecoin_delta_24h"] = stable.get("delta_24h_usd")

    # Economic calendar: next High-impact event hours away
    cal = raw.get("econ_calendar") or {}
    result["next_fomc_days"] = cal.get("next_fomc_days")
    upcoming = cal.get("upcoming_high") or []
    pre_event_hours: float | None = None
    next_event_title: str | None = None
    now_h = datetime.now().hour
    for ev in upcoming:
        days = ev.get("days_until", 999)
        if days < 0:
            continue
        t_str = ev.get("time", "")
        try:
            h, m = map(int, t_str.split(":"))
            hours = days * 24 + h - now_h
        except Exception:
            hours = float(days * 24)
        hours = max(0.0, hours)
        if pre_event_hours is None or hours < pre_event_hours:
            pre_event_hours = hours
            next_event_title = ev.get("title", "High-impact event")
    result["pre_event_hours"] = pre_event_hours
    result["next_event_title"] = next_event_title

    # Political
    pol = raw.get("political") or {}
    result["political_high_count"] = pol.get("high_relevance_count", 0)
    result["political_crypto_flag"] = pol.get("crypto_flag", False)

    # Liquidation cascade
    liq = raw.get("liquidation") or {}
    cascade_coins: list[str] = []
    liq_dirs: dict[str, str] = {}
    for band in liq.get("bands") or []:
        flag = band.get("flag", "")
        coin = band.get("coin", "")
        if "cascade_risk_long" in flag:
            cascade_coins.append(coin)
            liq_dirs[coin] = "long"
        elif "cascade_risk_short" in flag:
            cascade_coins.append(coin)
            liq_dirs[coin] = "short"
    result["liq_cascade_coins"] = cascade_coins
    result["liq_directions"] = liq_dirs

    # Order flow velocity
    of = raw.get("order_flow") or {}
    of_sigs: dict[str, str] = {}
    for v in of.get("velocities") or []:
        coin = v.get("coin", "")
        if coin:
            of_sigs[coin] = v.get("signal", "neutral")
    result["order_flow_signals"] = of_sigs
    result["order_flow_crowding"] = of.get("crowding_alerts") or []

    return result


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------


def collect() -> MarketIntelSnapshot:
    """Collect all feeds, save snapshot, return result."""
    mi = MarketIntelligence()
    snap = mi.collect()
    path = mi.save(snap)
    log.info("market_intel saved → %s", path)
    return snap


if __name__ == "__main__":
    import argparse

    from lib.core.routine_pause import abort_if_paused

    abort_if_paused("market-intel")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Market intelligence collector")
    parser.add_argument("--test", action="store_true", help="Test each feed independently")
    args = parser.parse_args()

    if args.test:
        print("\n=== Feed 1: Stablecoins ===")
        try:
            r = _fetch_stablecoins(None)
            print(f"  signal={r.signal}  total=${r.total_usd / 1e9:.2f}B")
            print(f"  {r.detail}")
        except Exception as e:
            print(f"  FAILED: {e}")

        print("\n=== Feed 2: Economic Calendar ===")
        try:
            r = _fetch_econ_calendar()
            print(f"  {len(r.events)} events, {len(r.upcoming_high)} high-impact (7d)")
            print(f"  next FOMC in {r.next_fomc_days}d")
            for ev in r.upcoming_high[:3]:
                print(f"  [{ev.days_until}d] {ev.impact} — {ev.title} ({ev.date})")
        except Exception as e:
            print(f"  FAILED: {e}")

        print("\n=== Feed 3: Political Signals ===")
        try:
            r = _fetch_political()
            print(
                f"  {len(r.signals)} signals, {r.high_relevance_count} high-relevance, crypto_flag={r.crypto_flag}"
            )
            for s in r.signals[:3]:
                print(f"  [{s.source}] score={s.relevance_score:.2f} — {s.title[:60]}")
        except Exception as e:
            print(f"  FAILED: {e}")

        print("\n=== Feed 4: Liquidation Estimator ===")
        try:
            r = _fetch_liquidation()
            print(f"  {len(r.bands)} bands tracked, alerts: {r.alerts or 'none'}")
            for b in r.bands[:4]:
                print(f"  {b.coin}: ${b.mark_price:,.2f}  {b.flag}  {b.detail}")
        except Exception as e:
            print(f"  FAILED: {e}")

        print("\n=== Feed 5: Order Flow (Funding Velocity) ===")
        try:
            r = _fetch_order_flow()
            print(f"  {len(r.velocities)} coins tracked, crowding: {r.crowding_alerts or 'none'}")
            for v in r.velocities:
                print(
                    f"  {v.coin}: rate={v.current_rate_8h * 100:+.4f}%/8h  vel={v.velocity:.2e}/h  {v.signal}"
                )
        except Exception as e:
            print(f"  FAILED: {e}")

        sys.exit(0)

    # Normal run: collect + save
    snap = collect()
    feed_status = {
        "stablecoins": "ok" if snap.stablecoins else "failed",
        "econ_calendar": "ok" if snap.econ_calendar else "failed",
        "political": "ok" if snap.political else "failed",
        "liquidation": "ok" if snap.liquidation else "failed",
        "order_flow": "ok" if snap.order_flow else "failed",
    }
    for feed, status in feed_status.items():
        print(f"  {feed}: {status}")
    if snap.errors:
        print(f"  errors: {snap.errors}")
