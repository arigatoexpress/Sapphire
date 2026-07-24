#!/usr/bin/env python3
"""Send architecture bottleneck digest to Telegram using live platform telemetry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _read_json(url: str, timeout: float = 15.0, auth: tuple[str, str] | None = None) -> dict[str, Any]:
    resp = requests.get(url, timeout=timeout, auth=auth)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _build_message(telemetry: dict[str, Any], brief: dict[str, Any]) -> tuple[str, str]:
    summary = telemetry.get("summary", {}) if isinstance(telemetry.get("summary"), dict) else {}
    thresholds = telemetry.get("thresholds", {}) if isinstance(telemetry.get("thresholds"), dict) else {}
    bottlenecks = telemetry.get("bottlenecks", []) if isinstance(telemetry.get("bottlenecks"), list) else []

    signals = int(summary.get("signals", 0) or 0)
    executions = int(summary.get("executions", 0) or 0)
    conversion = _clamp(_as_float(summary.get("conversion_rate_pct"), 0.0), 0.0, 100.0)
    conversion_sev = str(summary.get("conversion_severity", "steady")).lower()
    risk_state = str((brief.get("summary", {}) if isinstance(brief.get("summary"), dict) else {}).get("risk_state", "stable")).upper()

    watch_edges = [row for row in bottlenecks if str(row.get("severity", "")).lower() == "watch"]
    steady_edges = [row for row in bottlenecks if str(row.get("severity", "")).lower() == "steady"]

    lines = [
        "⚙️ <b>Sapphire Bottleneck Digest</b>",
        f"Time: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"Conversion: <b>{conversion:.1f}%</b> ({conversion_sev.upper()}) • {executions}/{signals} executions/signals",
        f"Risk State: <b>{risk_state}</b>",
    ]

    if watch_edges:
        lines.append("")
        lines.append("🚨 <b>Watch Lanes</b>")
        for row in watch_edges[:5]:
            src = str(row.get("source", "--")).replace("_", " ").title()
            tgt = str(row.get("target", "--")).replace("_", " ").title()
            tph = _as_float(row.get("throughput"), 0.0)
            label = str(row.get("label", "Flow lane"))
            lines.append(f"• {src} → {tgt}: <b>{tph:.2f}/h</b> ({label})")
    elif steady_edges:
        lines.append("")
        lines.append("🟡 <b>Steady Lanes</b>")
        for row in steady_edges[:4]:
            src = str(row.get("source", "--")).replace("_", " ").title()
            tgt = str(row.get("target", "--")).replace("_", " ").title()
            tph = _as_float(row.get("throughput"), 0.0)
            lines.append(f"• {src} → {tgt}: <b>{tph:.2f}/h</b>")
    else:
        lines.append("")
        lines.append("✅ No active watch bottlenecks in current telemetry window.")

    lines.append("")
    lines.append(
        "Thresholds: "
        f"lane watch&lt;{_as_float(thresholds.get('bottleneck_watch_tph'), 0.5):.2f}/h, "
        f"lane steady&lt;{_as_float(thresholds.get('bottleneck_steady_tph'), 1.1):.2f}/h, "
        f"conversion watch&lt;{_as_float(thresholds.get('conversion_watch_pct'), 55.0):.1f}%"
    )

    signature_payload = {
        "watch": [row.get("id") for row in watch_edges[:6]],
        "steady": [row.get("id") for row in steady_edges[:6]],
        "conversion_sev": conversion_sev,
        "conversion": round(conversion, 2),
        "risk_state": risk_state,
    }
    signature = hashlib.sha256(json.dumps(signature_payload, sort_keys=True).encode("utf-8")).hexdigest()
    return "\n".join(lines), signature


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _send_telegram(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Send architecture bottleneck digest")
    parser.add_argument("--domain", default=os.getenv("DOMAIN", "https://sapphirealpha.xyz"))
    parser.add_argument("--hours", type=int, default=int(os.getenv("BOTTLENECK_DIGEST_HOURS", "6")))
    parser.add_argument("--min-interval-sec", type=int, default=int(os.getenv("BOTTLENECK_DIGEST_MIN_INTERVAL_SEC", "3600")))
    parser.add_argument("--dry-run", action="store_true", help="Print digest and skip Telegram send")
    parser.add_argument("--force", action="store_true", help="Send even if no watch bottlenecks")
    args = parser.parse_args()

    domain = args.domain.rstrip("/")
    auth_user = os.getenv("AUTH_USER", "").strip()
    auth_pass = os.getenv("AUTH_PASS", "").strip()
    auth = (auth_user, auth_pass) if auth_user and auth_pass else None

    telemetry = _read_json(f"{domain}/api/platform/architecture-telemetry?hours={max(1, args.hours)}", auth=auth)
    brief = _read_json(f"{domain}/api/platform/business-brief?hours=24", auth=auth)
    message, signature = _build_message(telemetry, brief)

    summary = telemetry.get("summary", {}) if isinstance(telemetry.get("summary"), dict) else {}
    bottlenecks = telemetry.get("bottlenecks", []) if isinstance(telemetry.get("bottlenecks"), list) else []
    has_watch = any(str(row.get("severity", "")).lower() == "watch" for row in bottlenecks)
    conversion_sev = str(summary.get("conversion_severity", "steady")).lower()
    should_send = args.force or has_watch or conversion_sev == "watch"

    state_path = Path(__file__).resolve().parents[1] / "output" / "bottleneck_digest_state.json"
    state = _load_state(state_path)
    now_ts = int(time.time())
    last_sig = str(state.get("signature", ""))
    last_ts = int(state.get("sent_at", 0) or 0)
    cooled_down = (now_ts - last_ts) >= max(0, args.min_interval_sec)
    changed = signature != last_sig

    print(message)
    print(f"\nshould_send={should_send} changed={changed} cooled_down={cooled_down}")

    if args.dry_run:
        return 0

    if not should_send:
        print("skip: no watch-level bottleneck trigger")
        return 0
    if not (changed or cooled_down):
        print("skip: unchanged digest within cooldown window")
        return 0

    token = (
        os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        or os.getenv("SAPPHIRE_TELEGRAM_BOT_TOKEN", "").strip()
    )
    chat_id = (
        os.getenv("TELEGRAM_CHAT_ID", "").strip()
        or os.getenv("TELEGRAM_BOT_CHAT_ID", "").strip()
        or os.getenv("TELEGRAM_OWNER_USER_ID", "").strip()
    )
    if not token or not chat_id:
        print("skip: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured")
        return 0

    _send_telegram(token=token, chat_id=chat_id, message=message)
    _save_state(state_path, {"sent_at": now_ts, "signature": signature, "domain": domain})
    print("telegram_digest_sent=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
