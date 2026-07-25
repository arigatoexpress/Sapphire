"""CLI entrypoint for the LaunchAgent.

Usage:
    python3 -m lib.content                 # run today's scheduled slots
    python3 -m lib.content --kind weekly_crypto_brief
    python3 -m lib.content --all           # generate every report kind
    python3 -m lib.content --list-drafts

Language selection:
    python3 -m lib.content --kind weekly_crypto_brief --language es
    python3 -m lib.content --kind weekly_crypto_brief --language en,es
Without --language, the scheduler's TARGET_LANGUAGES for that report kind
is used (crypto brief and market pulse default to en+es).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or anywhere: add repo to sys.path
REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.content import publisher, report_generator, scheduler  # noqa: E402
from lib.core.routine_pause import abort_if_paused  # noqa: E402

GENERATORS = {
    "weekly_crypto_brief": report_generator.generate_weekly_crypto_brief,
    "ai_intel": report_generator.generate_ai_intel_report,
    "security_digest": report_generator.generate_security_digest,
    "market_pulse": report_generator.generate_market_pulse_tweet,
}


def run_kind(kind: str, languages: list[str] | None = None) -> dict:
    gen = GENERATORS.get(kind)
    if gen is None:
        raise SystemExit(f"unknown report kind: {kind}")
    report = gen()
    return publisher.publish(report, languages=languages)


def main(argv: list[str] | None = None) -> int:
    abort_if_paused("content-engine")
    ap = argparse.ArgumentParser(prog="lib.content")
    ap.add_argument("--kind", help="Generate a specific report kind")
    ap.add_argument("--all", action="store_true", help="Run every report kind")
    ap.add_argument("--list-drafts", action="store_true")
    ap.add_argument(
        "--publish",
        action="store_true",
        help="Run the live publishers against data/content/ready/ (dry-run unless SAPPHIRE_PUBLISH_LIVE=1)",
    )
    ap.add_argument(
        "--callback",
        help="Process a Telegram approval callback (e.g. 'apv:weekly-crypto-brief')",
    )
    ap.add_argument("--callback-id", help="Telegram callback_query.id (stops button spinner)")
    ap.add_argument("--chat-id", help="Chat ID of the original approval message (for edit)")
    ap.add_argument("--message-id", type=int, help="Message ID of the original approval (for edit)")
    ap.add_argument("--actor", default="telegram", help="Approver identity (for approval record)")
    ap.add_argument(
        "--language",
        help="Comma-separated language codes to render (e.g. 'en', 'es', 'en,es'). "
        "Overrides scheduler.TARGET_LANGUAGES for this run.",
    )
    args = ap.parse_args(argv)

    languages: list[str] | None = None
    if args.language:
        languages = [x.strip() for x in args.language.split(",") if x.strip()]

    if args.callback:
        from lib.content import telegram_approval

        out = telegram_approval.handle_callback(
            args.callback,
            callback_id=args.callback_id,
            chat_id=args.chat_id,
            message_id=args.message_id,
            actor=args.actor,
        )
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("ok") else 1

    if args.list_drafts:
        print(json.dumps(publisher.list_drafts(), indent=2, default=str))
        return 0

    if args.publish:
        from lib.content import auto_publish  # lazy — pulls in requests path

        out = auto_publish.run()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.kind:
        out = run_kind(args.kind, languages=languages)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.all:
        results = {k: run_kind(k, languages=languages) for k in GENERATORS}
        print(json.dumps(results, indent=2, default=str))
        return 0

    # Default: run today's scheduled slots
    results = []
    for slot in scheduler.today_plan():
        results.append(run_kind(slot.report_kind, languages=languages))
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
