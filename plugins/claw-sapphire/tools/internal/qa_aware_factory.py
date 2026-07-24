#!/usr/bin/env python3
"""QA-Aware Factory — reads the QA report and prioritizes intelligently.

Instead of blindly scanning all repos, this reads data/frontend_qa_report.json
and focuses on the highest-priority issues that actually matter.

Usage:
    python3 qa_aware_factory.py                # Check QA priorities
    python3 qa_aware_factory.py --verify       # Re-verify fixes
    python3 qa_aware_factory.py --update       # Update QA report with new scores
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

QA_REPORT_PATH = Path.home() / "Code" / "Sapphire" / "data" / "frontend_qa_report.json"
EVENTS_PATH = Path.home() / "Code" / "Sapphire" / "data" / "system_events.jsonl"


def load_qa_report() -> dict:
    """Load the QA report."""
    if not QA_REPORT_PATH.exists():
        return {"error": "No QA report found. Run QA audit first."}
    return json.loads(QA_REPORT_PATH.read_text(encoding="utf-8"))


def check_priority(priority: dict) -> dict:
    """Check if a QA priority has been fixed."""
    action = priority.get("action", "")
    result = {"action": action, "status": "unknown"}

    # Check specific fixes
    if "Dashboard" in action and "route" in action.lower():
        # Test if dashboard / returns 200
        try:
            r = subprocess.run(
                [
                    "curl",
                    "-s",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "-u",
                    "sapphire:sapphire",
                    "http://127.0.0.1:8080/",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            code = r.stdout.strip()
            result["status"] = "fixed" if code == "200" else f"still_broken (HTTP {code})"
            result["http_code"] = code
        except Exception:
            result["status"] = "service_down"

    elif "auth" in action.lower():
        # Check if service has auth
        service = "cointracker" if "Cointracker" in action else "regional"
        port = 8050 if "cointracker" in service else 8060
        try:
            r = subprocess.run(
                [
                    "curl",
                    "-s",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    f"http://127.0.0.1:{port}/",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            code = r.stdout.strip()
            result["status"] = "needs_auth" if code == "200" else f"has_auth ({code})"
        except Exception:
            result["status"] = "service_down"

    elif "mobile" in action.lower() or "sidebar" in action.lower():
        result["status"] = "requires_manual_check"

    elif "LaunchAgent" in action:
        # Check if service is running
        if "Regional" in action:
            try:
                r = subprocess.run(
                    [
                        "curl",
                        "-s",
                        "-o",
                        "/dev/null",
                        "-w",
                        "%{http_code}",
                        "http://127.0.0.1:8060/",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                result["status"] = "running" if r.stdout.strip() == "200" else "not_running"
            except Exception:
                result["status"] = "not_running"

    return result


def run_qa_check() -> dict:
    """Check all QA priorities."""
    report = load_qa_report()
    if "error" in report:
        print(report["error"])
        return report

    priorities = report.get("global_priorities", [])
    results = []

    print(f"{'=' * 60}")
    print(f"  QA PRIORITY CHECK — {datetime.now(UTC).strftime('%Y-%m-%d')}")
    print(f"{'=' * 60}\n")

    for p in priorities:
        check = check_priority(p)
        icon = (
            "✅"
            if check["status"] in ("fixed", "running", "has_auth")
            else "❌"
            if "broken" in check["status"] or "needs" in check["status"]
            else "⚠️"
        )
        print(f"  {icon} [{p.get('impact', '?')}] {p['action']}")
        print(f"     Status: {check['status']}")
        results.append({**p, "check": check})

    # Frontend scores
    print("\n  Frontend Scores:")
    for name, fe in report.get("frontends", {}).items():
        score = fe.get("ux_score", 0)
        status = fe.get("status", "unknown")
        icon = "🟢" if score >= 7 else "🟡" if score >= 5 else "🔴"
        print(f"    {icon} {name}: {score}/10 ({status})")

    fixed = sum(1 for r in results if r["check"]["status"] in ("fixed", "running"))
    print(f"\n  Fixed: {fixed}/{len(results)} priorities")

    return {"priorities": results, "fixed": fixed, "total": len(results)}


def update_qa_report(results: dict) -> None:
    """Update QA report with verification results."""
    report = load_qa_report()
    report["last_verified"] = datetime.now(UTC).isoformat()
    report["verification_results"] = results.get("priorities", [])
    QA_REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\n  Updated {QA_REPORT_PATH}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    results = run_qa_check()
    if args.update:
        update_qa_report(results)
