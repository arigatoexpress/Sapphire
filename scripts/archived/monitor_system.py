#!/usr/bin/env python3
"""
Sapphire System Monitor

Monitors all components of the trading infrastructure:
- Windows PC: TV Agent (100.71.10.48:8081), Webhook (100.71.10.48:9090)
- Pi Cluster: rari1 (100.120.191.1), rari2 (100.87.225.89)
- Cloud: Command Deck, Gateway, etc.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime

import aiohttp


@dataclass
class ServiceStatus:
    name: str
    url: str
    status: str  # online, offline, unknown
    latency_ms: float
    last_check: str
    details: dict | None = None


class SystemMonitor:
    """Monitor all Sapphire infrastructure components"""
    
    SERVICES = {
        # Windows PC (AI Workbench)
        "tv_agent": {
            "name": "TV Agent",
            "host": "100.71.10.48",
            "port": 8081,
            "endpoint": "/health"
        },
        "webhook_receiver": {
            "name": "Webhook Receiver",
            "host": "100.71.10.48",
            "port": 9090,
            "endpoint": "/health"
        },
        
        # Pi Cluster
        "rari1_research": {
            "name": "RARI1 Research Node",
            "host": "100.120.191.1",
            "port": 8000,
            "endpoint": "/output/latest_hourly.json"
        },
        "rari2_trading": {
            "name": "RARI2 Trading",
            "host": "100.87.225.89",
            "port": 18888,
            "endpoint": "/status"
        },
        
        # Cloud
        "command_deck": {
            "name": "Command Deck",
            "host": "sapphirealpha.xyz",
            "port": 443,
            "endpoint": "/health",
            "https": True
        },
        "gateway": {
            "name": "API Gateway",
            "host": "gateway.sapphirealpha.xyz",
            "port": 443,
            "endpoint": "/health",
            "https": True
        },
        "log_viewer": {
            "name": "Log Viewer",
            "host": "sapphire-log-viewer-267358751314.us-central1.run.app",
            "port": 443,
            "endpoint": "/",
            "https": True
        },
    }
    
    def __init__(self):
        self.statuses: dict[str, ServiceStatus] = {}
        self.session: aiohttp.ClientSession | None = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def check_service(self, key: str, config: dict) -> ServiceStatus:
        """Check a single service"""
        name = config["name"]
        host = config["host"]
        port = config["port"]
        endpoint = config.get("endpoint", "/")
        https = config.get("https", False)
        
        url = f"{'https' if https else 'http'}://{host}:{port}{endpoint or ''}"
        
        start_time = datetime.now()
        try:
            if endpoint:
                async with self.session.get(url) as resp:
                    latency = (datetime.now() - start_time).total_seconds() * 1000
                    
                    if resp.status == 200:
                        try:
                            details = await resp.json()
                        except:
                            details = {"status": "ok"}
                        
                        return ServiceStatus(
                            name=name,
                            url=url,
                            status="online",
                            latency_ms=round(latency, 2),
                            last_check=datetime.now().isoformat(),
                            details=details
                        )
                    else:
                        return ServiceStatus(
                            name=name,
                            url=url,
                            status="degraded",
                            latency_ms=round(latency, 2),
                            last_check=datetime.now().isoformat()
                        )
            else:
                # Simple TCP check for SSH
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=5.0
                )
                writer.close()
                await writer.wait_closed()
                
                latency = (datetime.now() - start_time).total_seconds() * 1000
                return ServiceStatus(
                    name=name,
                    url=f"{host}:{port}",
                    status="online",
                    latency_ms=round(latency, 2),
                    last_check=datetime.now().isoformat()
                )
                
        except TimeoutError:
            return ServiceStatus(
                name=name,
                url=url,
                status="timeout",
                latency_ms=9999,
                last_check=datetime.now().isoformat()
            )
        except Exception as e:
            return ServiceStatus(
                name=name,
                url=url,
                status="offline",
                latency_ms=9999,
                last_check=datetime.now().isoformat(),
                details={"error": str(e)}
            )
    
    async def check_all(self) -> dict[str, ServiceStatus]:
        """Check all services"""
        tasks = [
            self.check_service(key, config)
            for key, config in self.SERVICES.items()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for key, result in zip(self.SERVICES.keys(), results):
            if isinstance(result, Exception):
                config = self.SERVICES[key]
                self.statuses[key] = ServiceStatus(
                    name=config["name"],
                    url=f"{config['host']}:{config['port']}",
                    status="error",
                    latency_ms=9999,
                    last_check=datetime.now().isoformat(),
                    details={"error": str(result)}
                )
            else:
                self.statuses[key] = result
        
        return self.statuses
    
    def print_status(self):
        """Print status to console"""
        print("\n" + "="*70)
        print(f"  SAPPHIRE SYSTEM MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        
        online = sum(1 for s in self.statuses.values() if s.status == "online")
        total = len(self.statuses)
        
        print(f"\n  Overall: {online}/{total} services online")
        print()
        
        # Windows PC
        print("  🖥️  WINDOWS PC (100.71.10.48)")
        for key in ["tv_agent", "webhook_receiver"]:
            if key in self.statuses:
                s = self.statuses[key]
                icon = "🟢" if s.status == "online" else "🔴"
                print(f"     {icon} {s.name:<25} {s.status:<10} ({s.latency_ms}ms)")
        
        print()
        
        # Pi Cluster
        print("  🥧 PI CLUSTER")
        for key in ["rari1_research", "rari2_trading"]:
            if key in self.statuses:
                s = self.statuses[key]
                icon = "🟢" if s.status == "online" else "🔴"
                print(f"     {icon} {s.name:<25} {s.status:<10} ({s.latency_ms}ms)")
        
        print()
        
        # Cloud
        print("  ☁️  CLOUD SERVICES")
        for key in ["command_deck", "gateway", "log_viewer"]:
            if key in self.statuses:
                s = self.statuses[key]
                icon = "🟢" if s.status == "online" else "🔴"
                print(f"     {icon} {s.name:<25} {s.status:<10} ({s.latency_ms}ms)")
        
        print()
        print("="*70)
    
    def export_json(self) -> str:
        """Export status as JSON"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "services": {
                key: {
                    "name": s.name,
                    "url": s.url,
                    "status": s.status,
                    "latency_ms": s.latency_ms,
                    "last_check": s.last_check,
                    "details": s.details
                }
                for key, s in self.statuses.items()
            }
        }
        return json.dumps(data, indent=2)


async def main():
    """Run monitor"""
    async with SystemMonitor() as monitor:
        await monitor.check_all()
        monitor.print_status()
        
        # Optionally save to file
        # with open('status.json', 'w') as f:
        #     f.write(monitor.export_json())


if __name__ == "__main__":
    asyncio.run(main())
