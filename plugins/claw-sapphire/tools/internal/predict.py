#!/usr/bin/env python3
"""Sapphire Prediction Engine — TA-grounded price predictions.

Uses real technical analysis (RSI, MACD, Bollinger, MA, ATR) from OpenBB
to generate predictions. No hallucinated numbers — every value is computed.

Actions:
    predict  — Generate new predictions for BTC, ETH, SOL
    score    — Score pending predictions against live prices
    history  — Show prediction history and accuracy

Usage:
    echo '{"action":"predict"}' | python3 predict.py
    echo '{"action":"score"}' | python3 predict.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
PREDICTIONS_FILE = SAPPHIRE_DIR / "data" / "trading_predictions.jsonl"
CHAIN_LATEST_FILE = SAPPHIRE_DIR / "data" / "intelligence" / "latest" / "chain.json"

# Direction classification thresholds. Defaults preserve the legacy symmetric
# behavior (`net > 1.5` -> bullish, `net < -1.5` -> bearish). Operators can
# raise the bear threshold via SAPPHIRE_PREDICT_BEAR_THRESHOLD to require more
# bear evidence before flipping to a short call — see
# docs/research/bearish-direction-asymmetry-2026-04-26.md (Layer C).
DEFAULT_BULL_THRESHOLD = 1.5
DEFAULT_BEAR_THRESHOLD = 1.5

# Layer A — chain-factor delta caps. Each factor can contribute at most this
# much to either side, so funding/OI cannot single-handedly flip a direction.
# See docs/research/bearish-direction-asymmetry-2026-04-26.md §9.
_CHAIN_FACTOR_DELTA_CAP = 0.5
_FUNDING_Z_THRESHOLD = 1.5
_OI_CHANGE_PCT_THRESHOLD = 5.0


def _resolve_threshold(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def classify_direction(
    net: float,
    *,
    bull_threshold: float = DEFAULT_BULL_THRESHOLD,
    bear_threshold: float = DEFAULT_BEAR_THRESHOLD,
) -> str:
    if net > bull_threshold:
        return "bullish"
    if net < -bear_threshold:
        return "bearish"
    return "neutral"


def chain_factor_deltas(
    symbol: str,
    *,
    funding_z: float | None,
    oi_change_pct: float | None,
) -> tuple[float, float, list[str]]:
    """Compute additive bull/bear deltas from on-chain leverage signals.

    Pure function: no IO, no network — every input is passed in by the caller.

    Rationale (Layer A of bearish-direction-asymmetry-2026-04-26 §4.1):

    The base 6-factor scorer in :func:`action_predict` is blind to leverage
    crowding. When perpetual funding is extremely positive (longs paying shorts),
    the marginal long is paying carry and is unstable to a downside move; the
    setup is bear-confirming. The mirror holds for very negative funding.
    Open-interest changes are direction-agnostic on their own — a 5% OI
    expansion only matters in the context of an existing lean. We therefore
    add a small additive delta to whichever side already dominates so OI
    amplifies rather than dictates.

    Conservative deltas (capped at 0.5 per factor) are deliberate: a single
    chain factor must never single-handedly flip a direction. Two factors at
    cap together still only contribute 1.0, well under the legacy ±1.5
    threshold.

    Args:
        symbol: Asset symbol (BTC/ETH/SOL/...). Used only to label factors —
            no per-symbol logic, on purpose.
        funding_z: Standardized funding rate (z-score against rolling history).
            Pass ``None`` if unavailable. ``z > +1.5`` -> bear delta;
            ``z < -1.5`` -> bull delta.
        oi_change_pct: 24h open-interest change in percent. Pass ``None`` if
            unavailable. ``> +5%`` adds to whichever side already leads.

    Returns:
        ``(bull_delta, bear_delta, factors)``. Both deltas are non-negative.
        ``factors`` is a short list of human-readable labels for the per-call
        reasoning string.
    """
    bull_delta = 0.0
    bear_delta = 0.0
    factors: list[str] = []

    # Funding rate z-score. Crowded longs (high positive z) is bear-confirming;
    # crowded shorts (very negative z) is bull-confirming. Below |z| < 1.5 the
    # signal is noise and contributes nothing — same threshold the chain refresh
    # uses to flag "extreme" perps.
    if funding_z is not None:
        if funding_z > _FUNDING_Z_THRESHOLD:
            bear_delta += _CHAIN_FACTOR_DELTA_CAP
            factors.append(f"FundZ{funding_z:+.1f}↓")
        elif funding_z < -_FUNDING_Z_THRESHOLD:
            bull_delta += _CHAIN_FACTOR_DELTA_CAP
            factors.append(f"FundZ{funding_z:+.1f}↑")

    # OI change amplifies — never originates — direction. We only add weight to
    # the side that funding already pushed; if funding was neutral or absent
    # there is no "dominant context" for OI to amplify and we stay silent.
    if oi_change_pct is not None and oi_change_pct > _OI_CHANGE_PCT_THRESHOLD:
        if bear_delta > bull_delta:
            bear_delta += _CHAIN_FACTOR_DELTA_CAP
            factors.append(f"OI{oi_change_pct:+.1f}%↓")
        elif bull_delta > bear_delta:
            bull_delta += _CHAIN_FACTOR_DELTA_CAP
            factors.append(f"OI{oi_change_pct:+.1f}%↑")

    return bull_delta, bear_delta, factors


def _read_chain_features(symbol: str) -> tuple[float | None, float | None]:
    """Best-effort read of (funding_z, oi_change_pct) for ``symbol``.

    Reads from ``data/intelligence/latest/chain.json``, the artifact written
    by ``services.pipeline.chain_refresh``. Returns ``(None, None)`` on every
    error path — file missing, JSON malformed, schema mismatch, symbol absent,
    values non-numeric. Never raises.

    Schema is intentionally tolerant. The refresh emits perps under
    ``funding.perps`` (list of ``{"coin", "funding_rate_8h", ...}``); a future
    revision may emit per-symbol entries directly under ``perps`` or a
    ``per_symbol`` key. This adapter probes a few common shapes and returns
    whatever it finds. Stdlib only — no pandas/numpy/etc.

    Tests patch this via ``monkeypatch.setattr(predict, "_read_chain_features",
    lambda sym: (z, oi))`` rather than touching the filesystem.
    """
    try:
        if not CHAIN_LATEST_FILE.exists():
            return (None, None)
        raw = CHAIN_LATEST_FILE.read_text()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, ValueError):
        return (None, None)
    except Exception:  # noqa: BLE001 — adapter must never raise
        return (None, None)

    sym = symbol.upper()

    # Probe order:
    #   1. ``funding.perps`` list (chain_refresh.py shape).
    #   2. ``perps`` list (alternate refresh shape).
    #   3. ``per_symbol[sym]`` dict (future shape).
    candidates: list[dict] = []
    funding_section = data.get("funding") if isinstance(data, dict) else None
    if isinstance(funding_section, dict):
        perps = funding_section.get("perps")
        if isinstance(perps, list):
            candidates.extend(p for p in perps if isinstance(p, dict))
    top_perps = data.get("perps") if isinstance(data, dict) else None
    if isinstance(top_perps, list):
        candidates.extend(p for p in top_perps if isinstance(p, dict))
    per_symbol = data.get("per_symbol") if isinstance(data, dict) else None
    if isinstance(per_symbol, dict):
        entry = per_symbol.get(sym) or per_symbol.get(symbol)
        if isinstance(entry, dict):
            candidates.append(entry)

    funding_z: float | None = None
    oi_change_pct: float | None = None

    for entry in candidates:
        coin = entry.get("coin") or entry.get("symbol") or entry.get("ticker")
        if isinstance(coin, str) and coin.upper() != sym:
            continue
        fz = entry.get("funding_z")
        if fz is None:
            fz = entry.get("funding_zscore")
        oi = entry.get("oi_change_pct")
        if oi is None:
            oi = entry.get("open_interest_change_pct")
        if fz is not None and funding_z is None:
            try:
                funding_z = float(fz)
            except (TypeError, ValueError):
                pass
        if oi is not None and oi_change_pct is None:
            try:
                oi_change_pct = float(oi)
            except (TypeError, ValueError):
                pass
        if funding_z is not None and oi_change_pct is not None:
            break

    return (funding_z, oi_change_pct)


def _get_coingecko_prices() -> dict:
    """Get current prices from CoinGecko."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        return {
            "BTC": data["bitcoin"]["usd"],
            "ETH": data["ethereum"]["usd"],
            "SOL": data["solana"]["usd"],
        }
    except Exception:
        return {}


def action_predict() -> dict:
    """Generate TA-grounded predictions."""
    from technical_analysis import analyze_all

    profiles = analyze_all()
    predictions = []
    now = datetime.now(UTC).isoformat()
    bull_threshold = _resolve_threshold("SAPPHIRE_PREDICT_BULL_THRESHOLD", DEFAULT_BULL_THRESHOLD)
    bear_threshold = _resolve_threshold("SAPPHIRE_PREDICT_BEAR_THRESHOLD", DEFAULT_BEAR_THRESHOLD)
    # Layer A — opt-in chain factors. Default OFF: production behavior is
    # unchanged unless the operator explicitly sets the flag in the LaunchAgent
    # env. See docs/research/bearish-direction-asymmetry-2026-04-26.md §9.
    use_chain_factors = os.environ.get(
        "SAPPHIRE_PREDICT_USE_CHAIN_FACTORS", "0"
    ).strip().lower() in {"1", "true", "yes", "on"}

    for sym, profile in profiles.items():
        if profile is None:
            continue

        # ─── Multi-factor confidence scoring ───
        # Each factor contributes independently. Direction comes from consensus.
        bull_score = 0.0
        bear_score = 0.0
        factors = []

        # 1. MA trend (strongest directional signal)
        if profile.ma_trend == "bullish":
            bull_score += 2.0
            factors.append("MA↑")
        elif profile.ma_trend == "bearish":
            bear_score += 2.0
            factors.append("MA↓")

        # 2. RSI (contrarian near extremes, confirming in middle)
        if profile.rsi_14 < 30:
            bull_score += 1.5  # Oversold bounce
            factors.append(f"RSI{profile.rsi_14:.0f}↑")
        elif profile.rsi_14 < 45:
            bear_score += 0.5  # Weak
            factors.append(f"RSI{profile.rsi_14:.0f}")
        elif profile.rsi_14 < 55:
            pass  # Neutral
        elif profile.rsi_14 < 70:
            bull_score += 0.5  # Mildly bullish momentum
            factors.append(f"RSI{profile.rsi_14:.0f}")
        else:
            bear_score += 1.0  # Overbought, likely pullback
            factors.append(f"RSI{profile.rsi_14:.0f}↓")

        # 3. MACD cross
        if profile.macd_cross == "bullish_cross":
            bull_score += 1.5
            factors.append("MACD↑")
        elif profile.macd_cross == "bearish_cross":
            bear_score += 1.5
            factors.append("MACD↓")

        # 4. Bollinger position
        if profile.bb_position == "below_lower":
            bull_score += 1.0
            factors.append("BB<low")
        elif profile.bb_position == "above_upper":
            bear_score += 1.0
            factors.append("BB>high")

        # 5. Volume confirmation (amplifies existing signal)
        if profile.volume_ratio > 1.5:
            if bull_score > bear_score:
                bull_score += 0.5
            elif bear_score > bull_score:
                bear_score += 0.5
            factors.append("Vol↑")
        elif profile.volume_ratio < 0.5:
            # Low volume = weak conviction, dampen both
            bull_score *= 0.8
            bear_score *= 0.8
            factors.append("Vol↓")

        # 6. 7-day momentum
        if profile.change_7d_pct > 5:
            bull_score += 0.5
        elif profile.change_7d_pct < -5:
            bear_score += 0.5

        # 7. Chain factors (Layer A) — opt-in, default off. Read funding-rate
        # z-score and 24h OI change from the chain refresh artifact and apply
        # capped additive deltas. Adapter is best-effort and never raises;
        # missing values short-circuit the call so the legacy six-factor result
        # is preserved bit-for-bit.
        if use_chain_factors:
            funding_z, oi_change_pct = _read_chain_features(sym)
            if funding_z is not None and oi_change_pct is not None:
                bull_delta, bear_delta, chain_factors = chain_factor_deltas(
                    sym,
                    funding_z=funding_z,
                    oi_change_pct=oi_change_pct,
                )
                bull_score += bull_delta
                bear_score += bear_delta
                factors.extend(chain_factors)

        # ─── Direction decision ───
        net = bull_score - bear_score
        direction = classify_direction(
            net,
            bull_threshold=bull_threshold,
            bear_threshold=bear_threshold,
        )

        # ─── Confidence: based on how strong the consensus is ───
        total_score = bull_score + bear_score
        dominance = max(bull_score, bear_score) / total_score if total_score > 0 else 0.5
        conf = round(min(0.90, 0.40 + dominance * 0.4 + abs(net) * 0.05), 2)

        # ─── Target: entry ± 0.5 ATR (conservative) ───
        atr_move = profile.atr_14
        if direction == "bullish":
            target = profile.price + atr_move * 0.5
        elif direction == "bearish":
            target = profile.price - atr_move * 0.5
        else:
            target = profile.price

        pred = {
            "timestamp": now,
            "symbol": sym,
            "direction": direction,
            "confidence": round(conf, 2),
            "target_price": round(target, 2),
            "entry_price": profile.price,
            "timeframe": "24h",
            # TA indicators used
            "rsi": profile.rsi_14,
            "macd_cross": profile.macd_cross,
            "ma_trend": profile.ma_trend,
            "bb_position": profile.bb_position,
            "volume_signal": profile.volume_signal,
            "volatility": profile.volatility_regime,
            "signals_bullish": profile.signal_count_bullish,
            "signals_bearish": profile.signal_count_bearish,
            "net_signal": profile.net_signal,
            "reasoning": (
                f"{direction} (net={net:+.1f}): {' '.join(factors)}. "
                f"Bull={bull_score:.1f} Bear={bear_score:.1f}. "
                f"RSI {profile.rsi_14:.0f}, MA {profile.ma_trend}, BB {profile.bb_position}."
            ),
            "actual_price": None,
            "correct": None,
        }
        predictions.append(pred)

    # Append to predictions file
    with open(PREDICTIONS_FILE, "a") as f:
        for p in predictions:
            f.write(json.dumps(p) + "\n")

    return {
        "success": True,
        "predictions": len(predictions),
        "summary": [
            f"{p['symbol']} {p['direction']} → ${p['target_price']:,.0f} (conf {p['confidence']:.0%}, {p['net_signal']})"
            for p in predictions
        ],
    }


_TIMEFRAME_SECONDS = {
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "24h": 86400,
    "1d": 86400,
    "3d": 259200,
    "7d": 604800,
    "1w": 604800,
}


def _timeframe_elapsed(pred: dict, now: datetime) -> bool:
    """True once `pred["timestamp"] + pred["timeframe"]` is in the past."""
    tf = str(pred.get("timeframe", "24h"))
    window = _TIMEFRAME_SECONDS.get(tf, 86400)
    raw_ts = pred.get("timestamp")
    if not raw_ts:
        return False
    try:
        created = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return now - created >= timedelta(seconds=window)


def _atomic_write_lines(path: Path, lines: list[str]) -> None:
    """Write lines to path atomically via a same-directory temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def action_score() -> dict:
    """Score predictions whose timeframe has elapsed against live prices.

    Previously this scored every un-scored prediction the moment it saw one —
    which turned a "24h forecast" into a "does the current price beat entry
    right now" coin-flip and invalidated every published accuracy number.
    """
    prices = _get_coingecko_prices()
    if not prices:
        return {"error": "Could not fetch live prices"}

    if not PREDICTIONS_FILE.exists():
        return {
            "success": True,
            "newly_scored": 0,
            "total_scored": 0,
            "correct": 0,
            "accuracy": "N/A",
        }

    now = datetime.now(UTC)
    updated: list[str] = []
    scored_count = 0
    correct_count = 0
    pending_within_window = 0

    for line in PREDICTIONS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            p = json.loads(line)
        except json.JSONDecodeError:
            continue

        if p.get("correct") is None and p.get("symbol") in prices:
            if not _timeframe_elapsed(p, now):
                pending_within_window += 1
            else:
                current = prices[p["symbol"]]
                entry = p.get("entry_price") or p["target_price"]
                if entry and p["direction"] == "bullish":
                    p["correct"] = bool(current > entry)
                elif entry and p["direction"] == "bearish":
                    p["correct"] = bool(current < entry)
                elif entry:
                    p["correct"] = abs((current - entry) / entry * 100) < 3
                p["actual_price"] = current
                p["scored_at"] = now.isoformat()
                scored_count += 1

        if p.get("correct") is True:
            correct_count += 1

        updated.append(json.dumps(p))

    _atomic_write_lines(PREDICTIONS_FILE, updated)

    total_scored = sum(1 for line in updated if json.loads(line).get("correct") is not None)

    return {
        "success": True,
        "newly_scored": scored_count,
        "total_scored": total_scored,
        "correct": correct_count,
        "pending_within_window": pending_within_window,
        "accuracy": f"{correct_count / total_scored * 100:.0f}%" if total_scored else "N/A",
    }


def action_history() -> dict:
    """Show prediction history and accuracy."""
    if not PREDICTIONS_FILE.exists():
        return {"predictions": [], "accuracy": "N/A"}

    preds = [json.loads(l) for l in PREDICTIONS_FILE.read_text().strip().split("\n")]
    scored = [p for p in preds if p.get("correct") is not None]
    correct = sum(1 for p in scored if p["correct"])

    # Group by symbol
    by_symbol = {}
    for p in scored:
        sym = p["symbol"]
        by_symbol.setdefault(sym, {"correct": 0, "total": 0})
        by_symbol[sym]["total"] += 1
        if p["correct"]:
            by_symbol[sym]["correct"] += 1

    return {
        "total_predictions": len(preds),
        "scored": len(scored),
        "correct": correct,
        "accuracy": f"{correct / len(scored) * 100:.0f}%" if scored else "N/A",
        "by_symbol": {
            sym: f"{d['correct']}/{d['total']} = {d['correct']/d['total']*100:.0f}%"
            for sym, d in by_symbol.items()
        },
        "pending": len(preds) - len(scored),
    }


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "predict"}
    action = params.get("action", "predict")

    if action == "predict":
        result = action_predict()
    elif action == "score":
        result = action_score()
    elif action == "history":
        result = action_history()
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
