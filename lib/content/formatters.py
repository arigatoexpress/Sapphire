"""Platform formatters.

Each formatter takes a Report and produces a single string suited for the
target platform's constraints:

  - LinkedIn: up to 1300 characters, hook-led, line-broken, hashtags allowed.
  - Substack: full markdown article with sources footer.
  - X: thread — list of tweets, each <=270 chars so they post cleanly.

Formatters do not invent facts; they only draw from `report.facts` and
`report.body`. That keeps platform output in sync with the data.
"""

from __future__ import annotations

from .report_generator import Report

LINKEDIN_LIMIT = 1300
X_TWEET_LIMIT = 270  # leave headroom under the hard 280


# ---------- LinkedIn ----------

def _shorten_to(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    # Cut at the last sentence-ending before the limit.
    cut = text[:limit].rsplit(".", 1)[0]
    if len(cut) < limit * 0.6:
        cut = text[: limit - 1]
    return cut.rstrip() + "…"


def _linkedin_crypto(r: Report) -> str:
    f = r.facts
    preds = f["predictions"]
    port = f["portfolio"]
    sig = f["signal_pipeline"]
    hook = (
        f"{preds['total']} scored predictions later, Sapphire's 6-factor TA "
        f"model is at {preds['accuracy'] * 100:.1f}% accuracy."
    )
    symbol_line = " · ".join(
        f"{s} {v['hits']}/{v['total']}" for s, v in preds["by_symbol"].items()
    )
    book = (
        f"Paper book: ${port['capital']:,.0f} on a $100K start "
        f"({port['pnl_pct']:+.2f}%), {port['open_positions']} open."
    )
    pipe = (
        f"Signal pipeline: {sig['count']} logged this week, "
        f"{len(sig['symbols'])} symbols."
    )
    tail = "Data sources: " + ", ".join(r.sources)
    tags = " ".join(f"#{t}" for t in r.tags if t.isascii())
    body = "\n\n".join([hook, symbol_line, book, pipe, tail, tags])
    return _shorten_to(body, LINKEDIN_LIMIT)


def _linkedin_ai(r: Report) -> str:
    f = r.facts
    top_agent = (
        max(f["agent_counts"].items(), key=lambda x: x[1])
        if f["agent_counts"]
        else ("—", 0)
    )
    hook = (
        f"{f['event_count']} agent events across "
        f"{len(f['agent_counts'])} agents and "
        f"{len(f['device_counts'])} devices this cycle."
    )
    lead = f"Top agent by volume: {top_agent[0]} with {top_agent[1]} events."
    mesh = (
        "Mesh mix — "
        + ", ".join(f"{k}:{v}" for k, v in f["device_counts"].items())
        if f["device_counts"]
        else "Mesh idle."
    )
    proj = f"{f['tracked_projects']} active projects in the ledger."
    tail = "Source: " + ", ".join(r.sources)
    tags = " ".join(f"#{t}" for t in r.tags if t.isascii())
    return _shorten_to(
        "\n\n".join([hook, lead, mesh, proj, tail, tags]), LINKEDIN_LIMIT
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
    return _shorten_to(
        "\n\n".join([hook, "\n".join(tops), tail, tags]), LINKEDIN_LIMIT
    )


def format_linkedin(r: Report) -> str:
    if r.kind == "weekly_crypto_brief":
        return _linkedin_crypto(r)
    if r.kind == "ai_intel":
        return _linkedin_ai(r)
    if r.kind == "security_digest":
        return _linkedin_security(r)
    return _shorten_to(r.body, LINKEDIN_LIMIT)


# ---------- Substack ----------

def format_substack(r: Report) -> str:
    """Full markdown article: title, generated-at, body, sources."""
    header = f"# {r.title}\n\n_Generated {r.generated_at}_\n"
    body = r.body
    sources = "\n".join(f"- `{s}`" for s in r.sources) if r.sources else "(none)"
    footer = f"\n\n---\n\n## Data Sources\n\n{sources}\n"
    return "\n".join([header, body, footer])


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
    parts = [
        "Sapphire weekly crypto brief — thread.",
        f"Predictions: {preds['hits']}/{preds['total']} correct "
        f"({preds['accuracy'] * 100:.1f}% accuracy).",
    ]
    for sym, v in preds["by_symbol"].items():
        acc = v["accuracy"] * 100
        parts.append(f"{sym}: {v['hits']}/{v['total']} ({acc:.1f}%).")
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
            f"{item['cve']}{kev}{cvss} — {item['title']} "
            f"(prio {item['priority_score']:.2f})."
        )
    parts.append("Source: " + ", ".join(r.sources))
    return parts


def format_x_thread(r: Report) -> list[str]:
    if r.kind == "weekly_crypto_brief":
        parts = _x_crypto_parts(r)
    elif r.kind == "ai_intel":
        parts = _x_ai_parts(r)
    elif r.kind == "security_digest":
        parts = _x_security_parts(r)
    elif r.kind == "market_pulse":
        # Market pulse is a single tweet.
        single = r.body.strip()
        if len(single) > X_TWEET_LIMIT:
            single = single[: X_TWEET_LIMIT - 1] + "…"
        return [single]
    else:
        parts = [r.title, r.body]
    return _split_tweets(parts)
