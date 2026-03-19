from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Mapping, Sequence

from app.models import ChatConfig, ScoredNews


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _render_watchlist(config: ChatConfig) -> str:
    aster = ", ".join(config.aster_assets) if config.aster_assets else "none"
    lighter = ", ".join(config.lighter_assets) if config.lighter_assets else "none"
    extras = ", ".join(config.extra_keywords) if config.extra_keywords else "none"
    return f"Aster: {aster} | Lighter: {lighter} | Extra keywords: {extras}"


def _mentions_line(config: ChatConfig, text: str) -> str:
    if not text:
        return ""
    haystack = text.upper()
    watch = list(dict.fromkeys([*(config.aster_assets or []), *(config.lighter_assets or [])]))
    if not watch:
        return ""

    mentions: list[str] = []
    for sym in watch:
        s = (sym or "").strip().upper()
        if not s:
            continue
        # Word-ish boundary match (avoid SOL in SOLID, etc).
        if re.search(rf"(?<![A-Z0-9]){re.escape(s)}(?![A-Z0-9])", haystack):
            mentions.append(s)
        if len(mentions) >= 8:
            break
    return ", ".join(mentions)


def format_digest_message(
    chat_config: ChatConfig,
    scored_news: Sequence[ScoredNews],
    top_k: int,
    generated_at: datetime,
    summary_overrides: Mapping[str, str] | None = None,
) -> str:
    title = "<b>Sapphire Alpha Digest</b>"
    stamp = f"<i>{generated_at.strftime('%Y-%m-%d %H:%M UTC')}</i>"
    watchlist = html.escape(_render_watchlist(chat_config))

    if not scored_news:
        return (
            f"{title}\n{stamp}\n\n"
            "No high-confidence headlines matched your Aster/Lighter watchlist in the current window.\n"
            f"<i>{watchlist}</i>\n\n"
            "Use /setaster, /setlighter, /setkeywords to tune your feed."
        )

    lines = [title, stamp, f"<i>{watchlist}</i>", ""]
    for idx, scored in enumerate(scored_news[:top_k], start=1):
        item = scored.item
        safe_title = html.escape(_trim(item.title, 180))
        safe_url = html.escape(item.url, quote=True)
        safe_source = html.escape(item.source.name)
        safe_rationale = html.escape(_trim(scored.rationale, 220))
        summary = (summary_overrides.get(item.id) if summary_overrides else None) or item.summary
        safe_summary = html.escape(_trim(summary, 240)) if summary else ""
        mentions = _mentions_line(chat_config, f"{item.title} {summary or ''}")

        lines.append(f"{idx}. <a href=\"{safe_url}\">{safe_title}</a>")
        lines.append(
            f"   {safe_source} | Alpha {scored.alpha_score}/100 | {scored.bias} ({scored.confidence})"
        )
        if mentions:
            lines.append(f"   Mentions: {html.escape(mentions)}")
        lines.append(f"   Why: {safe_rationale}")
        if safe_summary:
            lines.append(f"   Summary: {safe_summary}")

    lines.append("")
    lines.append("<i>Complementary signal only. Not financial advice.</i>")

    output = "\n".join(lines)
    return _trim(output, 3900)


def format_watchlist_message(chat_config: ChatConfig) -> str:
    return f"<b>Current watchlist</b>\n{html.escape(_render_watchlist(chat_config))}"


def format_alpha_stream_message(
    chat_config: ChatConfig,
    alpha_stream: Mapping[str, object],
    *,
    max_chars: int = 3900,
) -> str:
    title = "<b>Sapphire Unified Alpha Stream</b>"
    generated_at = alpha_stream.get("generated_at")
    stamp = ""
    if isinstance(generated_at, str) and generated_at.strip():
        stamp = f"<i>{html.escape(generated_at.replace('T', ' ').replace('+00:00', ' UTC'))}</i>"
    watchlist = html.escape(_render_watchlist(chat_config))
    summary = alpha_stream.get("summary") if isinstance(alpha_stream.get("summary"), Mapping) else {}
    items = alpha_stream.get("items") if isinstance(alpha_stream.get("items"), Sequence) else []
    routes = alpha_stream.get("routes") if isinstance(alpha_stream.get("routes"), Mapping) else {}

    lines = [title]
    if stamp:
        lines.append(stamp)
    lines.extend(
        [
            f"<i>{watchlist}</i>",
            (
                f"Signals: {int(summary.get('returned_count', 0) or 0)}/{int(summary.get('total_scored', 0) or 0)}"
                f" | watchlist hits: {int(summary.get('watchlist_hit_count', 0) or 0)}"
            ),
            "",
        ]
    )
    for idx, raw in enumerate(items[:10], start=1):
        if not isinstance(raw, Mapping):
            continue
        safe_title = html.escape(_trim(str(raw.get("title") or "Untitled"), 180))
        safe_url = html.escape(str(raw.get("url") or ""), quote=True)
        safe_source = html.escape(str(raw.get("source") or "unknown"))
        score = int(raw.get("alpha_score", 0) or 0)
        bias = html.escape(str(raw.get("bias") or ""))
        confidence = html.escape(str(raw.get("confidence") or ""))
        assets = [str(a) for a in (raw.get("asset_hits") or []) if str(a).strip()]
        watch_hits = [str(a) for a in (raw.get("watchlist_asset_hits") or []) if str(a).strip()]
        actionability = html.escape(str(raw.get("actionability") or "monitor"))
        targets = [str(s) for s in (raw.get("target_streams") or []) if str(s).strip()]
        lines.append(f"{idx}. <a href=\"{safe_url}\">{safe_title}</a>")
        lines.append(f"   {safe_source} | Alpha {score}/100 | {bias} ({confidence})")
        if assets:
            lines.append(f"   Assets: {html.escape(', '.join(assets[:6]))}")
        if watch_hits:
            lines.append(f"   Watchlist hits: {html.escape(', '.join(watch_hits[:6]))}")
        lines.append(f"   Action: {actionability}")
        if targets:
            lines.append(f"   Routes: {html.escape(', '.join(targets[:6]))}")
    lines.extend(
        [
            "",
            (
                "Routes: "
                f"{html.escape(str(routes.get('telegram_command') or '/alphastream'))} | "
                f"{html.escape(str(routes.get('kimi_action') or 'alpha_stream'))} | "
                f"{html.escape(str(routes.get('system_endpoint') or '/api/alpha-stream'))}"
            ),
            "<i>Shared signal feed for frontend, Telegram, and agent/trader consumers.</i>",
        ]
    )
    return _trim("\n".join(lines), max_chars)
