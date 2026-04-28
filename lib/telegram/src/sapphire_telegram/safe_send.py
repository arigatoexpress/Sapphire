"""Safe Telegram sender — plaintext-first, with Markdown retry-fallback, splitting, and backoff.

Everything fans through `send()`. Callers get a robust HTTP surface that never
fails on parse errors, rate limits, or oversized messages.

Usage (Python):
    from sapphire_telegram.safe_send import send
    send("message text", priority="p1")
    send("📊 *Daily digest*\\n- line 1", parse_mode="markdown")
    send("chart attached", photo="/path/to/chart.png")

Usage (CLI):
    python -m sapphire_telegram.safe_send "msg" --priority p1
    python -m sapphire_telegram.safe_send "msg" --parse markdown
    python -m sapphire_telegram.safe_send "msg" --photo /path/to.png
"""

from __future__ import annotations

import json
import os
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_SSL_CTX = ssl.create_default_context()
try:
    import certifi

    _SSL_CTX.load_verify_locations(certifi.where())
except ImportError:
    pass

_TELEGRAM_LIMIT = 4096
_CHUNK_LIMIT = 3800  # leave headroom for prefix
_DEFAULT_TIMEOUT = 10

_SECRET_PATHS = [
    Path.home() / ".config" / "sapphire-secrets",
    Path.home() / ".config" / "sapphire",
]

# MarkdownV2 reserved chars per https://core.telegram.org/bots/api#markdownv2-style
_MDV2_RESERVED = r"_*[]()~`>#+-=|{}.!"

_PRIORITY_PREFIX = {
    "p0": "🚨",
    "p1": "📋",
    "p2": "ℹ️",
}


def get_bot_token(override: str | None = None) -> str | None:
    if override:
        return override.strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token.strip()
    for prefix in _SECRET_PATHS:
        path = prefix / "telegram_bot_token"
        if path.exists():
            return path.read_text().strip()
    env_path = Path.home() / "Code" / "Sapphire" / "services" / "control-plane" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get_chat_id(override: str | None = None) -> str | None:
    if override:
        return str(override).strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if chat:
        return chat.strip()
    allowed = os.environ.get("ALLOWED_TELEGRAM_CHAT_IDS", "")
    if allowed:
        first = allowed.split(",")[0].strip()
        if first:
            return first
    for prefix in _SECRET_PATHS:
        path = prefix / "telegram_chat_id"
        if path.exists():
            return path.read_text().strip()
    return None


def escape_markdown_v2(text: str) -> str:
    """Escape every MarkdownV2 reserved char so text renders literally."""
    return re.sub(rf"([{re.escape(_MDV2_RESERVED)}])", r"\\\1", text)


def safe_markdown(text: str) -> str:
    """Heuristic: keep *bold* and `code` intact, escape everything else.

    Splits on formatting markers, escapes non-marker segments, leaves markers alone.
    Use when you want *some* Markdown but want to survive ragged user-authored text.
    """
    # Very conservative: only preserve **bold**, `inline code`, and simple [label](url).
    # Strip * from single-star italics (they collide with underscores/asterisks in normal prose).
    out: list[str] = []
    i = 0
    while i < len(text):
        # `code span`
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end != -1:
                out.append(text[i : end + 1])
                i = end + 1
                continue
        # **bold**
        if text[i : i + 2] == "**":
            end = text.find("**", i + 2)
            if end != -1:
                inner = text[i + 2 : end]
                out.append(f"*{escape_markdown_v2(inner)}*")
                i = end + 2
                continue
        # [label](url)
        if text[i] == "[":
            close_label = text.find("]", i + 1)
            if close_label != -1 and close_label + 1 < len(text) and text[close_label + 1] == "(":
                close_url = text.find(")", close_label + 2)
                if close_url != -1:
                    label = text[i + 1 : close_label]
                    url = text[close_label + 2 : close_url]
                    out.append(f"[{escape_markdown_v2(label)}]({url})")
                    i = close_url + 1
                    continue
        # everything else gets per-char escape
        ch = text[i]
        if ch in _MDV2_RESERVED:
            out.append("\\" + ch)
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def split_message(text: str, limit: int = _CHUNK_LIMIT) -> list[str]:
    """Split on newlines; single line over limit is hard-chunked."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            # flush buf first
            if buf:
                chunks.append("".join(buf))
                buf = []
                buf_len = 0
            # hard-chunk the long line
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            continue
        if buf_len + len(line) > limit:
            chunks.append("".join(buf))
            buf = [line]
            buf_len = len(line)
        else:
            buf.append(line)
            buf_len += len(line)
    if buf:
        chunks.append("".join(buf))
    return chunks


def _post(url: str, payload: dict, timeout: int = _DEFAULT_TIMEOUT) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace") if e.fp else ""
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"description": body}
        return e.code, parsed
    except Exception as e:
        return 0, {"description": str(e), "network_error": True}


def _post_multipart(
    url: str, fields: dict, file_field: str, file_path: Path, timeout: int = 30
) -> tuple[int, dict]:
    boundary = f"----SapphireBoundary{random.randint(10**9, 10**10)}"
    body = bytearray()
    for k, v in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        body += f"{v}\r\n".encode()
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += file_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        body_out = e.read().decode(errors="replace") if e.fp else ""
        try:
            parsed = json.loads(body_out) if body_out else {}
        except json.JSONDecodeError:
            parsed = {"description": body_out}
        return e.code, parsed
    except Exception as e:
        return 0, {"description": str(e), "network_error": True}


def _send_one(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str | None,
    retries: int = 3,
    reply_markup: dict | None = None,
) -> dict:
    """Send one chunk with retries, Markdown→plaintext fallback, 429 honoring."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    last_resp: dict = {}
    for attempt in range(retries):
        status, resp = _post(url, payload)
        last_resp = resp
        if status == 200 and resp.get("ok"):
            return resp
        # 400 with parse error → strip parse_mode and try once more
        desc = (resp.get("description") or "").lower()
        if status == 400 and "parse" in desc and "parse_mode" in payload:
            payload.pop("parse_mode")
            continue
        # 429 → honor retry_after
        if status == 429:
            wait = resp.get("parameters", {}).get("retry_after", 2**attempt)
            time.sleep(min(int(wait) + 1, 60))
            continue
        # 5xx / network → backoff
        if status == 0 or 500 <= status < 600:
            time.sleep(2**attempt + random.uniform(0, 1))
            continue
        # 401/403 — no point retrying
        break
    return {"error": last_resp, "ok": False}


def send(
    text: str,
    *,
    priority: str = "p1",
    parse_mode: str | None = None,
    photo: str | Path | None = None,
    bot_token: str | None = None,
    chat_id: str | None = None,
    prefix: bool = True,
    banner: str | None = "*Sapphire OS*",
    reply_markup: dict | None = None,
) -> dict:
    """Send a Telegram message with robust error handling.

    Args:
        text: Message body (plaintext by default — NOT escaped).
        priority: "p0" | "p1" | "p2" — maps to prefix emoji.
        parse_mode: None (plaintext, default), "markdown", or "markdownv2".
            When set, safe_markdown escaping is applied so ragged user text doesn't 400.
        photo: path to an image to attach via sendPhoto (text becomes caption).
        bot_token / chat_id: overrides.
        prefix: prepend priority emoji + banner.
        banner: optional top line (pass None to skip).

    Returns:
        Dict with `ok: bool` and metadata. Never raises on API errors.
    """
    token = get_bot_token(bot_token)
    target = get_chat_id(chat_id)
    if not token:
        return {"ok": False, "error": "missing_bot_token"}
    if not target:
        return {"ok": False, "error": "missing_chat_id"}

    # Normalize parse_mode argument
    pm = None
    if parse_mode:
        pm_lower = parse_mode.lower().strip()
        if pm_lower in ("markdown", "markdownv2", "md"):
            pm = "MarkdownV2"
            text = safe_markdown(text)

    # Apply prefix/banner
    if prefix:
        emoji = _PRIORITY_PREFIX.get(priority, "📋")
        head_parts = [emoji]
        if banner:
            head_parts.append(safe_markdown(banner) if pm else banner)
        head = " ".join(head_parts)
        text = f"{head}\n\n{text}" if text else head

    # Inline keyboard can't span chunks — if set, truncate to one chunk to keep button attached.
    if reply_markup:
        if len(text) > _CHUNK_LIMIT:
            text = text[: _CHUNK_LIMIT - 20] + "\n… [truncated]"
        r = _send_one(token, target, text, pm, reply_markup=reply_markup)
        return {"ok": r.get("ok", False), "chunks": 1, "results": [r]}

    # Photo: send as single message with caption (truncated if necessary)
    if photo:
        photo_path = Path(photo).expanduser()
        if not photo_path.exists():
            return {"ok": False, "error": f"photo_not_found: {photo_path}"}
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        caption = text[:1024]  # Telegram caption limit
        fields = {
            "chat_id": target,
            "caption": caption,
            "disable_web_page_preview": "true",
        }
        if pm:
            fields["parse_mode"] = pm
        status, resp = _post_multipart(url, fields, "photo", photo_path)
        if status == 200 and resp.get("ok"):
            return resp
        # Fallback: strip parse_mode and retry once
        if status == 400 and "parse_mode" in fields:
            fields.pop("parse_mode")
            status2, resp2 = _post_multipart(url, fields, "photo", photo_path)
            if status2 == 200:
                return resp2
        return {"ok": False, "error": resp, "status": status}

    # Split + send chunks
    chunks = split_message(text, _CHUNK_LIMIT)
    results = []
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            tag = f"\n\n_({i + 1}/{len(chunks)})_" if pm else f"\n\n({i + 1}/{len(chunks)})"
            chunk = chunk + (tag if i == len(chunks) - 1 else "")
        r = _send_one(token, target, chunk, pm)
        results.append(r)
        if len(chunks) > 1 and i < len(chunks) - 1:
            time.sleep(0.35)  # polite pacing between chunks
    ok = all(r.get("ok") for r in results)
    return {"ok": ok, "chunks": len(chunks), "results": results}


def main() -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Safe Telegram sender")
    p.add_argument("message", help="Message text ('-' reads from stdin)")
    p.add_argument("--priority", default="p1", choices=["p0", "p1", "p2"])
    p.add_argument("--parse", default=None, choices=["markdown", "markdownv2", "md"])
    p.add_argument("--photo", default=None, help="Attach image path")
    p.add_argument("--no-prefix", action="store_true", help="Skip priority emoji + banner")
    p.add_argument(
        "--banner", default="*Sapphire OS*", help="Header banner (or empty string to skip)"
    )
    args = p.parse_args()

    text = sys.stdin.read() if args.message == "-" else args.message
    result = send(
        text,
        priority=args.priority,
        parse_mode=args.parse,
        photo=args.photo,
        prefix=not args.no_prefix,
        banner=args.banner or None,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
