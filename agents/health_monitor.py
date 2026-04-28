#!/usr/bin/env python3
"""
Sapphire Health Monitor Agent — runs on rari2 (100.87.225.89).

Monitors all Sapphire services and hardware vitals:
  - Pings all Mac services (inference proxy, dashboard, signal logger, etc.)
  - Checks Ollama health on all nodes (GPU, rari1, Mac)
  - Monitors rari disk space, RAM, CPU temp
  - Sends Telegram alerts when services go down or Pis overheat
  - Maintains uptime JSONL at /home/rari/sapphire/uptime.jsonl

Runs as systemd service: health-monitor.service
Health endpoint: http://rari2_ip:19002/health

Usage:
    python3 health_monitor.py [--once]
"""

from __future__ import annotations

import json
import logging
import os
import platform
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [health-monitor] %(message)s",
)
log = logging.getLogger("health-monitor")

# ─── Endpoints to Monitor ─────────────────────────────────────────────────────

MAC_IP = "100.67.171.79"
GPU_IP = "100.71.10.48"
RARI1_IP = "100.120.191.1"
RARI2_IP = "100.87.225.89"  # self

UPTIME_LOG = Path("/home/rari/sapphire/uptime.jsonl")
HEALTH_PORT = 19002
CHECK_INTERVAL = 60  # seconds between full checks
ALERT_COOLDOWN = 300  # 5 min between same-service alerts

SERVICES = [
    # (name, url, timeout)
    ("inference-proxy", f"http://{MAC_IP}:11435/health", 5),
    ("signal-logger", f"http://{MAC_IP}:18081/health", 5),
    ("dashboard", f"http://{MAC_IP}:8080/health", 5),
    ("control-plane", f"http://{MAC_IP}:8082/health", 5),
    ("regional-intel", f"http://{MAC_IP}:8787/health", 5),
    ("openbb-api", f"http://{MAC_IP}:6900/api/v1/system/status", 5),
    ("ollama-gpu", f"http://{GPU_IP}:11434/api/tags", 8),
    ("ollama-rari1", f"http://{RARI1_IP}:11434/api/tags", 8),
    ("ollama-mac", f"http://{MAC_IP}:11434/api/tags", 5),
    ("market-watchdog", f"http://{RARI1_IP}:19001/health", 5),
]

# Temperature thresholds (Celsius)
TEMP_WARNING = 65.0
TEMP_CRITICAL = 75.0

# Disk space threshold
DISK_WARNING_PCT = 85.0


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────


def _get(url: str, timeout: int = 5) -> tuple[bool, dict | None]:
    """Returns (healthy, response_data)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sapphire-healthmon/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            return True, data
    except urllib.error.HTTPError as e:
        return e.code < 500, None
    except Exception:
        return False, None


def _post(url: str, data: dict, timeout: int = 8) -> bool:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False


# ─── System Vitals (rari2 self-monitoring) ────────────────────────────────────


def get_cpu_temp() -> float | None:
    """Read CPU temperature from thermal zone (Linux)."""
    try:
        # ARM Linux thermal zone
        thermal = Path("/sys/class/thermal/thermal_zone0/temp")
        if thermal.exists():
            return float(thermal.read_text().strip()) / 1000.0
        # Fallback: vcgencmd (Raspberry Pi)
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            # "temp=47.8'C"
            temp_str = result.stdout.strip().replace("temp=", "").replace("'C", "")
            return float(temp_str)
    except Exception:
        pass
    return None


def get_memory_usage() -> dict:
    """Return memory usage stats (MB)."""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        info = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
        total = info.get("MemTotal", 0) // 1024
        free = info.get("MemFree", 0) // 1024
        avail = info.get("MemAvailable", 0) // 1024
        used = total - avail
        return {
            "total_mb": total,
            "used_mb": used,
            "free_mb": free,
            "used_pct": round(used / total * 100, 1) if total else 0,
        }
    except Exception:
        return {}


def get_disk_usage(path: str = "/") -> dict:
    """Return disk usage for a path."""
    try:
        result = subprocess.run(
            ["df", "-h", path],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                return {
                    "path": path,
                    "total": parts[1],
                    "used": parts[2],
                    "free": parts[3],
                    "used_pct": float(parts[4].rstrip("%")),
                }
    except Exception:
        pass
    return {}


def get_uptime_seconds() -> float:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:
        return 0.0


# ─── Telegram Alert ───────────────────────────────────────────────────────────


def send_telegram(msg: str) -> bool:
    """Send a Telegram alert via the bot API. Requires TELEGRAM_BOT_TOKEN +
    TELEGRAM_CHAT_ID. Returns False (logging a warning) when credentials
    are missing — the inference proxy is NOT a Telegram relay, so there
    is no LLM-path fallback.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not (bot_token and chat_id):
        log.warning(
            "send_telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset — alert dropped: %s",
            msg[:120],
        )
        return False
    data = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
    return _post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data)


# ─── Health Monitor ───────────────────────────────────────────────────────────


@dataclass
class ServiceStatus:
    name: str
    healthy: bool
    latency_ms: int
    error: str = ""
    checked_at: str = ""


class HealthMonitor:
    def __init__(self) -> None:
        self._running = False
        self._start_ts = time.time()
        self._last_status: dict[str, bool] = {}
        self._last_alerted: dict[str, float] = {}
        self._check_count = 0

        UPTIME_LOG.parent.mkdir(parents=True, exist_ok=True)
        log.info("HealthMonitor initialized | check_interval=%ds", CHECK_INTERVAL)

    def _should_alert(self, key: str) -> bool:
        last = self._last_alerted.get(key, 0)
        return (time.time() - last) >= ALERT_COOLDOWN

    def _alert(self, key: str, msg: str, icon: str = "⚠️") -> None:
        if not self._should_alert(key):
            return
        full = f"{icon} *Health Monitor* (rari2)\n\n{msg}\n\n_{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}_"
        log.warning("ALERT [%s]: %s", key, msg)
        send_telegram(full)
        self._last_alerted[key] = time.time()

    def check_services(self) -> list[ServiceStatus]:
        results = []
        for name, url, timeout in SERVICES:
            t0 = time.time()
            healthy, _ = _get(url, timeout)
            latency_ms = int((time.time() - t0) * 1000)
            status = ServiceStatus(
                name=name,
                healthy=healthy,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC).isoformat(),
            )
            results.append(status)

            # Detect state transitions
            was_healthy = self._last_status.get(name, True)
            if was_healthy and not healthy:
                self._alert(
                    f"down_{name}",
                    f"Service *{name}* is DOWN\nURL: `{url}`",
                    "🔴",
                )
            elif not was_healthy and healthy:
                self._alert(
                    f"recovered_{name}",
                    f"Service *{name}* recovered ✅\nLatency: {latency_ms}ms",
                    "🟢",
                )
            self._last_status[name] = healthy

        return results

    def check_hardware(self) -> dict:
        vitals: dict[str, Any] = {}

        # CPU temp
        temp = get_cpu_temp()
        if temp is not None:
            vitals["cpu_temp_c"] = round(temp, 1)
            if temp >= TEMP_CRITICAL:
                self._alert(
                    "temp_critical",
                    f"rari2 CPU temperature CRITICAL: {temp:.1f}°C ≥ {TEMP_CRITICAL}°C",
                    "🔥",
                )
            elif temp >= TEMP_WARNING:
                self._alert(
                    "temp_warning",
                    f"rari2 CPU temperature high: {temp:.1f}°C ≥ {TEMP_WARNING}°C",
                    "⚠️",
                )

        # Memory
        mem = get_memory_usage()
        if mem:
            vitals["memory"] = mem
            if mem.get("used_pct", 0) > 90:
                self._alert(
                    "mem_high",
                    f"rari2 memory usage high: {mem['used_pct']:.1f}%\n"
                    f"Used: {mem['used_mb']}MB / {mem['total_mb']}MB",
                    "⚠️",
                )

        # Disk
        disk = get_disk_usage("/")
        if disk:
            vitals["disk"] = disk
            used_pct = disk.get("used_pct", 0)
            if used_pct >= DISK_WARNING_PCT:
                self._alert(
                    "disk_low",
                    f"rari2 disk usage: {used_pct:.1f}%\n"
                    f"Used: {disk['used']} / {disk['total']} (free: {disk['free']})",
                    "💾",
                )

        vitals["uptime_seconds"] = int(get_uptime_seconds())
        vitals["platform"] = platform.machine()

        return vitals

    def write_uptime(self, statuses: list[ServiceStatus], vitals: dict) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "check_count": self._check_count,
            "services": {
                s.name: {"healthy": s.healthy, "latency_ms": s.latency_ms} for s in statuses
            },
            "vitals": vitals,
            "healthy_count": sum(1 for s in statuses if s.healthy),
            "total_count": len(statuses),
        }
        try:
            with open(UPTIME_LOG, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            log.warning("Uptime log write failed: %s", e)

    def run_once(self) -> dict:
        """Single check cycle."""
        statuses = self.check_services()
        vitals = self.check_hardware()
        self.write_uptime(statuses, vitals)
        self._check_count += 1
        healthy = sum(1 for s in statuses if s.healthy)
        log.info(
            "Check complete: %d/%d services healthy | temp=%s",
            healthy,
            len(statuses),
            vitals.get("cpu_temp_c", "?"),
        )
        return {"statuses": [asdict(s) for s in statuses], "vitals": vitals}

    def run(self) -> None:
        self._running = True
        log.info(
            "Health Monitor starting | interval=%ds | health_port=%d", CHECK_INTERVAL, HEALTH_PORT
        )

        # Start health HTTP server
        threading.Thread(target=self._health_server, daemon=True).start()

        # Initial alert
        self._alert(
            "monitor_start",
            f"Health Monitor started on rari2\nMonitoring {len(SERVICES)} services + hardware vitals",
            "🟢",
        )

        while self._running:
            try:
                self.run_once()
            except Exception as e:
                log.error("Check cycle error: %s", e, exc_info=True)
            time.sleep(CHECK_INTERVAL)

    def stop(self) -> None:
        self._running = False
        log.info("Health Monitor stopped")

    def get_latest(self) -> dict:
        """Return latest snapshot from uptime log."""
        try:
            lines = UPTIME_LOG.read_text().strip().splitlines()
            if lines:
                return json.loads(lines[-1])
        except Exception:
            pass
        return {}

    # ── Health HTTP Server ─────────────────────────────────────────────────

    def _health_server(self) -> None:
        monitor = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in {"/health", "/"}:
                    latest = monitor.get_latest()
                    body = json.dumps(
                        {
                            "status": "ok",
                            "agent": "health-monitor",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "uptime_seconds": int(time.time() - monitor._start_ts),
                            "check_count": monitor._check_count,
                            "last_check": latest,
                            "vitals": latest.get("vitals", {}),
                        }
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, fmt, *args):
                pass

        server = HTTPServer(("0.0.0.0", HEALTH_PORT), Handler)
        server.timeout = 1
        log.info("Health endpoint listening on :%d", HEALTH_PORT)
        while monitor._running:
            server.handle_request()


# ─── Entry Point ─────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Sapphire Health Monitor")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    args = parser.parse_args()

    # File logging
    log_dir = Path("/home/rari/sapphire/logs")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "health-monitor.log")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(fh)
    except Exception:
        pass

    monitor = HealthMonitor()

    def _shutdown(signum, frame):
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    if args.once:
        result = monitor.run_once()
        healthy = sum(1 for s in result["statuses"] if s["healthy"])
        print(f"\nHealth Check: {healthy}/{len(result['statuses'])} services healthy")
        for s in result["statuses"]:
            icon = "✅" if s["healthy"] else "❌"
            print(f"  {icon} {s['name']}: {s['latency_ms']}ms")
        vitals = result["vitals"]
        if vitals.get("cpu_temp_c"):
            print(
                f"\nHardware: temp={vitals['cpu_temp_c']}°C | "
                f"mem={vitals.get('memory', {}).get('used_pct', '?')}%"
            )
    else:
        monitor.run()


if __name__ == "__main__":
    main()
