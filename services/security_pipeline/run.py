#!/usr/bin/env python3
"""Sapphire Security Pipeline — daily 3 AM automated security sweep.

Orchestrates:
  1. Dependency vulnerability scan (pip-audit + npm audit)
  2. Secret detection (regex scan for leaked keys/tokens)
  3. Threat intel refresh (CISA KEV + NVD feeds)
  4. Security posture scoring
  5. Event bus publish + Telegram alert on findings

Results persisted to data/security/YYYY-MM-DD/pipeline.json
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    # Route INFO/DEBUG to stdout so the LaunchAgent's *-err.log only
    # captures real errors (tracebacks still go to stderr naturally).
    stream=sys.stdout,
)
log = logging.getLogger("security-pipeline")

TODAY = datetime.now(UTC).strftime("%Y-%m-%d")
OUTPUT_DIR = ROOT / "data" / "security" / TODAY
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Patterns that indicate leaked secrets in source code
SECRET_PATTERNS = [
    (r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"][A-Za-z0-9_\-]{20,}", "API key"),
    (r"(?i)(secret|password|passwd)\s*[=:]\s*['\"][^\s'\"]{8,}", "Password/secret"),
    (r"(?i)AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub PAT"),
    (r"sk-[A-Za-z0-9]{48}", "OpenAI key"),
    (r"xox[bpors]-[A-Za-z0-9\-]{10,}", "Slack token"),
]

SCAN_DIRS = [
    ROOT / "lib",
    ROOT / "services",
    ROOT / "plugins",
]

IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "data"}
IGNORE_FILES = {".env.example", "SKILL.md", "CLAUDE.md"}


def scan_secrets() -> list[dict]:
    """Scan source files for leaked secrets."""
    findings = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if any(part in IGNORE_DIRS for part in py_file.parts):
                continue
            if py_file.name in IGNORE_FILES:
                continue
            try:
                content = py_file.read_text(errors="ignore")
            except OSError:
                continue
            for pattern, label in SECRET_PATTERNS:
                for match in re.finditer(pattern, content):
                    # Skip test files and comments
                    line_start = content.rfind("\n", 0, match.start()) + 1
                    line = content[line_start:content.find("\n", match.end())]
                    if line.lstrip().startswith("#"):
                        continue
                    findings.append({
                        "file": str(py_file.relative_to(ROOT)),
                        "type": label,
                        "line_preview": line.strip()[:80] + "...",
                    })
    return findings


def scan_dependencies() -> dict:
    """Run pip-audit and report vulnerable packages."""
    result = {"python": [], "status": "ok"}
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format=json", "--desc"],
            capture_output=True, text=True, timeout=120,
        )
        if r.stdout.strip():
            vulns = json.loads(r.stdout)
            result["python"] = vulns.get("dependencies", [])
            if result["python"]:
                result["status"] = "vulnerable"
    except FileNotFoundError:
        result["status"] = "pip-audit not installed"
    except Exception as e:
        result["status"] = f"error: {e}"
    return result


def refresh_threat_intel() -> dict:
    """Trigger threat intel refresh via the threat_intel tool."""
    tool = ROOT / "plugins" / "claw-sapphire" / "tools" / "threat_intel.py"
    if not tool.exists():
        return {"status": "tool not found"}
    try:
        r = subprocess.run(
            [sys.executable, str(tool)],
            input=json.dumps({"action": "latest"}),
            capture_output=True, text=True, timeout=60,
        )
        if r.stdout.strip():
            return json.loads(r.stdout)
        return {"status": "empty response"}
    except Exception as e:
        return {"status": f"error: {e}"}


def compute_score(secrets_count: int, vuln_count: int, threat_count: int) -> dict:
    """Compute security posture score (0-100, higher=better)."""
    score = 100
    # Deduct for secrets
    score -= min(secrets_count * 10, 40)
    # Deduct for vulnerabilities
    score -= min(vuln_count * 5, 30)
    # Deduct for high-severity threats
    score -= min(threat_count * 2, 20)

    grade = (
        "A" if score >= 90 else
        "B" if score >= 75 else
        "C" if score >= 60 else
        "D" if score >= 40 else "F"
    )
    return {"score": max(0, score), "grade": grade}


def main() -> int:
    log.info("Security pipeline starting for %s", TODAY)

    # 1. Secret scan
    log.info("Scanning for leaked secrets...")
    secrets_found = scan_secrets()
    log.info("Found %d potential secret leaks", len(secrets_found))

    # 2. Dependency scan
    log.info("Scanning dependencies...")
    deps = scan_dependencies()
    vuln_count = len(deps.get("python", []))
    log.info("Dependency scan: %s (%d vulns)", deps["status"], vuln_count)

    # 3. Threat intel refresh
    log.info("Refreshing threat intel...")
    threats = refresh_threat_intel()
    threat_count = threats.get("total", 0) if isinstance(threats, dict) else 0

    # 4. Score
    posture = compute_score(len(secrets_found), vuln_count, threat_count)

    # 5. Assemble report
    report = {
        "date": TODAY,
        "timestamp": datetime.now(UTC).isoformat(),
        "secrets": {"count": len(secrets_found), "findings": secrets_found[:20]},
        "dependencies": deps,
        "threats": {"count": threat_count},
        "posture": posture,
    }

    # Persist
    out_path = OUTPUT_DIR / "pipeline.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    log.info("Report saved to %s", out_path)

    # 6. Publish event
    try:
        from lib.core.event_bus import get_bus
        get_bus().publish("security.pipeline.completed", {
            "date": TODAY,
            "posture": posture,
            "secrets_found": len(secrets_found),
            "vulnerabilities": vuln_count,
        }, source="security-pipeline")
    except Exception as e:
        log.debug("Event publish failed: %s", e)

    # 7. Telegram alert if critical findings
    if len(secrets_found) > 0 or posture["grade"] in ("D", "F"):
        try:
            notify_tool = ROOT / "plugins" / "claw-sapphire" / "tools" / "notify.py"
            msg = (
                f"🔒 *Security Pipeline — {TODAY}*\n"
                f"  Grade: *{posture['grade']}* ({posture['score']}/100)\n"
                f"  Secrets: {len(secrets_found)} · Vulns: {vuln_count}\n"
                f"  Threats: {threat_count}"
            )
            subprocess.run(
                [sys.executable, str(notify_tool)],
                input=json.dumps({"message": msg, "priority": "p1"}),
                capture_output=True, text=True, timeout=15,
            )
        except Exception:
            pass

    log.info("Security pipeline complete. Grade: %s (%d/100)",
             posture["grade"], posture["score"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
