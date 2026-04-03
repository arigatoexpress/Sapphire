#!/usr/bin/env python3
"""NemotronRariBot — Thin Telegram webhook service.

Delegates ALL logic to claw-code. The bot is just a UI layer.
Receives Telegram updates via webhook, creates claw-code sessions, returns results.

Run:
    uvicorn app:app --host 0.0.0.0 --port 8088
    # Or for development with polling:
    python3 app.py --poll
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

SECRETS_DIR = Path.home() / ".config" / "sapphire-secrets"
SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
CLAW_BIN = Path.home() / ".local" / "bin" / "claw"
PLUGIN_DIR = SAPPHIRE_DIR / "plugins" / "claw-sapphire"

BOT_TOKEN = (SECRETS_DIR / "telegram_bot_token").read_text().strip()
CHAT_ID = (SECRETS_DIR / "telegram_chat_id").read_text().strip()
ALLOWED_USERS = {int(CHAT_ID)}

# SSL context
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE

ENV = {**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{os.environ.get('PATH', '')}"}

# Command → claw-code prompt mapping
# Each command becomes a claw-code session that uses Sapphire plugin tools
COMMAND_MAP = {
    "/status": "Use sapphire_status to show the current mesh device status and inference endpoints. Format as a concise report.",
    "/scan": "Use sapphire_verify with all=true to scan all repos. Report lint errors, test status, and which repos are safe to commit.",
    "/fix": "Run `python3 -m ruff check --fix --select E,F,I .` in each Python repo under ~/Code/. Report how many errors were fixed per repo.",
    "/models": "Use sapphire_status to list all available Ollama models on GPU and local endpoints. Format as a concise list.",
    "/events": "Read the last 15 lines of ~/Code/Sapphire/data/system_events.jsonl and format them as a readable timeline.",
    "/budget": "Use sapphire_budget to show today's token usage per inference tier.",
    "/state": "Use sapphire_state with action=metrics to show factory metrics — issues tracked, fixed, in backoff.",
}


def tg_api(method: str, data: dict | None = None) -> dict:
    """Call Telegram Bot API."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if data:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def send_message(text: str, chat_id: str = CHAT_ID) -> dict:
    """Send Telegram message, splitting if needed."""
    if len(text) > 4000:
        text = text[:4000] + "\n\n_(truncated)_"
    return tg_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })


def run_claw(prompt: str, cwd: str | None = None, timeout: int = 120) -> str:
    """Run claw-code one-shot and return output."""
    work_dir = cwd or str(SAPPHIRE_DIR)

    try:
        proc = subprocess.run(
            [str(CLAW_BIN), "prompt", prompt],
            capture_output=True, text=True,
            cwd=work_dir, timeout=timeout, env=ENV,
        )
        return proc.stdout.strip() or proc.stderr.strip() or "No output"
    except subprocess.TimeoutExpired:
        return "⏱️ Task timed out"
    except FileNotFoundError:
        return "❌ Claw binary not found"
    except Exception as e:
        return f"❌ Error: {e}"


def run_tool_direct(tool_script: str, input_data: dict | None = None) -> str:
    """Run a Sapphire plugin tool directly (faster than claw for simple queries)."""
    tool_path = PLUGIN_DIR / "tools" / tool_script
    if not tool_path.exists():
        return f"Tool not found: {tool_script}"

    try:
        proc = subprocess.run(
            ["python3", str(tool_path)],
            input=json.dumps(input_data or {}),
            capture_output=True, text=True,
            timeout=60, env=ENV, cwd=str(SAPPHIRE_DIR),
        )
        return proc.stdout.strip() or proc.stderr.strip()
    except Exception as e:
        return f"Error: {e}"


def handle_command(cmd: str, args: str, chat_id: str) -> str:
    """Process a bot command."""
    # Direct tool calls (fast, no claw overhead)
    if cmd == "/status":
        return run_tool_direct("status.py")
    elif cmd == "/budget":
        return run_tool_direct("budget.py")
    elif cmd == "/state":
        return run_tool_direct("state.py", {"action": "metrics"})
    elif cmd == "/verify" and args:
        return run_tool_direct("verify.py", {"repo": args.strip()})
    elif cmd == "/dispatch" and args:
        send_message("🏭 Dispatching...", chat_id)
        return run_tool_direct("dispatch.py", {"task": args.strip()})

    # Market data commands
    elif cmd == "/price" and args:
        sym = args.strip().upper()
        return run_tool_direct("market.py", {"action": "quote", "symbol": sym})
    elif cmd == "/btc":
        return run_tool_direct("market.py", {"action": "crypto", "symbol": "BTC-USD", "start_date": "2026-03-28"})
    elif cmd == "/chart":
        return run_tool_direct("market.py", {"action": "tv_quote"})
    elif cmd == "/levels":
        filter_name = args.strip() if args else None
        return run_tool_direct("market.py", {"action": "tv_levels", "filter": filter_name})
    elif cmd == "/strategy":
        return run_tool_direct("market.py", {"action": "tv_strategy"})
    elif cmd == "/news":
        query = args.strip() if args else "crypto"
        return run_tool_direct("market.py", {"action": "news", "query": query, "limit": 5})
    elif cmd == "/snapshot" and args:
        symbols = [s.strip().upper() for s in args.split(",")]
        return run_tool_direct("market.py", {"action": "snapshot", "symbols": symbols})

    # Commands that use claw-code (more capable but slower)
    elif cmd == "/scan":
        send_message("🔍 Scanning all repos...", chat_id)
        return run_tool_direct("verify.py", {"all": True})
    elif cmd == "/fix":
        send_message("🔧 Running auto-fixer...", chat_id)
        result = subprocess.run(
            ["python3", "-m", "ruff", "check", "--fix", "--select", "E,F,I", "."],
            capture_output=True, text=True, cwd=str(SAPPHIRE_DIR), env=ENV, timeout=60,
        )
        return result.stdout.strip() or "No fixable errors"
    elif cmd == "/events":
        events_path = SAPPHIRE_DIR / "data" / "system_events.jsonl"
        if events_path.exists():
            lines = events_path.read_text().strip().splitlines()[-15:]
            out = ["📊 *Recent Events:*\n"]
            for line in lines:
                try:
                    e = json.loads(line)
                    ts = e["timestamp"][:19]
                    out.append(f"`{ts}` {e['type']}: {e['message'][:60]}")
                except Exception:
                    pass
            return "\n".join(out)
        return "No events found"
    elif cmd == "/models":
        return run_tool_direct("status.py")
    elif cmd == "/ask" and args:
        send_message("🧠 Thinking...", chat_id)
        from lib.nemotron import MODELS, generate
        result = generate(args, model=MODELS["classify"], timeout=30)
        if result.success:
            return f"{result.response}\n\n_({result.endpoint} • {result.model} • {result.eval_tokens} tokens • {result.tokens_per_second} t/s)_"
        return f"❌ {result.error}"
    elif cmd == "/think" and args:
        send_message("🧠 Deep thinking with nemotron-cascade-2...", chat_id)
        from lib.nemotron import MODELS, generate
        result = generate(args, model=MODELS["analyze"], timeout=120, max_tokens=1024)
        if result.success:
            return f"{result.response}\n\n_({result.endpoint} • {result.model} • {result.eval_tokens} tokens • {result.tokens_per_second} t/s)_"
        return f"❌ {result.error}"
    elif cmd == "/escalate" and args:
        send_message("🔴 Escalating to Claude...", chat_id)
        return run_tool_direct("dispatch.py", {"task": args.strip(), "tier": "t3"})
    elif cmd == "/kimi" and args:
        send_message("🟡 Routing to Kimi...", chat_id)
        return run_tool_direct("dispatch.py", {"task": args.strip(), "tier": "t1"})
    elif cmd in ("/help", "/start"):
        return """🤖 *NemotronRariBot — Sapphire OS*

*Market Data:*
  /price AAPL — Equity quote (OpenBB)
  /btc — BTC recent bars
  /chart — Live TradingView quote
  /levels [filter] — Indicator levels from chart
  /strategy — Strategy tester results
  /news [query] — Financial news
  /snapshot AAPL,MSFT,NVDA — Multi-symbol

*Factory:*
  /dispatch <task> — Auto-route to best tier
  /scan — Verify all repos
  /fix — Auto-fix lint
  /budget — Token usage per tier
  /state — Factory metrics

*Inference:*
  /ask <q> — Nemotron Nano (196 t/s)
  /think <q> — Cascade-2 (31.6B)
  /kimi <task> — Force Kimi CLI
  /escalate <task> — Force Claude

*System:*
  /status — Mesh + inference
  /events — Event stream
  /help — This message

_Free text → Nemotron inference_"""
    else:
        return None  # Not a recognized command


def handle_message(msg: dict) -> None:
    """Process a Telegram message."""
    chat_id = str(msg["chat"]["id"])
    user_id = msg["from"]["id"]
    text = msg.get("text", "").strip()

    if user_id not in ALLOWED_USERS:
        send_message("⛔ Unauthorized.", chat_id)
        return

    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""

        result = handle_command(cmd, args, chat_id)
        if result:
            send_message(result, chat_id)
        else:
            send_message(f"Unknown command: `{cmd}`. Use /help.", chat_id)
    else:
        # Free text → Nemotron inference
        sys.path.insert(0, str(PLUGIN_DIR / "lib"))
        from nemotron import MODELS, generate
        result = generate(text, model=MODELS["classify"], timeout=30)
        if result.success:
            send_message(
                f"{result.response}\n\n_({result.endpoint} • {result.tokens_per_second} t/s)_",
                chat_id,
            )
        else:
            send_message(f"❌ {result.error}", chat_id)


def poll_loop() -> None:
    """Long-polling mode for development."""
    import time
    print("🤖 NemotronRariBot (polling mode)")
    print(f"   Allowed users: {ALLOWED_USERS}")

    offset = 0
    while True:
        try:
            result = tg_api("getUpdates", {"offset": offset, "timeout": 30})
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update:
                    handle_message(update["message"])
        except KeyboardInterrupt:
            print("\n👋 Bot stopped.")
            break
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(5)


if __name__ == "__main__":
    if "--poll" in sys.argv:
        poll_loop()
    else:
        print("Use: python3 app.py --poll  (for development)")
        print("Or:  uvicorn app:app --host 0.0.0.0 --port 8088  (for production)")
