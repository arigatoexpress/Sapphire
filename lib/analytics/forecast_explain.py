"""Forecast + score interpretability — structured rationale generator.

Pure functions that turn a forecast row (``lib.analytics.forecast.forecast()``
output row) or a quick-signal-score result
(``lib.trading.tradingview_orchestrator.compute_quick_signal_score`` output)
into a structured rationale dict the dashboard can render.

Goal: when the dashboard shows a forecast or score, the user sees WHY.

Both inputs are already-captured data — no DB, no live calls. Calling these
functions is safe in any context (web request, test, batch job).

Output shape::

    {
      "headline":         "BTC: Strong Bull (composite +0.42)",
      "regime":           "BULL",
      "score":            0.42,
      "components": [
          {"name": "RSI", "value": 0.30, "weight": 0.30, "note": "RSI=62.0"},
          ...
      ],
      "rationale_short":  "RSI bullish + MACD positive + EMA stack aligned",
      "rationale_long":   "RSI at 62 (bullish vs 50 baseline), MACD ...",
      "confidence_band":  "high" | "medium" | "low",
      "show_math":        {<raw inputs that produced the score>},
    }
"""

from __future__ import annotations

from typing import Any

# Constants tuned to match the existing scorers' regime + threshold semantics.

# Regime thresholds applied to the composite score (range [-1, +1]).
_BULL_STRONG = 0.40
_BULL_MILD = 0.10
_BEAR_MILD = -0.10
_BEAR_STRONG = -0.40

# Confidence band thresholds applied to absolute composite score.
_CONF_HIGH = 0.50
_CONF_MEDIUM = 0.20

# Plain-English bucket labels for individual component scores.
_COMPONENT_LABELS: dict[str, dict[str, str]] = {
    "rsi": {
        "strong_bull": "RSI overbought / strongly bullish",
        "mild_bull": "RSI bullish",
        "neutral": "RSI neutral",
        "mild_bear": "RSI bearish",
        "strong_bear": "RSI oversold / strongly bearish",
    },
    "macd": {
        "strong_bull": "MACD strongly positive",
        "mild_bull": "MACD positive",
        "neutral": "MACD flat",
        "mild_bear": "MACD negative",
        "strong_bear": "MACD strongly negative",
    },
    "ema": {
        "strong_bull": "price well above EMA-20",
        "mild_bull": "EMA stack aligned",
        "neutral": "price near EMA-20",
        "mild_bear": "EMA stack inverted",
        "strong_bear": "price well below EMA-20",
    },
    "change_pct": {
        "strong_bull": "strong upside Δ over window",
        "mild_bull": "positive Δ over window",
        "neutral": "flat Δ over window",
        "mild_bear": "negative Δ over window",
        "strong_bear": "strong downside Δ over window",
    },
    "trend5": {
        "strong_bull": "5-bar trend strongly up",
        "mild_bull": "5-bar trend up",
        "neutral": "5-bar trend flat",
        "mild_bear": "5-bar trend down",
        "strong_bear": "5-bar trend strongly down",
    },
}


def _component_bucket(value: float) -> str:
    """Map a component score in [-1, +1] to a label key."""
    if value >= 0.5:
        return "strong_bull"
    if value >= 0.1:
        return "mild_bull"
    if value <= -0.5:
        return "strong_bear"
    if value <= -0.1:
        return "mild_bear"
    return "neutral"


def _component_label(name: str, value: float) -> str:
    bucket = _component_bucket(value)
    return _COMPONENT_LABELS.get(name, {}).get(
        bucket,
        f"{name} {bucket.replace('_', ' ')}",
    )


def _regime_from_score(score: float) -> str:
    """Bucket a composite score in [-1, +1] into a coarse regime label."""
    if score >= _BULL_STRONG:
        return "STRONG_BULL"
    if score >= _BULL_MILD:
        return "BULL"
    if score <= _BEAR_STRONG:
        return "STRONG_BEAR"
    if score <= _BEAR_MILD:
        return "BEAR"
    return "NEUTRAL"


def _confidence_band(score: float) -> str:
    abs_score = abs(score)
    if abs_score >= _CONF_HIGH:
        return "high"
    if abs_score >= _CONF_MEDIUM:
        return "medium"
    return "low"


def _normalize_components(
    raw: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Renormalize component weights to sum to 1.0 (or 0 if all zero)."""
    if not raw:
        return []
    total = sum(float(c.get("weight") or 0.0) for c in raw)
    if total <= 0:
        return [
            {
                "name": c.get("name"),
                "value": float(c.get("score") or c.get("value") or 0.0),
                "weight": 0.0,
                "note": c.get("note") or "",
            }
            for c in raw
        ]
    return [
        {
            "name": c.get("name"),
            "value": float(c.get("score") or c.get("value") or 0.0),
            "weight": round(float(c.get("weight") or 0.0) / total, 4),
            "note": c.get("note") or "",
        }
        for c in raw
    ]


def _format_headline(symbol: str, score: float, regime: str) -> str:
    """``BTC: Strong Bull (composite +0.42)`` style headline."""
    label_map = {
        "STRONG_BULL": "Strong Bull",
        "BULL": "Bull",
        "NEUTRAL": "Neutral",
        "BEAR": "Bear",
        "STRONG_BEAR": "Strong Bear",
    }
    pretty = label_map.get(regime, regime.replace("_", " ").title())
    sign = "+" if score >= 0 else ""
    return f"{symbol}: {pretty} (composite {sign}{score:.2f})"


def _short_rationale(components: list[dict[str, Any]]) -> str:
    """Sub-80-char colloquial summary of the dominant components."""
    if not components:
        return "no scorable components available"
    # Sort by absolute contribution (weight × |value|) and grab the top 3.
    ranked = sorted(
        components,
        key=lambda c: abs(float(c.get("value") or 0.0)) * float(c.get("weight") or 0.0),
        reverse=True,
    )
    top = ranked[:3]
    parts = [_component_label(c["name"], float(c["value"])) for c in top]
    text = " + ".join(parts)
    if len(text) > 80:
        text = text[:77].rstrip() + "..."
    return text


def _long_rationale(
    components: list[dict[str, Any]],
    score: float,
    regime: str,
) -> str:
    """Sub-400-char detailed prose."""
    if not components:
        return f"{regime.replace('_', ' ').title()} regime; no component data."
    pieces: list[str] = []
    for c in components:
        name = c.get("name") or ""
        value = float(c.get("value") or 0.0)
        weight = float(c.get("weight") or 0.0)
        note = c.get("note") or ""
        label = _component_label(name, value)
        sign = "+" if value >= 0 else ""
        if note:
            pieces.append(f"{label} ({note}, value={sign}{value:.2f}, w={weight:.2f})")
        else:
            pieces.append(f"{label} (value={sign}{value:.2f}, w={weight:.2f})")
    sign = "+" if score >= 0 else ""
    head = f"Regime {regime.replace('_', ' ').title()} (composite {sign}{score:.2f}). "
    body = "; ".join(pieces) + "."
    text = head + body
    if len(text) > 400:
        text = text[:397].rstrip() + "..."
    return text


def explain_score(
    score_payload: dict[str, Any],
    symbol: str = "?",
) -> dict[str, Any]:
    """Explain a quick_signal_score result.

    Input shape (matches ``compute_quick_signal_score`` output)::

        {
            "score": float,           # in [-1, +1]
            "regime": str,            # "RISK_ON" | "TRANSITION" | "RISK_OFF"
            "rationale": str,         # short scorer-emitted summary
            "components": [
                {"name": str, "score": float, "weight": float, "note": str},
                ...
            ],
        }

    Output: see module docstring.
    """
    if not isinstance(score_payload, dict):
        score_payload = {}

    raw_score = float(score_payload.get("score") or 0.0)
    score = max(-1.0, min(1.0, raw_score))
    components = _normalize_components(score_payload.get("components") or [])
    regime = _regime_from_score(score)
    headline = _format_headline(symbol, score, regime)
    short = _short_rationale(components)
    long_text = _long_rationale(components, score, regime)
    confidence = _confidence_band(score)

    show_math = {
        "raw_score": raw_score,
        "regime_input": score_payload.get("regime"),
        "scorer_rationale": score_payload.get("rationale"),
        "components_raw": list(score_payload.get("components") or []),
    }

    return {
        "kind": "quick_signal_score",
        "symbol": symbol,
        "headline": headline,
        "regime": regime,
        "score": round(score, 4),
        "components": components,
        "rationale_short": short,
        "rationale_long": long_text,
        "confidence_band": confidence,
        "show_math": show_math,
    }


# --------------------------------------------------------------------------- #
# Forecast row explanation
# --------------------------------------------------------------------------- #


def _forecast_components(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Build (kronos, ta) components from a forecast row."""
    components: list[dict[str, Any]] = []
    kronos = row.get("kronos") or {}
    ta = row.get("ta") or {}

    def _to_signed(direction: Any, confidence: Any) -> float:
        d = (direction or "").lower() if isinstance(direction, str) else ""
        try:
            conf = float(confidence or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if d in {"bullish", "long", "up", "buy"}:
            return max(-1.0, min(1.0, conf))
        if d in {"bearish", "short", "down", "sell"}:
            return max(-1.0, min(1.0, -conf))
        return 0.0

    if kronos:
        signed = _to_signed(kronos.get("direction"), kronos.get("confidence"))
        proj = kronos.get("projected_change_pct")
        proj_str = (
            f"{proj:+.2f}% over {kronos.get('horizon_hours') or '?'}b"
            if proj is not None
            else "horizon projection"
        )
        components.append(
            {
                "name": "kronos",
                "score": signed,
                "weight": 0.5,
                "note": f"{kronos.get('direction') or 'n/a'}@{(kronos.get('confidence') or 0):.2f} ({proj_str})",
            }
        )
    if ta:
        signed = _to_signed(ta.get("direction"), ta.get("confidence"))
        components.append(
            {
                "name": "ta",
                "score": signed,
                "weight": 0.5,
                "note": (
                    f"{ta.get('direction') or 'n/a'}@{(ta.get('confidence') or 0):.2f} "
                    f"({ta.get('timeframe') or '?'})"
                ),
            }
        )
    return components


_FORECAST_COMPONENT_LABELS: dict[str, dict[str, str]] = {
    "kronos": {
        "strong_bull": "Kronos strongly bullish",
        "mild_bull": "Kronos bullish",
        "neutral": "Kronos neutral",
        "mild_bear": "Kronos bearish",
        "strong_bear": "Kronos strongly bearish",
    },
    "ta": {
        "strong_bull": "TA scanner strongly bullish",
        "mild_bull": "TA scanner bullish",
        "neutral": "TA scanner neutral",
        "mild_bear": "TA scanner bearish",
        "strong_bear": "TA scanner strongly bearish",
    },
}


def _forecast_label(name: str, value: float) -> str:
    bucket = _component_bucket(value)
    return _FORECAST_COMPONENT_LABELS.get(name, {}).get(
        bucket,
        f"{name} {bucket.replace('_', ' ')}",
    )


_CONSENSUS_HEADLINE = {
    "AGREE_BULL": "Agree Bull",
    "AGREE_BEAR": "Agree Bear",
    "CONTRADICT": "Contradict",
    "PARTIAL": "Partial",
    "KRONOS_ONLY": "Kronos Only",
    "TA_ONLY": "TA Only",
    "NEITHER": "No Data",
}


def explain_forecast(
    row: dict[str, Any],
    symbol: str | None = None,
) -> dict[str, Any]:
    """Explain a forecast row from ``lib.analytics.forecast.forecast()``.

    Input shape (one ``rows[i]`` dict)::

        {
            "symbol": "BTC",
            "kronos": {"direction": "bullish", "confidence": 0.8, ...},
            "ta": {"direction": "bullish", "confidence": 0.75, ...},
            "consensus": "AGREE_BULL",
            "edge_score": 0.78,
        }

    Output: see module docstring.
    """
    if not isinstance(row, dict):
        row = {}

    sym = symbol or row.get("symbol") or "?"
    edge = float(row.get("edge_score") or 0.0)
    edge = max(-1.0, min(1.0, edge))
    consensus = row.get("consensus") or "NEITHER"
    components = _forecast_components(row)
    components = _normalize_components(components)
    regime = _regime_from_score(edge)

    pretty_consensus = _CONSENSUS_HEADLINE.get(consensus, consensus)
    sign = "+" if edge >= 0 else ""
    headline = f"{sym}: {pretty_consensus} (edge {sign}{edge:.2f})"

    # Short rationale — leverages forecast-specific labels.
    if components:
        ranked = sorted(
            components,
            key=lambda c: abs(float(c.get("value") or 0.0)) * float(c.get("weight") or 0.0),
            reverse=True,
        )
        parts = [_forecast_label(c["name"], float(c["value"])) for c in ranked[:3]]
        short = " + ".join(parts)
        if len(short) > 80:
            short = short[:77].rstrip() + "..."
    else:
        short = f"no Kronos/TA data for {sym}"

    # Long rationale — explicit per-source detail.
    if components:
        pieces = []
        for c in components:
            name = c.get("name") or ""
            value = float(c.get("value") or 0.0)
            weight = float(c.get("weight") or 0.0)
            note = c.get("note") or ""
            label = _forecast_label(name, value)
            sign_v = "+" if value >= 0 else ""
            pieces.append(
                f"{label} ({note}; signed={sign_v}{value:.2f}, w={weight:.2f})"
                if note
                else f"{label} (signed={sign_v}{value:.2f}, w={weight:.2f})"
            )
        head = f"Consensus {pretty_consensus}; edge {sign}{edge:.2f}. "
        body = "; ".join(pieces) + "."
        long_text = head + body
        if len(long_text) > 400:
            long_text = long_text[:397].rstrip() + "..."
    else:
        long_text = (
            f"No Kronos or TA data available for {sym}; consensus={pretty_consensus}."
        )

    show_math = {
        "raw_edge_score": row.get("edge_score"),
        "consensus": consensus,
        "kronos": row.get("kronos"),
        "ta": row.get("ta"),
        "kronos_symbol": row.get("kronos_symbol"),
        "ta_symbol": row.get("ta_symbol"),
    }

    return {
        "kind": "forecast",
        "symbol": sym,
        "headline": headline,
        "regime": regime,
        "score": round(edge, 4),
        "consensus": consensus,
        "components": components,
        "rationale_short": short,
        "rationale_long": long_text,
        "confidence_band": _confidence_band(edge),
        "show_math": show_math,
    }


def explain(payload: dict[str, Any], symbol: str | None = None) -> dict[str, Any]:
    """Dispatch to the right explainer based on the payload's shape.

    - If the payload has ``edge_score`` and ``consensus``, treat as a forecast row.
    - If the payload has ``score`` and ``components`` (and ``regime``), treat as a
      quick_signal_score result.
    - Otherwise, return an "unrecognized" structured rationale rather than raise.
    """
    if not isinstance(payload, dict):
        payload = {}
    if "edge_score" in payload or "consensus" in payload:
        return explain_forecast(payload, symbol=symbol)
    if "components" in payload and "score" in payload:
        return explain_score(payload, symbol=symbol or payload.get("symbol") or "?")
    sym = symbol or payload.get("symbol") or "?"
    return {
        "kind": "unrecognized",
        "symbol": sym,
        "headline": f"{sym}: no data",
        "regime": "NEUTRAL",
        "score": 0.0,
        "components": [],
        "rationale_short": "no recognizable forecast/score payload",
        "rationale_long": "Input did not match a known forecast row or quick_signal_score result.",
        "confidence_band": "low",
        "show_math": {"raw_input_keys": list(payload.keys())},
    }
