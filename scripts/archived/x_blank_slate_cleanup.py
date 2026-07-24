#!/usr/bin/env python3
"""Safely delete legacy X content (tweets/retweets/media) before a cutoff.

Uses authenticated web-session endpoints (browser cookies) to avoid paid API read limits.

Safety defaults:
- dry-run by default
- capped deletes per run
- delay + jitter between deletes
- persistent state file to avoid duplicate work
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.parse
from collections.abc import Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

try:
    import browser_cookie3
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"browser_cookie3 is required: {exc}")

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

WEB_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

QUERIES = {
    "UserTweets": "ix7iRrsAvfXyGUQ06Z7krA",
    "UserTweetsAndReplies": "RCpRL9JyzOSO5qS6YDOg7w",
    "UserMedia": "qf6w1MULRM9mM6qaoOSPDQ",
}

FEATURES = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}

FIELD_TOGGLES = {"withArticlePlainText": False}
DELETE_TWEET_MUTATION_ID = "nxpZCY2K-I6QoFHAHeojFQ"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Safe X blank-slate cleanup")
    p.add_argument("--env-file", default="", help="Optional dotenv file")
    p.add_argument("--cutoff-utc", default="", help="Delete posts older than this UTC timestamp (ISO8601). Default: now")
    p.add_argument("--max-scan", type=int, default=2500, help="Maximum timeline items to inspect")
    p.add_argument("--max-delete", type=int, default=30, help="Maximum deletes in this run")
    p.add_argument("--delay-seconds", type=float, default=16.0, help="Base delay between deletes")
    p.add_argument("--max-rate-limit-retries", type=int, default=1, help="Max retries per timeline request on 429")
    p.add_argument("--max-rate-limit-wait", type=int, default=90, help="Max seconds to wait on any single 429 retry")
    p.add_argument("--skip-scan", action="store_true", help="Use pending queue from state file instead of scanning timelines")
    p.add_argument("--state-file", default="/Users/aribs/Sapphire/output/x_cleanup/state.json")
    p.add_argument("--apply", action="store_true", help="Execute deletions (default dry-run)")
    return p.parse_args()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_cutoff(value: str) -> datetime:
    if not value:
        return _utc_now()
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"deleted_ids": [], "runs": []}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def _session_from_browser() -> tuple[requests.Session, dict[str, str], str]:
    cj = browser_cookie3.chrome(domain_name=".x.com")
    ct0 = next((c.value for c in cj if c.name == "ct0"), "")
    twid = next((c.value for c in cj if c.name == "twid"), "")
    if not ct0 or not twid:
        raise RuntimeError("Missing required X cookies (ct0/twid). Ensure you are logged in on Chrome.")

    twid_decoded = urllib.parse.unquote(twid)
    uid = twid_decoded.split("=", 1)[1] if "=" in twid_decoded else twid_decoded
    uid = re.sub(r"[^0-9]", "", uid)
    if not uid:
        raise RuntimeError("Could not parse account user id from twid cookie")

    s = requests.Session()
    s.cookies.update(cj)
    headers = {
        "authorization": f"Bearer {WEB_BEARER}",
        "x-csrf-token": ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "user-agent": "Mozilla/5.0",
    }
    return s, headers, uid


def _timeline_entries(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    instructions = (
        payload.get("data", {})
        .get("user", {})
        .get("result", {})
        .get("timeline", {})
        .get("timeline", {})
        .get("instructions", [])
    )
    for ins in instructions:
        entries = ins.get("entries") if isinstance(ins, dict) else None
        if isinstance(entries, list):
            for e in entries:
                if isinstance(e, dict):
                    yield e


def _extract_tweet(entry: dict[str, Any], own_uid: str) -> dict[str, Any] | None:
    content = entry.get("content", {}) or {}
    item = content.get("itemContent", {}) or {}
    tweet = item.get("tweet_results", {}).get("result")
    if not isinstance(tweet, dict) or tweet.get("__typename") != "Tweet":
        return None

    rest_id = str(tweet.get("rest_id", "") or "")
    if not rest_id:
        return None

    core_user = (
        tweet.get("core", {})
        .get("user_results", {})
        .get("result", {})
    )
    author_id = str(core_user.get("rest_id", "") or core_user.get("id", "") or "")
    legacy = tweet.get("legacy", {}) or {}
    if not author_id:
        author_id = str(legacy.get("user_id_str", "") or "")
    if own_uid and author_id and author_id != own_uid:
        return None

    created_at_raw = str(legacy.get("created_at", "") or "")
    if not created_at_raw:
        return None
    created_at = parsedate_to_datetime(created_at_raw).astimezone(UTC)

    full_text = str(legacy.get("full_text", "") or "")
    is_retweet = "retweeted_status_result" in legacy or full_text.startswith("RT @")
    has_media = bool((legacy.get("entities", {}) or {}).get("media")) or bool((legacy.get("extended_entities", {}) or {}).get("media"))

    return {
        "id": rest_id,
        "created_at": created_at.isoformat(),
        "text": full_text,
        "is_retweet": is_retweet,
        "has_media": has_media,
        "source_query": item.get("__typename", ""),
    }


def _wait_from_rate_limit_headers(resp: requests.Response, default_seconds: int = 60, max_wait_seconds: int = 90) -> int:
    reset = resp.headers.get("x-rate-limit-reset")
    if reset:
        try:
            wait_s = int(reset) - int(time.time()) + 2
            return min(max_wait_seconds, max(5, wait_s))
        except Exception:
            pass
    return min(max_wait_seconds, max(5, default_seconds))


def collect_candidates(
    s: requests.Session,
    headers: dict[str, str],
    own_uid: str,
    cutoff: datetime,
    max_scan: int,
    max_rate_limit_retries: int = 3,
    max_rate_limit_wait: int = 90,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    seen_ids = set()
    rows: list[dict[str, Any]] = []
    meta: dict[str, Any] = {"rate_limited": False, "errors": [], "requests": 0}

    for op_name, qid in QUERIES.items():
        cursor = None
        scanned = 0
        retries = 0
        while scanned < max_scan:
            variables = {
                "userId": own_uid,
                "count": 40,
                "includePromotedContent": True,
                "withQuickPromoteEligibilityTweetFields": True,
                "withVoice": True,
            }
            if cursor:
                variables["cursor"] = cursor

            url = (
                f"https://x.com/i/api/graphql/{qid}/{op_name}"
                f"?variables={urllib.parse.quote(json.dumps(variables, separators=(',', ':')))}"
                f"&features={urllib.parse.quote(json.dumps(FEATURES, separators=(',', ':')))}"
                f"&fieldToggles={urllib.parse.quote(json.dumps(FIELD_TOGGLES, separators=(',', ':')))}"
            )
            r = s.get(url, headers=headers, timeout=30)
            meta["requests"] += 1
            if r.status_code != 200:
                if r.status_code == 429 and retries < max_rate_limit_retries:
                    retries += 1
                    meta["rate_limited"] = True
                    wait_s = _wait_from_rate_limit_headers(r, default_seconds=30 * retries, max_wait_seconds=max_rate_limit_wait)
                    meta["errors"].append(f"{op_name}:429_retry_{retries}_wait_{wait_s}s")
                    time.sleep(wait_s)
                    continue
                meta["errors"].append(f"{op_name}:status_{r.status_code}")
                break
            retries = 0

            payload = r.json()
            next_cursor = None
            page_added = 0
            for entry in _timeline_entries(payload):
                entry_id = str(entry.get("entryId", "") or "")
                content = entry.get("content", {}) or {}
                if entry_id.startswith("cursor-bottom-"):
                    next_cursor = content.get("value") or content.get("itemContent", {}).get("value")

                tweet = _extract_tweet(entry, own_uid)
                if not tweet:
                    continue
                scanned += 1
                tid = tweet["id"]
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)

                created = datetime.fromisoformat(tweet["created_at"])
                if created < cutoff:
                    rows.append(tweet)
                page_added += 1
                if scanned >= max_scan:
                    break

            if not next_cursor or page_added == 0:
                break
            cursor = next_cursor
            time.sleep(1.1)

    rows.sort(key=lambda x: x["created_at"])  # oldest first
    return rows, meta


def delete_tweet(s: requests.Session, headers: dict[str, str], tweet_id: str) -> tuple[bool, str]:
    h = dict(headers)
    h["content-type"] = "application/json"
    url = f"https://x.com/i/api/graphql/{DELETE_TWEET_MUTATION_ID}/DeleteTweet"
    payload = {
        "variables": {"tweet_id": str(tweet_id), "dark_request": False},
        "queryId": DELETE_TWEET_MUTATION_ID,
    }
    r = s.post(url, headers=h, json=payload, timeout=30)
    if r.status_code == 200:
        body = r.text
        if "delete_tweet" in body:
            return True, "ok"
        return False, f"status_200_unexpected_body: {body[:220].replace(chr(10), ' ')}"
    msg = r.text[:220].replace("\n", " ")
    return False, f"status_{r.status_code}: {msg}"


def main() -> int:
    args = parse_args()
    if args.env_file:
        if load_dotenv is None:
            print(json.dumps({"ok": False, "error": "python_dotenv_not_installed"}, indent=2))
            return 2
        load_dotenv(args.env_file, override=False)

    cutoff = _parse_cutoff(args.cutoff_utc)
    state_path = Path(args.state_file)
    state = _load_state(state_path)
    already_deleted = set(str(x) for x in state.get("deleted_ids", []))
    pending_ids = [str(x) for x in state.get("pending_ids", []) if str(x)]
    pending_meta = state.get("pending_meta", {})

    s, headers, uid = _session_from_browser()
    if args.skip_scan and pending_ids:
        rows = [{"id": tid, "created_at": "", "text": "", "is_retweet": False, "has_media": False, "source_query": "state_queue"} for tid in pending_ids]
        scan_meta = {"used_state_queue": True, "errors": [], "rate_limited": False, "requests": 0}
    else:
        rows, scan_meta = collect_candidates(
            s,
            headers,
            uid,
            cutoff,
            max_scan=max(1, int(args.max_scan)),
            max_rate_limit_retries=max(0, int(args.max_rate_limit_retries)),
            max_rate_limit_wait=max(5, int(args.max_rate_limit_wait)),
        )
        rows = [r for r in rows if str(r["id"]) not in already_deleted]
        state["pending_ids"] = [str(r["id"]) for r in rows]
        state["pending_meta"] = {
            "cutoff_utc": cutoff.isoformat(),
            "captured_at": _utc_now().isoformat(),
            "candidate_count": len(rows),
            "scan_meta": scan_meta,
        }
        _save_state(state_path, state)

    summary = {
        "ok": True,
        "dry_run": not args.apply,
        "user_id": uid,
        "cutoff_utc": cutoff.isoformat(),
        "candidate_count": len(rows),
        "retweet_count": sum(1 for r in rows if r.get("is_retweet")),
        "media_count": sum(1 for r in rows if r.get("has_media")),
        "oldest_candidate": rows[0]["created_at"] if rows else None,
        "newest_candidate": rows[-1]["created_at"] if rows else None,
        "preview": rows[:10],
        "scan_meta": scan_meta,
    }

    if not args.apply:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    to_delete = rows[: max(0, int(args.max_delete))]
    deleted = []
    errors = []
    for row in to_delete:
        ok, detail = delete_tweet(s, headers, row["id"])
        if ok:
            deleted.append(row["id"])
            already_deleted.add(str(row["id"]))
            pending_ids = [x for x in pending_ids if x != str(row["id"])]
        else:
            errors.append({"id": row["id"], "error": detail})
            # keep failed ids in queue for later retry unless they are clearly gone
            if "status_404" in detail or "status_401" in detail:
                pending_ids = [x for x in pending_ids if x != str(row["id"])]

        state["deleted_ids"] = sorted(already_deleted)
        state["pending_ids"] = pending_ids
        _save_state(state_path, state)
        sleep_s = max(5.0, float(args.delay_seconds)) + random.uniform(0.8, 2.8)
        time.sleep(sleep_s)

    state["deleted_ids"] = sorted(already_deleted)
    state["pending_ids"] = pending_ids
    state.setdefault("runs", []).append(
        {
            "timestamp": _utc_now().isoformat(),
            "cutoff_utc": cutoff.isoformat(),
            "requested": len(to_delete),
            "deleted": len(deleted),
            "errors": len(errors),
        }
    )
    _save_state(state_path, state)

    out = dict(summary)
    out.update(
        {
            "dry_run": False,
            "deleted_count": len(deleted),
            "deleted_ids": deleted,
            "errors": errors,
            "remaining_candidates_estimate": max(0, len(rows) - len(deleted)),
            "state_file": str(state_path),
        }
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
