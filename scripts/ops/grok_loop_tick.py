#!/usr/bin/env python3
"""Grok project steering tick — update taskboard from live signals."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.grok.genome import LessonBook  # noqa: E402
from lib.grok.loop import DEFAULT_TASKS, render_markdown, tick  # noqa: E402
from lib.grok.policy import OrderProposal, evaluate_proposal  # noqa: E402
from lib.grok.research_worker import validate_research_manifest  # noqa: E402
from lib.grok.system_brief import bridge_inventory, policy_smoke  # noqa: E402

BOARD_JSON = ROOT / "projects/grok/data/taskboard.json"
BOARD_MD = ROOT / "projects/grok/TASKBOARD.md"
AUTO_MD = ROOT / "projects/grok/AUTOMATIONS.md"


def _detect_signals() -> dict:
    signals = {}
    signals["monorepo_bridge_tools_ok"] = (
        ROOT / "scripts/ops/sync_grok_web_exports.sh"
    ).is_file() and (ROOT / "scripts/ops/grok_bridge_status.py").is_file()
    dens = evaluate_proposal(OrderProposal("BINGBONG", "buy", "rh_l2", "l2_token", 1.0))
    dust = evaluate_proposal(OrderProposal("IBIT", "buy", "rh_agentic", "equity", 10.0))
    signals["policy_tests_ok"] = (
        (not dens.allow) and (not dust.allow) and (ROOT / "lib/grok/policy.py").is_file()
    )

    book = LessonBook.load(ROOT / "projects/grok/data/genome_seed_lessons.json")
    if book.summary()["count"] == 0:
        book.seed_axti_and_dens()
    signals["genome_seeded"] = book.summary()["count"] >= 2

    signals["windows_module_ok"] = (ROOT / "lib/grok/windows.py").is_file()
    good = {
        "schema_version": 1,
        "generated_at": "x",
        "host": "h",
        "git_sha": "a",
        "paper_only": True,
        "live_trading_enabled": False,
        "telegram_sends_enabled": False,
    }
    bad = {**good, "paper_only": False, "live_trading_enabled": True}
    signals["research_validator_ok"] = (
        validate_research_manifest(good)["ok"] and not validate_research_manifest(bad)["ok"]
    )
    signals["automations_catalog_ok"] = (ROOT / "lib/grok/automations.py").is_file()
    try:
        signals["streamline_ok"] = policy_smoke()["ok"] and bridge_inventory()["export_count"] >= 5
    except Exception:
        signals["streamline_ok"] = False

    # plant local-export receipt on recent git log (best-effort)
    try:
        log = subprocess.check_output(
            ["git", "-C", str(ROOT), "log", "--oneline", "-20"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        signals["bridge_local_export_seen"] = any(
            k in log.lower() for k in ("local-export", "plant-wire", "plant wire", "mac-bridge")
        )
    except Exception:
        signals["bridge_local_export_seen"] = False

    # force True only if explicit file marker
    marker = ROOT / "projects/grok/data/BRIDGE_PLANT_GREEN"
    if marker.is_file():
        signals["bridge_local_export_seen"] = True

    exp = ROOT / "data/grok-web-exports"
    signals["gate_wired"] = any(exp.glob("*free-reign-gate-wired*")) or any(
        exp.glob("*gate_order*wired*")
    )
    signals["genome_wired"] = any(exp.glob("*genome-closes-wired*"))
    signals["executor_reloaded"] = any(exp.glob("*executor-reload*"))
    signals["desk_fresh"] = any(exp.glob("*telemetry-desk*")) or any(exp.glob("*desk-refresh*"))

    return signals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write TASKBOARD.md + taskboard.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if BOARD_JSON.is_file():
        board = json.loads(BOARD_JSON.read_text(encoding="utf-8"))
    else:
        board = {"tasks": DEFAULT_TASKS, "dynamic_tasks": []}
    if not board.get("tasks"):
        board["tasks"] = list(DEFAULT_TASKS)

    signals = _detect_signals()
    out = tick(board, signals)

    if args.write:
        BOARD_JSON.parent.mkdir(parents=True, exist_ok=True)
        BOARD_JSON.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        BOARD_MD.write_text(render_markdown(out), encoding="utf-8")
        # refresh automations md
        from lib.grok.automations import catalog, summary

        lines = [
            "# Grok-related automations",
            "",
            f"_Count: {summary()['count']} · by_status: {summary()['by_status']}_",
            "",
            "| id | surface | status | action |",
            "|---|---|---|---|",
        ]
        for a in catalog():
            lines.append(f"| `{a['id']}` | {a['surface']} | {a['status']} | {a['action']} |")
        lines.append("")
        AUTO_MD.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {BOARD_MD.relative_to(ROOT)}", file=sys.stderr)
        print(f"wrote {BOARD_JSON.relative_to(ROOT)}", file=sys.stderr)
        print(f"wrote {AUTO_MD.relative_to(ROOT)}", file=sys.stderr)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(render_markdown(out))
        print("\n## Detected signals\n")
        for k, v in signals.items():
            print(f"- {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
