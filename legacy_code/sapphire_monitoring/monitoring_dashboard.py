#!/usr/bin/env python3
"""
Sapphire Trading Cluster - Real-time Monitoring Dashboard
Live view of all system metrics
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime
from typing import Dict


class MonitoringDashboard:
    """Real-time monitoring dashboard"""
    
    def __init__(self):
        self.running = True
        self.metrics = {
            'rari2': {},
            'rari1': {},
            'vpn': {},
            'trades': {}
        }
        
    async def start(self):
        """Start the monitoring dashboard"""
        print("\033[2J\033[H")  # Clear screen
        
        while self.running:
            await self._update_metrics()
            self._render()
            await asyncio.sleep(5)  # Update every 5 seconds
            
    async def _update_metrics(self):
        """Update all metrics"""
        timeout = aiohttp.ClientTimeout(total=5)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Check rari2 (trading engine)
            try:
                async with session.get('http://10.0.0.2:18888/status') as resp:
                    if resp.status == 200:
                        self.metrics['rari2'] = await resp.json()
            except:
                self.metrics['rari2'] = {'error': 'unreachable'}
            
            # Check rari1 (workbench)
            try:
                async with session.get('http://localhost:18891/workbench/stats') as resp:
                    if resp.status == 200:
                        self.metrics['rari1'] = await resp.json()
            except:
                self.metrics['rari1'] = {'error': 'unreachable'}
                
    def _render(self):
        """Render the dashboard"""
        # Clear screen and move to top
        print("\033[2J\033[H")
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Header
        print("=" * 80)
        print(f"  SAPPHIRE TRADING CLUSTER - LIVE DASHBOARD - {now}")
        print("=" * 80)
        print()
        
        # rari2 Status
        print("┌─ RARI2 (Trading Engine) 10.0.0.2 ────────────────────────────────────────────┐")
        rari2 = self.metrics.get('rari2', {})
        if 'error' in rari2:
            print(f"│  Status: ❌ {rari2['error']:<67} │")
        else:
            status = "✅ RUNNING" if rari2.get('running') else "❌ STOPPED"
            vpn = rari2.get('vpn_status', {})
            vpn_status = "✅" if vpn.get('connected') else "❌"
            pair = rari2.get('pair_trading', {})
            
            print(f"│  Status:     {status:<62} │")
            print(f"│  Lighter:    {'✅' if rari2.get('lighter_connected') else '❌'} SDK Connected{' ':45} │")
            print(f"│  VPN:        {vpn_status} {vpn.get('ip', 'Unknown'):<15} ({vpn.get('location', 'Unknown')}){' ':25} │")
            print(f"│  Pairs:      {len(pair.get('supported_pairs', []))} supported ({', '.join(pair.get('supported_pairs', [])[:2])}...)" + " "*25 + "│")
            print(f"│  Tradable:   {', '.join(pair.get('tradable_symbols', []))}" + " "*45 + "│")
        print("└──────────────────────────────────────────────────────────────────────────────┘")
        print()
        
        # rari1 Status
        print("┌─ RARI1 (Controller/Workbench) 10.0.0.1 ──────────────────────────────────────┐")
        rari1 = self.metrics.get('rari1', {})
        if 'error' in rari1:
            print(f"│  Status: ❌ {rari1['error']:<67} │")
        else:
            print(f"│  Proposals:     Total: {rari1.get('total_proposals', 0):<3} | "
                  f"Executed: {rari1.get('executed', 0):<3} | "
                  f"Approved: {rari1.get('approved_pending', 0):<3}          │")
            print(f"│  Pending:       Analysis: {rari1.get('pending_analysis', 0):<3} | "
                  f"Rejected: {rari1.get('rejected', 0):<3}                  │")
            print(f"│  Success Rate:  {rari1.get('success_rate', 0):.0%}" + " "*61 + "│")
        print("└──────────────────────────────────────────────────────────────────────────────┘")
        print()
        
        # Quick Actions
        print("┌─ QUICK ACTIONS ──────────────────────────────────────────────────────────────┐")
        print("│                                                                              │")
        print("│  Press Ctrl+C to exit                                                        │")
        print("│                                                                              │")
        print("│  API Endpoints:                                                              │")
        print("│    Trading:  curl http://10.0.0.2:18888/status                               │")
        print("│    Workbench: curl http://10.0.0.1:18891/workbench/stats                     │")
        print("│    Webhook:   curl http://10.0.0.1:18890/webhook/status                      │")
        print("│                                                                              │")
        print("└──────────────────────────────────────────────────────────────────────────────┘")
        
        print()
        print("Refreshing every 5 seconds... (Press Ctrl+C to exit)")


async def main():
    """Main entry point"""
    dashboard = MonitoringDashboard()
    try:
        await dashboard.start()
    except KeyboardInterrupt:
        print("\n\nDashboard stopped.")


if __name__ == '__main__':
    asyncio.run(main())
