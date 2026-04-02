#!/usr/bin/env python3
"""
Telegram Bot Controller for Autonomous Trading

Handles incoming Telegram commands and controls the trading daemon.

Usage:
    python3 telegram_bot_controller.py
    
Commands:
    /start - Show welcome message
    /status - Check trading system status
    /pause - Pause trading
    /resume - Resume trading
    /trade - Execute manual trade
    /mode - Check/set trading mode
    /stats - Show trading statistics
    /help - Show help message
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Configuration
DAEMON_STATE_FILE = Path("/home/rari/.openclaw/runtime/codex-projects/output/trading-daemon/daemon_state.json")
KIMI_BIN = os.getenv("KIMI_BIN", "/home/rari/.local/bin/kimi")
GATEWAY_SIGNAL_URL = os.getenv(
    "SAPPHIRE_GATEWAY_SIGNAL_URL",
    "https://sapphire-gateway-267358751314.us-central1.run.app/api/signals/create",
).strip()
KNOWN_TRADE_PLATFORMS = {"aster", "lighter", "both"}
ENV_FILES = [
    Path("/home/rari/kimi-claw/.env"),
    Path("/home/rari/kimi-claw-v2/.env"),
    Path("/home/rari/.openclaw/trading_api/.env"),
]


def _load_env_value(key: str, files: list[Path]) -> str:
    """Load key from environment, then fallback env files."""
    env_val = os.getenv(key, "").strip()
    if env_val:
        return env_val

    for env_file in files:
        try:
            if not env_file.exists():
                continue
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
        except Exception:
            continue
    return ""


BOT_TOKEN = _load_env_value(
    "TELEGRAM_BOT_TOKEN",
    ENV_FILES,
)

CONTROL_API_TOKEN = _load_env_value("SAPPHIRE_CONTROL_API_TOKEN", ENV_FILES)

if not BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN is not configured")
    sys.exit(1)

def get_bot_updates(offset: int = None) -> list[dict]:
    """Get updates from Telegram bot."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    if offset:
        url += f"?offset={offset}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                return data.get("result", [])
    except Exception as e:
        print(f"Error getting updates: {e}")
    return []

def send_message(chat_id: str, text: str, parse_mode: str | None = "HTML") -> dict:
    """Send message to chat."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        data["parse_mode"] = parse_mode
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error sending message: {e}")
        return {"ok": False, "error": str(e)}

def get_daemon_state() -> dict:
    """Get daemon state from file."""
    if DAEMON_STATE_FILE.exists():
        try:
            return json.loads(DAEMON_STATE_FILE.read_text())
        except Exception:
            pass
    return {"running": False, "paused": False}

def update_daemon_state(updates: dict) -> bool:
    """Update daemon state file."""
    try:
        state = get_daemon_state()
        state.update(updates)
        DAEMON_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        DAEMON_STATE_FILE.write_text(json.dumps(state, indent=2))
        return True
    except Exception as e:
        print(f"Error updating state: {e}")
        return False

def execute_trade(platform: str, symbol: str, side: str, size: float) -> dict:
    """Execute a manual trade by publishing a signal through the canonical gateway."""
    if not CONTROL_API_TOKEN:
        return {"success": False, "error": "SAPPHIRE_CONTROL_API_TOKEN missing on Pi env"}

    target_platforms = (
        ["aster", "lighter"] if platform == "both" else [platform]
    )
    payload = {
        "symbol": str(symbol or "").upper(),
        "side": str(side or "").upper(),
        "signal_type": "entry",
        "confidence": 0.95,
        "target_platforms": target_platforms,
        "quantity": float(size),
    }

    try:
        req = urllib.request.Request(
            GATEWAY_SIGNAL_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Sapphire-Control-Token": CONTROL_API_TOKEN,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode() or "{}")
            body["success"] = True
            body["platforms"] = target_platforms
            return body
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode() or "{}")
        except Exception:
            detail = {"detail": str(e)}
        return {
            "success": False,
            "error": f"Gateway HTTP {e.code}",
            "detail": detail,
            "platforms": target_platforms,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "platforms": target_platforms}


def query_kimi(prompt: str, timeout: int = 90) -> str:
    """Forward non-command text to Kimi CLI."""
    try:
        proc = subprocess.run(
            [KIMI_BIN, "--print", "--quiet"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            return f"Kimi error: {err[:280] or 'unknown failure'}"
        text = (proc.stdout or "").strip()
        return text[:3900] if text else "No response from Kimi."
    except FileNotFoundError:
        return "Kimi CLI not found on node."
    except subprocess.TimeoutExpired:
        return "Kimi request timed out."
    except Exception as exc:
        return f"Kimi query failed: {str(exc)[:280]}"

def handle_command(message: dict) -> str:
    """Handle a Telegram command."""
    text = message.get("text", "").strip()
    chat_id = message["chat"]["id"]
    
    if not text.startswith("/"):
        return None
    
    parts = text.split()
    command = parts[0].lower()
    args = parts[1:]
    
    state = get_daemon_state()
    
    if command == "/start":
        return (
            "🤖 <b>Autonomous Trading Bot</b>\n\n"
            "Welcome! I control your 24/7 trading system and route non-command chat to Kimi.\n\n"
            "<b>Commands:</b>\n"
            "/status - Check system status\n"
            "/pause - Pause trading\n"
            "/resume - Resume trading\n"
            "/trade [PLATFORM] SYMBOL SIDE SIZE - Execute trade\n"
            "   Example: /trade aster SOLUSDT buy 0.05\n"
            "   Example: /trade lighter BTCUSDT sell 0.01\n"
            "/mode - Check trading mode\n"
            "/stats - Show statistics\n"
            "/help - Show this help\n\n"
            "Send plain text to chat with Kimi."
        )
    
    elif command == "/help":
        return (
            "<b>Available Commands:</b>\n\n"
            "📊 <b>/status</b> - Check if daemon is running\n"
            "⏸️ <b>/pause</b> - Pause all trading\n"
            "▶️ <b>/resume</b> - Resume trading\n"
            "💰 <b>/trade</b> - Execute manual trade\n"
            "   Usage: /trade [platform] SYMBOL SIDE SIZE\n"
            "   Platforms: aster | lighter | both (default: aster)\n"
            "   Example: /trade aster SOLUSDT buy 0.05\n"
            "🎮 <b>/mode</b> - Check live/paper mode\n"
            "📈 <b>/stats</b> - Show trade statistics\n"
            "💬 <b>plain text</b> - Ask Kimi directly\n"
            "❓ <b>/help</b> - Show this message"
        )
    
    elif command == "/status":
        running = "✅ Running" if state.get("running") else "❌ Stopped"
        paused = "⏸️ Paused" if state.get("paused") else "▶️ Active"
        mode = state.get("settings", {}).get("trading_mode", "unknown")
        
        return (
            f"📊 <b>System Status</b>\n\n"
            f"Status: {running}\n"
            f"Trading: {paused}\n"
            f"Mode: {mode.upper()}\n"
            f"Trades Today: {state.get('trades_today', 0)}\n"
            f"Total Trades: {state.get('total_trades', 0)}\n"
            f"Started: {state.get('started_at', 'N/A')[:19] if state.get('started_at') else 'N/A'}"
        )
    
    elif command == "/pause":
        if update_daemon_state({"paused": True}):
            return "⏸️ <b>Trading Paused</b>\n\nNo new trades will be executed."
        return "❌ Failed to pause trading"
    
    elif command == "/resume":
        if update_daemon_state({"paused": False}):
            return "▶️ <b>Trading Resumed</b>\n\nTrades will now be executed!"
        return "❌ Failed to resume trading"
    
    elif command == "/mode":
        mode = state.get("settings", {}).get("trading_mode", "unknown")
        emoji = "🚀" if mode == "live" else "📄"
        return f"{emoji} <b>Trading Mode:</b> {mode.upper()}"
    
    elif command == "/stats":
        return (
            f"📈 <b>Trading Statistics</b>\n\n"
            f"Total Trades: {state.get('total_trades', 0)}\n"
            f"Successful: {state.get('successful_trades', 0)}\n"
            f"Failed: {state.get('failed_trades', 0)}\n"
            f"Trades Today: {state.get('trades_today', 0)}\n"
            f"Last Trade: {state.get('last_trade_at', 'N/A')[:19] if state.get('last_trade_at') else 'N/A'}"
        )
    
    elif command == "/trade":
        if len(args) < 3:
            return (
                "❌ <b>Invalid Trade Command</b>\n\n"
                "Usage: /trade [platform] SYMBOL SIDE SIZE\n"
                "Platforms: aster | lighter | both\n"
                "Example: /trade aster SOLUSDT buy 0.05"
            )

        platform = "aster"
        symbol_idx = 0
        if args and args[0].lower() in KNOWN_TRADE_PLATFORMS:
            platform = args[0].lower()
            symbol_idx = 1

        if len(args) - symbol_idx < 3:
            return (
                "❌ <b>Invalid Trade Command</b>\n\n"
                "Usage: /trade [platform] SYMBOL SIDE SIZE\n"
                "Example: /trade lighter BTCUSDT sell 0.01"
            )

        symbol = args[symbol_idx].upper()
        side = args[symbol_idx + 1].lower()
        try:
            size = float(args[symbol_idx + 2])
        except ValueError:
            return "❌ Size must be a number"

        if side not in ["buy", "sell"]:
            return "❌ Side must be 'buy' or 'sell'"
        if size <= 0:
            return "❌ Size must be > 0"

        send_message(
            chat_id,
            f"⏳ Dispatching {side.upper()} {size} {symbol} on {platform.upper()} via gateway...",
            parse_mode=None,
        )

        result = execute_trade(platform, symbol, side, size)

        if result.get("success"):
            signal_id = result.get("signal_id", "n/a")
            message_id = result.get("message_id", "n/a")
            platforms = ", ".join([p.upper() for p in result.get("platforms", [])]) or platform.upper()
            return (
                f"🚀 <b>Manual Trade Signal Published</b>\n\n"
                f"Symbol: {symbol}\n"
                f"Side: {side.upper()}\n"
                f"Size: {size}\n"
                f"Platforms: {platforms}\n"
                f"Signal ID: <code>{signal_id}</code>\n"
                f"Message ID: <code>{message_id}</code>"
            )
        else:
            error = str(result.get("error", "Unknown error"))
            detail = result.get("detail")
            detail_text = ""
            if isinstance(detail, dict) and detail.get("detail"):
                detail_text = f"\nDetail: {str(detail.get('detail'))[:220]}"
            return f"❌ <b>Trade Dispatch Failed</b>\n\nError: {error[:200]}{detail_text}"
    
    else:
        return f"❓ Unknown command: {command}\nUse /help for available commands"

def main():
    """Main bot loop."""
    print("=" * 60)
    print("Telegram Bot Controller Starting")
    print("=" * 60)
    print("Bot: @RariCryptonBot")
    print("Monitoring for commands...")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    offset = None
    
    try:
        while True:
            updates = get_bot_updates(offset)
            
            for update in updates:
                # Update offset
                offset = update["update_id"] + 1
                
                # Process message
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    message_text = message.get("text", "").strip()
                    
                    # Check if it's a command
                    if message_text.startswith("/"):
                        response = handle_command(message)
                        
                        if response:
                            send_message(chat_id, response)
                            print(f"[{datetime.now().isoformat()}] Command from {chat_id}: {message_text}")
                    elif message_text:
                        send_message(chat_id, "🤔 Thinking...", parse_mode=None)
                        response = query_kimi(message_text)
                        send_message(chat_id, response, parse_mode=None)
                        print(f"[{datetime.now().isoformat()}] Kimi chat from {chat_id}: {message_text[:80]}")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping bot controller...")

if __name__ == "__main__":
    main()
