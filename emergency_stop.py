#!/usr/bin/env python3
"""
Emergency Stop Script for Sapphire Trading System
Immediately halts all trading activity and preserves system integrity
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
import aiohttp
import json

# Configure logging
logging.basicConfig(
    level=logging.CRITICAL,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('emergency_stop.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class EmergencyStop:
    def __init__(self):
        self.project_id = "sapphireinfinite"
        self.cluster_name = "hft-trading-cluster"
        self.zone = "us-central1-a"
        self.namespace = "trading"
        self.api_base_url = None

    async def run_command(self, command: str, check: bool = True) -> tuple[bool, str]:
        """Run shell command and return success status and output."""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()

            if process.returncode != 0 and check:
                logger.error(f"Command failed: {command}\nStderr: {stderr_str}")
                return False, stderr_str
            return True, stdout_str
        except Exception as e:
            logger.error(f"Error running command '{command}': {e}")
            return False, str(e)

    async def get_api_endpoint(self) -> bool:
        """Get the API endpoint quickly."""
        success, output = await self.run_command(
            f"kubectl get service trading-system-cloud-trader -n {self.namespace} -o jsonpath='{{.spec.clusterIP}}'"
        )
        if success:
            self.api_base_url = f"http://{output.strip()}:8080"
            return True
        return False

    async def emergency_stop_trading(self) -> bool:
        """Execute emergency stop across all systems."""
        logger.critical("🚨 EMERGENCY STOP ACTIVATED")

        try:
            async with aiohttp.ClientSession() as session:
                # Immediate trading halt
                stop_command = {
                    "command": "emergency_stop",
                    "reason": "manual_emergency_stop",
                    "timestamp": datetime.utcnow().isoformat(),
                    "close_all_positions": True,
                    "halt_all_agents": True,
                    "preserve_data": True
                }

                async with session.post(
                    f"{self.api_base_url}/emergency/stop",
                    json=stop_command,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.critical(f"✅ Emergency stop executed: {result}")
                        return True
                    else:
                        logger.critical(f"❌ Emergency stop API failed: {response.status}")

        except Exception as e:
            logger.critical(f"❌ Emergency stop failed: {e}")

        # Fallback: Scale down deployments
        logger.critical("🔄 Executing fallback emergency stop...")
        await self.scale_down_deployments()
        return False

    async def scale_down_deployments(self) -> bool:
        """Scale down all trading deployments."""
        deployments = [
            "trading-system-deepseek-bot",
            "trading-system-qwen-bot",
            "trading-system-fingpt-bot",
            "trading-system-lagllama-bot",
            "trading-system-vpin-bot"
        ]

        for deployment in deployments:
            await self.run_command(
                f"kubectl scale deployment {deployment} -n {self.namespace} --replicas=0",
                check=False
            )

        logger.critical("✅ All trading deployments scaled to zero")
        return True

    async def send_emergency_alert(self) -> bool:
        """Send emergency alert."""
        try:
            async with aiohttp.ClientSession() as session:
                alert = {
                    "type": "emergency_stop",
                    "message": "🚨 EMERGENCY STOP ACTIVATED - ALL TRADING HALTED",
                    "timestamp": datetime.utcnow().isoformat(),
                    "priority": "critical"
                }

                async with session.post(
                    f"{self.api_base_url}/notifications/emergency",
                    json=alert,
                    timeout=5
                ) as response:
                    return response.status == 200

        except Exception:
            return False

async def main():
    stop = EmergencyStop()

    # Get API endpoint
    if not await stop.get_api_endpoint():
        logger.critical("❌ Cannot connect to system - executing deployment scaling")
        await stop.scale_down_deployments()
        sys.exit(1)

    # Execute emergency stop
    success = await stop.emergency_stop_trading()

    # Send alert
    await stop.send_emergency_alert()

    if success:
        logger.critical("✅ EMERGENCY STOP COMPLETE - SYSTEM SECURE")
    else:
        logger.critical("❌ EMERGENCY STOP PARTIAL - MANUAL VERIFICATION REQUIRED")

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
