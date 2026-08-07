"""Unified system brief — alpha + policy + genome + automations + bridge.

Read-only composition for operators and densify. No broker I/O.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from lib.grok.automations import catalog as automation_catalog
from lib.grok.automations import summary as automation_summary
from lib.grok.genome import LessonBook
from lib.grok.policy import (
    FREE_REIGN_DEFAULTS,
    OrderProposal,
    evaluate_proposal,
    evaluate_scale_out,
)
from lib.grok.windows import evaluate_windows_acceptance
from lib.grok.blindspots import blindspot_scoreboard
from lib.grok.playbooks import playbook_summary

ROOT = Path(__file__).resolve().parents[2]
ALPHA_PATH = ROOT / "data" / "alpha" / "alpha_ledger.json"
EXPORT_DIR = ROOT / "data" / "grok-web-exports"
WIN_STATE = ROOT / "projects" / "grok" / "data" / "windows_acceptance.json"
GENOME_SEED = ROOT / "projects" / "grok" / "data" / "genome_seed_lessons.json"
BRIEF_JSON = ROOT / "projects" / "grok" / "data" / "SYSTEM_BRIEF.json"
BRIEF_MD = ROOT / "projects" / "grok" / "SYSTEM_BRIEF.md"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_alpha(path: Path = ALPHA_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"items": [], "invariants": [], "itemCount": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def critical_alpha(alpha: Mapping[str, Any], *, limit: int = 12) -> list[dict[str, Any]]:
    items = list(alpha.get("items") or [])
    items.sort(
        key=lambda x: (
            SEVERITY_ORDER.get(str(x.get("severity", "low")).lower(), 9),
            str(x.get("recency") or ""),
        )
    )
    # prefer open-ish statuses
    pref = []
    for it in items:
        if str(it.get("severity", "")).lower() in ("critical", "high"):
            pref.append(it)
    return pref[:limit]


def policy_smoke() -> dict[str, Any]:
    """Prove policy encodes dens / dust / L2 / AXTI / MOSS fences."""
    cases = {
        "dens_sonny": evaluate_proposal(
            OrderProposal("SONNY", "buy", "rh_l2", "l2_token", 5.0)
        ).as_dict(),
        "dust_ibit": evaluate_proposal(
            OrderProposal("IBIT", "buy", "rh_agentic", "equity", 10.0)
        ).as_dict(),
        "l2_over_cap": evaluate_proposal(
            OrderProposal("ETH", "buy", "rh_l2", "l2_token", 50.0)
        ).as_dict(),
        "moss_no_grant": evaluate_proposal(
            OrderProposal("X", "buy", "moss", "l2_token", 1.0, moss_grant_hours_left=-1)
        ).as_dict(),
        "axti_option_ok": evaluate_proposal(
            OrderProposal(
                "AXTI",
                "buy",
                "rh_agentic",
                "option",
                35.0,
                is_defined_risk_option=True,
            )
        ).as_dict(),
        "axti_scale_out": evaluate_scale_out(
            entry_premium=0.70, mark_premium=2.25, remaining_qty=2
        ).as_dict(),
    }
    expected_block = {
        "dens_sonny": "DENS_BLOCK",
        "dust_ibit": {"DUST_NO_REBUY", "OPTIONS_FIRST"},
        "l2_over_cap": "L2_NOTIONAL_CAP",
        "moss_no_grant": "MOSS_GRANT",
    }
    ok = True
    for k, codes in expected_block.items():
        code = cases[k]["code"]
        if isinstance(codes, set):
            if code not in codes or cases[k]["allow"]:
                ok = False
        else:
            if code != codes or cases[k]["allow"]:
                ok = False
    if cases["axti_option_ok"]["allow"] is not True:
        ok = False
    if cases["axti_scale_out"]["code"] != "AXTI_SCALE_OUT":
        ok = False
    return {"ok": ok, "cases": cases, "mandate": FREE_REIGN_DEFAULTS.get("mandate")}


def bridge_inventory(export_dir: Path = EXPORT_DIR) -> dict[str, Any]:
    files = sorted(export_dir.glob("*.md"))
    dated = [p for p in files if re.match(r"^\d{4}-\d{2}-\d{2}", p.name)]
    by_day: dict[str, int] = {}
    for p in dated:
        day = p.name[:10]
        by_day[day] = by_day.get(day, 0) + 1
    latest = [p.name for p in dated[-8:]]
    return {
        "export_count": len(dated),
        "by_day": by_day,
        "latest": latest,
        "plant_wired": (export_dir / "2026-08-06_plant-wire-receipt.md").is_file(),
        "mac_bridge_note": (export_dir / "2026-08-06_grok-mac-bridge-live.md").is_file(),
        "mac_bridge_service": (ROOT / "services/grok-bridge/app.py").is_file(),
        "plant_wire_receipt": (export_dir / "2026-08-06_plant-wire-receipt.md").is_file(),
        "gate_wired": any(export_dir.glob("*free-reign-gate-wired*")),
        "genome_wired": any(export_dir.glob("*genome-closes-wired*")),
        "executor_reloaded": any(export_dir.glob("*executor-reload*")),
        "gate_scope_accepted": (export_dir / "2026-08-06_operator-accept-gate-scope.md").is_file(),
    }


def automation_link_check() -> dict[str, Any]:
    """Check that automation paths resolve inside the monorepo when local."""
    rows = []
    ok_n = 0
    for a in automation_catalog():
        path = str(a.get("path") or "")
        exists: bool | None
        if path.startswith("~/") or path.startswith("ops-state"):
            exists = None  # plant-only
        else:
            # strip trailing slash; take first segment file or dir
            rel = path.rstrip("/")
            exists = (ROOT / rel).exists() if rel else False
        if exists is True:
            ok_n += 1
        rows.append(
            {
                "id": a["id"],
                "path": path,
                "status": a.get("status"),
                "exists_in_repo": exists,
                "action": a.get("action"),
            }
        )
    return {
        "summary": automation_summary(),
        "resolved_in_repo": ok_n,
        "items": rows,
    }


def alpha_policy_links(alpha_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map critical alpha to which policy fence covers it."""
    out = []
    for it in alpha_items:
        tags = [str(t).lower() for t in (it.get("tags") or [])]
        title = str(it.get("title") or "").lower()
        body = str(it.get("body") or "").lower()
        blob = " ".join(tags + [title, body, str(it.get("id"))])
        fences: list[str] = []
        if "dens" in blob or "sonny" in blob or "bingbong" in blob:
            fences.append("policy.is_dens_blocked / DENS_BLOCK")
        if "axti" in blob or "options" in blob or "scale-out" in blob or "scale out" in blob:
            fences.append("policy.evaluate_scale_out / AXTI")
        if "free-reign" in blob or "free_reign" in blob or "l2" in blob:
            fences.append("policy.evaluate_proposal rails rh_l2/rh_agentic")
        if "moss" in blob or "megaeth" in blob:
            fences.append("policy MOSS_GRANT")
        if "dust" in blob or "ibit" in blob:
            fences.append("policy DUST_NO_REBUY")
        if "windows" in blob or "datacenter" in blob or "win" in blob:
            fences.append("windows.evaluate_windows_acceptance")
        if "bridge" in blob or "grok" in blob or "gemini" in blob:
            fences.append("bridge exports + sync_grok_web_exports")
        if "genome" in blob or "self-improv" in blob or "harness" in blob:
            fences.append("genome.LessonBook")
        out.append(
            {
                "id": it.get("id"),
                "severity": it.get("severity"),
                "title": it.get("title"),
                "action": it.get("action"),
                "policy_links": fences or ["review_manually"],
            }
        )
    return out


def build_system_brief() -> dict[str, Any]:
    alpha = load_alpha()
    crit = critical_alpha(alpha)
    book = LessonBook.load(GENOME_SEED)
    if book.summary()["count"] == 0:
        book.seed_axti_and_dens()
    win_state = {}
    if WIN_STATE.is_file():
        win_state = json.loads(WIN_STATE.read_text(encoding="utf-8")).get("state") or {}

    policy = policy_smoke()
    bridge = bridge_inventory()
    autos = automation_link_check()
    links = alpha_policy_links(crit)

    streamline_score = 0
    streamline_max = 8
    if policy["ok"]:
        streamline_score += 1
    if bridge["plant_wired"]:
        streamline_score += 1
    if bridge.get("mac_bridge_service") or bridge.get("mac_bridge_note"):
        streamline_score += 1
    if book.summary()["count"] >= 2:
        streamline_score += 1
    if autos["resolved_in_repo"] >= 5:
        streamline_score += 1
    if len(crit) >= 5:
        streamline_score += 1
    if bridge.get("gate_wired"):
        streamline_score += 1
    if bridge.get("genome_wired"):
        streamline_score += 1

    next_actions = []
    if not policy["ok"]:
        next_actions.append("Repair lib.grok.policy smoke cases")
    if not bridge["plant_wired"]:
        next_actions.append("Plant: land plant-wire-receipt for densify beat")
    else:
        next_actions.append("Plant: keep 30m grok-web-bridge LaunchAgent green")
    if not bridge.get("gate_wired"):
        next_actions.append("Plant: wire gate_order into free-reign sole-writer (via=free_reign)")
    elif not bridge.get("executor_reloaded"):
        next_actions.append("Plant: reload rh-executor so gate_order is live in process")
    else:
        next_actions.append("Plant: free-reign gate loaded — Ari RH re-auth if hung on login; then monitor denials")
    if not any((ROOT / "data/grok-web-exports").glob("*telemetry-desk*")) and not any(
        (ROOT / "data/grok-web-exports").glob("*desk-refresh*")
    ):
        next_actions.append("Plant: fill desk.* via lib.grok.desk_projection (posture not stuck unknown)")
    if not bridge.get("genome_wired"):
        next_actions.append("Plant: wire record_closed_trade on full lot closes")
    else:
        next_actions.append("Plant: upgrade genome to source=broker when fill prices available")
    if not bridge.get("gate_scope_accepted"):
        next_actions.append("Operator: accept free_reign-only gate scope")
    next_actions.append("Win: run P0 acceptance before ARM L2")
    next_actions.append("Gemini: Phase 3 MC paint + data-truth UI (live pulse, stale honesty, operating rules)")
    next_actions.append("Plant: telemetry desk refresh via lib.grok.desk_projection each publish cycle")
    next_actions.append("GCP: cost posture min-instances=0 + Vertex idle skim")

    return {
        "generated_at": _utc(),
        "streamline": {
            "score": streamline_score,
            "max": streamline_max,
            "ratio": round(streamline_score / streamline_max, 2),
        },
        "mission": {
            "windows_dc": "docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md",
            "grok_project": "projects/grok/",
            "website_prompt": "docs/handoffs/GEMINI-CLOUDSHELL-WEBSITE-GCP-MASTER-PROMPT-2026-08-06.md",
        },
        "invariants": alpha.get("invariants") or [],
        "policy_smoke": policy,
        "genome": book.summary(),
        "windows": evaluate_windows_acceptance(win_state),
        "bridge": bridge,
        "automations": autos,
        "alpha_critical": links,
        "alpha_item_count": alpha.get("itemCount") or len(alpha.get("items") or []),
        "next_actions": next_actions,
        "blindspots": blindspot_scoreboard(),
        "playbooks": playbook_summary(),
    }


def render_brief_markdown(brief: Mapping[str, Any]) -> str:
    s = brief.get("streamline") or {}
    lines = [
        "# Sapphire × Grok — System Brief",
        "",
        f"_Generated: {brief.get('generated_at')}_",
        "",
        f"**Streamline score:** {s.get('score')}/{s.get('max')} ({s.get('ratio')})",
        "",
        "## Next actions",
        "",
    ]
    for a in brief.get("next_actions") or []:
        lines.append(f"- {a}")
    lines += ["", "## Policy smoke", ""]
    ps = brief.get("policy_smoke") or {}
    lines.append(f"- ok: **{ps.get('ok')}** · mandate: `{ps.get('mandate')}`")
    lines += ["", "## Genome", "", f"```json\n{json.dumps(brief.get('genome'), indent=2)}\n```"]
    lines += ["", "## Bridge", "", f"```json\n{json.dumps(brief.get('bridge'), indent=2)}\n```"]
    win = brief.get("windows") or {}
    lines += [
        "",
        "## Windows DC",
        "",
        f"- p0_ok: {win.get('p0_ok')} · arm_l2_allowed: {win.get('arm_l2_allowed')}",
        f"- failed_p0: {win.get('failed_p0')}",
    ]
    lines += ["", "## Critical alpha ↔ policy links", ""]
    for it in brief.get("alpha_critical") or []:
        lines.append(
            f"- `{it.get('id')}` **{it.get('severity')}** — {it.get('title')}"
        )
        lines.append(f"  - fences: {', '.join(it.get('policy_links') or [])}")
        if it.get("action"):
            lines.append(f"  - action: {it.get('action')}")
    auto = brief.get("automations") or {}
    lines += [
        "",
        "## Automations",
        "",
        f"- catalog: {auto.get('summary')} · resolved_in_repo: {auto.get('resolved_in_repo')}",
        "",
    ]
    for row in (auto.get("items") or [])[:12]:
        ex = row.get("exists_in_repo")
        mark = "✓" if ex is True else ("·" if ex is None else "✗")
        lines.append(f"- {mark} `{row.get('id')}` `{row.get('status')}` — {row.get('path')}")
    bs = brief.get("blindspots") or {}
    lines += ["", "## Blindspots", "", f"- scoreboard: `{bs}`", ""]
    pb = brief.get("playbooks") or {}
    lines += ["## Playbooks", "", f"- {pb}", ""]
    lines += ["", "## Invariants", ""]
    for inv in brief.get("invariants") or []:
        lines.append(f"- {inv}")
    lines.append("")
    return "\n".join(lines)


def write_brief(brief: Mapping[str, Any] | None = None) -> dict[str, Path]:
    brief = dict(brief or build_system_brief())
    BRIEF_JSON.parent.mkdir(parents=True, exist_ok=True)
    BRIEF_JSON.write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
    BRIEF_MD.write_text(render_brief_markdown(brief), encoding="utf-8")
    return {"json": BRIEF_JSON, "md": BRIEF_MD}
