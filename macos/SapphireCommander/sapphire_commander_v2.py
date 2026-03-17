#!/usr/bin/env python3
"""Sapphire Operator Companion (macOS menu bar).

Focused, read-only operator companion aligned to canonical platform contracts.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
import subprocess
import webbrowser
import os

import requests
import rumps

CONFIG = {
    "base_url": "https://sapphirealpha.xyz",
    "operator_paths": {
        "home": "/",
        "organization": "/organization",
        "intelligence": "/intelligence",
        "activity": "/activity",
        "readiness": "/production-readiness",
        "status_json": "/api/platform/status",
        "contracts_json": "/api/platform/contracts",
    },
    "internal_urls": {
        "pm_hub_org": "https://agentic-pm-hub-267358751314.us-central1.run.app/organization",
        "pm_manager": "https://agentic-pm-hub-267358751314.us-central1.run.app/organization",
        "scout_status": "https://sapphire-alpha-267358751314.us-central1.run.app/forum/scout/status",
        "scout_control": "https://sapphire-openclaw-cloud-s77j6bxyra-uc.a.run.app",
        "scout_sandbox_health": "https://sapphire-scout-sandbox-s77j6bxyra-uc.a.run.app/health",
    },
    "refresh_interval": 30,
    "timeout_seconds": 12,
    "rari1_ip": "100.120.191.1",
    "rari2_ip": "100.87.225.89",
    "windows_ip": "100.71.10.48",
    "operator_user": os.getenv("SAPPHIRE_OPERATOR_USER", "").strip(),
    "operator_password": os.getenv("SAPPHIRE_OPERATOR_PASSWORD", "").strip(),
}


def notify(title: str, message: str, sound: bool = False) -> None:
    sound_cmd = 'sound name "Default"' if sound else ""
    script = f'display notification "{message}" with title "{title}" {sound_cmd}'
    try:
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception:
        pass


@dataclass
class Snapshot:
    service_healthy: int = 0
    service_total: int = 0
    readiness_ok: bool = False
    projects_count: int = 0
    workspaces: int = 0
    agents_online: int = 0
    agents_total: int = 0
    signals_count: int = 0
    trades_count: int = 0
    pnl_total: float = 0.0
    btc_price: float = 0.0
    latest_log: str = "No activity yet"
    latest_log_ts: str = ""
    scout_dispatch_mode: str = "unknown"
    scout_registered: bool = False
    scout_fallback_ready: bool = False
    scout_sandbox_ready: bool = False
    scout_items: int = 0
    scout_hint: str = ""
    updated_at: str = "Never"
    error: str = ""

    @property
    def service_ratio(self) -> float:
        if self.service_total <= 0:
            return 0.0
        return self.service_healthy / max(1, self.service_total)


class SapphireOperatorCompanion(rumps.App):
    def __init__(self):
        super().__init__(name="SapphireOperatorCompanion", title="💎", icon=None, quit_button="Quit")

        self.state = Snapshot()
        self.notifications_enabled = True
        self.last_health_notified = None

        self._build_menu()
        self.update_status(None)
        self.timer = rumps.Timer(self.update_status, CONFIG["refresh_interval"])
        self.timer.start()

    def _build_menu(self):
        self.status_item = rumps.MenuItem("Status: loading...")
        self.pm_item = rumps.MenuItem("PM: loading...")
        self.trading_item = rumps.MenuItem("Trading: loading...")
        self.scout_item = rumps.MenuItem("Scout: loading...")
        self.activity_item = rumps.MenuItem("Activity: loading...")
        self.updated_item = rumps.MenuItem("Updated: never")

        open_home = rumps.MenuItem("🌐 Open Platform (Public)", callback=lambda _: self._open_public("home"))
        open_org = rumps.MenuItem("🏢 Open Organization (Public)", callback=lambda _: self._open_public("organization"))
        open_intel = rumps.MenuItem("🧠 Open Intelligence (Public)", callback=lambda _: self._open_public("intelligence"))
        open_activity = rumps.MenuItem("📡 Open Activity (Public)", callback=lambda _: self._open_public("activity"))
        open_readiness = rumps.MenuItem("✅ Open Readiness (Public)", callback=lambda _: self._open_public("readiness"))
        open_scout_control = rumps.MenuItem("🛰️ Open Scout Control (Internal)", callback=lambda _: self._open_internal("scout_control"))
        open_scout_status = rumps.MenuItem("📡 Open Scout Status (Internal)", callback=lambda _: self._open_internal("scout_status"))
        open_scout_sandbox = rumps.MenuItem("🔬 Open Scout Sandbox (Internal)", callback=lambda _: self._open_internal("scout_sandbox_health"))
        open_pm_hub = rumps.MenuItem("📋 Open PM Hub (Internal)", callback=lambda _: self._open_internal("pm_hub_org"))
        open_pm_manager = rumps.MenuItem("🗂️ Open AI PM Manager (Internal)", callback=lambda _: self._open_internal("pm_manager"))

        refresh_now = rumps.MenuItem("🔄 Refresh now", callback=self.update_status)
        self.toggle_notifications_item = rumps.MenuItem("🔔 Notifications: ON", callback=self.toggle_notifications)
        view_status_json = rumps.MenuItem("🧾 Open Status JSON", callback=lambda _: self._open_public("status_json"))
        view_contracts_json = rumps.MenuItem("📜 Open Contracts JSON", callback=lambda _: self._open_public("contracts_json"))

        ssh_rari1 = rumps.MenuItem("SSH RARI1", callback=lambda _: self.ssh_to("rari1"))
        ssh_rari2 = rumps.MenuItem("SSH RARI2", callback=lambda _: self.ssh_to("rari2"))
        ssh_windows = rumps.MenuItem("SSH Windows", callback=lambda _: self.ssh_to("windows"))

        self.menu = [
            self.status_item,
            self.pm_item,
            self.trading_item,
            self.scout_item,
            self.activity_item,
            self.updated_item,
            rumps.separator,
            open_home,
            open_org,
            open_intel,
            open_scout_control,
            open_scout_status,
            open_scout_sandbox,
            open_activity,
            open_readiness,
            open_pm_hub,
            open_pm_manager,
            rumps.separator,
            ("Infra", [ssh_rari1, ssh_rari2, ssh_windows]),
            ("Actions", [refresh_now, self.toggle_notifications_item, view_status_json, view_contracts_json]),
            rumps.separator,
        ]

    def toggle_notifications(self, _):
        self.notifications_enabled = not self.notifications_enabled
        self.toggle_notifications_item.title = f"🔔 Notifications: {'ON' if self.notifications_enabled else 'OFF'}"

    def ssh_to(self, node: str):
        ip = CONFIG.get(f"{node}_ip", "").strip()
        if not ip:
            notify("Sapphire Operator", f"No IP configured for {node}")
            return
        script = f'''
        tell application "Terminal"
            activate
            do script "ssh rari@{ip}"
        end tell
        '''
        subprocess.run(["osascript", "-e", script], check=False)

    def update_status(self, _):
        t = threading.Thread(target=self._fetch_snapshot, daemon=True)
        t.start()

    def _open_public(self, key: str):
        path = str((CONFIG.get("operator_paths") or {}).get(key, "") or "").strip()
        if not path:
            notify("Sapphire Operator", f"Missing public route mapping: {key}")
            return
        base = str(CONFIG.get("base_url", "")).rstrip("/")
        if not base:
            notify("Sapphire Operator", "Missing base_url configuration")
            return
        webbrowser.open(f"{base}{path}")

    def _open_internal(self, key: str):
        url = str((CONFIG.get("internal_urls") or {}).get(key, "") or "").strip()
        if not url:
            notify("Sapphire Operator", f"Missing internal URL mapping: {key}")
            return
        webbrowser.open(url)

    def _fetch_snapshot(self):
        try:
            auth = None
            if CONFIG["operator_user"] and CONFIG["operator_password"]:
                auth = (CONFIG["operator_user"], CONFIG["operator_password"])
            try:
                data = self._get_json("/api/platform/home-snapshot", auth=auth, timeout=CONFIG["timeout_seconds"])
            except requests.exceptions.Timeout:
                # Fallback to smaller endpoints when home-snapshot is slow.
                data = {
                    "status": self._get_json("/api/platform/status", auth=auth, timeout=6),
                    "organization": self._get_json("/api/platform/organization", auth=auth, timeout=6),
                    "projects": self._get_json("/api/platform/projects", auth=auth, timeout=6),
                    "metrics": self._get_json("/api/platform/metrics", auth=auth, timeout=8),
                    "logs": self._get_json("/api/platform/logs?hours=24&limit=5", auth=auth, timeout=8),
                    "readiness": self._get_json("/api/platform/readiness", auth=auth, timeout=6),
                }

            scout_status_url = str((CONFIG.get("internal_urls") or {}).get("scout_status", "") or "").strip()
            scout_status = self._get_direct_json(scout_status_url, timeout=4) if scout_status_url else {}
            scout_bridge = (scout_status or {}).get("external_bridge") or {}
            scout_registration = (scout_status or {}).get("registration") or {}

            scout_intel_count = 0
            try:
                scout_sandbox_url = str((CONFIG.get("internal_urls") or {}).get("scout_sandbox_health", "") or "").strip()
                scout_sandbox = self._get_direct_json(scout_sandbox_url, timeout=4) if scout_sandbox_url else {}
                scout_sandbox_ready = bool((scout_sandbox or {}).get("sandbox_token_configured", False))
            except Exception:
                scout_sandbox_ready = False

            status_summary = (data.get("status") or {}).get("summary") or {}
            org_summary = (data.get("organization") or {}).get("summary") or {}
            trading = (data.get("metrics") or {}).get("trading") or {}
            logs = ((data.get("logs") or {}).get("logs") or [])
            autonomy = (data.get("autonomy") or {})
            if isinstance(autonomy, dict):
                scout_intel_count = int((((autonomy.get("scout") or {}).get("external_bridge") or {}).get("item_count", 0) or 0))

            latest_log = logs[0] if logs else {}
            latest_msg = str(latest_log.get("message") or "No activity yet").strip()
            latest_sym = str(latest_log.get("symbol") or "").strip()
            latest_evt = str(latest_log.get("event_type") or "").strip()
            latest = latest_msg
            if latest_sym:
                latest += f" [{latest_sym}]"
            if latest_evt:
                latest += f" ({latest_evt})"

            pnl_total = 0.0
            pnl = trading.get("pnl")
            if isinstance(pnl, dict):
                pnl_total = float(pnl.get("total", 0.0) or 0.0)

            btc_price = 0.0
            market = (data.get("metrics") or {}).get("market") or {}
            if isinstance(market, dict):
                btc = market.get("BTC") or market.get("btc") or {}
                if isinstance(btc, dict):
                    btc_price = float(btc.get("price", 0.0) or 0.0)

            self.state = Snapshot(
                service_healthy=int(status_summary.get("service_healthy", 0) or 0),
                service_total=int(status_summary.get("service_total", 0) or 0),
                readiness_ok=bool((data.get("readiness") or {}).get("overall_ok", False)),
                projects_count=int((data.get("projects") or {}).get("count", 0) or 0),
                workspaces=int(org_summary.get("workspaces", 0) or 0),
                agents_online=int(org_summary.get("agents_online", 0) or 0),
                agents_total=int(org_summary.get("agents_total", 0) or 0),
                signals_count=int(trading.get("signals_total", 0) or trading.get("active_signals", 0) or 0),
                trades_count=int(trading.get("trades_count", 0) or 0),
                pnl_total=pnl_total,
                btc_price=btc_price,
                latest_log=latest[:88],
                latest_log_ts=str(latest_log.get("timestamp") or ""),
                scout_dispatch_mode=str(scout_bridge.get("dispatch_mode", "unknown") or "unknown"),
                scout_registered=bool(scout_registration.get("registered", False)),
                scout_fallback_ready=bool(scout_bridge.get("fallback_ready", False)),
                scout_sandbox_ready=bool(scout_bridge.get("sandbox_ready", False) and scout_sandbox_ready),
                scout_items=scout_intel_count,
                scout_hint=str(scout_bridge.get("operator_hint", "") or ""),
                updated_at=datetime.now().strftime("%H:%M:%S"),
            )

            self._update_ui()
        except Exception as exc:
            self.state.error = str(exc)
            self.state.updated_at = datetime.now().strftime("%H:%M:%S")
            self._update_ui(error_mode=True)

    def _get_json(self, path: str, auth=None, timeout: int | None = None):
        r = requests.get(
            f"{CONFIG['base_url']}{path}",
            timeout=timeout or CONFIG["timeout_seconds"],
            auth=auth,
            headers={"Accept": "application/json"},
        )
        if r.status_code == 401:
            raise RuntimeError("Unauthorized (set SAPPHIRE_OPERATOR_USER / SAPPHIRE_OPERATOR_PASSWORD)")
        r.raise_for_status()
        return r.json()

    def _get_direct_json(self, url: str, timeout: int | None = None):
        r = requests.get(
            url,
            timeout=timeout or CONFIG["timeout_seconds"],
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()

    def _update_ui(self, error_mode: bool = False):
        st = self.state
        if error_mode:
            self.title = "❌"
            self.status_item.title = "Status: offline"
            self.pm_item.title = "PM: unavailable"
            self.trading_item.title = "Trading: unavailable"
            self.activity_item.title = f"Activity: {st.error[:72]}"
            self.updated_item.title = f"Updated: {st.updated_at}"
            return

        if st.service_total > 0 and st.service_healthy == st.service_total and st.readiness_ok:
            icon = "💎"
            health_label = "GREEN"
        elif st.service_ratio >= 0.7:
            icon = "💠"
            health_label = "WATCH"
        else:
            icon = "⚠️"
            health_label = "DEGRADED"

        self.title = icon
        self.status_item.title = (
            f"Status: {st.service_healthy}/{st.service_total} services | Readiness: {health_label}"
        )
        self.pm_item.title = (
            f"PM: {st.projects_count} projects | {st.workspaces} workspaces | agents {st.agents_online}/{st.agents_total}"
        )
        self.trading_item.title = (
            f"Trading: signals {st.signals_count} | trades {st.trades_count} | PnL ${st.pnl_total:,.2f} | BTC ${st.btc_price:,.0f}"
        )
        scout_external = "registered" if st.scout_registered else "pending"
        scout_lane = []
        if st.scout_sandbox_ready:
            scout_lane.append("sandbox")
        if st.scout_fallback_ready:
            scout_lane.append("hook")
        if not scout_lane:
            scout_lane.append("offline")
        self.scout_item.title = (
            f"Scout: {'+'.join(scout_lane)} | {scout_external} | mode {st.scout_dispatch_mode} | items {st.scout_items}"
        )
        self.activity_item.title = f"Activity: {st.latest_log}"
        self.updated_item.title = f"Updated: {st.updated_at}"

        if self.notifications_enabled:
            # Notify once when transitioning into degraded mode.
            current_health = "degraded" if icon in {"⚠️", "❌"} else "ok"
            if self.last_health_notified != current_health:
                if current_health == "degraded":
                    notify("Sapphire Operator", "Platform health is degraded", sound=True)
                self.last_health_notified = current_health


if __name__ == "__main__":
    app = SapphireOperatorCompanion()
    app.run()
