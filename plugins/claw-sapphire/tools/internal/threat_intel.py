#!/usr/bin/env python3
"""Sapphire Threat Intelligence Tool — powered by cyber-threat-bot.

Wraps ~/Code/cyber-threat-bot as a plugin tool for the Sapphire ecosystem.
Provides live threat signals from CISA KEV, NVD, MITRE ATT&CK, Dark Reading.

Actions:
    latest   — Pull latest threat signals, ranked by urgency
    brief    — Deep-dive brief on a CVE or ATT&CK technique
    offers   — Revenue opportunities from current threats (needs profile)
    scan     — Quick scan: are there any critical threats right now?

Usage (stdin JSON):
    echo '{"action":"latest","days":7}' | python3 threat_intel.py
    echo '{"action":"brief","target":"CVE-2026-1340"}' | python3 threat_intel.py
    echo '{"action":"offers","profile":"profiles/ai-saas.json"}' | python3 threat_intel.py
    echo '{"action":"scan"}' | python3 threat_intel.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Add cyber-threat-bot to path
CTB_ROOT = Path.home() / "Code" / "cyber-threat-bot"
CTB_SRC = CTB_ROOT / "src"
if CTB_SRC.exists():
    sys.path.insert(0, str(CTB_SRC))

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
INTEL_DIR = SAPPHIRE_DIR / "data" / "threat_intel"
INTEL_DIR.mkdir(parents=True, exist_ok=True)

# Event bus — optional, degrades silently if unavailable
_EVENT_BUS_PATH = SAPPHIRE_DIR / "lib" / "core"
if str(_EVENT_BUS_PATH) not in sys.path:
    sys.path.insert(0, str(_EVENT_BUS_PATH))
try:
    from event_bus import get_bus as _get_event_bus

    _EVENT_BUS = _get_event_bus(source="threat_intel")
except Exception:
    _EVENT_BUS = None


def _publish_threats(records, *, trigger: str) -> None:
    """Emit one threat.detected event per critical record (exploited or CVSS >= 9)."""
    if _EVENT_BUS is None:
        return
    try:
        for r in records:
            score = getattr(r, "score", None) or 0.0
            exploited = bool(getattr(r, "exploited", False))
            if not (exploited or score >= 9.0):
                continue
            level = "critical" if exploited else "high"
            _EVENT_BUS.publish(
                "threat.detected",
                {
                    "id": getattr(r, "canonical_id", ""),
                    "title": (getattr(r, "title", "") or "")[:200],
                    "source": getattr(r, "source", ""),
                    "score": score,
                    "exploited": exploited,
                    "level": level,
                    "trigger": trigger,
                },
            )
    except Exception:
        pass  # telemetry must never break the tool


def _import_ctb():
    """Import cyber-threat-bot modules. Returns None tuple if not installed."""
    try:
        from cyber_threat_bot import briefs, render, scoring, sources

        return sources, render, briefs, scoring
    except ImportError:
        return None, None, None, None


def action_latest(days: int = 7, per_source: int = 8, fmt: str = "markdown") -> dict:
    """Pull latest threat signals from all sources."""
    sources, render, briefs, scoring = _import_ctb()
    if sources is None:
        return {
            "error": "cyber-threat-bot not installed. Run: pip install -e ~/Code/cyber-threat-bot"
        }

    records = sources.collect_latest_records(days=days, per_source=per_source)

    # Sort by priority
    records.sort(key=lambda r: scoring.record_priority(r), reverse=True)

    output = render.to_json(records) if fmt == "json" else render.render_latest_markdown(records)

    # Save to data dir
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = INTEL_DIR / f"latest_{ts}.md"
    out_path.write_text(output)

    _publish_threats(records, trigger="latest")

    return {
        "success": True,
        "records": len(records),
        "critical": sum(1 for r in records if r.exploited),
        "saved_to": str(out_path),
        "output": output[:2000],  # Truncate for plugin response
    }


def action_brief(target: str, fmt: str = "markdown") -> dict:
    """Generate a deep-dive brief on a CVE or ATT&CK technique."""
    sources, render, briefs_mod, scoring = _import_ctb()
    if sources is None:
        return {"error": "cyber-threat-bot not installed"}

    target = target.upper().strip()

    if target.startswith("CVE-"):
        record = sources.fetch_nvd_cve(target)
        # Enrich with CISA KEV if exploited
        kev = sources.find_cisa_kev_record(target)
        supporting = [kev] if kev else None
        output = briefs_mod.render_threat_brief_markdown(record, supporting=supporting)
    elif target.startswith("T") and target[1:].isdigit():
        record = sources.fetch_attack_technique(target)
        output = briefs_mod.render_technique_brief_markdown(record)
    else:
        return {"error": f"Unknown target format: {target}. Use CVE-YYYY-NNNN or TNNNN."}

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = INTEL_DIR / f"brief_{target}_{ts}.md"
    out_path.write_text(output)

    return {
        "success": True,
        "target": target,
        "saved_to": str(out_path),
        "output": output[:3000],
    }


def action_offers(profile_path: str | None = None, days: int = 7, per_source: int = 8) -> dict:
    """Generate revenue opportunities from current threats."""
    sources, render, briefs_mod, scoring = _import_ctb()
    if sources is None:
        return {"error": "cyber-threat-bot not installed"}

    from cyber_threat_bot.profiles import load_profile
    from cyber_threat_bot.revenue import build_revenue_opportunities, render_revenue_markdown

    profile = load_profile(profile_path)
    records = sources.collect_latest_records(days=days, per_source=per_source)
    opportunities = build_revenue_opportunities(records, profile)
    output = render_revenue_markdown(profile, opportunities)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = INTEL_DIR / f"offers_{ts}.md"
    out_path.write_text(output)

    return {
        "success": True,
        "opportunities": len(opportunities),
        "total_pipeline": sum(o.price_anchor for o in opportunities),
        "saved_to": str(out_path),
        "output": output[:2000],
    }


def action_scan() -> dict:
    """Quick scan: any critical threats right now?"""
    sources, render, briefs_mod, scoring = _import_ctb()
    if sources is None:
        return {"error": "cyber-threat-bot not installed"}

    records = sources.collect_latest_records(days=3, per_source=5)
    records.sort(key=lambda r: scoring.record_priority(r), reverse=True)

    critical = [r for r in records if r.exploited or (r.score and r.score >= 9.0)]

    _publish_threats(records, trigger="scan")

    summary = {
        "success": True,
        "total_signals": len(records),
        "critical_count": len(critical),
        "status": "CRITICAL" if critical else "NORMAL",
    }

    if critical:
        summary["critical_items"] = [
            {
                "id": r.canonical_id,
                "title": r.title[:100],
                "score": r.score,
                "exploited": r.exploited,
                "source": r.source,
            }
            for r in critical[:5]
        ]

    return summary


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        raw = '{"action": "scan"}'

    try:
        params = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        return

    action = params.get("action", "scan")

    if action == "latest":
        result = action_latest(
            days=params.get("days", 7),
            per_source=params.get("per_source", 8),
            fmt=params.get("format", "markdown"),
        )
    elif action == "brief":
        target = params.get("target")
        if not target:
            result = {"error": "Missing 'target' (e.g., CVE-2026-1340 or T1059)"}
        else:
            result = action_brief(target, fmt=params.get("format", "markdown"))
    elif action == "offers":
        result = action_offers(
            profile_path=params.get("profile"),
            days=params.get("days", 7),
            per_source=params.get("per_source", 8),
        )
    elif action == "scan":
        result = action_scan()
    else:
        result = {"error": f"Unknown action: {action}. Use: latest, brief, offers, scan"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
