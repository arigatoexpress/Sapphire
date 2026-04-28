"""Per-source adapters for the Sapphire Signal Correlation Engine.

Every adapter implements :class:`SignalSource` and exposes
:meth:`latest_for(symbol, timeframe) -> SourceSignal | None`.

Read-only by design
-------------------

Adapters read from disk snapshots under ``data/`` — no live network
calls, no subprocesses. This keeps tests fast and the engine itself
deterministic given a frozen on-disk state.

If the underlying snapshot file is missing or unreadable, the adapter
returns ``None``. Adapters never raise from ``latest_for``; the
:func:`engine.correlate_universe` orchestrator catches anything that
does as a defence-in-depth fallback.

Adapters covered
----------------

- :class:`TradingViewSource`         — TV webhook signals (``data/signals/<date>.jsonl``)
- :class:`TelegramIntelSource`       — Telegram channel intel (~/.sapphire/telegram_intel_signals.jsonl)
- :class:`HyperliquidSource`         — Hyperliquid public feed (~/.sapphire/hyperliquid_signals.jsonl)
- :class:`ThreatIntelSource`         — CVE threat intel digest (data/threat_intel/latest_*.md sentiment-derived)
- :class:`ConvergenceWatchlistSource` — convergence-watchlist (world_knowledge/research/.../convergence_watchlist.json)
- :class:`SovereignThesisSource`     — sovereign-thesis snapshots (data/sovereign-thesis/latest.json)
- :class:`KronosForecastSource`      — Kronos predictions (data/intelligence/<date>/predictions.json)
- :class:`TAScannerSource`           — TA scanner predictions (data/trading_predictions.jsonl)
- :class:`CrossAssetRegimeSource`    — cross-asset regime labels (data/cross_asset/<date>/regimes.jsonl)

Each adapter normalizes its source's wire format into a
:class:`SourceSignal` dataclass with a stable schema:

::

    SourceSignal(
        symbol="BTC",
        timeframe="1h",
        direction="bull" | "bear" | "neutral",
        confidence=0.0..1.0,
        age_seconds=0.0+,
        timestamp_iso="2026-04-28T...",
        raw={...},  # opaque, for audit only
    )
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSignal:
    """A single source's view of one ``(symbol, timeframe)``."""

    source: str
    symbol: str
    timeframe: str
    direction: str  # "bull" | "bear" | "neutral"
    confidence: float
    age_seconds: float
    timestamp_iso: str
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SignalSource(Protocol):
    """Adapter Protocol every source implementation satisfies."""

    name: str

    def latest_for(
        self, symbol: str, timeframe: str
    ) -> SourceSignal | None:  # pragma: no cover - protocol
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SYMBOL_ALIAS = {
    "BTC-USD": "BTC",
    "ETH-USD": "ETH",
    "SOL-USD": "SOL",
    "BTCUSD": "BTC",
    "ETHUSD": "ETH",
    "SOLUSD": "SOL",
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
}


def _canonical_symbol(value: Any) -> str:
    s = str(value or "").strip().upper()
    return _SYMBOL_ALIAS.get(s, s)


def _parse_iso(ts: Any) -> datetime | None:
    if not ts:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=UTC)
        s = str(ts)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, OSError):
        return None


def _age_seconds(ts: datetime | None, *, now: datetime) -> float:
    if ts is None:
        return float("inf")
    delta = now - ts
    return max(0.0, delta.total_seconds())


def _coerce_confidence(value: Any, *, default: float = 0.5) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------------
# Base adapter — common JSONL tail logic
# ---------------------------------------------------------------------------


def _iter_jsonl(path: Path, *, limit: int = 1000) -> Iterable[dict[str, Any]]:
    """Yield up to ``limit`` parsed JSON lines, newest-first."""
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


# ---------------------------------------------------------------------------
# 1. TradingView webhook signals
# ---------------------------------------------------------------------------


@dataclass
class TradingViewSource:
    name: str = "tradingview"
    base_dir: Path = field(default_factory=lambda: REPO_ROOT / "data" / "signals")

    def _candidate_files(self, max_days_back: int = 14) -> list[Path]:
        if not self.base_dir.exists():
            return []
        files = sorted(p for p in self.base_dir.glob("*.jsonl") if p.is_file())
        return list(reversed(files[-max_days_back:]))

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = _canonical_symbol(symbol)
        now = datetime.now(UTC)
        for path in self._candidate_files():
            for entry in _iter_jsonl(path, limit=2000):
                if _canonical_symbol(entry.get("symbol")) != target:
                    continue
                ts = _parse_iso(entry.get("timestamp"))
                age = _age_seconds(ts, now=now)
                direction = (entry.get("direction") or entry.get("action") or "").strip().lower()
                if direction in {"buy", "long"}:
                    direction = "bull"
                elif direction in {"sell", "short"}:
                    direction = "bear"
                elif direction not in {"bull", "bear", "neutral"}:
                    direction = "neutral"
                return SourceSignal(
                    source=self.name,
                    symbol=target,
                    timeframe=timeframe,
                    direction=direction,
                    confidence=_coerce_confidence(entry.get("confidence")),
                    age_seconds=age,
                    timestamp_iso=ts.isoformat() if ts else "",
                    raw={"path": str(path), "score": entry.get("score")},
                )
        return None


# ---------------------------------------------------------------------------
# 2. Telegram channel intel
# ---------------------------------------------------------------------------


@dataclass
class TelegramIntelSource:
    name: str = "telegram_intel"
    path: Path = field(
        default_factory=lambda: Path.home() / ".sapphire" / "telegram_intel_signals.jsonl"
    )

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = _canonical_symbol(symbol)
        now = datetime.now(UTC)
        for entry in _iter_jsonl(self.path, limit=2000):
            symbols = entry.get("symbols") or [entry.get("symbol")]
            if not isinstance(symbols, list):
                symbols = [symbols]
            if target not in {_canonical_symbol(s) for s in symbols if s}:
                continue
            ts = _parse_iso(entry.get("timestamp") or entry.get("ts"))
            label = (entry.get("label") or entry.get("sentiment") or "").strip().lower()
            if label in {"bull", "bullish", "long", "positive"}:
                direction = "bull"
            elif label in {"bear", "bearish", "short", "negative"}:
                direction = "bear"
            else:
                direction = "neutral"
            return SourceSignal(
                source=self.name,
                symbol=target,
                timeframe=timeframe,
                direction=direction,
                confidence=_coerce_confidence(
                    entry.get("confidence") or entry.get("score"), default=0.4
                ),
                age_seconds=_age_seconds(ts, now=now),
                timestamp_iso=ts.isoformat() if ts else "",
                raw={"channel": entry.get("channel"), "id": entry.get("id")},
            )
        return None


# ---------------------------------------------------------------------------
# 3. Hyperliquid public feed
# ---------------------------------------------------------------------------


@dataclass
class HyperliquidSource:
    name: str = "hyperliquid_public_feed"
    path: Path = field(
        default_factory=lambda: Path.home() / ".sapphire" / "hyperliquid_signals.jsonl"
    )

    _DIR_BY_KIND = {
        "trade_imbalance_buy": "bull",
        "trade_imbalance_sell": "bear",
        "depth_drop_bid": "bear",
        "depth_drop_ask": "bull",
        "spoofing_bid": "bear",
        "spoofing_ask": "bull",
        "imbalance_persistent_bid": "bull",
        "imbalance_persistent_ask": "bear",
    }

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = _canonical_symbol(symbol)
        now = datetime.now(UTC)
        for entry in _iter_jsonl(self.path, limit=2000):
            if _canonical_symbol(entry.get("symbol") or entry.get("coin")) != target:
                continue
            kind = (entry.get("kind") or entry.get("event") or "").strip().lower()
            direction = self._DIR_BY_KIND.get(kind)
            if direction is None:
                # Fall back to side / direction fields.
                side = (entry.get("side") or entry.get("direction") or "").strip().lower()
                if side in {"buy", "bid", "bull"}:
                    direction = "bull"
                elif side in {"sell", "ask", "bear"}:
                    direction = "bear"
                else:
                    direction = "neutral"
            ts = _parse_iso(entry.get("timestamp") or entry.get("ts"))
            return SourceSignal(
                source=self.name,
                symbol=target,
                timeframe=timeframe,
                direction=direction,
                confidence=_coerce_confidence(
                    entry.get("confidence") or entry.get("strength"), default=0.5
                ),
                age_seconds=_age_seconds(ts, now=now),
                timestamp_iso=ts.isoformat() if ts else "",
                raw={"kind": kind},
            )
        return None


# ---------------------------------------------------------------------------
# 4. Threat-intel
# ---------------------------------------------------------------------------


@dataclass
class ThreatIntelSource:
    """Threat intel snapshots emit a defensive (bear) bias on tickers
    named in active CVE briefs.

    The shape we consume is a `data/threat_intel/sapphire_signals.json`
    file (optional) emitted by the threat refresh routine. Falls back
    to None when not present — threat intel is a *modulator*, not a
    primary direction source, so missing data is normal.
    """

    name: str = "threat_intel"
    path: Path = field(
        default_factory=lambda: REPO_ROOT / "data" / "threat_intel" / "sapphire_signals.json"
    )

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        target = _canonical_symbol(symbol)
        signals = data.get("signals") or {}
        entry = signals.get(target) if isinstance(signals, dict) else None
        if not isinstance(entry, dict):
            return None
        ts = _parse_iso(entry.get("timestamp") or data.get("generated_at"))
        sentiment = (entry.get("sentiment") or "").strip().lower()
        if sentiment == "bearish":
            direction = "bear"
        elif sentiment == "bullish":
            direction = "bull"
        else:
            direction = "neutral"
        return SourceSignal(
            source=self.name,
            symbol=target,
            timeframe=timeframe,
            direction=direction,
            confidence=_coerce_confidence(entry.get("confidence"), default=0.3),
            age_seconds=_age_seconds(ts, now=datetime.now(UTC)),
            timestamp_iso=ts.isoformat() if ts else "",
            raw={"cves": entry.get("cves", [])},
        )


# ---------------------------------------------------------------------------
# 5. Convergence watchlist
# ---------------------------------------------------------------------------


@dataclass
class ConvergenceWatchlistSource:
    """Tickers in the convergence watchlist contribute a bullish thesis
    bias scaled by tier (conservative_core / growth_satellite /
    speculative_moonshots)."""

    name: str = "convergence_watchlist"
    path: Path = field(
        default_factory=lambda: REPO_ROOT
        / "world_knowledge"
        / "research"
        / "kimi-p1-sun-drone"
        / "convergence_watchlist.json"
    )

    _TIER_CONF = {
        "conservative_core": 0.85,
        "growth_satellite": 0.65,
        "speculative_moonshots": 0.45,
    }

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        target = _canonical_symbol(symbol)
        tiers = data.get("tiers") or {}
        if not isinstance(tiers, dict):
            return None
        for tier_name, tier in tiers.items():
            if not isinstance(tier, dict):
                continue
            for pos in tier.get("positions") or []:
                ticker = _canonical_symbol(pos.get("ticker"))
                if ticker == target:
                    generated = _parse_iso(data.get("generated"))
                    return SourceSignal(
                        source=self.name,
                        symbol=target,
                        timeframe=timeframe,
                        direction="bull",
                        confidence=self._TIER_CONF.get(tier_name, 0.5),
                        age_seconds=_age_seconds(generated, now=datetime.now(UTC)),
                        timestamp_iso=generated.isoformat() if generated else "",
                        raw={"tier": tier_name, "thesis": pos.get("thesis")},
                    )
        return None


# ---------------------------------------------------------------------------
# 6. Sovereign-thesis snapshot
# ---------------------------------------------------------------------------


@dataclass
class SovereignThesisSource:
    """Snapshot of the sovereign-thesis matrix. We consume a
    pre-computed `data/sovereign-thesis/latest.json` if available."""

    name: str = "sovereign_thesis"
    path: Path = field(
        default_factory=lambda: REPO_ROOT / "data" / "sovereign-thesis" / "latest.json"
    )

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        assets = data.get("assets") or {}
        target = _canonical_symbol(symbol)
        entry = assets.get(target) if isinstance(assets, dict) else None
        if not isinstance(entry, dict):
            return None
        score = entry.get("composite_score")
        try:
            sc = float(score)
        except (TypeError, ValueError):
            sc = 0.0
        if sc > 0.05:
            direction = "bull"
        elif sc < -0.05:
            direction = "bear"
        else:
            direction = "neutral"
        ts = _parse_iso(data.get("generated_at"))
        return SourceSignal(
            source=self.name,
            symbol=target,
            timeframe=timeframe,
            direction=direction,
            confidence=_coerce_confidence(abs(sc), default=0.3),
            age_seconds=_age_seconds(ts, now=datetime.now(UTC)),
            timestamp_iso=ts.isoformat() if ts else "",
            raw={"composite_score": sc, "fit": entry.get("fit")},
        )


# ---------------------------------------------------------------------------
# 7. Kronos forecast
# ---------------------------------------------------------------------------


@dataclass
class KronosForecastSource:
    name: str = "kronos_forecast"
    base_dir: Path = field(default_factory=lambda: REPO_ROOT / "data" / "intelligence")

    def _latest_predictions(self) -> tuple[Path | None, dict[str, Any]]:
        if not self.base_dir.exists():
            return None, {}
        candidates = sorted(
            p for p in self.base_dir.iterdir() if p.is_dir() and (p / "predictions.json").exists()
        )
        if not candidates:
            return None, {}
        path = candidates[-1] / "predictions.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return path, {}
        return path, data if isinstance(data, dict) else {}

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        path, data = self._latest_predictions()
        if not data:
            return None
        target = _canonical_symbol(symbol)
        preds = data.get("predictions") or {}
        # Match against canonical symbol.
        match: dict[str, Any] | None = None
        for k, v in preds.items():
            if _canonical_symbol(k) == target and isinstance(v, dict):
                match = v
                break
        if match is None:
            return None
        ts = _parse_iso(data.get("generated_at"))
        direction_raw = (match.get("direction") or "").strip().lower()
        if direction_raw in {"bullish", "bull", "long", "up"}:
            direction = "bull"
        elif direction_raw in {"bearish", "bear", "short", "down"}:
            direction = "bear"
        else:
            direction = "neutral"
        return SourceSignal(
            source=self.name,
            symbol=target,
            timeframe=timeframe,
            direction=direction,
            confidence=_coerce_confidence(match.get("confidence"), default=0.5),
            age_seconds=_age_seconds(ts, now=datetime.now(UTC)),
            timestamp_iso=ts.isoformat() if ts else "",
            raw={
                "interval": match.get("interval"),
                "predict_bars": match.get("predict_bars"),
                "source_file": str(path) if path else None,
            },
        )


# ---------------------------------------------------------------------------
# 8. TA scanner
# ---------------------------------------------------------------------------


@dataclass
class TAScannerSource:
    name: str = "ta_scanner"
    path: Path = field(
        default_factory=lambda: REPO_ROOT / "data" / "trading_predictions.jsonl"
    )

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = _canonical_symbol(symbol)
        now = datetime.now(UTC)
        for entry in _iter_jsonl(self.path, limit=2000):
            if _canonical_symbol(entry.get("symbol")) != target:
                continue
            ts = _parse_iso(entry.get("timestamp"))
            direction = (entry.get("direction") or "").strip().lower()
            if direction in {"bullish", "bull", "long", "buy"}:
                direction = "bull"
            elif direction in {"bearish", "bear", "short", "sell"}:
                direction = "bear"
            else:
                direction = "neutral"
            return SourceSignal(
                source=self.name,
                symbol=target,
                timeframe=timeframe,
                direction=direction,
                confidence=_coerce_confidence(entry.get("confidence")),
                age_seconds=_age_seconds(ts, now=now),
                timestamp_iso=ts.isoformat() if ts else "",
                raw={"timeframe_source": entry.get("timeframe")},
            )
        return None


# ---------------------------------------------------------------------------
# 9. Cross-asset regime
# ---------------------------------------------------------------------------


_REGIME_TO_SIGNAL: dict[str, tuple[str, float]] = {
    "crisis_correlation_spike": ("bear", 0.90),
    "risk_off_flight_to_dollar": ("bear", 0.75),
    "risk_on_correlated": ("bull", 0.70),
    "risk_on_decorrelated": ("neutral", 0.45),
    "regime_uncertain": ("neutral", 0.15),
}


@dataclass
class CrossAssetRegimeSource:
    name: str = "cross_asset_regime"
    base_dir: Path = field(default_factory=lambda: REPO_ROOT / "data" / "cross_asset")

    def _candidate_files(self, max_days_back: int = 30) -> list[Path]:
        if not self.base_dir.exists():
            return []
        files = sorted(self.base_dir.glob("*/regimes.jsonl"))
        return list(reversed(files[-max_days_back:]))

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = _canonical_symbol(symbol)
        now = datetime.now(UTC)
        for path in self._candidate_files():
            for entry in _iter_jsonl(path, limit=500):
                label = str(entry.get("label") or entry.get("regime_label") or "").strip()
                if not label:
                    continue
                direction, default_confidence = _REGIME_TO_SIGNAL.get(label, ("neutral", 0.20))
                ts = _parse_iso(
                    entry.get("timestamp")
                    or entry.get("generated_at")
                    or entry.get("as_of")
                )
                return SourceSignal(
                    source=self.name,
                    symbol=target,
                    timeframe=timeframe,
                    direction=direction,
                    confidence=_coerce_confidence(entry.get("confidence"), default=default_confidence),
                    age_seconds=_age_seconds(ts, now=now),
                    timestamp_iso=ts.isoformat() if ts else "",
                    raw={
                        "label": label,
                        "source_file": str(path),
                        "metrics": entry.get("metrics") or entry.get("evidence"),
                    },
                )
        return None


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def available_sources() -> tuple[type, ...]:
    """All shipped adapter classes (for introspection / docs)."""
    return (
        TradingViewSource,
        TelegramIntelSource,
        HyperliquidSource,
        ThreatIntelSource,
        ConvergenceWatchlistSource,
        SovereignThesisSource,
        KronosForecastSource,
        TAScannerSource,
        CrossAssetRegimeSource,
    )


def build_default_sources() -> list[SignalSource]:
    """Construct one of each adapter at default paths."""
    return [
        TradingViewSource(),
        TelegramIntelSource(),
        HyperliquidSource(),
        ThreatIntelSource(),
        ConvergenceWatchlistSource(),
        SovereignThesisSource(),
        KronosForecastSource(),
        TAScannerSource(),
        CrossAssetRegimeSource(),
    ]


__all__ = [
    "ConvergenceWatchlistSource",
    "CrossAssetRegimeSource",
    "HyperliquidSource",
    "KronosForecastSource",
    "SignalSource",
    "SourceSignal",
    "SovereignThesisSource",
    "TAScannerSource",
    "TelegramIntelSource",
    "ThreatIntelSource",
    "TradingViewSource",
    "available_sources",
    "build_default_sources",
]
