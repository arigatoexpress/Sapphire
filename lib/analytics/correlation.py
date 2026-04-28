"""Multi-asset correlation engine.

Tracks 30-day rolling Pearson correlations across crypto, equities, DXY, gold,
and VIX. Flags decorrelation events (e.g., BTC↔SPY drops below 0.3) which
often precede regime shifts.

Data source: yfinance daily closes. Cached to `data/analytics/price_cache.parquet`
to avoid refetching; refreshed if older than 6h.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "analytics"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = DATA_DIR / "price_cache.parquet"
HISTORY_FILE = DATA_DIR / "correlation_history.jsonl"
CACHE_TTL_SECS = 6 * 3600
OPENBB_BASE = "http://127.0.0.1:6900/api/v1"

# Event bus — optional, degrades silently if unavailable
import sys as _sys

_EVT_PATH = Path(__file__).resolve().parents[2] / "lib" / "core"
if str(_EVT_PATH) not in _sys.path:
    _sys.path.insert(0, str(_EVT_PATH))
try:
    from event_bus import get_bus as _get_event_bus

    _EVENT_BUS = _get_event_bus(source="correlation")
except Exception:
    _EVENT_BUS = None

# Symbol universe — full watchlist across crypto, equities, commodities, macro
# Note: HYPE and PENGU are not available on yfinance; they are covered by watchdog.yaml
DEFAULT_SYMBOLS = {
    # Crypto
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "ZEC": "ZEC-USD",
    # Equities
    "SPY": "SPY",
    "QQQ": "QQQ",
    # Commodities
    "GLD": "GLD",
    "SLV": "SLV",
    "USO": "USO",
    "URA": "URA",
    "COPX": "COPX",
    # Macro
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "TNX": "^TNX",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CorrelationMatrix:
    timestamp: str
    window_days: int
    symbols: list[str]
    matrix: list[list[float]]  # symmetric NxN, rounded to 3dp
    sample_count: int


@dataclass
class DecorrelationEvent:
    pair: tuple[str, str]
    current: float
    baseline: float  # historical average
    severity: str  # "mild", "moderate", "severe"
    note: str


@dataclass
class CorrelationReport:
    timestamp: str
    matrix: CorrelationMatrix
    decorrelation_events: list[DecorrelationEvent] = field(default_factory=list)
    risk_on_matrix: CorrelationMatrix | None = None
    risk_off_matrix: CorrelationMatrix | None = None


# ---------------------------------------------------------------------------
# Price cache
# ---------------------------------------------------------------------------


def _load_cache(*, allow_stale: bool = False) -> pd.DataFrame | None:
    if not CACHE_FILE.exists():
        return None
    try:
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age > CACHE_TTL_SECS and not allow_stale:
            return None
        df = pd.read_parquet(CACHE_FILE)
        return df
    except Exception:
        return None


def _save_cache(df: pd.DataFrame) -> None:
    try:
        df.to_parquet(CACHE_FILE)
    except Exception:
        # Non-fatal — cache is an optimization
        pass


def _publish_refresh_warning(kind: str, **payload: object) -> None:
    payload = {"kind": kind, **payload}
    log.warning("correlation refresh warning: %s", json.dumps(payload, sort_keys=True, default=str))
    if _EVENT_BUS is not None:
        try:
            _EVENT_BUS.publish("correlation.refresh_warning", payload)
        except Exception as exc:
            log.debug("event bus warning publish failed: %s", exc)


def _normalize_close_series(data: pd.DataFrame | None, label: str) -> pd.Series | None:
    """Extract a usable close series from yfinance's shifting return shapes."""
    if data is None or data.empty:
        return None

    close: pd.Series | pd.DataFrame | None = None
    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            close = data["Close"]
        elif "Close" in data.columns.get_level_values(-1):
            close = data.xs("Close", axis=1, level=-1)
    elif "Close" in data.columns:
        close = data["Close"]

    if close is None:
        numeric = data.select_dtypes(include="number")
        if numeric.empty:
            return None
        close = numeric.iloc[:, 0]

    if isinstance(close, pd.DataFrame):
        if close.empty:
            return None
        close = close.iloc[:, 0]

    series = pd.to_numeric(close, errors="coerce").dropna()
    if series.empty:
        return None

    series.name = label
    return series


def _fetch_prices_openbb(symbols: dict[str, str], days: int = 180) -> pd.DataFrame:
    """Fallback historical fetcher via the local OpenBB service."""
    start = (datetime.now(UTC) - timedelta(days=days + 10)).strftime("%Y-%m-%d")
    frames: dict[str, pd.Series] = {}

    def _fetch_one(label: str, ticker: str) -> tuple[str, pd.Series | None]:
        if ticker.endswith("-USD"):
            path = "/crypto/price/historical"
            symbol = ticker.replace("-", "")
        else:
            path = "/equity/price/historical"
            symbol = ticker

        params = urllib.parse.urlencode(
            {"symbol": symbol, "provider": "yfinance", "start_date": start}
        )
        url = f"{OPENBB_BASE}{path}?{params}"
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                payload = json.loads(response.read())
        except Exception:
            return label, None

        rows = payload.get("results") or []
        if not rows:
            return label, None
        data = pd.DataFrame(rows)
        if "date" not in data.columns or "close" not in data.columns:
            return label, None
        return label, pd.Series(
            data["close"].astype(float).values,
            index=pd.to_datetime(data["date"]),
            name=label,
        )

    with ThreadPoolExecutor(max_workers=min(8, len(symbols) or 1)) as pool:
        futures = [pool.submit(_fetch_one, label, ticker) for label, ticker in symbols.items()]
        for future in as_completed(futures):
            label, series = future.result()
            if series is not None:
                frames[label] = series

    if not frames:
        raise RuntimeError("No price data could be fetched from OpenBB")

    df = pd.concat(frames.values(), axis=1)
    df.columns = list(frames.keys())
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.sort_index().ffill().dropna(how="all")


def _fetch_prices(symbols: dict[str, str], days: int = 180) -> pd.DataFrame:
    """Fetch daily adjusted closes for all symbols. Returns DF indexed by date."""
    cached = _load_cache()
    stale_cached = _load_cache(allow_stale=True)
    need_refresh = False
    if cached is None:
        need_refresh = True
    else:
        missing = set(symbols.keys()) - set(cached.columns)
        if missing:
            need_refresh = True

    if not need_refresh and cached is not None:
        return cached[list(symbols.keys())].copy()

    frames: dict[str, pd.Series] = {}
    failures: dict[str, str] = {}
    try:
        import yfinance as yf

        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    except Exception:
        yf = None

    if yf is not None:
        end = datetime.now(UTC)
        start = end - timedelta(days=days + 10)
        for label, ticker in symbols.items():
            try:
                data = yf.download(
                    ticker,
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=True,
                    threads=True,
                )
                series = _normalize_close_series(data, label)
                if series is None:
                    failures[label] = "empty_or_invalid_yfinance_frame"
                    continue
                frames[label] = series
            except Exception as exc:
                failures[label] = exc.__class__.__name__
                continue

    missing = {label: ticker for label, ticker in symbols.items() if label not in frames}
    if missing:
        try:
            openbb = _fetch_prices_openbb(missing, days=days)
            for label in missing:
                if label in openbb.columns:
                    frames[label] = (
                        pd.to_numeric(openbb[label], errors="coerce").dropna().rename(label)
                    )
            missing = {label: ticker for label, ticker in symbols.items() if label not in frames}
        except Exception as exc:
            _publish_refresh_warning(
                "openbb_fallback_failed",
                missing_symbols=sorted(missing),
                error=exc.__class__.__name__,
            )

    if missing and stale_cached is not None:
        stale_available = [label for label in missing if label in stale_cached.columns]
        for label in stale_available:
            frames[label] = (
                pd.to_numeric(stale_cached[label], errors="coerce").dropna().rename(label)
            )
        if stale_available:
            age_hours = (
                (time.time() - CACHE_FILE.stat().st_mtime) / 3600 if CACHE_FILE.exists() else None
            )
            _publish_refresh_warning(
                "using_stale_price_cache",
                stale_symbols=sorted(stale_available),
                unresolved_symbols=sorted(set(missing) - set(stale_available)),
                yfinance_failures=failures,
                cache_age_hours=round(age_hours, 2) if age_hours is not None else None,
            )
        missing = {label: ticker for label, ticker in symbols.items() if label not in frames}

    if not frames:
        raise RuntimeError("No price data could be fetched from yfinance, OpenBB, or stale cache")

    if missing:
        _publish_refresh_warning(
            "partial_price_refresh",
            missing_symbols=sorted(missing),
            available_symbols=sorted(frames),
            yfinance_failures=failures,
        )

    ordered = [label for label in symbols if label in frames]
    df = pd.concat([frames[label] for label in ordered], axis=1)
    df.columns = ordered
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index().ffill().dropna(how="all")

    # Do not replace a fuller last-known-good cache with a degraded partial
    # refresh. The next run can still recover missing symbols from the cache.
    if not missing or stale_cached is None:
        _save_cache(df)
    return df


# ---------------------------------------------------------------------------
# CorrelationEngine
# ---------------------------------------------------------------------------


class CorrelationEngine:
    """Computes rolling correlations and detects decorrelation events."""

    # Historical "normal" correlations — used as baselines for decorrelation
    BASELINES: dict[tuple[str, str], float] = {
        ("BTC", "ETH"): 0.85,
        ("BTC", "SOL"): 0.75,
        ("ETH", "SOL"): 0.80,
        ("BTC", "SPY"): 0.45,
        ("ETH", "SPY"): 0.45,
        ("SPY", "QQQ"): 0.95,
        ("BTC", "DXY"): -0.35,
        ("SPY", "DXY"): -0.40,
        ("BTC", "GLD"): 0.20,
        ("SPY", "VIX"): -0.80,
        ("BTC", "VIX"): -0.30,
    }

    def __init__(self, symbols: dict[str, str] | None = None):
        self.symbols = symbols or DEFAULT_SYMBOLS

    # ------------------------------------------------------------------

    def _log_returns(self, prices: pd.DataFrame) -> pd.DataFrame:
        return np.log(prices / prices.shift(1)).dropna(how="any")

    MIN_SAMPLES = 25

    def build_matrix(self, window_days: int = 30) -> CorrelationMatrix:
        prices = _fetch_prices(self.symbols, days=max(180, window_days + 30))
        rets = self._log_returns(prices)
        recent = rets.tail(window_days)
        if len(recent) < self.MIN_SAMPLES:
            log.warning(
                "correlation window has only %d samples (< MIN_SAMPLES=%d); "
                "results are statistically unreliable and emitted as None.",
                len(recent),
                self.MIN_SAMPLES,
            )
        corr = recent.corr(method="pearson").round(3)
        syms = list(corr.columns)
        raw = corr.values.tolist()
        # Preserve NaN as None — coercing to 0.0 masks degenerate data
        # (constant-variance asset, missing column) as "no correlation,"
        # which then triggers false decorrelation alerts downstream.
        matrix: list[list[float | None]] = []
        for row in raw:
            out_row: list[float | None] = []
            for x in row:
                if pd.isna(x):
                    out_row.append(None)
                else:
                    out_row.append(float(x))
            matrix.append(out_row)
        return CorrelationMatrix(
            timestamp=datetime.now(UTC).isoformat(),
            window_days=window_days,
            symbols=syms,
            matrix=matrix,
            sample_count=len(recent),
        )

    def detect_decorrelations(self, matrix: CorrelationMatrix) -> list[DecorrelationEvent]:
        """Flag pairs whose correlation has deviated meaningfully from baseline."""
        events: list[DecorrelationEvent] = []
        syms = matrix.symbols
        idx = {s: i for i, s in enumerate(syms)}
        for (a, b), baseline in self.BASELINES.items():
            if a not in idx or b not in idx:
                continue
            curr = matrix.matrix[idx[a]][idx[b]]
            # Skip degenerate cells: NaN→None means constant variance or
            # missing data — not a real decorrelation signal.
            if curr is None:
                log.debug("correlation pair %s↔%s is None, skipping", a, b)
                continue
            delta = curr - baseline
            # Abs deviation threshold (independent of sign)
            abs_dev = abs(delta)
            if abs_dev < 0.20:
                continue
            if abs_dev >= 0.50:
                sev = "severe"
            elif abs_dev >= 0.35:
                sev = "moderate"
            else:
                sev = "mild"
            note = (
                f"{a}↔{b}: {curr:+.2f} vs baseline {baseline:+.2f} "
                f"({'weakening' if abs(curr) < abs(baseline) else 'strengthening'})"
            )
            events.append(
                DecorrelationEvent(
                    pair=(a, b),
                    current=float(curr),
                    baseline=baseline,
                    severity=sev,
                    note=note,
                )
            )
        events.sort(key=lambda e: -abs(e.current - e.baseline))
        return events

    def regime_adjusted_matrices(
        self,
        regime_log_path: Path | None = None,
        window_days: int = 60,
    ) -> tuple[CorrelationMatrix | None, CorrelationMatrix | None]:
        """Split correlations by regime (RISK_ON vs RISK_OFF).

        Reads regime history from `data/chain/history.jsonl` (or custom path).
        Returns (risk_on_matrix, risk_off_matrix) — either may be None if
        insufficient data exists for that regime.
        """
        regime_log_path = regime_log_path or (
            Path(__file__).resolve().parents[2] / "data" / "chain" / "history.jsonl"
        )
        if not regime_log_path.exists():
            return None, None

        regime_days: dict[str, set[str]] = {"RISK_ON": set(), "RISK_OFF": set()}
        try:
            with regime_log_path.open() as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if e.get("kind") != "regime":
                        continue
                    state = e.get("state")
                    ts = e.get("unix_ts")
                    if not (state in regime_days and ts):
                        continue
                    day = datetime.fromtimestamp(ts, tz=UTC).date().isoformat()
                    regime_days[state].add(day)
        except OSError:
            return None, None

        # Require ≥5 days in BOTH regimes — splitting correlations only makes
        # sense when each side has enough observations. Prior `and` returned
        # only when both were below the floor, letting one-sided (e.g. 200
        # RISK_ON, 2 RISK_OFF) runs pass through and emit a degenerate matrix.
        if len(regime_days["RISK_ON"]) < 5 or len(regime_days["RISK_OFF"]) < 5:
            return None, None

        prices = _fetch_prices(self.symbols, days=max(180, window_days + 30))
        rets = self._log_returns(prices).tail(window_days * 2)

        def _matrix_for(days: set[str]) -> CorrelationMatrix | None:
            subset = rets[rets.index.strftime("%Y-%m-%d").isin(days)]
            if len(subset) < 10:
                return None
            corr = subset.corr(method="pearson").round(3)
            syms = list(corr.columns)
            return CorrelationMatrix(
                timestamp=datetime.now(UTC).isoformat(),
                window_days=len(subset),
                symbols=syms,
                matrix=[
                    [float(x) if not (isinstance(x, float) and np.isnan(x)) else 0.0 for x in row]
                    for row in corr.values.tolist()
                ],
                sample_count=len(subset),
            )

        on = _matrix_for(regime_days["RISK_ON"])
        off = _matrix_for(regime_days["RISK_OFF"])
        return on, off

    # ------------------------------------------------------------------

    def report(self, window_days: int = 30) -> CorrelationReport:
        matrix = self.build_matrix(window_days=window_days)
        events = self.detect_decorrelations(matrix)
        on, off = self.regime_adjusted_matrices()
        report = CorrelationReport(
            timestamp=datetime.now(UTC).isoformat(),
            matrix=matrix,
            decorrelation_events=events,
            risk_on_matrix=on,
            risk_off_matrix=off,
        )
        # Persist for daily brief
        try:
            with HISTORY_FILE.open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "timestamp": report.timestamp,
                            "window_days": window_days,
                            "matrix": matrix.matrix,
                            "symbols": matrix.symbols,
                            "events": [asdict(e) for e in events],
                        }
                    )
                    + "\n"
                )
        except OSError:
            pass

        if _EVENT_BUS is not None:
            try:
                for ev in events:
                    _EVENT_BUS.publish(
                        "correlation.broken",
                        {
                            "pair": list(ev.pair),
                            "current": ev.current,
                            "baseline": ev.baseline,
                            "severity": ev.severity,
                            "state": "decorrelated",
                            "note": ev.note,
                        },
                    )
            except Exception as e:
                log.warning("event bus publish failed: %s", e)

        return report

    def pair_correlation(self, a: str, b: str, window_days: int = 30) -> float | None:
        """Convenience: just the pair correlation."""
        m = self.build_matrix(window_days=window_days)
        if a not in m.symbols or b not in m.symbols:
            return None
        ia, ib = m.symbols.index(a), m.symbols.index(b)
        return m.matrix[ia][ib]


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    eng = CorrelationEngine()
    r = eng.report(window_days=30)
    print(f"=== 30-day correlation matrix ({r.matrix.sample_count} samples) ===")
    syms = r.matrix.symbols
    header = "       " + " ".join(f"{s:>7}" for s in syms)
    print(header)
    for i, row in enumerate(r.matrix.matrix):
        print(f"{syms[i]:>7}" + " ".join(f"{v:+7.2f}" for v in row))

    print(f"\nDecorrelation events: {len(r.decorrelation_events)}")
    for ev in r.decorrelation_events:
        print(f"  [{ev.severity:8}] {ev.note}")
