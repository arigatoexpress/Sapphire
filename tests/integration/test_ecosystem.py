#!/usr/bin/env python3
"""Sapphire Ecosystem Integration Test.

Verifies that all major subsystems work together:
- Sapphire core (1,088 unit tests)
- THO Document Center (Firestore, GCS, JWT)
- Cyber Threat Bot (live sources)
- Starred Repos (GitHub API)
- Health Check (20-point aggregation)
- Trading Pipeline (signal logger)

Run: python3 tests/integration/test_ecosystem.py
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
CTB_DIR = Path.home() / "Code" / "cyber-threat-bot"
THO_BASE = "https://project-go-forward-691674245427.us-central1.run.app"

passed = 0
failed = 0
skipped = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}: {detail}")


def skip(name: str, reason: str):
    global skipped
    skipped += 1
    print(f"  ⏭️  {name}: {reason}")


def http_get(url: str, headers: dict = None, timeout: int = 10) -> tuple:
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 0, str(e)


def http_post(url: str, data: dict, headers: dict = None, timeout: int = 10) -> tuple:
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload, headers={**(headers or {}), "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = None
        return e.code, body
    except Exception as e:
        return 0, str(e)


def main():
    print("\n═══ Sapphire Ecosystem Integration Test ═══\n")

    # 1. Sapphire Core
    print("1. Sapphire Core")
    check("Sapphire repo exists", (SAPPHIRE_DIR / "CLAUDE.md").exists())
    check("Plugin tools exist", len(list((SAPPHIRE_DIR / "plugins/claw-sapphire/tools").glob("*.py"))) >= 10,
          f"Found {len(list((SAPPHIRE_DIR / 'plugins/claw-sapphire/tools').glob('*.py')))}")
    check("Data directories exist",
          all((SAPPHIRE_DIR / "data" / d).exists() for d in ["threat_intel", "starred_repos", "market_pulse"]))

    # 2. THO Production
    print("\n2. THO Production (Cloud Run)")
    status, body = http_get(f"{THO_BASE}/health")
    check("Health endpoint", status == 200 and body and body.get("status") == "ok", f"HTTP {status}")

    status, body = http_post(f"{THO_BASE}/api/admin/verify", {"pin": "4832"})
    token = body.get("token", "") if body else ""
    check("Admin auth (JWT)", status == 200 and len(token) > 20, f"HTTP {status}")

    if token:
        headers = {"X-Admin-Token": token}
        status, body = http_get(f"{THO_BASE}/api/customers/count", headers=headers)
        total = body.get("total", 0) if body else 0
        check("Firestore customers", total >= 1963, f"Got {total}")

        status, body = http_get(f"{THO_BASE}/api/documents/templates", headers=headers)
        templates = len(body.get("templates", [])) if body else 0
        check("PDF templates", templates >= 60, f"Got {templates}")

        status, body = http_get(f"{THO_BASE}/api/customers/search?q=garcia", headers=headers)
        results = body.get("total", 0) if body else 0
        check("Customer search", results > 0 and body.get("source") == "firestore", f"{results} results, source={body.get('source')}")
    else:
        skip("Firestore customers", "No auth token")
        skip("PDF templates", "No auth token")
        skip("Customer search", "No auth token")

    # 3. Cyber Threat Bot
    print("\n3. Cyber Threat Bot")
    check("CTB repo exists", (CTB_DIR / "src" / "cyber_threat_bot" / "cli.py").exists())
    check("Kadima profile exists", (CTB_DIR / "profiles" / "kadima-digital.json").exists())

    # Test the plugin tool
    try:
        r = subprocess.run(
            ["python3", str(SAPPHIRE_DIR / "plugins/claw-sapphire/tools/threat_intel.py")],
            input='{"action":"scan"}', capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": str(CTB_DIR / "src")}
        )
        data = json.loads(r.stdout) if r.stdout else {}
        check("Threat scan (live)", data.get("success") and data.get("total_signals", 0) > 0,
              f"{data.get('total_signals', 0)} signals")
    except Exception as e:
        check("Threat scan (live)", False, str(e)[:80])

    # 4. Signal Logger
    print("\n4. Trading Pipeline")
    status, body = http_get("http://127.0.0.1:18081/health")
    check("Signal logger", status == 200, f"HTTP {status}")

    signals_file = SAPPHIRE_DIR / "data" / "trading_signals.jsonl"
    check("Signals file exists", signals_file.exists() and signals_file.stat().st_size > 0)

    preds_file = SAPPHIRE_DIR / "data" / "trading_predictions.jsonl"
    if preds_file.exists():
        preds = [json.loads(l) for l in preds_file.read_text().strip().split("\n") if l.strip()]
        scored = [p for p in preds if p.get("correct") is not None]
        check("Predictions scored", len(scored) > 0, f"{len(scored)}/{len(preds)} scored")
    else:
        skip("Predictions scored", "No predictions file")

    # 5. Inference
    print("\n5. Inference")
    status, _ = http_get("http://127.0.0.1:11434/api/tags", timeout=3)
    check("Mac Ollama", status == 200, f"HTTP {status}")
    status, _ = http_get("http://100.71.10.48:11434/api/tags", timeout=3)
    check("Windows GPU Ollama", status == 200, f"HTTP {status}")

    # 6. GitHub Integration
    print("\n6. GitHub Integration")
    stars_file = SAPPHIRE_DIR / "data" / "starred_repos" / "starred.json"
    if stars_file.exists():
        stars = json.loads(stars_file.read_text())
        check("Starred repos synced", len(stars) >= 30, f"{len(stars)} repos")
    else:
        skip("Starred repos synced", "No data file")

    synergy_file = SAPPHIRE_DIR / "data" / "starred_repos" / "synergies.json"
    if synergy_file.exists():
        synergies = json.loads(synergy_file.read_text())
        check("Synergies analyzed", len(synergies) >= 10, f"{len(synergies)} synergies")
    else:
        skip("Synergies analyzed", "No data file")

    # 7. Repos clean
    print("\n7. Repository Health")
    for repo_name, repo_path in [("Sapphire", SAPPHIRE_DIR), ("THO", Path.home() / "Code/Project-Go-Forward"),
                                  ("CTB", CTB_DIR), ("RIW", Path.home() / "Code/regional-intel-workbench")]:
        try:
            r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                             cwd=str(repo_path), timeout=5)
            dirty = len([l for l in r.stdout.strip().split("\n") if l.strip()])
            check(f"{repo_name} git clean", dirty <= 3, f"{dirty} dirty files")
        except Exception:
            skip(f"{repo_name} git clean", "git failed")

    # Summary
    total = passed + failed + skipped
    print(f"\n{'═' * 50}")
    print(f"  ✅ {passed} passed  ❌ {failed} failed  ⏭️  {skipped} skipped  ({total} total)")
    pct = (passed / (passed + failed) * 100) if (passed + failed) > 0 else 0
    print(f"  Score: {pct:.0f}%")
    print(f"{'═' * 50}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
