#!/usr/bin/env python3
"""
X Nuclear Delete Toolkit — dry-run by default.

Usage:
  python3 nuke.py                  # dry-run curated nuclear-list.json
  python3 nuke.py --execute        # actually DELETE (irreversible)
  python3 nuke.py --scan           # pull timelines, score, append matches
  python3 nuke.py --scan --execute # scan + delete auto-scored hits
  python3 nuke.py --account rariwrldd
  python3 nuke.py --priority P0,P1
  python3 nuke.py --checklist      # write open-checklist.html

Requires OAuth 1.0a user tokens with Read+Write (see .env.example).
X API write access is paid on most tiers — if 403, use checklist mode.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

try:
    from requests_oauthlib import OAuth1Session
except ImportError:
    print("Missing deps. Run: pip install requests requests-oauthlib", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
LIST_PATH = ROOT / "nuclear-list.json"
ENV_PATH = ROOT / ".env"
RESULTS_DIR = ROOT / "results"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def load_list() -> dict:
    return json.loads(LIST_PATH.read_text())


def session_for(prefix: str) -> OAuth1Session:
    keys = {
        "client_key": os.environ.get(f"{prefix}_API_KEY", ""),
        "client_secret": os.environ.get(f"{prefix}_API_SECRET", ""),
        "resource_owner_key": os.environ.get(f"{prefix}_ACCESS_TOKEN", ""),
        "resource_owner_secret": os.environ.get(f"{prefix}_ACCESS_TOKEN_SECRET", ""),
    }
    missing = [k for k, v in keys.items() if not v]
    if missing:
        raise SystemExit(
            f"Missing env for {prefix}: {', '.join(missing)}\n"
            f"Copy .env.example → .env and fill keys (Read+Write OAuth 1.0a)."
        )
    return OAuth1Session(**keys)


def delete_tweet(sess: OAuth1Session, tweet_id: str) -> tuple[bool, str]:
    url = f"https://api.twitter.com/2/tweets/{tweet_id}"
    r = sess.delete(url, timeout=30)
    if r.status_code in (200, 201):
        return True, "deleted"
    if r.status_code == 404:
        return True, "already_gone"
    return False, f"HTTP {r.status_code}: {r.text[:300]}"


def fetch_user_id(sess: OAuth1Session, username: str) -> str:
    r = sess.get(
        "https://api.twitter.com/2/users/by/username/" + username.lstrip("@"),
        timeout=30,
    )
    if r.status_code != 200:
        raise SystemExit(f"Lookup @{username} failed: {r.status_code} {r.text[:200]}")
    return r.json()["data"]["id"]


def fetch_timeline(sess: OAuth1Session, user_id: str, max_pages: int = 20) -> list[dict]:
    """Pull up to ~2000 recent tweets (100/page)."""
    posts: list[dict] = []
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,text,public_metrics",
        "exclude": "retweets",
    }
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    token = None
    for _ in range(max_pages):
        p = dict(params)
        if token:
            p["pagination_token"] = token
        r = sess.get(url, params=p, timeout=30)
        if r.status_code == 429:
            print("Rate limited on timeline; sleeping 60s…")
            time.sleep(60)
            continue
        if r.status_code != 200:
            print(f"Timeline error {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        posts.extend(data.get("data") or [])
        token = (data.get("meta") or {}).get("next_token")
        if not token:
            break
        time.sleep(0.5)
    return posts


def score_text(text: str, patterns: dict) -> str | None:
    """Return priority label or None."""
    for pat in patterns.get("never_auto_delete") or []:
        if re.search(pat, text):
            return None
    for pat in patterns.get("always_delete") or []:
        if re.search(pat, text):
            return "P0"
    for pat in patterns.get("likely_delete") or []:
        if re.search(pat, text):
            return "P1"
    return None


def write_checklist(data: dict, out: Path) -> None:
    rows = []
    for _acct, meta in data["accounts"].items():
        for p in meta.get("posts") or []:
            url = f"https://x.com/{meta['username']}/status/{p['id']}"
            reason = html_lib.escape(p.get("reason") or "")
            snippet = html_lib.escape((p.get("text") or "")[:80])
            rows.append(
                f'<li data-priority="{html_lib.escape(p["priority"])}">'
                f'<a href="{url}" target="_blank" rel="noopener">'
                f"{html_lib.escape(p['priority'])} · @{html_lib.escape(meta['username'])} · {p['id']}"
                f"</a> "
                f'<span class="why">{reason}</span> '
                f"<code>{snippet}</code></li>"
            )
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>X Nuclear Checklist</title>
<style>
  body {{ font-family: ui-sans-serif, system-ui; max-width: 900px; margin: 2rem auto; padding: 0 1rem; background: #0b0f14; color: #e7ecf3; }}
  h1 {{ font-size: 1.25rem; }}
  .hint {{ color: #9aa8b8; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  li {{ margin: 0.6rem 0; line-height: 1.4; }}
  a {{ color: #7dd3fc; }}
  .why {{ color: #fbbf24; font-size: 0.85rem; }}
  code {{ display: block; color: #94a3b8; font-size: 0.8rem; margin-top: 0.15rem; }}
  button {{ background: #2563eb; color: white; border: 0; padding: 0.6rem 1rem; border-radius: 8px; cursor: pointer; margin: 0.25rem; }}
</style></head><body>
<h1>X Nuclear Delete Checklist ({len(rows)} posts)</h1>
<p class="hint">Logged into the right account → open each link → ⋯ → Delete.
<button type="button" id="openAll">Open all (staggered)</button>
— review before mass-open.</p>
<ol>
{"".join(rows)}
</ol>
<script>
document.getElementById('openAll').onclick = function () {{
  document.querySelectorAll('ol a').forEach(function (a, i) {{
    setTimeout(function () {{ window.open(a.href, '_blank'); }}, i * 400);
  }});
}};
</script>
</body></html>
"""
    out.write_text(html)
    print(f"Wrote {out}")


def run_delete(
    data: dict,
    accounts: list[str] | None,
    priorities: set[str],
    execute: bool,
) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = RESULTS_DIR / f"delete-{stamp}.jsonl"
    results = []

    for _acct_key, meta in data["accounts"].items():
        if accounts and _acct_key not in accounts and meta.get("username") not in accounts:
            continue
        posts = [p for p in (meta.get("posts") or []) if p.get("priority", "P2") in priorities]
        if not posts:
            continue
        prefix = meta["env_prefix"]
        print(
            f"\n=== @{meta['username']} · {len(posts)} posts · "
            f"{'EXECUTE' if execute else 'DRY-RUN'} ==="
        )

        sess = None
        if execute:
            sess = session_for(prefix)

        for p in posts:
            tid = p["id"]
            url = f"https://x.com/{meta['username']}/status/{tid}"
            entry = {
                "account": meta["username"],
                "id": tid,
                "priority": p.get("priority"),
                "reason": p.get("reason"),
                "url": url,
            }
            if not execute:
                print(f"  [dry] would delete {p['priority']} {tid} — {p.get('reason')}")
                entry["status"] = "dry_run"
            else:
                ok, msg = delete_tweet(sess, tid)
                entry["status"] = "ok" if ok else "error"
                entry["detail"] = msg
                print(f"  [{'ok' if ok else 'ERR'}] {tid} → {msg}")
                time.sleep(1.1)
            results.append(entry)
            with log_path.open("a") as f:
                f.write(json.dumps(entry) + "\n")

    print(f"\nLog: {log_path}")
    if not execute:
        print("Dry-run only. Re-run with --execute to delete.")
    else:
        ok_n = sum(1 for r in results if r.get("status") == "ok")
        print(f"Done: {ok_n}/{len(results)} deleted or already gone.")


def run_scan(data: dict, accounts: list[str] | None, execute: bool) -> None:
    patterns = data.get("auto_scan_patterns") or {}
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    scan_out = RESULTS_DIR / f"scan-{stamp}.json"
    found_all = []

    for _acct_key, meta in data["accounts"].items():
        if accounts and _acct_key not in accounts and meta.get("username") not in accounts:
            continue
        prefix = meta["env_prefix"]
        print(f"\n=== SCAN @{meta['username']} ===")
        sess = session_for(prefix)
        uid = meta.get("user_id_hint") or fetch_user_id(sess, meta["username"])
        if not meta.get("user_id_hint"):
            print(f"  user_id={uid}")
        timeline = fetch_timeline(sess, uid)
        print(f"  fetched {len(timeline)} tweets")

        existing = {p["id"] for p in meta.get("posts") or []}
        hits = []
        for t in timeline:
            pri = score_text(t.get("text") or "", patterns)
            if not pri:
                continue
            hit = {
                "id": t["id"],
                "priority": pri,
                "reason": "auto_scan_pattern",
                "text": (t.get("text") or "")[:200],
                "created_at": t.get("created_at"),
            }
            hits.append(hit)
            if t["id"] not in existing:
                meta.setdefault("posts", []).append(hit)
                existing.add(t["id"])
            print(f"  HIT {pri} {t['id']}: {(t.get('text') or '')[:70]!r}")

        found_all.append({"account": meta["username"], "hits": hits})

        if execute and hits:
            print(f"  deleting {len(hits)} scan hits…")
            for h in hits:
                ok, msg = delete_tweet(sess, h["id"])
                print(f"    [{'ok' if ok else 'ERR'}] {h['id']} → {msg}")
                time.sleep(1.1)

    LIST_PATH.write_text(json.dumps(data, indent=2) + "\n")
    scan_out.write_text(json.dumps(found_all, indent=2) + "\n")
    print(f"\nUpdated {LIST_PATH}")
    print(f"Scan report: {scan_out}")


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser(description="X nuclear delete toolkit")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default: dry-run)",
    )
    ap.add_argument(
        "--scan",
        action="store_true",
        help="Fetch timeline and score with patterns",
    )
    ap.add_argument(
        "--checklist",
        action="store_true",
        help="Write HTML checklist",
    )
    ap.add_argument(
        "--account",
        action="append",
        help="Limit to account key/username (repeatable)",
    )
    ap.add_argument(
        "--priority",
        default="P0,P1,P2",
        help="Comma priorities to include (default P0,P1,P2 = nuclear)",
    )
    args = ap.parse_args()
    data = load_list()
    priorities = {p.strip() for p in args.priority.split(",") if p.strip()}

    if args.checklist:
        write_checklist(data, ROOT / "open-checklist.html")
        return

    if args.scan:
        run_scan(data, args.account, args.execute)
        if not args.execute:
            data = load_list()
            run_delete(data, args.account, priorities, execute=False)
        return

    run_delete(data, args.account, priorities, args.execute)


if __name__ == "__main__":
    main()
