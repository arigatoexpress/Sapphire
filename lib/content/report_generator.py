"""Data-driven report generation.

Every report is a dataclass containing:
  - structured `facts` (numeric, sourced)
  - a rendered markdown `body`
  - a `sources` list pinning every claim to a Sapphire data file

The formatters (linkedin/substack/x) consume these fields, not freeform text,
so platform renderings stay truthful to the underlying data.

Sources used (all from the repo's own data/):
  - data/trading_predictions.jsonl — prediction accuracy + latest forecasts
  - data/paper_portfolio.json      — live $100K paper trading state
  - data/trading_signals.jsonl     — TradingView → webhook pipeline signals
  - data/threat_intel/latest_*.md  — CVE feed digest (CISA KEV + NVD)
  - data/system_events.jsonl       — agent / service events
  - data/tracked_projects.json     — active projects ledger
  - data/market_pulse/pulse_*.md   — market pulse snapshots
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.core.provenance import write_envelope_sidecar

from .performance_policy import (
    has_public_accuracy_track_record,
    small_sample_accuracy_notice,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

# Commodity + macro tickers for weekly brief context
_MACRO_TICKERS: dict[str, tuple[str, str]] = {
    "GLD": ("Gold (GLD)", "commodity"),
    "SLV": ("Silver (SLV)", "commodity"),
    "USO": ("Oil (USO)", "commodity"),
    "URA": ("Uranium (URA)", "commodity"),
    "COPX": ("Copper (COPX)", "commodity"),
    "DX-Y.NYB": ("DXY", "macro"),
    "^VIX": ("VIX", "macro"),
    "^TNX": ("10Y Yield", "macro"),
}


def _fetch_macro_context() -> dict[str, Any]:
    """Fetch 5-day returns for commodity and macro tickers via yfinance."""
    try:
        import yfinance as yf  # optional — brief still renders without it

        tickers = list(_MACRO_TICKERS.keys())
        raw = yf.download(tickers, period="6d", interval="1d", progress=False, auto_adjust=True)
        closes = raw["Close"] if "Close" in raw.columns else raw
        result: dict[str, dict] = {}
        for ticker, (name, category) in _MACRO_TICKERS.items():
            if ticker not in closes.columns:
                continue
            col = closes[ticker].dropna()
            if len(col) < 2:
                continue
            pct = float((col.iloc[-1] - col.iloc[0]) / col.iloc[0] * 100)
            result[ticker] = {
                "name": name,
                "category": category,
                "price": round(float(col.iloc[-1]), 4),
                "pct_5d": round(pct, 2),
            }
        return result
    except Exception:
        return {}


# ---------- models ----------


@dataclass
class Report:
    kind: str
    title: str
    generated_at: str
    facts: dict[str, Any]
    body: str
    sources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "generated_at": self.generated_at,
            "facts": self.facts,
            "body": self.body,
            "sources": self.sources,
            "tags": self.tags,
        }


# ---------- data loaders ----------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def _latest_threat_file() -> Path | None:
    d = DATA_DIR / "threat_intel"
    if not d.exists():
        return None
    files = sorted(d.glob("latest_*.md"))
    return files[-1] if files else None


def _latest_pulse_file() -> Path | None:
    d = DATA_DIR / "market_pulse"
    if not d.exists():
        return None
    files = sorted(d.glob("pulse_*.md"))
    return files[-1] if files else None


def _persist_market_pulse(body: str, sources: list[str]) -> None:
    out_dir = DATA_DIR / "market_pulse"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pulse_{datetime.now(UTC).strftime('%Y%m%d')}.md"
    footer = "\n".join(f"- `{src}`" for src in sources) if sources else "(none)"
    text = f"{body}\n\n## Sources\n\n{footer}\n"
    try:
        path.write_text(text)
        write_envelope_sidecar(
            path,
            generator="lib.content.report_generator",
            source_paths=tuple(sources),
            metadata={"kind": "market_pulse"},
        )
    except OSError:
        pass


# ---------- fact extractors ----------


def prediction_stats(preds: list[dict]) -> dict[str, Any]:
    """Overall + per-symbol accuracy from scored predictions."""
    scored = [p for p in preds if "correct" in p]
    total = len(scored)
    hits = sum(1 for p in scored if p.get("correct"))
    per_sym: dict[str, dict[str, int]] = {}
    for p in scored:
        sym = p.get("symbol", "?")
        per_sym.setdefault(sym, {"hits": 0, "total": 0})
        per_sym[sym]["total"] += 1
        if p.get("correct"):
            per_sym[sym]["hits"] += 1
    per_sym_acc = {
        sym: {
            "hits": v["hits"],
            "total": v["total"],
            "accuracy": round(v["hits"] / v["total"], 3) if v["total"] else 0.0,
        }
        for sym, v in per_sym.items()
    }
    return {
        "total": total,
        "hits": hits,
        "accuracy": round(hits / total, 3) if total else 0.0,
        "by_symbol": per_sym_acc,
    }


def latest_forecasts(preds: list[dict], n_per_symbol: int = 1) -> list[dict]:
    """Most recent forecast per symbol (unscored or scored)."""
    by_sym: dict[str, list[dict]] = {}
    for p in sorted(preds, key=lambda r: r.get("timestamp", "")):
        by_sym.setdefault(p.get("symbol", "?"), []).append(p)
    out = []
    for rows in by_sym.values():
        for r in rows[-n_per_symbol:]:
            out.append(r)
    return out


def portfolio_snapshot(pf: dict) -> dict[str, Any]:
    positions = pf.get("positions", [])
    capital = pf.get("capital", 0.0)
    initial = pf.get("initial_capital", capital)
    pnl_pct = ((capital - initial) / initial * 100) if initial else 0.0
    return {
        "capital": capital,
        "initial_capital": initial,
        "pnl_pct": round(pnl_pct, 2),
        "open_positions": len(positions),
        "symbols": [p.get("symbol") for p in positions],
        "positions": positions,
    }


def signal_pipeline_stats(signals: list[dict]) -> dict[str, Any]:
    if not signals:
        return {"count": 0, "sources": {}, "symbols": {}}
    sources: dict[str, int] = {}
    symbols: dict[str, int] = {}
    for s in signals:
        sources[s.get("source", "?")] = sources.get(s.get("source", "?"), 0) + 1
        symbols[s.get("symbol", "?")] = symbols.get(s.get("symbol", "?"), 0) + 1
    return {
        "count": len(signals),
        "sources": sources,
        "symbols": symbols,
        "latest": signals[-1] if signals else None,
    }


_PRIO_RE = re.compile(r"Priority score:\s*([0-9.]+)")
_CVE_RE = re.compile(r"Canonical ID:\s*`([^`]+)`")
_TITLE_RE = re.compile(r"^###\s*\d+\.\s*(.+)$", re.MULTILINE)
_CVSS_RE = re.compile(r"CVSS base score:\s*([0-9.]+)")
_EXPLOITED_RE = re.compile(r"Exploited in the wild:\s*(yes|no)", re.IGNORECASE)
_SUMMARY_RE = re.compile(r"^- Summary:\s*(.+?)(?=\n- |\Z)", re.MULTILINE | re.DOTALL)
_SOURCES_RE = re.compile(r"^- Sources:\s*(.+)$", re.MULTILINE)
_EVIDENCE_DATE_RE = re.compile(r"^- Latest evidence date:\s*(\S+)", re.MULTILINE)
_REMEDIATION_RE = re.compile(r"CISA remediation due date:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


def threat_intel_summary(md_path: Path | None, limit: int = 5) -> dict[str, Any]:
    """Parse the prioritized queue from the latest threat digest.

    Extracts title, CVE ID, priority score, CVSS, exploited-in-wild flag, plus
    summary text, vendor label, source providers, latest-evidence date, and any
    CISA remediation deadline embedded in the summary.
    """
    if md_path is None or not md_path.exists():
        return {
            "path": None,
            "items": [],
            "count": 0,
            "total_in_queue": 0,
            "source_age_days": None,
            "source_generated_at": None,
        }
    txt = md_path.read_text()
    # Split into queue items by "### N." heading. Count all of them, surface `limit`.
    blocks = re.split(r"\n(?=###\s*\d+\.)", txt)
    total = sum(1 for b in blocks if _CVE_RE.search(b))
    items = []
    for b in blocks:
        title_m = _TITLE_RE.search(b)
        cve_m = _CVE_RE.search(b)
        if not (title_m and cve_m):
            continue
        prio_m = _PRIO_RE.search(b)
        cvss_m = _CVSS_RE.search(b)
        exp_m = _EXPLOITED_RE.search(b)
        sum_m = _SUMMARY_RE.search(b)
        src_m = _SOURCES_RE.search(b)
        ev_m = _EVIDENCE_DATE_RE.search(b)
        raw_title = title_m.group(1).strip()
        # Vendor is the leading segment before the first ":" (e.g. "Microsoft SharePoint").
        vendor = raw_title.split(":", 1)[0].strip() if ":" in raw_title else raw_title
        # CISA KEV titles come as "Vendor Product: Vendor Product ..." — collapse the dup.
        title = raw_title
        if ": " in title:
            head, tail = title.split(": ", 1)
            if tail.lower().startswith(head.lower()):
                title = f"{head} — {tail[len(head) :].lstrip(' :')}"
        summary_text = sum_m.group(1).strip() if sum_m else ""
        # Squeeze runs of whitespace/newlines from the summary block.
        summary_text = re.sub(r"\s+", " ", summary_text)
        rem_m = _REMEDIATION_RE.search(summary_text) if summary_text else None
        items.append(
            {
                "title": title,
                "vendor": vendor,
                "cve": cve_m.group(1).strip(),
                "priority_score": float(prio_m.group(1)) if prio_m else 0.0,
                "cvss": float(cvss_m.group(1)) if cvss_m else None,
                "exploited": (exp_m.group(1).lower() == "yes") if exp_m else False,
                "summary": summary_text,
                "sources": [s.strip() for s in src_m.group(1).split(",")] if src_m else [],
                "latest_evidence_date": ev_m.group(1) if ev_m else None,
                "remediation_due": rem_m.group(1) if rem_m else None,
            }
        )
        if len(items) >= limit:
            break

    # Derive freshness of the underlying threat pack itself.
    gen_m = re.search(r"Generated at:\s*(\S+)", txt)
    generated_at = gen_m.group(1) if gen_m else None
    source_age_days: float | None = None
    if generated_at:
        try:
            gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            source_age_days = round((datetime.now(UTC) - gen_dt).total_seconds() / 86400.0, 1)
        except ValueError:
            source_age_days = None

    return {
        "path": str(md_path),
        "items": items,
        "count": len(items),
        "total_in_queue": total,
        "source_age_days": source_age_days,
        "source_generated_at": generated_at,
    }


# ---------- report generators ----------


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def generate_weekly_crypto_brief() -> Report:
    """Weekly crypto brief: predictions, paper portfolio, signal pipeline."""
    preds = _read_jsonl(DATA_DIR / "trading_predictions.jsonl")
    pf = _read_json(DATA_DIR / "paper_portfolio.json", default={})
    sigs = _read_jsonl(DATA_DIR / "trading_signals.jsonl")
    pulse = _latest_pulse_file()

    stats = prediction_stats(preds)
    forecasts = latest_forecasts(preds, n_per_symbol=1)
    port = portfolio_snapshot(pf)
    sig = signal_pipeline_stats(sigs)
    macro = _fetch_macro_context()

    sources = [
        _rel(DATA_DIR / "trading_predictions.jsonl"),
        _rel(DATA_DIR / "paper_portfolio.json"),
        _rel(DATA_DIR / "trading_signals.jsonl"),
    ]
    if pulse is not None:
        sources.append(_rel(pulse))

    facts = {
        "predictions": stats,
        "latest_forecasts": forecasts,
        "portfolio": port,
        "signal_pipeline": sig,
        "macro_context": macro,
    }

    body = _render_crypto_brief(facts)

    return Report(
        kind="weekly_crypto_brief",
        title=f"Sapphire Weekly Crypto Brief — {datetime.now(UTC).strftime('%Y-%m-%d')}",
        generated_at=_now_iso(),
        facts=facts,
        body=body,
        sources=sources,
        tags=["crypto", "trading", "predictions", "weekly"],
    )


def generate_ai_intel_report() -> Report:
    """AI intel: inference routing, model usage, agent activity."""
    events = _read_jsonl(DATA_DIR / "system_events.jsonl")
    projects = _read_json(DATA_DIR / "tracked_projects.json", default={})

    # Agent tag counts
    agent_counts: dict[str, int] = {}
    device_counts: dict[str, int] = {}
    types: dict[str, int] = {}
    for e in events:
        for tag in e.get("tags", []):
            if tag.startswith("agent:"):
                agent_counts[tag[6:]] = agent_counts.get(tag[6:], 0) + 1
            elif tag.startswith("device:"):
                device_counts[tag[7:]] = device_counts.get(tag[7:], 0) + 1
        types[e.get("type", "?")] = types.get(e.get("type", "?"), 0) + 1

    project_count = 0
    projects_list: list[dict] = []
    if isinstance(projects, dict):
        projects_list = projects.get("projects", []) or []
    elif isinstance(projects, list):
        projects_list = projects
    project_count = len(projects_list)

    facts = {
        "event_count": len(events),
        "agent_counts": agent_counts,
        "device_counts": device_counts,
        "event_types": types,
        "tracked_projects": project_count,
    }

    sources = [
        _rel(DATA_DIR / "system_events.jsonl"),
        _rel(DATA_DIR / "tracked_projects.json"),
    ]

    body = _render_ai_intel(facts)

    return Report(
        kind="ai_intel",
        title=f"Sapphire AI Intelligence — {datetime.now(UTC).strftime('%Y-%m-%d')}",
        generated_at=_now_iso(),
        facts=facts,
        body=body,
        sources=sources,
        tags=["ai", "agents", "infra"],
    )


def generate_security_digest() -> Report:
    """Security digest: top CVEs, exploited-in-the-wild count, priority scores."""
    md_path = _latest_threat_file()
    intel = threat_intel_summary(md_path)

    exploited_count = sum(1 for i in intel["items"] if i["exploited"])
    avg_cvss = 0.0
    scored_cvss = [i["cvss"] for i in intel["items"] if i.get("cvss") is not None]
    if scored_cvss:
        avg_cvss = round(sum(scored_cvss) / len(scored_cvss), 2)

    # Group by vendor to catch clusters (e.g. multiple Fortinet CVEs on one patch cycle).
    vendor_counts: dict[str, int] = {}
    for i in intel["items"]:
        v = i.get("vendor") or "Unknown"
        vendor_counts[v] = vendor_counts.get(v, 0) + 1
    vendor_clusters = sorted(
        [(v, n) for v, n in vendor_counts.items() if n >= 2],
        key=lambda kv: (-kv[1], kv[0]),
    )

    # Overdue-remediation callout (CISA-tracked deadlines already past today).
    today_iso = datetime.now(UTC).strftime("%Y-%m-%d")
    overdue = [
        i for i in intel["items"] if i.get("remediation_due") and i["remediation_due"] < today_iso
    ]

    facts = {
        "top_cves": intel["items"],
        "count": intel["count"],
        "exploited_in_wild": exploited_count,
        "avg_cvss": avg_cvss,
        "total_in_queue": intel["total_in_queue"],
        "source_age_days": intel["source_age_days"],
        "source_generated_at": intel["source_generated_at"],
        "vendor_clusters": vendor_clusters,
        "overdue_count": len(overdue),
    }
    sources = []
    if intel["path"]:
        sources.append(_rel(Path(intel["path"])))

    body = _render_security(facts)

    return Report(
        kind="security_digest",
        title=f"Sapphire Security Digest — {datetime.now(UTC).strftime('%Y-%m-%d')}",
        generated_at=_now_iso(),
        facts=facts,
        body=body,
        sources=sources,
        tags=["security", "cve", "threat-intel"],
    )


def generate_market_pulse_tweet() -> Report:
    """Short daily tweet sourced from latest predictions + portfolio."""
    preds = _read_jsonl(DATA_DIR / "trading_predictions.jsonl")
    pf = _read_json(DATA_DIR / "paper_portfolio.json", default={})

    forecasts = latest_forecasts(preds, n_per_symbol=1)
    stats = prediction_stats(preds)
    port = portfolio_snapshot(pf)

    facts = {
        "forecasts": forecasts,
        "predictions": stats,
        "accuracy": stats["accuracy"],
        "portfolio": port,
    }
    sources = [
        _rel(DATA_DIR / "trading_predictions.jsonl"),
        _rel(DATA_DIR / "paper_portfolio.json"),
    ]
    body = _render_market_pulse(facts)
    _persist_market_pulse(body, sources)

    return Report(
        kind="market_pulse",
        title=f"Market Pulse — {datetime.now(UTC).strftime('%Y-%m-%d')}",
        generated_at=_now_iso(),
        facts=facts,
        body=body,
        sources=sources,
        tags=["crypto", "pulse", "daily"],
    )


# ---------- body renderers (markdown) ----------


def _fmt_pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def _render_crypto_brief(f: dict[str, Any]) -> str:
    preds = f["predictions"]
    forecasts = f["latest_forecasts"]
    port = f["portfolio"]
    sig = f["signal_pipeline"]

    lines = []
    lines.append("## Where the Predictions Stand")
    lines.append("")
    if has_public_accuracy_track_record(preds):
        lines.append(
            f"Across {preds['total']} scored forecasts, the 6-factor TA model hit "
            f"{preds['hits']} ({_fmt_pct(preds['accuracy'])}). Per symbol:"
        )
        for sym, v in preds["by_symbol"].items():
            lines.append(f"- {sym}: {v['hits']}/{v['total']} correct ({_fmt_pct(v['accuracy'])})")
    else:
        lines.append(small_sample_accuracy_notice(preds, subject="The 6-factor TA model"))
        if preds["by_symbol"]:
            lines.append(
                "Coverage is live across "
                + ", ".join(sorted(preds["by_symbol"]))
                + ". Per-symbol hit-rate tables stay internal until the public sample clears 100 scored forecasts."
            )
    lines.append("")

    if forecasts:
        lines.append("## Latest Forecasts")
        lines.append("")
        for fc in forecasts:
            sym = fc.get("symbol", "?")
            d = fc.get("direction", "?")
            conf = fc.get("confidence", 0.0)
            tp = fc.get("target_price")
            ep = fc.get("entry_price") or fc.get("actual_price")
            rsi = fc.get("rsi")
            extra = ""
            if rsi is not None:
                extra = f", RSI {rsi:.1f}"
            lines.append(f"- {sym} {d} → target ${tp} (entry ${ep}, conf {_fmt_pct(conf)}{extra})")
        lines.append("")

    lines.append("## Paper Portfolio ($100K book)")
    lines.append("")
    lines.append(
        f"Capital ${port['capital']:,.2f} vs start ${port['initial_capital']:,.2f} "
        f"({port['pnl_pct']:+.2f}%). {port['open_positions']} open: "
        f"{', '.join(port['symbols']) if port['symbols'] else '—'}."
    )
    for pos in port["positions"]:
        lines.append(
            f"- {pos.get('symbol')} {pos.get('side')} "
            f"@ ${pos.get('entry_price')} · SL ${pos.get('stop_loss')} "
            f"TP ${pos.get('take_profit')} · size ${pos.get('size_usd'):,.0f}"
        )
    lines.append("")

    lines.append("## Signal Pipeline")
    lines.append("")
    lines.append(
        f"{sig['count']} signals logged this period. "
        f"Sources: {sig['sources']}. Symbols seen: {list(sig['symbols'].keys())}."
    )
    if sig.get("latest"):
        last = sig["latest"]
        lines.append(
            f"Most recent: {last.get('symbol')} {last.get('action')} "
            f"conf {last.get('confidence')} via {last.get('source')}."
        )
    return "\n".join(lines)


def _render_ai_intel(f: dict[str, Any]) -> str:
    lines = []
    lines.append("## Agent Activity")
    lines.append("")
    lines.append(
        f"Logged {f['event_count']} system events across "
        f"{len(f['agent_counts'])} agents and {len(f['device_counts'])} devices."
    )
    if f["agent_counts"]:
        top_agents = sorted(f["agent_counts"].items(), key=lambda x: -x[1])[:5]
        lines.append("Top agents:")
        for name, n in top_agents:
            lines.append(f"- {name}: {n} events")
    lines.append("")

    lines.append("## Inference Mesh")
    lines.append("")
    if f["device_counts"]:
        for dev, n in sorted(f["device_counts"].items(), key=lambda x: -x[1]):
            lines.append(f"- {dev}: {n} events")
    else:
        lines.append("No device-tagged events in window.")
    lines.append("")

    lines.append("## Projects Tracked")
    lines.append("")
    lines.append(
        f"{f['tracked_projects']} projects in the active ledger (data/tracked_projects.json)."
    )
    return "\n".join(lines)


def _render_security(f: dict[str, Any]) -> str:
    total = f.get("total_in_queue") or f["count"]
    age = f.get("source_age_days")
    age_note = ""
    if age is not None:
        if age < 1.5:
            age_note = f"Threat pack is {age:.1f} day old."
        elif age <= 3.0:
            age_note = f"Threat pack is {age:.1f} days old."
        else:
            age_note = (
                f"Threat pack is {age:.1f} days old; upstream refresh may have lagged this cycle."
            )

    lines: list[str] = []

    # Executive summary — the "so what" up top so a skim reads clean.
    lines.append("## Executive Summary")
    lines.append("")
    exec_bits = [
        f"{f['count']} of {total} prioritized CVEs surfaced this cycle",
        f"All {f['exploited_in_wild']} are actively exploited (CISA KEV)"
        if f["exploited_in_wild"] == f["count"] and f["count"]
        else f"{f['exploited_in_wild']} actively exploited (CISA KEV)",
        f"Average CVSS {f['avg_cvss']}",
    ]
    if f.get("overdue_count", 0):
        exec_bits.append(f"{f['overdue_count']} past CISA remediation deadline")
    lines.append(". ".join(exec_bits) + ".")
    if age_note:
        lines.append("")
        lines.append(f"_{age_note}_")
    lines.append("")

    # Vendor-cluster insight only fires when there's a real pattern.
    clusters = f.get("vendor_clusters") or []
    if clusters:
        cluster_text = "; ".join(f"{n}x {v}" for v, n in clusters)
        lines.append(
            "**Pattern to watch.** Multiple entries share a vendor this cycle "
            f"({cluster_text}) — a single patch window likely covers each cluster."
        )
        lines.append("")

    lines.append("## Top Priority CVEs")
    lines.append("")
    for item in f["top_cves"]:
        tags: list[str] = []
        if item.get("cvss") is not None:
            tags.append(f"CVSS {item['cvss']}")
        if item.get("exploited"):
            tags.append("CISA KEV")
        tags.append(f"priority {item['priority_score']:.2f}")
        tag_str = " · ".join(tags)

        lines.append(f"### {item['cve']} — {item['title']}")
        lines.append(f"_{tag_str}_")
        if item.get("summary"):
            lines.append("")
            lines.append(item["summary"])
        meta_bits: list[str] = []
        if item.get("remediation_due"):
            meta_bits.append(f"CISA remediation due **{item['remediation_due']}**")
        if item.get("latest_evidence_date"):
            meta_bits.append(f"latest evidence {item['latest_evidence_date']}")
        if item.get("sources"):
            meta_bits.append("via " + ", ".join(item["sources"]))
        if meta_bits:
            lines.append("")
            lines.append("_" + " · ".join(meta_bits) + "._")
        lines.append("")

    # Defender guidance is fixed but concrete — no fluff.
    lines.append("## Mitigation Priorities")
    lines.append("")
    lines.append(
        "1. Confirm each KEV-listed CVE against your asset inventory before the CISA "
        "deadline; missed deadlines are the fingerprint most commonly cited in incident "
        "reviews."
    )
    lines.append(
        "2. Where multiple CVEs share a vendor, treat them as one patch window — do not "
        "ship staged partial fixes that leave a known-exploited variant live."
    )
    lines.append(
        "3. For network-edge devices (Fortinet, SonicWall, F5, Ivanti), verify management "
        "interfaces are not internet-exposed even after patching; edge-device compromise is "
        "still the top public-sector initial-access vector."
    )
    return "\n".join(lines)


def _render_market_pulse(f: dict[str, Any]) -> str:
    preds = f.get("predictions", {})
    parts = []
    for fc in f["forecasts"]:
        sym = fc.get("symbol", "?")
        d = fc.get("direction", "?")
        tp = fc.get("target_price")
        conf = fc.get("confidence", 0)
        tf = fc.get("timeframe", "24h")
        parts.append(f"{sym} forecast {d} toward ${tp} ({conf:.0%} confidence, {tf} horizon)")
    forecast_text = "; ".join(parts) if parts else "no live forecasts available today"
    port = f["portfolio"]
    holdings = port.get("open_positions", 0)
    book_val = port.get("total_value", 0)
    if has_public_accuracy_track_record(preds):
        performance_line = (
            f"Prediction model running at {_fmt_pct(preds.get('accuracy', 0.0))} accuracy "
            f"across {preds.get('total', 0)} scored signals. "
        )
    else:
        performance_line = small_sample_accuracy_notice(preds, subject="The prediction model") + " "
    return (
        f"Sapphire market pulse: {forecast_text}. "
        f"{performance_line}"
        f"Paper portfolio at {port['pnl_pct']:+.2f}% overall "
        f"with {holdings} open positions "
        f"and ${book_val:,.0f} total book value. "
        f"Signals generated from RSI, MACD, Bollinger, and moving average crossovers."
    )
