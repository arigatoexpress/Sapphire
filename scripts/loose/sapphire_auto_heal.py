#!/usr/bin/env python3
"""
Sapphire AI - Auto-Healing System
Monitors and automatically recovers services
"""

import asyncio
import logging
import subprocess
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


class AutoHealSystem:
    """
    Autonomous healing for Sapphire AI trading system
    """
    
    def __init__(self):
        self.services = {
            # Mac services
            "mac_orchestrator": {
                "host": "localhost",
                "port": 8087,
                "check_url": "http://localhost:8087/stats",
                "start_cmd": "cd /Users/aribs && python3 sapphire_ai_orchestrator.py > /tmp/orchestrator.log 2>&1 &",
                "pid_file": "/tmp/orchestrator.pid",
                "type": "mac"
            },
            "mac_bridge": {
                "host": "localhost",
                "port": 8083,
                "check_url": "http://localhost:8083/status",
                "start_cmd": "cd /Users/aribs && python3 tv_mac_bridge.py > /tmp/bridge.log 2>&1 &",
                "pid_file": "/tmp/tv_bridge.pid",
                "type": "mac"
            },
            "mac_dashboard": {
                "host": "localhost",
                "port": 8088,
                "check_url": "http://localhost:8088",
                "start_cmd": "cd /Users/aribs && python3 serve_dashboard.py > /tmp/dashboard.log 2>&1 &",
                "pid_file": "/tmp/dashboard.pid",
                "type": "mac"
            },
            "mac_background_agent": {
                "host": "localhost",
                "port": 8086,
                "check_url": "http://localhost:8086/status",
                "start_cmd": "cd /Users/aribs && python3 tv_background_agent.py > /tmp/background_agent.log 2>&1 &",
                "pid_file": "/tmp/tv_background.pid",
                "type": "mac"
            },
            # Windows services (just monitoring, can't auto-heal without SSH)
            "windows_webhook": {
                "host": "100.71.10.48",
                "port": 9090,
                "check_url": "http://100.71.10.48:9090/status",
                "type": "windows",
                "auto_heal": False
            },
        }
        
        self.pi_services = {
            "pi1_lighter": {
                "host": "192.168.1.23",
                "service": "lighter-trading",
                "auto_heal": True
            },
            "pi1_aster": {
                "host": "192.168.1.23",
                "service": "aster-trading",
                "auto_heal": True
            },
            "pi2_lighter": {
                "host": "192.168.1.173",
                "service": "lighter-trading",
                "auto_heal": True
            },
            "pi2_aster": {
                "host": "192.168.1.173",
                "service": "sapphire-aster-pi",
                "auto_heal": True
            },
            "pi2_auto": {
                "host": "192.168.1.173",
                "service": "autonomous-trading-daemon",
                "auto_heal": True
            }
        }
        
        self.heal_history = []
        
    async def check_service(self, name: str, config: dict) -> bool:
        """Check if service is healthy"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session, session.get(
                config["check_url"],
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                return resp.status == 200
        except Exception:
            return False
            
    async def heal_mac_service(self, name: str, config: dict):
        """Heal a Mac service"""
        logger.warning(f"🔧 Auto-healing {name}...")
        
        # Try to kill existing process
        try:
            with open(config["pid_file"]) as f:
                pid = f.read().strip()
                subprocess.run(['kill', pid], capture_output=True)
                await asyncio.sleep(1)
        except:
            pass
            
        # Start new process
        subprocess.Popen(
            config["start_cmd"],
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Save PID
        await asyncio.sleep(2)
        # Note: PID saving would need to be done by the service itself
        
        self.heal_history.append({
            "timestamp": datetime.now().isoformat(),
            "service": name,
            "action": "restarted"
        })
        
        logger.info(f"✅ {name} restarted")
        
    async def heal_pi_service(self, name: str, config: dict):
        """Heal a Pi service via SSH"""
        logger.warning(f"🔧 Auto-healing {name} on {config['host']}...")
        
        try:
            # Restart service
            cmd = [
                'ssh', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=no',
                f'rari@{config["host"]}',
                f'echo "rari" | sudo -S systemctl restart {config["service"]}'
            ]
            subprocess.run(cmd, capture_output=True, timeout=15)
            
            self.heal_history.append({
                "timestamp": datetime.now().isoformat(),
                "service": name,
                "action": "restarted",
                "host": config["host"]
            })
            
            logger.info(f"✅ {name} restarted on {config['host']}")
        except Exception as e:
            logger.error(f"❌ Failed to heal {name}: {e}")
            
    async def check_and_heal_pi(self, name: str, config: dict):
        """Check and heal Pi service"""
        try:
            # Check status
            cmd = [
                'ssh', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=no',
                f'rari@{config["host"]}',
                f'systemctl is-active {config["service"]}'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0 or "inactive" in result.stdout:
                logger.warning(f"⚠️  {name} is DOWN on {config['host']}")
                if config.get("auto_heal", False):
                    await self.heal_pi_service(name, config)
            else:
                logger.debug(f"✅ {name} is healthy")
                
        except Exception as e:
            logger.error(f"❌ Cannot check {name}: {e}")
            
    async def run_health_check(self):
        """Run one health check cycle"""
        logger.info("🏥 Running health check cycle...")
        
        # Check Mac services
        for name, config in self.services.items():
            if config["type"] == "mac":
                healthy = await self.check_service(name, config)
                if not healthy:
                    logger.warning(f"⚠️  {name} is DOWN")
                    await self.heal_mac_service(name, config)
                else:
                    logger.debug(f"✅ {name} is healthy")
                    
        # Check Pi services
        for name, config in self.pi_services.items():
            await self.check_and_heal_pi(name, config)
            
        logger.info("✅ Health check cycle complete")
        
    async def generate_report(self) -> dict:
        """Generate health report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "services": {},
            "heal_history": self.heal_history[-10:],  # Last 10 heals
            "summary": {
                "total_services": len(self.services) + len(self.pi_services),
                "healthy": 0,
                "unhealthy": 0
            }
        }
        
        for name, config in self.services.items():
            healthy = await self.check_service(name, config)
            report["services"][name] = "healthy" if healthy else "unhealthy"
            if healthy:
                report["summary"]["healthy"] += 1
            else:
                report["summary"]["unhealthy"] += 1
                
        return report
        
    async def run(self):
        """Main auto-heal loop"""
        logger.info("🚀 Sapphire Auto-Heal System started")
        logger.info("   Monitoring services every 60 seconds")
        
        while True:
            try:
                await self.run_health_check()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Auto-heal error: {e}")
                await asyncio.sleep(60)


# HTTP API for monitoring
from aiohttp import web


async def start_heal_api(healer: AutoHealSystem, port: int = 8089):
    """Start API for auto-heal system"""
    
    app = web.Application()
    
    async def status(request):
        report = await healer.generate_report()
        return web.json_response(report)
        
    async def heal_now(request):
        await healer.run_health_check()
        return web.json_response({"status": "heal_cycle_complete"})
        
    async def heal_history(request):
        return web.json_response(healer.heal_history)
    
    app.router.add_get('/status', status)
    app.router.add_post('/heal', heal_now)
    app.router.add_get('/history', heal_history)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"🌐 Auto-Heal API on port {port}")
    return runner


async def main():
    healer = AutoHealSystem()
    
    # Start API
    await start_heal_api(healer, port=8089)
    
    logger.info("")
    logger.info("═══════════════════════════════════════════════════════════")
    logger.info("  🏥 SAPPHIRE AUTO-HEAL SYSTEM")
    logger.info("═══════════════════════════════════════════════════════════")
    logger.info("")
    logger.info("Monitoring:")
    logger.info("  • AI Orchestrator (:8087)")
    logger.info("  • Strategy Bridge (:8083)")
    logger.info("  • Dashboard (:8088)")
    logger.info("  • Background Agent (:8086)")
    logger.info("  • Windows Webhook (:9090)")
    logger.info("  • Pi 1 & Pi 2 bots")
    logger.info("")
    logger.info("API: http://localhost:8089")
    logger.info("  GET /status   - Health report")
    logger.info("  POST /heal    - Trigger heal now")
    logger.info("  GET /history  - Heal history")
    logger.info("")
    
    # Run auto-heal loop
    await healer.run()


if __name__ == "__main__":
    asyncio.run(main())
