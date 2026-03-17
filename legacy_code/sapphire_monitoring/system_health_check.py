#!/usr/bin/env python3
"""
Sapphire Trading Cluster - Health Check & Diagnostics
Comprehensive system verification
"""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime
from typing import Dict, List, Tuple

# System configuration
RARI1_IP = "192.168.1.23"
RARI2_IP = "192.168.1.173"
PRIVATE_IP_1 = "10.0.0.1"
PRIVATE_IP_2 = "10.0.0.2"

# Endpoints
ENDPOINTS = {
    "rari1_controller": f"http://{RARI1_IP}:18891/workbench/stats",
    "rari1_webhook": f"http://{RARI1_IP}:18890/webhook/status",
    "rari2_trading": f"http://{RARI2_IP}:18888/status",
    "rari2_private": f"http://{PRIVATE_IP_2}:18888/status",
}


class HealthChecker:
    """System health checker"""
    
    def __init__(self):
        self.results = {}
        
    async def check_all(self):
        """Run all health checks"""
        print("=" * 70)
        print(" SAPPHIRE TRADING CLUSTER - HEALTH CHECK")
        print("=" * 70)
        print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Check network connectivity
        await self._check_network()
        
        # Check services
        await self._check_services()
        
        # Check VPN
        await self._check_vpn()
        
        # Check workbench
        await self._check_workbench()
        
        # Print summary
        self._print_summary()
        
    async def _check_network(self):
        """Check network connectivity between Pis"""
        print("🔌 NETWORK CONNECTIVITY")
        print("-" * 70)
        
        import subprocess
        
        checks = [
            ("rari1 WiFi", RARI1_IP),
            ("rari2 WiFi", RARI2_IP),
            ("rari1 Private", PRIVATE_IP_1),
            ("rari2 Private", PRIVATE_IP_2),
        ]
        
        for name, ip in checks:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", ip],
                capture_output=True
            )
            status = "✅ UP" if result.returncode == 0 else "❌ DOWN"
            print(f"  {name:20} {ip:15} {status}")
        
        print()
        
    async def _check_services(self):
        """Check all services"""
        print("🔧 SERVICE STATUS")
        print("-" * 70)
        
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for name, url in ENDPOINTS.items():
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self.results[name] = {"status": "ok", "data": data}
                            print(f"  {name:25} ✅ RUNNING")
                        else:
                            self.results[name] = {"status": "error", "code": resp.status}
                            print(f"  {name:25} ❌ HTTP {resp.status}")
                except Exception as e:
                    self.results[name] = {"status": "error", "error": str(e)}
                    print(f"  {name:25} ❌ {str(e)[:40]}")
        
        print()
        
    async def _check_vpn(self):
        """Check VPN status"""
        print("🔒 VPN STATUS")
        print("-" * 70)
        
        if "rari2_trading" in self.results:
            data = self.results["rari2_trading"].get("data", {})
            vpn = data.get("vpn_status", {})
            
            if vpn.get("connected"):
                print(f"  Status:     ✅ CONNECTED")
                print(f"  IP:         {vpn.get('ip', 'Unknown')}")
                print(f"  Location:   {vpn.get('location', 'Unknown')}")
            else:
                print(f"  Status:     ❌ DISCONNECTED")
                print(f"  Warning:    Trading may be blocked!")
        else:
            print("  Status:     ❌ Cannot check (service unavailable)")
        
        print()
        
    async def _check_workbench(self):
        """Check workbench status"""
        print("📊 WORKBENCH STATUS")
        print("-" * 70)
        
        if "rari1_controller" in self.results:
            data = self.results["rari1_controller"].get("data", {})
            
            print(f"  Total Proposals:     {data.get('total_proposals', 0)}")
            print(f"  Executed:            {data.get('executed', 0)}")
            print(f"  Approved (Pending):  {data.get('approved_pending', 0)}")
            print(f"  Pending Analysis:    {data.get('pending_analysis', 0)}")
            print(f"  Rejected:            {data.get('rejected', 0)}")
            print(f"  Success Rate:        {data.get('success_rate', 0):.0%}")
        else:
            print("  Status:              ❌ Cannot check (service unavailable)")
        
        print()
        
    def _print_summary(self):
        """Print health summary"""
        print("=" * 70)
        print(" SUMMARY")
        print("=" * 70)
        
        # Count healthy services
        healthy = sum(1 for r in self.results.values() if r.get("status") == "ok")
        total = len(ENDPOINTS)
        
        print(f"\n  Services Healthy: {healthy}/{total}")
        
        if healthy == total:
            print("\n  ✅ ALL SYSTEMS OPERATIONAL")
            return 0
        elif healthy >= total * 0.75:
            print("\n  ⚠️  MOSTLY OPERATIONAL (some issues)")
            return 1
        else:
            print("\n  ❌ SYSTEM DEGRADED (multiple issues)")
            return 2


async def test_pair_conversion():
    """Test pair trading conversion"""
    print("=" * 70)
    print(" PAIR TRADING CONVERSION TEST")
    print("=" * 70)
    print()
    
    test_cases = [
        {
            "name": "ETHBTC BUY (Z=-2.5)",
            "payload": {
                "symbol": "ETHBTC",
                "side": "buy",
                "amount_usd": 5.0,
                "z_score": -2.5,
                "confidence": 0.85,
                "dry_run": True
            },
            "expected_symbol": "ETH",
            "expected_side": "buy"
        },
        {
            "name": "ETHBTC SELL (Z=+2.5)",
            "payload": {
                "symbol": "ETHBTC",
                "side": "sell",
                "amount_usd": 5.0,
                "z_score": 2.5,
                "confidence": 0.85,
                "dry_run": True
            },
            "expected_symbol": "ETH",
            "expected_side": "sell"
        },
        {
            "name": "Direct ETH trade",
            "payload": {
                "symbol": "ETH",
                "side": "buy",
                "amount_usd": 5.0,
                "dry_run": True
            },
            "expected_symbol": "ETH",
            "expected_side": "buy"
        }
    ]
    
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for test in test_cases:
            print(f"  Testing: {test['name']}")
            
            try:
                async with session.post(
                    f"http://{RARI2_IP}:18888/trade",
                    json=test['payload']
                ) as resp:
                    data = await resp.json()
                    
                    # Check for trading hours error (expected outside 9-4 ET)
                    if data.get('success') == False and 'trading hours' in data.get('error', '').lower():
                        # Check if conversion happened
                        if data.get('resolved_symbol') == test['expected_symbol']:
                            print(f"    ✅ Conversion: {test['payload']['symbol']} → {data['resolved_symbol']}")
                            print(f"    ⏸️  Trading hours restriction (expected)")
                        else:
                            print(f"    ❌ Conversion failed")
                    elif data.get('success'):
                        print(f"    ✅ Success: {data.get('side')} {data.get('symbol')}")
                        if 'pair_conversion' in data:
                            conv = data['pair_conversion']
                            print(f"    🔄 Converted: {conv['original']} → {conv['tradable_symbol']}")
                    else:
                        print(f"    ❌ Error: {data.get('error', 'Unknown')}")
                        
            except Exception as e:
                print(f"    ❌ Exception: {str(e)[:50]}")
            
            print()


if __name__ == '__main__':
    checker = HealthChecker()
    
    # Run health check
    exit_code = asyncio.run(checker.check_all())
    
    # Run pair conversion test
    asyncio.run(test_pair_conversion())
    
    print("=" * 70)
    print(" Health check complete!")
    print("=" * 70)
    
    sys.exit(exit_code)
