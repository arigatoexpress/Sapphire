"""Chain + macro regime classifier with shift alerting.

Pulls live sentiment (alternative.me Fear & Greed), perpetual funding
(Binance USDT-perp premium index), BTC dominance + 24h delta (CoinGecko),
and DXY/VIX closes (yfinance) to classify the market into one of
{RISK_ON, RISK_OFF, NEUTRAL}. Persists every snapshot to
`data/chain/history.jsonl`, and when the classification changes vs the
last persisted state it:

  * emits a Telegram p0 alert
  * publishes a `risk-alerts` Pub/Sub message (best-effort)

The module degrades gracefully — any single data source failing returns
None for that field rather than crashing the snapshot. Classification
uses a scoring scheme so it works with partial inputs.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import certifi

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "chain"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.jsonl"
LAST_STATE_FILE = DATA_DIR / "last_state.json"

NOTIFY_TOOL = ROOT / "plugins" / "claw-sapphire" / "tools" / "notify.py"

HTTP_TIMEOUT = 10.0
REQUEST_HEADERS = {"User-Agent": "SapphireOS/1.0 (chain-intelligence)"}


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class Regime(str, Enum):  # noqa: UP042 — str base is load-bearing for JSON round-trip
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"


@dataclass
class RegimeClassification:
    regime: Regime
    score: float  # -1 (max risk-off) .. +1 (max risk-on)
    reasons: list[str] = field(default_factory=list)
    inputs_ok: int = 0
    inputs_total: int = 0


@dataclass
class ChainSnapshot:
    timestamp: str
    unix_ts: int
    fear_greed: int | None
    fear_greed_label: str | None
    btc_dominance: float | None
    btc_dominance_24h_change: float | None
    total_mcap_usd: float | None
    total_mcap_24h_change_pct: float | None
    btc_funding_rate_pct: float | None  # 8h funding, percent
    eth_funding_rate_pct: float | None
    dxy: float | None
    dxy_1d_change_pct: float | None
    vix: float | None
    vix_1d_change_pct: float | None
    classification: RegimeClassification


@dataclass
class RegimeShiftEvent:
    from_regime: Regime
    to_regime: Regime
    from_score: float
    to_score: float
    timestamp: str
    reasons: list[str]


# ---------------------------------------------------------------------------
# HTTP helpers (no external deps — uses urllib)
# ---------------------------------------------------------------------------


def _http_json(url: str, timeout: float = HTTP_TIMEOUT) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=timeout) as r:
            raw = r.read(4 * 1024 * 1024)
        return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        log.debug("chain: fetch failed %s (%s)", url, exc)
        return None


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


def _fetch_fear_greed() -> tuple[int | None, str | None]:
    """alternative.me Fear & Greed Index (0-100)."""
    data = _http_json("https://api.alternative.me/fng/?limit=1")
    if not isinstance(data, dict):
        return None, None
    items = data.get("data", [])
    if not items:
        return None, None
    try:
        value = int(items[0]["value"])
        label = str(items[0].get("value_classification", ""))
        return value, label
    except (KeyError, ValueError, TypeError):
        return None, None


def _fetch_coingecko_global() -> dict | None:
    data = _http_json("https://api.coingecko.com/api/v3/global")
    if not isinstance(data, dict):
        return None
    return data.get("data") if isinstance(data.get("data"), dict) else None


def _fetch_binance_funding(symbol: str) -> float | None:
    """Binance premium index (8h funding rate). Returns percent."""
    data = _http_json(
        f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}",
        timeout=6.0,
    )
    if not isinstance(data, dict):
        return None
    raw = data.get("lastFundingRate")
    if raw is None:
        return None
    try:
        return float(raw) * 100.0
    except (TypeError, ValueError):
        return None


def _fetch_yf_close(ticker: str) -> tuple[float | None, float | None]:
    """Last close and 1d % change via yfinance. Returns (close, pct_change)."""
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return None, None
    try:
        data = yf.download(
            ticker,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=False,
        )
        if data is None or data.empty or "Close" not in data.columns:
            return None, None
        closes = data["Close"].dropna()
        # yfinance ≥0.2.x returns MultiIndex columns for single-ticker downloads
        if hasattr(closes, "squeeze"):
            closes = closes.squeeze()
        if len(closes) < 2:
            last = float(closes.iloc[-1]) if len(closes) else None
            return last, None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        if prev == 0:
            return last, None
        pct = (last - prev) / prev * 100.0
        return last, pct
    except Exception as exc:  # noqa: BLE001 — yfinance raises a menagerie
        log.debug("chain: yfinance failed for %s: %s", ticker, exc)
        return None, None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _score_fear_greed(v: int | None) -> tuple[float, str] | None:
    if v is None:
        return None
    # Map 0-100 to -1..+1 (extreme fear -> risk-off, extreme greed -> risk-on)
    score = (v - 50) / 50.0
    label = "extreme fear" if v < 20 else "fear" if v < 40 else "neutral" if v < 60 else "greed" if v < 80 else "extreme greed"
    return score, f"Fear&Greed={v} ({label})"


def _score_funding(btc: float | None, eth: float | None) -> tuple[float, str] | None:
    if btc is None and eth is None:
        return None
    parts = []
    if btc is not None:
        parts.append(btc)
    if eth is not None:
        parts.append(eth)
    avg = sum(parts) / len(parts)
    # >0.02% per 8h is elevated; map ±0.05% to ±1
    score = max(-1.0, min(1.0, avg / 0.05))
    tag = f"funding avg={avg:.3f}%"
    return score, tag


def _score_dominance(delta_24h: float | None) -> tuple[float, str] | None:
    if delta_24h is None:
        return None
    # Rising BTC dominance = flight to safety = risk-off (alts bleeding).
    score = max(-1.0, min(1.0, -delta_24h / 1.5))
    return score, f"BTC dom 24h={delta_24h:+.2f}%"


def _score_mcap_change(pct: float | None) -> tuple[float, str] | None:
    if pct is None:
        return None
    score = max(-1.0, min(1.0, pct / 3.0))
    return score, f"total mcap 24h={pct:+.2f}%"


def _score_dxy(delta_1d: float | None) -> tuple[float, str] | None:
    if delta_1d is None:
        return None
    # Dollar up = risk-off for crypto
    score = max(-1.0, min(1.0, -delta_1d / 0.7))
    return score, f"DXY 1d={delta_1d:+.2f}%"


def _score_vix(vix: float | None) -> tuple[float, str] | None:
    if vix is None:
        return None
    # VIX 15 = benign, 25 = stressed
    score = max(-1.0, min(1.0, (20.0 - vix) / 10.0))
    return score, f"VIX={vix:.1f}"


def classify(snapshot_inputs: dict) -> RegimeClassification:
    components: list[tuple[float, str]] = []
    scorers = [
        (_score_fear_greed, snapshot_inputs.get("fear_greed")),
        (_score_funding, (snapshot_inputs.get("btc_funding_rate_pct"),
                          snapshot_inputs.get("eth_funding_rate_pct"))),
        (_score_dominance, snapshot_inputs.get("btc_dominance_24h_change")),
        (_score_mcap_change, snapshot_inputs.get("total_mcap_24h_change_pct")),
        (_score_dxy, snapshot_inputs.get("dxy_1d_change_pct")),
        (_score_vix, snapshot_inputs.get("vix")),
    ]
    inputs_total = len(scorers)
    inputs_ok = 0

    for fn, arg in scorers:
        result = fn(*arg) if isinstance(arg, tuple) else fn(arg)  # type: ignore[arg-type]
        if result is None:
            continue
        inputs_ok += 1
        components.append(result)

    if inputs_ok == 0:
        return RegimeClassification(
            regime=Regime.NEUTRAL, score=0.0, reasons=["no inputs available"],
            inputs_ok=0, inputs_total=inputs_total,
        )

    score = sum(s for s, _ in components) / len(components)
    reasons = [tag for _, tag in components]
    if score >= 0.25:
        regime = Regime.RISK_ON
    elif score <= -0.25:
        regime = Regime.RISK_OFF
    else:
        regime = Regime.NEUTRAL
    return RegimeClassification(
        regime=regime, score=round(score, 3), reasons=reasons,
        inputs_ok=inputs_ok, inputs_total=inputs_total,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _read_last_state() -> dict | None:
    if not LAST_STATE_FILE.exists():
        return None
    try:
        return json.loads(LAST_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_last_state(snapshot: ChainSnapshot) -> None:
    try:
        LAST_STATE_FILE.write_text(json.dumps({
            "timestamp": snapshot.timestamp,
            "unix_ts": snapshot.unix_ts,
            "regime": snapshot.classification.regime.value,
            "score": snapshot.classification.score,
        }))
    except OSError as exc:
        log.warning("chain: could not write last_state: %s", exc)


def _append_history(snapshot: ChainSnapshot) -> None:
    entry = {
        "kind": "regime",
        "timestamp": snapshot.timestamp,
        "unix_ts": snapshot.unix_ts,
        "state": snapshot.classification.regime.value,
        "score": snapshot.classification.score,
        "reasons": snapshot.classification.reasons,
        "inputs_ok": snapshot.classification.inputs_ok,
        "inputs_total": snapshot.classification.inputs_total,
        "data": {
            "fear_greed": snapshot.fear_greed,
            "btc_dominance": snapshot.btc_dominance,
            "btc_dominance_24h_change": snapshot.btc_dominance_24h_change,
            "total_mcap_24h_change_pct": snapshot.total_mcap_24h_change_pct,
            "btc_funding_rate_pct": snapshot.btc_funding_rate_pct,
            "eth_funding_rate_pct": snapshot.eth_funding_rate_pct,
            "dxy": snapshot.dxy,
            "dxy_1d_change_pct": snapshot.dxy_1d_change_pct,
            "vix": snapshot.vix,
        },
    }
    try:
        with HISTORY_FILE.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        log.warning("chain: could not append history: %s", exc)


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------


def _send_telegram(msg: str, priority: str = "p0") -> None:
    try:
        subprocess.run(
            [sys.executable, str(NOTIFY_TOOL), msg, "--priority", priority],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("chain: telegram notify failed: %s", exc)


def _publish_pubsub(topic: str, payload: dict) -> None:
    """Best-effort Pub/Sub publish. Skipped entirely if disabled via env.

    Set SAPPHIRE_PUBSUB=0 to skip. Otherwise attempts lib/core PubSub client.
    """
    if os.getenv("SAPPHIRE_PUBSUB", "1") == "0":
        return
    try:
        core_src = ROOT / "lib" / "core" / "src"
        if str(core_src) not in sys.path:
            sys.path.insert(0, str(core_src))
        from sapphire_core.pubsub.client import get_pubsub_client  # type: ignore

        client = get_pubsub_client()
        # Reuse the running loop if one exists; otherwise, do nothing —
        # blocking here would stall a sync caller (dashboard, CLI tools).
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            # Fire synchronously on a short-lived loop; tolerate failure.
            try:
                asyncio.run(client.publish(topic, payload))
            except Exception as exc:  # noqa: BLE001
                log.debug("chain: sync pubsub publish failed: %s", exc)
        else:
            loop.create_task(client.publish(topic, payload))
    except Exception as exc:  # noqa: BLE001
        log.debug("chain: pubsub client unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ChainIntelligence:
    """Snapshot builder + regime shift alerter.

    Instantiate and call `.snapshot()` — every call fetches fresh data (no
    internal cache; callers should cache if needed — the dashboard already
    uses a 10s cache around this endpoint).
    """

    def snapshot(self, *, alert_on_shift: bool = True) -> dict:
        now = datetime.now(UTC)
        fg_value, fg_label = _fetch_fear_greed()

        gl = _fetch_coingecko_global() or {}
        btc_dominance = None
        btc_dominance_24h_change = None
        total_mcap_usd = None
        total_mcap_24h_change_pct = None
        try:
            mcp = gl.get("market_cap_percentage") or {}
            btc_dominance = float(mcp.get("btc")) if mcp.get("btc") is not None else None
            # CoinGecko doesn't return dominance delta directly — derive from
            # total mcap 24h change vs BTC price change if both present.
            total_mcap_usd = float((gl.get("total_market_cap") or {}).get("usd")) if (gl.get("total_market_cap") or {}).get("usd") else None
            total_mcap_24h_change_pct = (
                float(gl.get("market_cap_change_percentage_24h_usd"))
                if gl.get("market_cap_change_percentage_24h_usd") is not None
                else None
            )
        except (TypeError, ValueError):
            pass

        # BTC dominance delta: compare to last persisted snapshot
        last = _read_last_state() or {}
        if btc_dominance is not None and isinstance(last.get("btc_dominance"), (int, float)):
            btc_dominance_24h_change = btc_dominance - float(last["btc_dominance"])

        btc_funding = _fetch_binance_funding("BTCUSDT")
        eth_funding = _fetch_binance_funding("ETHUSDT")

        dxy, dxy_chg = _fetch_yf_close("DX-Y.NYB")
        vix, _vix_chg = _fetch_yf_close("^VIX")

        inputs = {
            "fear_greed": fg_value,
            "btc_funding_rate_pct": btc_funding,
            "eth_funding_rate_pct": eth_funding,
            "btc_dominance_24h_change": btc_dominance_24h_change,
            "total_mcap_24h_change_pct": total_mcap_24h_change_pct,
            "dxy_1d_change_pct": dxy_chg,
            "vix": vix,
        }
        classification = classify(inputs)

        snap = ChainSnapshot(
            timestamp=now.isoformat(),
            unix_ts=int(now.timestamp()),
            fear_greed=fg_value,
            fear_greed_label=fg_label,
            btc_dominance=round(btc_dominance, 3) if btc_dominance is not None else None,
            btc_dominance_24h_change=round(btc_dominance_24h_change, 3) if btc_dominance_24h_change is not None else None,
            total_mcap_usd=total_mcap_usd,
            total_mcap_24h_change_pct=round(total_mcap_24h_change_pct, 2) if total_mcap_24h_change_pct is not None else None,
            btc_funding_rate_pct=round(btc_funding, 4) if btc_funding is not None else None,
            eth_funding_rate_pct=round(eth_funding, 4) if eth_funding is not None else None,
            dxy=round(dxy, 3) if dxy is not None else None,
            dxy_1d_change_pct=round(dxy_chg, 3) if dxy_chg is not None else None,
            vix=round(vix, 2) if vix is not None else None,
            vix_1d_change_pct=None,
            classification=classification,
        )

        _append_history(snap)

        prev_regime = None
        prev_score = None
        if last.get("regime"):
            try:
                prev_regime = Regime(last["regime"])
                prev_score = float(last.get("score", 0.0))
            except (ValueError, TypeError):
                prev_regime = None

        shift: RegimeShiftEvent | None = None
        if prev_regime is not None and prev_regime != classification.regime:
            shift = RegimeShiftEvent(
                from_regime=prev_regime,
                to_regime=classification.regime,
                from_score=prev_score if prev_score is not None else 0.0,
                to_score=classification.score,
                timestamp=snap.timestamp,
                reasons=classification.reasons,
            )
            if alert_on_shift:
                self._handle_shift(shift, snap)

        # Persist last_state AFTER dispatching the shift so a crash mid-alert
        # results in the shift being re-detected on next run rather than lost.
        # Also stash btc_dominance so the next call can compute delta.
        try:
            payload = {
                "timestamp": snap.timestamp,
                "unix_ts": snap.unix_ts,
                "regime": classification.regime.value,
                "score": classification.score,
                "btc_dominance": btc_dominance,
            }
            LAST_STATE_FILE.write_text(json.dumps(payload))
        except OSError as exc:
            log.warning("chain: could not write last_state: %s", exc)

        result = asdict(snap)
        if shift:
            result["regime_shift"] = {
                "from": shift.from_regime.value,
                "to": shift.to_regime.value,
                "from_score": shift.from_score,
                "to_score": shift.to_score,
                "reasons": shift.reasons,
            }
        return result

    def _handle_shift(self, shift: RegimeShiftEvent, snap: ChainSnapshot) -> None:
        arrow = "→"
        msg = (
            f"*Regime shift*: {shift.from_regime.value} {arrow} {shift.to_regime.value}\n"
            f"Score: {shift.from_score:+.2f} {arrow} {shift.to_score:+.2f}\n"
            f"\n"
            + "\n".join(f"• {r}" for r in shift.reasons[:6])
        )
        _send_telegram(msg, priority="p0")
        _publish_pubsub("risk-alerts", {
            "kind": "regime_shift",
            "from": shift.from_regime.value,
            "to": shift.to_regime.value,
            "from_score": shift.from_score,
            "to_score": shift.to_score,
            "timestamp": shift.timestamp,
            "reasons": shift.reasons,
            "snapshot": {
                "fear_greed": snap.fear_greed,
                "btc_funding_rate_pct": snap.btc_funding_rate_pct,
                "vix": snap.vix,
                "dxy_1d_change_pct": snap.dxy_1d_change_pct,
                "btc_dominance_24h_change": snap.btc_dominance_24h_change,
            },
        })
        log.warning(
            "chain: regime shift %s -> %s (score %+.2f -> %+.2f)",
            shift.from_regime.value, shift.to_regime.value,
            shift.from_score, shift.to_score,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    snap = ChainIntelligence().snapshot()
    print(json.dumps(snap, indent=2, default=str))
