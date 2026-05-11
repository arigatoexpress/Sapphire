#!/usr/bin/env python3
"""Plan or explicitly apply Sapphire PM bot Telegram webhook registration.

Default mode is dry-run: build the exact Bot API ``setWebhook`` plan without
calling Telegram. Applying the webhook is an external Telegram mutation and
requires both ``--apply`` and ``SAPPHIRE_PM_BOT_REGISTER_WEBHOOK_APPLY=1``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PM_BOT_DIR = REPO_ROOT / "services" / "pm_bot"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PM_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(PM_BOT_DIR))

import server  # noqa: E402

APPLY_ENV = "SAPPHIRE_PM_BOT_REGISTER_WEBHOOK_APPLY"


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _sanitize_jsonable(value: Any) -> Any:
    """Return a JSON-safe value with Telegram credentials redacted."""

    try:
        text = json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        text = json.dumps(str(value))
    return json.loads(server._redact_sensitive_text(text))


def build_webhook_readiness_report(
    *,
    url: str,
    secret_token_configured: bool,
    drop_pending_updates: bool = False,
    apply: bool = False,
    apply_gate_enabled: bool = False,
    apply_response: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    """Build a sanitized registration/readiness report."""

    blockers: list[str] = []
    plan: dict[str, Any] | None = None
    if not url:
        blockers.append("missing_webhook_url")
    else:
        try:
            plan = server.sanitized_webhook_registration_plan(
                url=url,
                secret_token_configured=secret_token_configured,
                drop_pending_updates=drop_pending_updates,
                allowed_updates=server._SUPPORTED_UPDATE_TYPES,
            )
        except ValueError as exc:
            blockers.append(str(exc).replace(" ", "_"))

    if apply and not apply_gate_enabled:
        blockers.append(f"{APPLY_ENV}_not_enabled")
    if error:
        blockers.append("telegram_apply_failed")

    if error:
        status = "error"
    elif blockers:
        status = "blocked"
    elif apply:
        status = "applied"
    else:
        status = "dry_run"

    return {
        "status": status,
        "dry_run": not apply,
        "apply_requested": apply,
        "apply_gate_enabled": apply_gate_enabled,
        "mode": server.SETTINGS.mode,
        "token_role": server._telegram_token_role(),
        "webhook_secret_configured": secret_token_configured,
        "plan": plan,
        "blockers": blockers,
        "telegram_response": _sanitize_jsonable(apply_response or {}),
        "error": server._redact_sensitive_text(error) if error else "",
        "safety": {
            "calls_telegram": bool(apply and not blockers and apply_response is not None),
            "sends_telegram_messages": False,
            "starts_polling": False,
            "touches_trading": False,
        },
    }


def _emit(report: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(f"Status: {report['status']}")
    print(f"Mode: {report['mode']}")
    print(f"Token role: {report['token_role']}")
    print(f"Dry run: {report['dry_run']}")
    if report["blockers"]:
        print("Blockers: " + ", ".join(report["blockers"]))
    plan = report.get("plan") or {}
    if plan:
        print(f"Webhook URL: {plan['url']}")
        print(f"Allowed updates: {plan['allowed_update_count']}")
        print(f"Secret configured: {plan['secret_token_configured']}")
        print(f"Apply gate: {plan['apply_gate']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.getenv("SAPPHIRE_PM_BOT_WEBHOOK_URL", "").strip(),
        help="Public HTTPS webhook URL. Defaults to SAPPHIRE_PM_BOT_WEBHOOK_URL.",
    )
    parser.add_argument("--drop-pending-updates", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Call Telegram setWebhook.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    apply_gate_enabled = _env_enabled(APPLY_ENV)
    url = str(args.url or "").strip()
    secret = server.SETTINGS.webhook_secret

    initial = build_webhook_readiness_report(
        url=url,
        secret_token_configured=bool(secret),
        drop_pending_updates=bool(args.drop_pending_updates),
        apply=bool(args.apply),
        apply_gate_enabled=apply_gate_enabled,
    )
    if initial["blockers"]:
        _emit(initial, json_output=bool(args.json))
        return 2

    if not args.apply:
        _emit(initial, json_output=bool(args.json))
        return 0

    try:
        response = server.TELEGRAM_API.set_webhook(
            url=url,
            secret_token=secret,
            drop_pending_updates=bool(args.drop_pending_updates),
            allowed_updates=server._SUPPORTED_UPDATE_TYPES,
        )
        report = build_webhook_readiness_report(
            url=url,
            secret_token_configured=bool(secret),
            drop_pending_updates=bool(args.drop_pending_updates),
            apply=True,
            apply_gate_enabled=apply_gate_enabled,
            apply_response=response,
        )
    except Exception as exc:  # pragma: no cover - live Telegram behavior
        report = build_webhook_readiness_report(
            url=url,
            secret_token_configured=bool(secret),
            drop_pending_updates=bool(args.drop_pending_updates),
            apply=True,
            apply_gate_enabled=apply_gate_enabled,
            error=str(exc),
        )
    _emit(report, json_output=bool(args.json))
    return 0 if report["status"] == "applied" else 1


if __name__ == "__main__":
    raise SystemExit(main())
