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
from collections.abc import Callable
from pathlib import Path
from typing import Any

SECRETS_DIR = Path.home() / ".config" / "sapphire-secrets"
SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
CLAW_BIN = Path.home() / ".local" / "bin" / "claw"
PLUGIN_DIR = SAPPHIRE_DIR / "plugins" / "claw-sapphire"

Sender = Callable[[str, str | None], dict[str, Any]]


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _read_secret_file(name: str) -> str:
    try:
        return (SECRETS_DIR / name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _load_secret(*env_names: str, file_name: str) -> str:
    for env_name in env_names:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return _read_secret_file(file_name)


def _load_allowed_users(chat_id: str) -> set[int]:
    raw = (
        os.environ.get("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS")
        or os.environ.get("ALLOWED_TELEGRAM_USER_IDS")
        or os.environ.get("TELEGRAM_ALLOWED_USER_IDS")
        or ""
    )
    users = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            users.add(int(part))
        except ValueError:
            continue
    if not users and chat_id:
        try:
            users.add(int(chat_id))
        except ValueError:
            pass
    return users


BOT_TOKEN = _load_secret("TELEGRAM_BOT_TOKEN", file_name="telegram_bot_token")
CHAT_ID = _load_secret("TELEGRAM_CHAT_ID", file_name="telegram_chat_id")
ALLOWED_USERS = _load_allowed_users(CHAT_ID)

# SSL context
_SSL_CTX = ssl.create_default_context()
try:
    import certifi

    _SSL_CTX.load_verify_locations(certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE

ENV = {
    **os.environ,
    "PATH": f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{os.environ.get('PATH', '')}",
}

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
    if not BOT_TOKEN:
        raise RuntimeError("Telegram bot token is not configured")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if data:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def send_message(text: str, chat_id: str | None = None) -> dict:
    """Send Telegram message, splitting if needed."""
    if not text or not text.strip():
        return {"ok": False, "error": "empty_message"}
    chat_id = chat_id or CHAT_ID
    if not chat_id:
        return {"ok": False, "error": "missing_chat_id"}
    if len(text) > 4000:
        text = text[:4000] + "\n\n_(truncated)_"
    if _truthy_env("TELEGRAM_DRY_RUN"):
        return {
            "ok": True,
            "dry_run": True,
            "method": "sendMessage",
            "chat_id": chat_id,
            "text_len": len(text),
        }
    if not BOT_TOKEN:
        return {"ok": False, "error": "missing_bot_token"}
    return tg_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
    )


def run_claw(prompt: str, cwd: str | None = None, timeout: int = 120) -> str:
    """Run claw-code one-shot and return output."""
    work_dir = cwd or str(SAPPHIRE_DIR)

    try:
        proc = subprocess.run(
            [str(CLAW_BIN), "prompt", prompt],
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
            env=ENV,
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
            capture_output=True,
            text=True,
            timeout=60,
            env=ENV,
            cwd=str(SAPPHIRE_DIR),
        )
        return proc.stdout.strip() or proc.stderr.strip()
    except Exception as e:
        return f"Error: {e}"


def handle_command(
    cmd: str,
    args: str,
    chat_id: str,
    sender: Sender | None = None,
) -> str | None:
    """Process a bot command."""
    sender = sender or send_message
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
        sender("🏭 Dispatching...", chat_id)
        return run_tool_direct("dispatch.py", {"task": args.strip()})

    # Market data commands
    elif cmd == "/price" and args:
        sym = args.strip().upper()
        return run_tool_direct("market.py", {"action": "quote", "symbol": sym})
    elif cmd == "/btc":
        return run_tool_direct(
            "market.py", {"action": "crypto", "symbol": "BTC-USD", "start_date": "2026-03-28"}
        )
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

    # Threat intelligence
    elif cmd == "/threats":
        sender("🔍 Scanning threat sources...", chat_id)
        return run_tool_direct("threat_intel.py", {"action": "scan"})
    elif cmd == "/threat" and args:
        sender(f"📋 Generating brief for {args.strip().upper()}...", chat_id)
        result = run_tool_direct("threat_intel.py", {"action": "brief", "target": args.strip()})
        try:
            data = json.loads(result)
            return data.get("output", result)[:4000]
        except Exception:
            return result
    elif cmd == "/offers":
        sender("💰 Analyzing threat revenue opportunities...", chat_id)
        result = run_tool_direct(
            "threat_intel.py",
            {
                "action": "offers",
                "profile": str(Path.home() / "Code/cyber-threat-bot/profiles/kadima-digital.json"),
            },
        )
        try:
            data = json.loads(result)
            return data.get("output", result)[:4000]
        except Exception:
            return result

    # System health
    elif cmd == "/health":
        sender("🔬 Running 20-point health check...", chat_id)
        result = run_tool_direct("health_check.py")
        try:
            data = json.loads(result)
            lines = [f"*{data['overall']}* — {data['summary']}\n"]
            for section in ["services", "repos", "data_freshness", "inference"]:
                for name, info in data.get(section, {}).items():
                    icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(
                        info.get("status"), "⚪"
                    )
                    lines.append(f"{icon} `{name}`: {info.get('detail', '')[:50]}")
            return "\n".join(lines)
        except Exception:
            return result

    # GitHub discovery
    elif cmd == "/repos":
        return run_tool_direct("starred_repos.py", {"action": "sync"})

    # Commands that use claw-code (more capable but slower)
    elif cmd == "/scan":
        sender("🔍 Scanning all repos...", chat_id)
        return run_tool_direct("verify.py", {"all": True})
    elif cmd == "/fix":
        sender("🔧 Running auto-fixer...", chat_id)
        result = subprocess.run(
            ["python3", "-m", "ruff", "check", "--fix", "--select", "E,F,I", "."],
            capture_output=True,
            text=True,
            cwd=str(SAPPHIRE_DIR),
            env=ENV,
            timeout=60,
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
        sender("🧠 Thinking...", chat_id)
        from lib.nemotron import MODELS, generate

        result = generate(args, model=MODELS["classify"], timeout=30)
        if result.success and result.response:
            return f"{result.response}\n\n_({result.endpoint} • {result.model} • {result.eval_tokens} tokens • {result.tokens_per_second} t/s)_"
        return f"❌ {result.error or 'Nemotron returned empty response — model may be loading'}"
    elif cmd == "/think" and args:
        sender("🧠 Deep thinking with nemotron-cascade-2...", chat_id)
        from lib.nemotron import MODELS, generate

        result = generate(args, model=MODELS["analyze"], timeout=120, max_tokens=1024)
        if result.success and result.response:
            return f"{result.response}\n\n_({result.endpoint} • {result.model} • {result.eval_tokens} tokens • {result.tokens_per_second} t/s)_"
        return f"❌ {result.error or 'Nemotron returned empty response — model may be loading'}"
    elif cmd == "/escalate" and args:
        sender("🔴 Escalating to Claude...", chat_id)
        return run_tool_direct("dispatch.py", {"task": args.strip(), "tier": "t3"})
    elif cmd == "/kimi" and args:
        sender("🟡 Routing to Kimi...", chat_id)
        return run_tool_direct("dispatch.py", {"task": args.strip(), "tier": "t1"})
    elif cmd in ("/help", "/start"):
        return """🤖 *NemotronRariBot — Sapphire OS*

*Market Data:*
  /price AAPL — Equity quote (OpenBB)
  /btc — BTC recent bars
  /chart — Live TradingView quote
  /levels [filter] — Indicator levels
  /news [query] — Financial news
  /snapshot AAPL,MSFT — Multi-symbol

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

*Security:*
  /threats — Live threat scan (CISA/NVD)
  /threat CVE-2026-1340 — Deep brief
  /offers — Revenue opportunities

*System:*
  /health — 20-point ecosystem check
  /status — Mesh + inference
  /events — Event stream
  /repos — GitHub starred sync
  /help — This message

💬 *Just type naturally* — Sapphire AI responds using Hermes 3 on RTX 5070 Ti with full conversation memory."""
    else:
        return None  # Not a recognized command


def handle_message(msg: dict, sender: Sender | None = None) -> None:
    """Process a Telegram message."""
    sender = sender or send_message
    chat_id = str(msg["chat"]["id"])
    user_id = msg["from"]["id"]
    text = msg.get("text", "").strip()

    if user_id not in ALLOWED_USERS:
        sender("⛔ Unauthorized.", chat_id)
        return

    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""

        result = handle_command(cmd, args, chat_id, sender=sender)
        if result:
            sender(result, chat_id)
        else:
            sender(f"Unknown command: `{cmd}`. Use /help.", chat_id)
    else:
        # Free text → Hermes 3 conversational AI on Windows GPU
        sender("🧠", chat_id)  # Thinking indicator
        response = chat_with_hermes(text, chat_id)
        sender(response, chat_id)


# ─── Conversational AI (Hermes 3 on Windows GPU) ────────────────────────────

# Per-user conversation history (last N messages)
_chat_history: dict[str, list[dict]] = {}
_MAX_HISTORY = 10

SAPPHIRE_SYSTEM_PROMPT = """You are Sapphire, the AI assistant for Kadima Digital Strategies. You run on a dual-node system: Mac (commander) + Windows PC (RTX 5070 Ti GPU).

Your personality: sharp, concise, technically deep but accessible. You're a trusted advisor, not a chatbot. If you don't know something, say so.

What you know about the system:
- Sapphire OS: autonomous AI operations platform spanning trading, cybersecurity, real estate tech, and intelligence
- 8 code repositories, 1,211+ automated tests, 20 scheduled tasks running 24/7
- Trading pipeline: TradingView → Windows webhook → Mac signal logger, prediction scoring at 67% accuracy
- THO (Texas Home Outlet): client app on Google Cloud Run with 1,963 customers in Firestore, 63 PDF templates
- Cyber-threat-bot: live CISA KEV, NVD, MITRE ATT&CK intelligence with revenue synthesis
- Regional Intel Workbench: business intelligence for Austin/Houston/Gunnison regions
- Inference: Hermes 3 (8B, tool calling), Nemotron Mini (2.7B, fast), Llama 3.2 (3B) on RTX 5070 Ti

When users ask about markets, threats, system status, or projects — give real, actionable answers based on what you know. For specific data queries, suggest they use slash commands like /threats, /health, /price.

Keep responses under 300 words unless the topic warrants depth."""


def chat_with_hermes(user_text: str, chat_id: str) -> str:
    """Send a conversational message to Hermes 3 on Windows GPU."""
    import urllib.error

    # Maintain conversation history per user
    history = _chat_history.get(chat_id, [])
    history.append({"role": "user", "content": user_text})

    # Trim to last N messages
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    _chat_history[chat_id] = history

    messages = [{"role": "system", "content": SAPPHIRE_SYSTEM_PROMPT}] + history

    # Try Windows GPU first, then Mac
    endpoints = [
        ("gpu", "http://100.71.10.48:11434"),
        ("local", "http://localhost:11434"),
    ]

    for ep_name, base_url in endpoints:
        try:
            payload = json.dumps(
                {
                    "model": "hermes3:8b",
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 512},
                }
            ).encode()

            req = urllib.request.Request(
                f"{base_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as resp:
                data = json.loads(resp.read())

            assistant_msg = data.get("message", {}).get("content", "")
            if not assistant_msg:
                continue

            # Add assistant response to history
            history.append({"role": "assistant", "content": assistant_msg})
            _chat_history[chat_id] = history

            # Token stats
            eval_count = data.get("eval_count", 0)
            eval_dur = data.get("eval_duration", 1)
            tps = eval_count / (eval_dur / 1e9) if eval_dur else 0

            return f"{assistant_msg}\n\n_({ep_name} • hermes3:8b • {tps:.0f} t/s)_"

        except Exception:
            continue

    return "❌ All inference endpoints unavailable. Check Ollama on Windows (100.71.10.48:11434) and Mac (localhost:11434)."


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
