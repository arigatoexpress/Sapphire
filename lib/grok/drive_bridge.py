"""Grok ↔ Google Drive densify packager (no Drive API keys in monorepo).

Builds a local pack under data/grok-drive-pack/ that plant or Grok connectors
can upload into the Sapphire/Grok Bridge folder tree. Never includes secrets.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "data" / "grok-web-exports"
PACK = ROOT / "data" / "grok-drive-pack"
FOLDER_REG = ROOT / "projects" / "grok" / "data" / "drive_bridge_folders.json"

# crude secret patterns — refuse to copy matching files
_SECRETISH = re.compile(
    r"(api[_-]?key|private[_-]?key|BEGIN (RSA |OPENSSH )?PRIVATE|password\s*=|secret\s*=|"
    r"xai-|sk-[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z_-]{20,})",
    re.I,
)


def _utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_folder_registry() -> dict[str, Any]:
    if FOLDER_REG.is_file():
        return json.loads(FOLDER_REG.read_text(encoding="utf-8"))
    return {}


def _safe_text(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if _SECRETISH.search(text):
        return False
    return path.suffix.lower() not in {".pem", ".p12", ".key", ".env"}


def _copy_safe(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    if not _safe_text(src):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def build_drive_pack(*, max_exports: int = 40) -> dict[str, Any]:
    """Materialize data/grok-drive-pack/ for Drive upload."""
    reg = load_folder_registry()
    if PACK.exists():
        shutil.rmtree(PACK)
    for sub in (
        "01-exports",
        "02-handoffs",
        "03-briefs-and-rules",
        "04-audits",
        "05-operator-index",
    ):
        (PACK / sub).mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    skipped: list[str] = []

    # exports
    md_files = sorted(EXPORTS.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in md_files[:max_exports]:
        if _copy_safe(p, PACK / "01-exports" / p.name):
            copied.append(f"01-exports/{p.name}")
        else:
            skipped.append(p.name)

    # handoffs of interest
    handoff_globs = (
        "docs/handoffs/*GROK*",
        "docs/handoffs/*GEMINI*",
        "docs/handoffs/*CLAUDE*",
        "docs/handoffs/*GCP*",
        "docs/strategy/PUBLIC-TRADING*",
        "docs/strategy/HOLISTIC*",
        "docs/strategy/WINDOWS*",
        "docs/strategy/PAPER*",
    )
    for pattern in handoff_globs:
        for p in ROOT.glob(pattern):
            if p.is_file() and _copy_safe(p, PACK / "02-handoffs" / p.name):
                copied.append(f"02-handoffs/{p.name}")

    # briefs
    for rel in (
        "projects/grok/SYSTEM_BRIEF.md",
        "projects/grok/NEXT.md",
        "projects/grok/TASKBOARD.md",
        "projects/grok/AUTOMATIONS.md",
        "projects/grok/data/public_operating_rules.json",
        "projects/grok/data/free_reign_policy.json",
        "projects/grok/data/playbooks.json",
        "projects/grok/data/drive_bridge_folders.json",
    ):
        p = ROOT / rel
        if p.is_file() and _copy_safe(p, PACK / "03-briefs-and-rules" / p.name):
            copied.append(f"03-briefs-and-rules/{p.name}")

    # audits
    for rel in (
        "projects/grok/data/public_surface_audit.json",
        "projects/grok/data/desk_projection_example.json",
        "projects/grok/data/telemetry_publisher_checklist.json",
        "projects/grok/data/blindspots.json",
    ):
        p = ROOT / rel
        if p.is_file() and _copy_safe(p, PACK / "04-audits" / p.name):
            copied.append(f"04-audits/{p.name}")

    index = _render_index(reg, copied, skipped)
    (PACK / "05-operator-index" / "INDEX.md").write_text(index, encoding="utf-8")
    (PACK / "INDEX.md").write_text(index, encoding="utf-8")
    copied.append("05-operator-index/INDEX.md")

    manifest = {
        "generated_at": _utc(),
        "copied_count": len(copied),
        "skipped_count": len(skipped),
        "copied": copied,
        "skipped_secretish_or_missing": skipped,
        "drive_folders": reg.get("lanes") or {},
        "grok_bridge_url": (reg.get("grok_bridge") or {}).get("url"),
    }
    (PACK / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _render_index(reg: dict[str, Any], copied: list[str], skipped: list[str]) -> str:
    gb = reg.get("grok_bridge") or {}
    lines = [
        "# Sapphire × Grok Bridge — Google Drive operator index",
        "",
        f"_Generated: {_utc()}_",
        "",
        f"**Drive folder:** [{gb.get('name', 'Grok Bridge')}]({gb.get('url', '')})",
        "",
        "## What this is",
        "",
        "Local densify pack (`data/grok-drive-pack/`) mirroring monorepo Grok web exports,",
        "handoffs, briefs, and public-safe audits into Google Drive so mobile / Drive / Grok",
        "connectors share one operator surface — **without secrets or trading authority**.",
        "",
        "## Folder lanes",
        "",
    ]
    for name, meta in (reg.get("lanes") or {}).items():
        lines.append(f"- **{name}** — {meta.get('purpose')} — [open]({meta.get('url')})")
    lines += [
        "",
        "## How to sync (plant)",
        "",
        "```bash",
        "cd ~/Code/Sapphire && git pull --ff-only",
        "python3 scripts/ops/grok_drive_pack.py --write",
        "# then either:",
        "#  - rclone copy data/grok-drive-pack/ gdrive:Sapphire/Grok\\ Bridge/ ...",
        "#  - or Google Drive desktop sync of the pack folder",
        "#  - or Grok connector: create/update files into the lane folder IDs",
        "```",
        "",
        "## Grok web automations",
        "",
        "| Automation | Role |",
        "|---|---|",
        "| densify 30m → Knowledge | plant inbox |",
        "| grok-drive-pack | materialize Drive-ready pack |",
        "| Drive connector (this chat) | list/search/read; folder create |",
        "| mac-bridge :19998 | live Grok CLI (not Drive) |",
        "",
        "## Fences",
        "",
    ]
    for f in reg.get("fences") or []:
        lines.append(f"- {f}")
    lines += [
        "",
        "## Pack stats",
        "",
        f"- copied: **{len(copied)}**",
        f"- skipped: **{len(skipped)}**",
        "",
        "## Related monorepo",
        "",
        "- `lib/grok/drive_bridge.py`",
        "- `scripts/ops/grok_drive_pack.py`",
        "- `projects/grok/data/drive_bridge_folders.json`",
        "",
    ]
    return "\n".join(lines) + "\n"


def pack_summary() -> dict[str, Any]:
    man = PACK / "MANIFEST.json"
    if man.is_file():
        return json.loads(man.read_text(encoding="utf-8"))
    return {"exists": False}
