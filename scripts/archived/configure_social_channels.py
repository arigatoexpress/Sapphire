#!/usr/bin/env python3
"""Sapphire social channel automation runner.

API-first replacement for brittle browser automation:
- update X profile metadata/banner/profile image
- publish to X
- publish to Substack (email or webhook mode)
- print readiness/status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
ALPHA_SRC = ROOT / "services" / "alpha-engine" / "src"
if str(ALPHA_SRC) not in sys.path:
    sys.path.insert(0, str(ALPHA_SRC))

from media.substack import SubstackClient  # noqa: E402
from media.twitter import TwitterClient  # noqa: E402


def _print_json(payload: dict):
    print(json.dumps(payload, indent=2, sort_keys=True))


async def cmd_status(_: argparse.Namespace) -> int:
    twitter = TwitterClient()
    substack = SubstackClient()
    await twitter.start()
    await substack.start()

    payload = {
        "twitter": {
            "enabled": twitter.enabled,
            "ready": twitter.ready,
            "handle": twitter.handle,
            "has_api_key": bool(twitter.api_key),
            "has_access_token": bool(twitter.access_token),
            "has_access_secret": bool(twitter.access_secret),
            "has_bearer": bool(twitter.bearer_token),
        },
        "substack": {
            "enabled": substack.enabled,
            "ready": substack.ready,
            "mode": substack.mode,
            "publication_url": substack.publication_url,
            "publication_email": substack.publication_email,
            "post_url": substack.post_url,
        },
    }
    _print_json(payload)
    return 0 if (twitter.ready or substack.ready) else 2


async def cmd_x_branding(args: argparse.Namespace) -> int:
    twitter = TwitterClient()
    await twitter.start()
    if not twitter.ready:
        _print_json({"ok": False, "error": "twitter_not_ready"})
        return 2

    result = await twitter.update_branding(
        name=args.name or "",
        description=args.bio or "",
        url=args.url or "",
        location=args.location or "",
        clear_location=bool(args.clear_location),
        banner_path=args.banner or "",
        profile_image_path=args.profile_image or "",
    )
    _print_json(result)
    return 0 if result.get("ok") else 1


async def cmd_x_prune_following(args: argparse.Namespace) -> int:
    twitter = TwitterClient()
    await twitter.start()
    if not twitter.ready:
        _print_json({"ok": False, "error": "twitter_not_ready"})
        return 2

    keep_handles = []
    if args.keep_handles:
        keep_handles.extend([h.strip() for h in args.keep_handles.split(",") if h.strip()])
    if args.keep_handles_env:
        keep_handles.extend([h.strip() for h in os.getenv(args.keep_handles_env, "").split(",") if h.strip()])

    try:
        result = await twitter.prune_following(
            max_scan=max(1, int(args.max_scan)),
            max_actions=max(0, int(args.max_actions)),
            min_score=int(args.min_score),
            delay_seconds=float(args.delay_seconds),
            dry_run=not bool(args.apply),
            keep_handles=keep_handles,
        )
    except Exception as exc:
        _print_json(
            {
                "ok": False,
                "error": "x_following_scan_blocked",
                "detail": str(exc),
                "next_action": "Use x-unfollow-handles with an explicit handle list, or add X API credits for automated following scan.",
            }
        )
        return 1
    _print_json(result)
    return 0 if result.get("ok") else 1


async def cmd_x_unfollow_handles(args: argparse.Namespace) -> int:
    twitter = TwitterClient()
    await twitter.start()
    if not twitter.ready:
        _print_json({"ok": False, "error": "twitter_not_ready"})
        return 2

    handles = []
    if args.handles:
        handles.extend([h.strip() for h in args.handles.split(",") if h.strip()])
    if args.handles_file:
        text = Path(args.handles_file).read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            handles.append(line)

    result = await twitter.unfollow_handles(
        handles=handles,
        max_actions=max(0, int(args.max_actions)),
        delay_seconds=float(args.delay_seconds),
        dry_run=not bool(args.apply),
    )
    _print_json(result)
    return 0 if result.get("ok") else 1


async def cmd_x_post(args: argparse.Namespace) -> int:
    twitter = TwitterClient()
    await twitter.start()
    if not twitter.ready:
        _print_json({"ok": False, "error": "twitter_not_ready"})
        return 2

    text = (args.text or "").strip()
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8").strip()
    if not text:
        _print_json({"ok": False, "error": "empty_text"})
        return 2

    post_id = await twitter.post(text)
    _print_json({"ok": True, "id": post_id})
    return 0


async def cmd_substack_post(args: argparse.Namespace) -> int:
    substack = SubstackClient()
    await substack.start()
    if not substack.ready:
        _print_json({"ok": False, "error": "substack_not_ready", "mode": substack.mode})
        return 2

    title = (args.title or "").strip() or "Sapphire Update"
    body = (args.body or "").strip()
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8").strip()
    if not body:
        _print_json({"ok": False, "error": "empty_body"})
        return 2

    post_id = await substack.post(title, body)
    _print_json({"ok": True, "id": post_id, "mode": substack.mode})
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Configure and operate Sapphire social channels")
    parser.add_argument("--env-file", default="", help="Optional .env file to load before execution")

    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show readiness status for X + Substack")
    status.set_defaults(func=cmd_status)

    x_brand = sub.add_parser("x-branding", help="Update X profile metadata and visuals")
    x_brand.add_argument("--name", default="")
    x_brand.add_argument("--bio", default="")
    x_brand.add_argument("--url", default="")
    x_brand.add_argument("--location", default="")
    x_brand.add_argument("--clear-location", action="store_true", help="Clear location field on profile")
    x_brand.add_argument("--banner", default="", help="Path to banner image")
    x_brand.add_argument("--profile-image", default="", help="Path to profile image")
    x_brand.set_defaults(func=cmd_x_branding)

    x_prune = sub.add_parser("x-prune-following", help="Prune low-signal following with conservative safety defaults")
    x_prune.add_argument("--max-scan", type=int, default=400)
    x_prune.add_argument("--max-actions", type=int, default=15)
    x_prune.add_argument("--min-score", type=int, default=2)
    x_prune.add_argument("--delay-seconds", type=float, default=12.0)
    x_prune.add_argument("--keep-handles", default="", help="Comma-separated handles to never unfollow")
    x_prune.add_argument("--keep-handles-env", default="SAPPHIRE_TWITTER_KEEP_HANDLES", help="Env var with comma-separated keep handles")
    x_prune.add_argument("--apply", action="store_true", help="Execute unfollows (default is dry-run)")
    x_prune.set_defaults(func=cmd_x_prune_following)

    x_unfollow = sub.add_parser("x-unfollow-handles", help="Unfollow explicit handles in safe batches")
    x_unfollow.add_argument("--handles", default="", help="Comma-separated handles")
    x_unfollow.add_argument("--handles-file", default="", help="Text file (one handle per line)")
    x_unfollow.add_argument("--max-actions", type=int, default=15)
    x_unfollow.add_argument("--delay-seconds", type=float, default=12.0)
    x_unfollow.add_argument("--apply", action="store_true", help="Execute unfollows (default is dry-run)")
    x_unfollow.set_defaults(func=cmd_x_unfollow_handles)

    x_post = sub.add_parser("x-post", help="Publish text/thread to X")
    x_post.add_argument("--text", default="")
    x_post.add_argument("--file", default="", help="Path to text file")
    x_post.set_defaults(func=cmd_x_post)

    substack_post = sub.add_parser("substack-post", help="Publish a Substack entry")
    substack_post.add_argument("--title", default="Sapphire Weekly Lab Note")
    substack_post.add_argument("--body", default="")
    substack_post.add_argument("--body-file", default="", help="Path to markdown/text file")
    substack_post.set_defaults(func=cmd_substack_post)

    return parser


async def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.env_file:
        if load_dotenv is None:
            _print_json({"ok": False, "error": "python_dotenv_not_installed"})
            return 2
        load_dotenv(args.env_file, override=False)

    return await args.func(args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
