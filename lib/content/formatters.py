"""Platform formatters.

Each formatter takes a Report and produces a single string suited for the
target platform's constraints:

  - LinkedIn: up to 1300 characters, hook-led, line-broken, hashtags allowed.
  - Substack: full markdown article with sources footer.
  - X: thread — list of tweets, each <=270 chars so they post cleanly.

Formatters do not invent facts; they only draw from `report.facts` and
`report.body`. That keeps platform output in sync with the data.

Bilingual (EN / ES): pass ``language="es"`` to any formatter to route the
English rendering through the glossary-driven translator. English remains
the default so existing call-sites are unchanged.
"""

from __future__ import annotations

from .performance_policy import (
    has_public_accuracy_track_record,
    small_sample_accuracy_notice,
    small_sample_accuracy_notice_es,
)
from .report_generator import Report
from .translator import Translator, is_supported_language

LINKEDIN_LIMIT = 1300
X_TWEET_LIMIT = 270  # leave headroom under the hard 280
SHORT_DISCLAIMER = "Informational only. Not investment advice."
MARKDOWN_DISCLAIMER = "_For informational and educational purposes only. Not investment advice._"
SHORT_DISCLAIMER_ES = "Solo con fines informativos. No es asesoría de inversión."
MARKDOWN_DISCLAIMER_ES = "_Solo con fines informativos y educativos. No es asesoría de inversión._"


# ---------- LinkedIn ----------


def _shorten_to(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    # Cut at the last sentence-ending before the limit.
    cut = text[:limit].rsplit(".", 1)[0]
    if len(cut) < limit * 0.6:
        cut = text[: limit - 1]
    return cut.rstrip() + "…"


def _append_tail(text: str, tail: str, limit: int) -> str:
    """Append a fixed tail while guaranteeing it survives truncation."""
    if not tail:
        return _shorten_to(text, limit)
    joiner = "\n\n"
    if len(text) + len(joiner) + len(tail) <= limit:
        return text + joiner + tail
    budget = max(0, limit - len(joiner) - len(tail))
    if budget == 0:
        return tail[:limit]
    # Reaching here means *text* must be shortened, and _shorten_to appends its
    # ellipsis after cutting (so it is bounded to budget + 1, not budget) —
    # aim one char lower to keep the joined result within *limit*.
    return _shorten_to(text, budget - 1) + joiner + tail


def _linkedin_crypto(r: Report) -> str:
    f = r.facts
    preds = f["predictions"]
    port = f["portfolio"]
    sig = f["signal_pipeline"]
    if has_public_accuracy_track_record(preds):
        hook = (
            f"{preds['total']} scored predictions later, Sapphire's 6-factor TA "
            f"model is at {preds['accuracy'] * 100:.1f}% accuracy."
        )
        symbol_line = " · ".join(
            f"{s} {v['hits']}/{v['total']}" for s, v in preds["by_symbol"].items()
        )
    else:
        hook = small_sample_accuracy_notice(preds, subject="Sapphire's 6-factor TA model")
        tracked = ", ".join(sorted(preds["by_symbol"])) if preds["by_symbol"] else "live markets"
        symbol_line = (
            f"Coverage is live across {tracked}. "
            "Per-symbol hit-rate tables stay internal until the public sample clears 100 scored forecasts."
        )
    book = (
        f"Paper book: ${port['capital']:,.0f} on a $100K start "
        f"({port['pnl_pct']:+.2f}%), {port['open_positions']} open."
    )
    pipe = f"Signal pipeline: {sig['count']} logged this week, {len(sig['symbols'])} symbols."
    tail = "Data sources: " + ", ".join(r.sources)
    tags = " ".join(f"#{t}" for t in r.tags if t.isascii())
    body = "\n\n".join([hook, symbol_line, book, pipe, tail, tags])
    return _append_tail(body, SHORT_DISCLAIMER, LINKEDIN_LIMIT)


def _linkedin_ai(r: Report) -> str:
    f = r.facts
    top_agent = (
        max(f["agent_counts"].items(), key=lambda x: x[1]) if f["agent_counts"] else ("—", 0)
    )
    hook = (
        f"{f['event_count']} agent events across "
        f"{len(f['agent_counts'])} agents and "
        f"{len(f['device_counts'])} devices this cycle."
    )
    lead = f"Top agent by volume: {top_agent[0]} with {top_agent[1]} events."
    mesh = (
        "Mesh mix — " + ", ".join(f"{k}:{v}" for k, v in f["device_counts"].items())
        if f["device_counts"]
        else "Mesh idle."
    )
    proj = f"{f['tracked_projects']} active projects in the ledger."
    tail = "Source: " + ", ".join(r.sources)
    tags = " ".join(f"#{t}" for t in r.tags if t.isascii())
    return _append_tail(
        "\n\n".join([hook, lead, mesh, proj, tail, tags]),
        SHORT_DISCLAIMER,
        LINKEDIN_LIMIT,
    )


def _linkedin_security(r: Report) -> str:
    f = r.facts
    hook = (
        f"{f['count']} CVEs prioritized this cycle, "
        f"{f['exploited_in_wild']} exploited in the wild. "
        f"Average CVSS {f['avg_cvss']}."
    )
    tops = []
    for item in f["top_cves"][:3]:
        kev = " (KEV)" if item["exploited"] else ""
        tops.append(f"• {item['cve']}{kev} — {item['title']}")
    tail = "Source: " + ", ".join(r.sources)
    tags = " ".join(f"#{t}" for t in r.tags if t.isascii())
    return _append_tail(
        "\n\n".join([hook, "\n".join(tops), tail, tags]),
        SHORT_DISCLAIMER,
        LINKEDIN_LIMIT,
    )


# ---------- LinkedIn (Spanish) ----------


def _linkedin_crypto_es(r: Report) -> str:
    f = r.facts
    preds = f["predictions"]
    port = f["portfolio"]
    sig = f["signal_pipeline"]
    if has_public_accuracy_track_record(preds):
        hook = (
            f"Con {preds['total']} pronósticos evaluados, el modelo TA de 6 factores "
            f"de Sapphire acumula {preds['accuracy'] * 100:.1f}% de precisión."
        )
        symbol_line = " · ".join(
            f"{s} {v['hits']}/{v['total']}" for s, v in preds["by_symbol"].items()
        )
    else:
        hook = small_sample_accuracy_notice_es(
            preds, subject="El modelo TA de 6 factores de Sapphire"
        )
        tracked = (
            ", ".join(sorted(preds["by_symbol"])) if preds["by_symbol"] else "mercados en vivo"
        )
        symbol_line = (
            f"Cobertura en vivo en {tracked}. "
            "Las tablas de acierto por símbolo se mantienen internas hasta que la muestra "
            "pública supere las 100 predicciones evaluadas."
        )
    book = (
        f"Cartera en papel: ${port['capital']:,.0f} sobre una base de $100K "
        f"({port['pnl_pct']:+.2f}%), {port['open_positions']} posiciones abiertas."
    )
    pipe = (
        f"Flujo de señales: {sig['count']} registradas esta semana en "
        f"{len(sig['symbols'])} símbolos."
    )
    tail = "Fuentes de datos: " + ", ".join(r.sources)
    tags = " ".join(f"#{t}" for t in r.tags if t.isascii())
    body = "\n\n".join([hook, symbol_line, book, pipe, tail, tags])
    return _append_tail(body, SHORT_DISCLAIMER_ES, LINKEDIN_LIMIT)


def format_linkedin(r: Report, language: str = "en") -> str:
    if not is_supported_language(language):
        raise ValueError(f"unsupported language: {language!r}")
    # Native Spanish templates exist for the report kinds actually declared
    # bilingual in scheduler.TARGET_LANGUAGES. Everything else falls back to
    # the glossary translator, which is safe but reads more as Spanglish.
    if language == "es":
        if r.kind == "weekly_crypto_brief":
            return _linkedin_crypto_es(r)
        # fall through — glossary translation of the EN template

    if r.kind == "weekly_crypto_brief":
        text = _linkedin_crypto(r)
    elif r.kind == "ai_intel":
        text = _linkedin_ai(r)
    elif r.kind == "security_digest":
        text = _linkedin_security(r)
    else:
        text = _append_tail(r.body, SHORT_DISCLAIMER, LINKEDIN_LIMIT)
    if language == "en":
        return text
    translated = Translator(language).translate(text, platform="linkedin")
    # Spanish is typically 15–30% longer; re-clip if we're now over budget.
    if len(translated) > LINKEDIN_LIMIT:
        translated = _shorten_to(translated, LINKEDIN_LIMIT)
    return translated


# ---------- Substack ----------


def format_substack(r: Report, language: str = "en") -> str:
    """Full markdown article: title, generated-at, body, sources."""
    if not is_supported_language(language):
        raise ValueError(f"unsupported language: {language!r}")
    header = f"# {r.title}\n\n_Generated {r.generated_at}_\n"
    body = r.body
    sources = "\n".join(f"- `{s}`" for s in r.sources) if r.sources else "(none)"
    footer = f"\n\n---\n\n## Data Sources\n\n{sources}\n\n## Disclaimer\n\n{MARKDOWN_DISCLAIMER}\n"
    text = "\n".join([header, body, footer])
    if language == "en":
        return text
    return Translator(language).translate(text, platform="substack")


# ---------- X thread ----------


def _split_tweets(parts: list[str], limit: int = X_TWEET_LIMIT) -> list[str]:
    """Pack parts into tweets up to limit chars, numbered N/M."""
    # First, assemble without numbering to see how many we'll need.
    merged: list[str] = []
    cur = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Leave 8 chars for numbering suffix like " (12/99)"
        cap = limit - 8
        if not cur:
            cur = p[:cap] if len(p) > cap else p
            continue
        joined = cur + " " + p
        if len(joined) <= cap:
            cur = joined
        else:
            merged.append(cur)
            cur = p[:cap] if len(p) > cap else p
    if cur:
        merged.append(cur)
    total = len(merged)
    return [f"{t} ({i + 1}/{total})" for i, t in enumerate(merged)]


def _x_crypto_parts(r: Report) -> list[str]:
    f = r.facts
    preds = f["predictions"]
    port = f["portfolio"]
    parts = ["Sapphire weekly crypto brief — thread."]
    if has_public_accuracy_track_record(preds):
        parts.append(
            f"Predictions: {preds['hits']}/{preds['total']} correct "
            f"({preds['accuracy'] * 100:.1f}% accuracy)."
        )
        for sym, v in preds["by_symbol"].items():
            acc = v["accuracy"] * 100
            parts.append(f"{sym}: {v['hits']}/{v['total']} ({acc:.1f}%).")
    else:
        parts.append(small_sample_accuracy_notice(preds, subject="The 6-factor TA model"))
        if preds["by_symbol"]:
            parts.append(
                "Coverage live across "
                + ", ".join(sorted(preds["by_symbol"]))
                + ". Per-symbol accuracy tables stay internal until the public sample clears 100 scored forecasts."
            )
    parts.append(
        f"Paper book: ${port['capital']:,.0f} "
        f"({port['pnl_pct']:+.2f}% vs $100K), "
        f"{port['open_positions']} open."
    )
    for pos in port["positions"][:3]:
        parts.append(
            f"{pos.get('symbol')} {pos.get('side')} @ "
            f"${pos.get('entry_price')} · SL ${pos.get('stop_loss')} "
            f"TP ${pos.get('take_profit')}."
        )
    parts.append("Sources: " + ", ".join(r.sources))
    return parts


def _x_ai_parts(r: Report) -> list[str]:
    f = r.facts
    parts = [
        f"Sapphire agent activity: {f['event_count']} events, "
        f"{len(f['agent_counts'])} agents, {len(f['device_counts'])} devices.",
    ]
    for agent, n in sorted(f["agent_counts"].items(), key=lambda x: -x[1])[:5]:
        parts.append(f"Agent {agent}: {n} events.")
    for dev, n in sorted(f["device_counts"].items(), key=lambda x: -x[1])[:3]:
        parts.append(f"Device {dev}: {n} events.")
    parts.append(f"{f['tracked_projects']} projects tracked.")
    parts.append("Source: " + ", ".join(r.sources))
    return parts


def _x_security_parts(r: Report) -> list[str]:
    f = r.facts
    parts = [
        f"Security digest: {f['count']} prioritized CVEs, "
        f"{f['exploited_in_wild']} in KEV, avg CVSS {f['avg_cvss']}."
    ]
    for item in f["top_cves"][:5]:
        kev = " KEV" if item["exploited"] else ""
        cvss = f" CVSS {item['cvss']}" if item.get("cvss") is not None else ""
        parts.append(
            f"{item['cve']}{kev}{cvss} — {item['title']} (prio {item['priority_score']:.2f})."
        )
    parts.append("Source: " + ", ".join(r.sources))
    return parts


# ---------- X thread (Spanish) ----------


def _x_crypto_parts_es(r: Report) -> list[str]:
    f = r.facts
    preds = f["predictions"]
    port = f["portfolio"]
    parts = ["Informe semanal de cripto de Sapphire — hilo."]
    if has_public_accuracy_track_record(preds):
        parts.append(
            f"Predicciones: {preds['hits']}/{preds['total']} correctas "
            f"({preds['accuracy'] * 100:.1f}% de precisión)."
        )
        for sym, v in preds["by_symbol"].items():
            acc = v["accuracy"] * 100
            parts.append(f"{sym}: {v['hits']}/{v['total']} ({acc:.1f}%).")
    else:
        parts.append(small_sample_accuracy_notice_es(preds, subject="El modelo TA de 6 factores"))
        if preds["by_symbol"]:
            parts.append(
                "Cobertura en vivo en "
                + ", ".join(sorted(preds["by_symbol"]))
                + ". Las tablas de acierto por símbolo se mantienen internas hasta que "
                "la muestra pública supere las 100 predicciones evaluadas."
            )
    parts.append(
        f"Cartera en papel: ${port['capital']:,.0f} "
        f"({port['pnl_pct']:+.2f}% vs $100K), "
        f"{port['open_positions']} posiciones abiertas."
    )
    for pos in port["positions"][:3]:
        side_es = "larga" if pos.get("side") == "long" else "corta"
        parts.append(
            f"{pos.get('symbol')} posición {side_es} en "
            f"${pos.get('entry_price')} · SL ${pos.get('stop_loss')} "
            f"TP ${pos.get('take_profit')}."
        )
    parts.append("Fuentes: " + ", ".join(r.sources))
    return parts


def _translate_market_pulse_body_es(body: str, facts: dict) -> str:
    """Native ES render of the market pulse body from the same facts.

    The EN body is assembled in `_render_market_pulse`; we mirror it here in
    Spanish so the pulse tweet reads natively instead of Spanglish.
    """
    preds = facts.get("predictions", {})
    port = facts.get("portfolio", {})
    forecasts = facts.get("forecasts") or []

    parts: list[str] = []
    for fc in forecasts:
        sym = fc.get("symbol", "?")
        d = fc.get("direction", "?")
        tp = fc.get("target_price")
        conf = fc.get("confidence", 0)
        tf = fc.get("timeframe", "24h")
        dir_es = {"bullish": "alcista", "bearish": "bajista", "neutral": "neutral"}.get(
            str(d).lower(), d
        )
        parts.append(
            f"{sym} pronóstico {dir_es} hacia ${tp} ({conf:.0%} de confianza, horizonte {tf})"
        )
    forecast_text = "; ".join(parts) if parts else "sin pronósticos en vivo hoy"

    holdings = port.get("open_positions", 0)
    book_val = port.get("total_value", 0)
    if has_public_accuracy_track_record(preds):
        performance_line = (
            f"El modelo acumula {preds.get('accuracy', 0.0) * 100:.1f}% de precisión "
            f"en {preds.get('total', 0)} señales evaluadas. "
        )
    else:
        performance_line = (
            small_sample_accuracy_notice_es(preds, subject="El modelo de predicción") + " "
        )
    return (
        f"Pulso de mercado de Sapphire: {forecast_text}. "
        f"{performance_line}"
        f"La cartera en papel va {port.get('pnl_pct', 0):+.2f}% en total "
        f"con {holdings} posiciones abiertas "
        f"y un valor de libro de ${book_val:,.0f}. "
        "Señales generadas a partir de RSI, MACD, bandas de Bollinger y cruces de medias móviles."
    )


def format_x_thread(r: Report, language: str = "en") -> list[str]:
    if not is_supported_language(language):
        raise ValueError(f"unsupported language: {language!r}")

    # Spanish path — native templates first for the bilingual report kinds.
    if language == "es":
        if r.kind == "weekly_crypto_brief":
            parts = _x_crypto_parts_es(r)
            parts.append(SHORT_DISCLAIMER_ES)
            return _split_tweets(parts)
        if r.kind == "market_pulse":
            body_es = _translate_market_pulse_body_es(r.body, r.facts).strip()
            return [_append_tail(body_es, SHORT_DISCLAIMER_ES, X_TWEET_LIMIT)]
        # fall through to glossary translation for the rest

    if r.kind == "weekly_crypto_brief":
        parts = _x_crypto_parts(r)
    elif r.kind == "ai_intel":
        parts = _x_ai_parts(r)
    elif r.kind == "security_digest":
        parts = _x_security_parts(r)
    elif r.kind == "market_pulse":
        single = [_append_tail(r.body.strip(), SHORT_DISCLAIMER, X_TWEET_LIMIT)]
        if language == "en":
            return single
        return Translator(language).translate_x_thread(single)
    else:
        parts = [r.title, r.body]
    parts.append(SHORT_DISCLAIMER)
    thread = _split_tweets(parts)
    if language == "en":
        return thread
    return Translator(language).translate_x_thread(thread)
