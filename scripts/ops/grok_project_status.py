#!/usr/bin/env python3
"""Roll-up status for the dedicated Grok project."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.grok.automations import summary as auto_summary  # noqa: E402
from lib.grok.genome import LessonBook  # noqa: E402
from lib.grok.policy import OrderProposal, evaluate_proposal  # noqa: E402
from lib.grok.research_worker import validate_research_manifest  # noqa: E402
from lib.grok.windows import evaluate_windows_acceptance  # noqa: E402


def main() -> int:
    book = LessonBook.load(ROOT / "projects/grok/data/genome_seed_lessons.json")
    if book.summary()["count"] == 0:
        book.seed_axti_and_dens()

    dens = evaluate_proposal(
        OrderProposal("SONNY", "buy", "rh_l2", "l2_token", 5.0, contract_address="0x9763abc")
    )
    good = json.loads(
        (ROOT / "projects/grok/fixtures/research_worker_manifest_good.json").read_text()
    )
    bad = json.loads(
        (ROOT / "projects/grok/fixtures/research_worker_manifest_bad.json").read_text()
    )
    win_state = json.loads((ROOT / "projects/grok/data/windows_acceptance.json").read_text())[
        "state"
    ]

    report = {
        "project": "projects/grok",
        "lib": "lib/grok",
        "policy_dens_blocks_sonny": dens.allow is False and dens.code == "DENS_BLOCK",
        "genome": book.summary(),
        "research_good_ok": validate_research_manifest(good)["ok"],
        "research_bad_ok": validate_research_manifest(bad)["ok"],
        "windows": evaluate_windows_acceptance(win_state),
        "automations": auto_summary(),
        "bridge_exports": len(list((ROOT / "data/grok-web-exports").glob("2026-*.md"))),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
