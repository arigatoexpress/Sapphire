#!/usr/bin/env python3
"""Headed X account deactivation helper — NO X API.

Designed for Ari's Mac plant (Claude/Codex/Grok CLI).
Pauses for human login, 2FA, and final confirmation.

Usage:
  python3 scripts/ops/x_account_teardown_playwright.py --account rariwrldd
  python3 scripts/ops/x_account_teardown_playwright.py --account 0guard_
  python3 scripts/ops/x_account_teardown_playwright.py --account rariwrldd --delete-posts-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("Install: python3 -m pip install --user playwright && python3 -m playwright install chromium", file=sys.stderr)
    sys.exit(1)

HOME = Path.home()
OPS = HOME / "ops-state"
REPO_CANDIDATES = [
    HOME / "Code" / "Sapphire",
    HOME / "Sapphire",
    Path(__file__).resolve().parents[2],
]


def find_repo() -> Path:
    for p in REPO_CANDIDATES:
        if (p / "data" / "grok-web-exports").exists() or (p / "scripts" / "ops").exists():
            return p
    return Path.cwd()


def load_nuclear(repo: Path) -> dict:
    p = repo / "data" / "grok-web-exports" / "x-nuke-nuclear-list.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"accounts": {}}


def profile_dir(account: str) -> Path:
    d = OPS / "browser" / f"x-teardown-{account}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def wait_human(page, msg: str) -> None:
    print("\n" + "=" * 60)
    print(msg)
    print("Press ENTER in this terminal when done…")
    print("=" * 60 + "\n")
    try:
        input()
    except EOFError:
        # non-interactive agent: wait wall clock for human
        print("(no TTY — waiting 120s for human to finish in browser)")
        time.sleep(120)


def goto_deactivate(page) -> None:
    urls = [
        "https://x.com/settings/deactivate",
        "https://twitter.com/settings/deactivate",
        "https://x.com/settings/account",
    ]
    for u in urls:
        try:
            page.goto(u, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
            if "login" not in page.url.lower() or "settings" in page.url.lower():
                return
        except PWTimeout:
            continue


def try_click_deactivate(page) -> bool:
    """Best-effort clicks through deactivate UI. Returns True if something was clicked."""
    candidates = [
        "text=Deactivate",
        "text=Deactivate account",
        "text=Deactivate your account",
        "text=Yes, deactivate",
        "text=Deactivate now",
        '[data-testid="confirmationSheetConfirm"]',
        'div[role="button"]:has-text("Deactivate")',
    ]
    clicked = False
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=1500):
                print(f"  click: {sel}")
                loc.click()
                clicked = True
                time.sleep(1.5)
        except Exception:
            continue
    return clicked


def delete_posts(page, username: str, ids: list[str]) -> None:
    for tid in ids:
        url = f"https://x.com/{username}/status/{tid}"
        print(f"  open {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(1.5)
            # caret / more
            for sel in [
                '[data-testid="caret"]',
                '[aria-label="More"]',
                'div[aria-label="More"]',
            ]:
                try:
                    page.locator(sel).first.click(timeout=2000)
                    break
                except Exception:
                    continue
            time.sleep(0.5)
            for sel in [
                'text=Delete',
                '[data-testid="Dropdown"] >> text=Delete',
                'div[role="menuitem"]:has-text("Delete")',
            ]:
                try:
                    page.locator(sel).first.click(timeout=2000)
                    break
                except Exception:
                    continue
            time.sleep(0.5)
            for sel in [
                '[data-testid="confirmationSheetConfirm"]',
                'text=Delete',
                'button:has-text("Delete")',
            ]:
                try:
                    page.locator(sel).first.click(timeout=2000)
                    print(f"    deleted? {tid}")
                    break
                except Exception:
                    continue
            time.sleep(1.0)
        except Exception as e:
            print(f"    skip {tid}: {e}")


def write_receipt(account: str, mode: str, notes: str) -> Path:
    OPS.mkdir(parents=True, exist_ok=True)
    reports = OPS / "agent-reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / "X-TEARDOWN-RECEIPT-2026-08-08.md"
    prev = path.read_text() if path.exists() else "# X Teardown Receipt 2026-08-08\n\n"
    block = (
        f"\n## @{account}\n"
        f"- mode: {mode}\n"
        f"- notes: {notes}\n"
        f"- ts: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
    )
    path.write_text(prev + block)
    print(f"Receipt: {path}")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True, choices=["rariwrldd", "0guard_"])
    ap.add_argument("--delete-posts-only", action="store_true")
    ap.add_argument("--headed", action="store_true", default=True)
    args = ap.parse_args()

    repo = find_repo()
    data = load_nuclear(repo)
    username = args.account
    meta = (data.get("accounts") or {}).get(username) or {"username": username, "posts": []}
    posts = [p["id"] for p in meta.get("posts") or []]

    user_data = profile_dir(username)
    print(f"Persistent profile: {user_data}")
    print(f"Repo root: {repo}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data),
            headless=False,
            channel="chrome" if sys.platform == "darwin" else None,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)

        wait_human(
            page,
            f"LOG IN as @{username} in the browser window (2FA OK).\n"
            f"When the home timeline for @{username} is visible, return here and press ENTER.",
        )

        if args.delete_posts_only:
            delete_posts(page, username, posts)
            write_receipt(username, "delete-posts-only", f"attempted {len(posts)} ids")
        else:
            goto_deactivate(page)
            wait_human(
                page,
                f"You should be on Deactivate settings for @{username}.\n"
                f"If not, navigate: Settings → Your account → Deactivate your account.\n"
                f"Press ENTER when the deactivate page is visible; script will try to click through.\n"
                f"YOU must type password / confirm if prompted — script will pause again.",
            )
            try_click_deactivate(page)
            wait_human(
                page,
                f"Complete password + final DEACTIVATE for @{username}.\n"
                f"Press ENTER when account is deactivated or you aborted.",
            )
            write_receipt(username, "deactivate", "human-confirmed flow")

        context.close()

    print("Done. If deactivating 0guard_ next, re-run with --account 0guard_")


if __name__ == "__main__":
    main()
