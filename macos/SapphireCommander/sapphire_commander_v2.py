#!/usr/bin/env python3
"""
Sapphire Commander v2.0 - macOS Menu Bar App with Notifications
Enhanced version with native macOS notifications and alerts
"""

import rumps
import requests
import threading
import time
from datetime import datetime
import json
import os
import subprocess
import webbrowser
# macOS native notifications via osascript
def show_mac_notification(title, message, sound=True):
    """Show native macOS notification using AppleScript"""
    import subprocess
    sound_cmd = 'sound name "Default"' if sound else ''
    script = f'''
    display notification "{message}" with title "{title}" {sound_cmd}
    '''
    try:
        subprocess.run(['osascript', '-e', script], check=False)
        return True
    except Exception as e:
        print(f"Notification error: {e}")
        return False

# Fallback for plyer if available
try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False

# Configuration
CONFIG = {
    'sapphire_url': 'https://sapphirealpha.xyz',
    'gateway_url': 'https://sapphire-gateway-267358751314.us-central1.run.app',
    'pm_hub_url': 'https://agentic-pm-hub-267358751314.us-central1.run.app',
    'rari1_ip': '100.120.191.1',
    'rari2_ip': '100.87.225.89',
    'windows_ip': '100.71.10.48',
    'refresh_interval': 30,  # seconds
    'alert_threshold': 0.7,  # Alert if <70% healthy
}

class SapphireCommander(rumps.App):
    def __init__(self):
        super(SapphireCommander, self).__init__(
            name="SapphireCommander",
            title="💎",
            icon=None,
            quit_button="Quit"
        )
        
        # Status tracking
        self.system_status = {"healthy": 0, "total": 0, "last_healthy_ratio": 1.0}
        self.pm_projects = 0
        self.active_signals = 0
        self.prices = {"BTC": 0, "ETH": 0, "SOL": 0}
        self.last_update = None
        self.alert_sent = False
        
        # Build menu
        self._build_menu()
        
        # Start background updates
        self.update_status(None)
        self.timer = rumps.Timer(self.update_status, CONFIG['refresh_interval'])
        self.timer.start()
        
        # Show startup notification
        self.show_notification(
            "Sapphire Commander",
            "Menu bar app started. Monitoring your infrastructure.",
            sound=False
        )
    
    def show_notification(self, title, message, sound=True):
        """Show native macOS notification"""
        # Try native AppleScript first (most reliable on macOS)
        if show_mac_notification(title, message, sound):
            return
        
        # Fallback to plyer if available
        if HAS_PLYER:
            try:
                notification.notify(
                    title=title,
                    message=message,
                    app_name="Sapphire Commander",
                    timeout=5
                )
                return
            except Exception as e:
                print(f"Plyer notification error: {e}")
        
        # Last resort: print to console
        print(f"[NOTIFICATION] {title}: {message}")
    
    def _build_menu(self):
        """Build the menu bar menu"""
        # Status section
        self.status_item = rumps.MenuItem("⏳ Loading...")
        self.pm_item = rumps.MenuItem("📊 PM: Loading...")
        self.signals_item = rumps.MenuItem("📡 Signals: Loading...")
        self.prices_item = rumps.MenuItem("💰 Prices: Loading...")
        self.last_update_item = rumps.MenuItem("🕐 Updated: Never")
        
        # Quick actions
        open_dashboard = rumps.MenuItem("🌐 Open Dashboard", callback=self.open_dashboard)
        open_pm = rumps.MenuItem("📋 Open PM Hub", callback=self.open_pm_hub)
        
        # SSH submenu
        ssh_rari1 = rumps.MenuItem("🔧 SSH to RARI1", callback=lambda _: self.ssh_to('rari1'))
        ssh_rari2 = rumps.MenuItem("⚡ SSH to RARI2", callback=lambda _: self.ssh_to('rari2'))
        
        # Actions submenu
        refresh = rumps.MenuItem("🔄 Refresh Now", callback=self.update_status)
        check_logs = rumps.MenuItem("📄 Check Logs", callback=self.check_logs)
        test_alert = rumps.MenuItem("🔔 Test Notification", callback=self.test_notification)
        
        # Settings
        self.notifications_item = rumps.MenuItem("🔔 Notifications: ON", callback=self.toggle_notifications)
        self.notifications_enabled = True
        
        # Separator and quit
        separator = rumps.separator
        
        # Build menu
        self.menu = [
            self.status_item,
            self.pm_item,
            self.signals_item,
            self.prices_item,
            self.last_update_item,
            separator,
            open_dashboard,
            open_pm,
            separator,
            ("SSH", [ssh_rari1, ssh_rari2]),
            ("Actions", [refresh, check_logs, test_alert]),
            separator,
            self.notifications_item,
            separator,
        ]
    
    def toggle_notifications(self, _):
        """Toggle notifications on/off"""
        self.notifications_enabled = not self.notifications_enabled
        status = "ON" if self.notifications_enabled else "OFF"
        self.notifications_item.title = f"🔔 Notifications: {status}"
        self.show_notification("Sapphire Commander", f"Notifications {status}", sound=False)
    
    def test_notification(self, _):
        """Test notification system"""
        self.show_notification(
            "Sapphire Commander Test",
            "Notifications are working! 🎉",
            sound=True
        )
    
    def update_status(self, _):
        """Update system status in background"""
        def fetch():
            try:
                # Fetch status from sapphire
                resp = requests.get(f"{CONFIG['sapphire_url']}/api/status", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    by_cat = data.get('by_category', {})
                    
                    # Count healthy services
                    healthy = 0
                    total = 0
                    for cat in by_cat.values():
                        for svc in cat:
                            total += 1
                            if svc.get('healthy'):
                                healthy += 1
                    
                    # Check for health degradation
                    previous_ratio = self.system_status.get('last_healthy_ratio', 1.0)
                    current_ratio = healthy / total if total > 0 else 0
                    
                    # Alert if health drops below threshold
                    if current_ratio < CONFIG['alert_threshold'] and not self.alert_sent:
                        if self.notifications_enabled:
                            self.show_notification(
                                "⚠️ Sapphire Alert",
                                f"Service health degraded: {healthy}/{total} healthy",
                                sound=True
                            )
                        self.alert_sent = True
                    elif current_ratio >= CONFIG['alert_threshold']:
                        self.alert_sent = False  # Reset alert when recovered
                    
                    # Alert if health improved significantly
                    if previous_ratio < CONFIG['alert_threshold'] and current_ratio >= CONFIG['alert_threshold']:
                        if self.notifications_enabled:
                            self.show_notification(
                                "✅ Sapphire Recovered",
                                f"All services healthy: {healthy}/{total}",
                                sound=False
                            )
                    
                    self.system_status = {
                        "healthy": healthy, 
                        "total": total,
                        "last_healthy_ratio": current_ratio
                    }
                    
                    # Update menu bar icon based on health
                    if healthy == total:
                        self.title = "💎"
                    elif current_ratio > CONFIG['alert_threshold']:
                        self.title = "💠"
                    else:
                        self.title = "⚠️"
                else:
                    # API error
                    self.title = "❌"
                    if not self.alert_sent and self.notifications_enabled:
                        self.show_notification(
                            "❌ Sapphire Error",
                            f"Cannot reach sapphirealpha.xyz (HTTP {resp.status_code})",
                            sound=True
                        )
                        self.alert_sent = True
                
                # Fetch PM projects
                resp = requests.get(f"{CONFIG['sapphire_url']}/api/projects", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    new_count = data.get('count', 0)
                    
                    # Notify if project count changed significantly
                    if self.pm_projects > 0 and new_count != self.pm_projects:
                        if self.notifications_enabled:
                            self.show_notification(
                                "📊 Sapphire PM",
                                f"Projects updated: {new_count} total",
                                sound=False
                            )
                    
                    self.pm_projects = new_count
                
                # Fetch trading metrics
                resp = requests.get(f"{CONFIG['sapphire_url']}/api/trading/metrics", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    self.active_signals = data.get('active_signals', 0)
                
                # Fetch prices
                resp = requests.get(f"{CONFIG['sapphire_url']}/api/market/prices", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    old_btc = self.prices.get('BTC', 0)
                    new_btc = data.get('BTC', {}).get('price', 0)
                    
                    # Alert on significant BTC price move (>5%)
                    if old_btc > 0 and abs(new_btc - old_btc) / old_btc > 0.05:
                        change = ((new_btc - old_btc) / old_btc) * 100
                        if self.notifications_enabled:
                            self.show_notification(
                                "💰 BTC Price Alert",
                                f"BTC moved {change:+.1f}% to ${new_btc:,.0f}",
                                sound=False
                            )
                    
                    self.prices = {
                        'BTC': new_btc,
                        'ETH': data.get('ETH', {}).get('price', 0),
                        'SOL': data.get('SOL', {}).get('price', 0),
                    }
                
                self.last_update = datetime.now()
                self._update_menu_items()
                
            except requests.exceptions.Timeout:
                print("Timeout fetching status")
                self.title = "⏱"
            except requests.exceptions.ConnectionError:
                print("Connection error")
                self.title = "❌"
                if not self.alert_sent and self.notifications_enabled:
                    self.show_notification(
                        "❌ Sapphire Offline",
                        "Cannot connect to sapphirealpha.xyz",
                        sound=True
                    )
                    self.alert_sent = True
            except Exception as e:
                print(f"Error updating status: {e}")
                self.title = "❌"
        
        # Run in background thread
        thread = threading.Thread(target=fetch)
        thread.daemon = True
        thread.start()
    
    def _update_menu_items(self):
        """Update menu items with current data"""
        healthy = self.system_status['healthy']
        total = self.system_status['total']
        
        self.status_item.title = f"Status: {healthy}/{total} healthy"
        self.pm_item.title = f"📊 PM: {self.pm_projects} projects"
        self.signals_item.title = f"📡 Signals: {self.active_signals} active"
        self.prices_item.title = f"💰 BTC: ${self.prices['BTC']:,.0f} | ETH: ${self.prices['ETH']:,.0f}"
        
        if self.last_update:
            time_str = self.last_update.strftime('%H:%M:%S')
            self.last_update_item.title = f"🕐 Updated: {time_str}"
    
    def open_dashboard(self, _):
        """Open sapphirealpha.xyz in browser"""
        webbrowser.open(CONFIG['sapphire_url'])
    
    def open_pm_hub(self, _):
        """Open PM Hub in browser"""
        webbrowser.open(CONFIG['pm_hub_url'])
    
    def ssh_to(self, node):
        """Open terminal with SSH to Pi node"""
        ip = CONFIG.get(f'{node}_ip', '')
        if not ip:
            self.show_notification("Sapphire Commander", f"No IP configured for {node}", sound=False)
            return
        
        # Open Terminal.app with SSH
        script = f'''
        tell application "Terminal"
            activate
            do script "ssh rari@{ip}"
        end tell
        '''
        subprocess.run(['osascript', '-e', script])
    
    def check_logs(self, _):
        """Open logs in browser"""
        webbrowser.open(f"{CONFIG['sapphire_url']}/api/logs?limit=50")
    
    @rumps.clicked("About")
    def about(self, _):
        rumps.alert(
            title="Sapphire Commander v2.0",
            message="macOS Menu Bar App for Sapphire Trading Infrastructure\n\n"
                   f"URL: {CONFIG['sapphire_url']}\n"
                   f"Refresh: {CONFIG['refresh_interval']}s\n"
                   f"Alert Threshold: {CONFIG['alert_threshold']*100:.0f}%\n\n"
                   "Features:\n"
                   "• Real-time health monitoring\n"
                   "• Native macOS notifications\n"
                   "• Price alerts\n"
                   "• One-click SSH\n\n"
                   "© 2026 Sapphire Inc."
        )

if __name__ == "__main__":
    # Check dependencies
    try:
        import rumps
        import requests
        import plyer
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Installing requirements...")
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        import rumps
        import requests
        import plyer
    
    app = SapphireCommander()
    app.run()
