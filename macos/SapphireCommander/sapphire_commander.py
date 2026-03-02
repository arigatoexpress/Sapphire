#!/usr/bin/env python3
"""
Sapphire Commander - macOS Menu Bar App
Quick access to trading infrastructure and PM system
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

# Configuration
CONFIG = {
    'sapphire_url': 'https://sapphirealpha.xyz',
    'gateway_url': 'https://sapphire-gateway-267358751314.us-central1.run.app',
    'pm_hub_url': 'https://agentic-pm-hub-267358751314.us-central1.run.app',
    'rari1_ip': '100.120.191.1',
    'rari2_ip': '100.87.225.89',
    'windows_ip': '100.71.10.48',
    'refresh_interval': 30,  # seconds
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
        self.system_status = {"healthy": 0, "total": 0}
        self.pm_projects = 0
        self.active_signals = 0
        self.prices = {"BTC": 0, "ETH": 0, "SOL": 0}
        self.last_update = None
        
        # Build menu
        self._build_menu()
        
        # Start background updates
        self.update_status(None)
        self.timer = rumps.Timer(self.update_status, CONFIG['refresh_interval'])
        self.timer.start()
    
    def _build_menu(self):
        """Build the menu bar menu"""
        # Status section
        self.status_item = rumps.MenuItem("⏳ Loading...")
        self.pm_item = rumps.MenuItem("📊 PM: Loading...")
        self.signals_item = rumps.MenuItem("📡 Signals: Loading...")
        self.prices_item = rumps.MenuItem("💰 Prices: Loading...")
        
        # Quick actions
        open_dashboard = rumps.MenuItem("🌐 Open Dashboard", callback=self.open_dashboard)
        open_pm = rumps.MenuItem("📋 Open PM Hub", callback=self.open_pm_hub)
        
        # SSH submenu
        ssh_rari1 = rumps.MenuItem("🔧 SSH to RARI1", callback=lambda _: self.ssh_to('rari1'))
        ssh_rari2 = rumps.MenuItem("⚡ SSH to RARI2", callback=lambda _: self.ssh_to('rari2'))
        
        # Actions submenu
        refresh = rumps.MenuItem("🔄 Refresh Status", callback=self.update_status)
        check_logs = rumps.MenuItem("📄 Check Logs", callback=self.check_logs)
        
        # Separator and quit
        separator = rumps.separator
        
        # Build menu
        self.menu = [
            self.status_item,
            self.pm_item,
            self.signals_item,
            self.prices_item,
            separator,
            open_dashboard,
            open_pm,
            separator,
            ("SSH", [ssh_rari1, ssh_rari2]),
            ("Actions", [refresh, check_logs]),
            separator,
        ]
    
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
                    
                    self.system_status = {"healthy": healthy, "total": total}
                    
                    # Update menu bar icon based on health
                    if healthy == total:
                        self.title = "💎"
                    elif healthy / total > 0.7:
                        self.title = "💠"
                    else:
                        self.title = "⚠️"
                
                # Fetch PM projects
                resp = requests.get(f"{CONFIG['sapphire_url']}/api/projects", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    self.pm_projects = data.get('count', 0)
                
                # Fetch trading metrics
                resp = requests.get(f"{CONFIG['sapphire_url']}/api/trading/metrics", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    self.active_signals = data.get('active_signals', 0)
                
                # Fetch prices
                resp = requests.get(f"{CONFIG['sapphire_url']}/api/market/prices", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    self.prices = {
                        'BTC': data.get('BTC', {}).get('price', 0),
                        'ETH': data.get('ETH', {}).get('price', 0),
                        'SOL': data.get('SOL', {}).get('price', 0),
                    }
                
                self.last_update = datetime.now()
                self._update_menu_items()
                
            except Exception as e:
                print(f"Error updating status: {e}")
                self.title = "❌"
                self.status_item.title = "❌ Offline"
        
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
            rumps.notification("Sapphire Commander", "Error", f"No IP configured for {node}")
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
            title="Sapphire Commander",
            message="macOS Menu Bar App for Sapphire Trading Infrastructure\n\n"
                   f"URL: {CONFIG['sapphire_url']}\n"
                   f"Refresh: {CONFIG['refresh_interval']}s\n\n"
                   "© 2026 Sapphire Inc."
        )

if __name__ == "__main__":
    # Check if rumps is installed
    try:
        import rumps
    except ImportError:
        print("Installing required packages...")
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        import rumps
    
    app = SapphireCommander()
    app.run()
