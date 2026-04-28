#!/usr/bin/env python3
"""
Sapphire System Monitor with Alerts

Continuously monitors all infrastructure components and sends alerts
when services go down.
"""

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime

import aiohttp


@dataclass
class ServiceCheck:
    name: str
    url: str
    status: str
    latency_ms: float
    timestamp: str
    alert_sent: bool = False


class ServiceMonitor:
    """Monitor services with alerting"""
    
    SERVICES = {
        "windows_webhook": {
            "name": "Windows Webhook",
            "url": "http://100.71.10.48:9090/status",
            "critical": True
        },
        "windows_tv_agent": {
            "name": "TV Agent",
            "url": "http://100.71.10.48:8081/health",
            "critical": True
        },
        "rari1_research": {
            "name": "RARI1 Research Node",
            "url": "http://100.120.191.1:8000/output/latest_hourly.json",
            "critical": False
        },
        "rari2_trading": {
            "name": "RARI2 Trading",
            "url": "http://100.87.225.89:18888/status",
            "critical": True
        },
        "sapphire_frontend": {
            "name": "Sapphire Frontend",
            "url": "https://sapphirealpha.xyz/health",
            "critical": False
        },
        "gateway": {
            "name": "API Gateway",
            "url": "https://gateway.sapphirealpha.xyz/health",
            "critical": False
        },
        "pm_hub": {
            "name": "PM Hub",
            "url": "https://agentic-pm-hub-267358751314.us-central1.run.app/health",
            "critical": False
        }
    }
    
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self.statuses: dict[str, ServiceCheck] = {}
        self.alert_history: list[dict] = []
        self.consecutive_failures: dict[str, int] = {}
        self.session: aiohttp.ClientSession | None = None
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def check_service(self, key: str, config: dict) -> ServiceCheck:
        """Check a single service"""
        name = config["name"]
        url = config["url"]
        
        start = time.time()
        try:
            async with self.session.get(url) as resp:
                latency = (time.time() - start) * 1000
                
                if resp.status in (200, 401, 403):
                    status = "online"
                    self.consecutive_failures[key] = 0
                else:
                    status = "degraded"
                    self.consecutive_failures[key] = self.consecutive_failures.get(key, 0) + 1
                    
        except TimeoutError:
            status = "timeout"
            latency = 9999
            self.consecutive_failures[key] = self.consecutive_failures.get(key, 0) + 1
        except Exception:
            status = "offline"
            latency = 9999
            self.consecutive_failures[key] = self.consecutive_failures.get(key, 0) + 1
        
        check = ServiceCheck(
            name=name,
            url=url,
            status=status,
            latency_ms=round(latency, 2),
            timestamp=datetime.now().isoformat()
        )
        
        # Alert if service just went down (3 consecutive failures)
        if status in ["offline", "timeout"] and self.consecutive_failures.get(key, 0) == 3:
            await self.send_alert(key, name, status)
            check.alert_sent = True
        
        return check
    
    async def send_alert(self, key: str, name: str, status: str):
        """Send alert notification"""
        alert = {
            "timestamp": datetime.now().isoformat(),
            "severity": "critical" if self.SERVICES[key].get("critical") else "warning",
            "service": name,
            "status": status,
            "message": f"🚨 {name} is {status}"
        }
        
        self.alert_history.append(alert)
        
        # Print to console (could be extended to send to Telegram, etc.)
        print(f"\n{'='*60}")
        print(f"ALERT: {alert['message']}")
        print(f"Time: {alert['timestamp']}")
        print(f"{'='*60}\n")
        
    async def check_all(self):
        """Check all services"""
        tasks = [
            self.check_service(key, config)
            for key, config in self.SERVICES.items()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for key, result in zip(self.SERVICES.keys(), results):
            if isinstance(result, Exception):
                config = self.SERVICES[key]
                self.statuses[key] = ServiceCheck(
                    name=config["name"],
                    url=config["url"],
                    status="error",
                    latency_ms=9999,
                    timestamp=datetime.now().isoformat()
                )
            else:
                self.statuses[key] = result
    
    def print_dashboard(self):
        """Print status dashboard"""
        print("\033[2J\033[H")  # Clear screen
        print("="*70)
        print(f"  SAPPHIRE SYSTEM MONITOR - {datetime.now().strftime('%H:%M:%S')}")
        print("="*70)
        print()
        
        online = sum(1 for s in self.statuses.values() if s.status == "online")
        total = len(self.statuses)
        
        print(f"  Services: {online}/{total} online | Check interval: {self.check_interval}s")
        print()
        
        # Group by category
        categories = [
            ("🖥️  Windows PC", ["windows_webhook", "windows_tv_agent"]),
            ("🥧 Pi Cluster", ["rari1_research", "rari2_trading"]),
            ("☁️  Cloud", ["sapphire_frontend", "gateway", "pm_hub"])
        ]
        
        for cat_name, keys in categories:
            print(f"  {cat_name}")
            for key in keys:
                if key in self.statuses:
                    s = self.statuses[key]
                    icon = "🟢" if s.status == "online" else "🔴" if s.status == "offline" else "🟡"
                    print(f"     {icon} {s.name:<25} {s.status:<12} {s.latency_ms:>6.1f}ms")
            print()
        
        # Recent alerts
        if self.alert_history:
            print("  Recent Alerts:")
            for alert in self.alert_history[-3:]:
                print(f"     ⚠️  {alert['timestamp'][11:19]} - {alert['message']}")
            print()
        
        print("="*70)
        print("  Press Ctrl+C to exit")
        print("="*70)
    
    def save_status(self, filename: str = "status.json"):
        """Save status to file"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "services": {
                k: asdict(s) for k, s in self.statuses.items()
            }
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    async def run(self):
        """Main monitoring loop"""
        print(f"Starting monitor (interval: {self.check_interval}s)...")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                await self.check_all()
                self.print_dashboard()
                self.save_status()
                await asyncio.sleep(self.check_interval)
        except KeyboardInterrupt:
            print("\n\nMonitor stopped.")


async def main():
    parser = argparse.ArgumentParser(description="Monitor Sapphire infrastructure")
    parser.add_argument("--interval", "-i", type=int, default=60, 
                       help="Check interval in seconds (default: 60)")
    args = parser.parse_args()
    
    async with ServiceMonitor(check_interval=args.interval) as monitor:
        await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
