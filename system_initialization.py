#!/usr/bin/env python3
"""
System Initialization Script for Sapphire Trading System
Executes post-deployment initialization sequence for live trading
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
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('system_initialization.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class SystemInitializer:
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
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

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
        """Get the API endpoint for the cloud-trader service."""
        logger.info("🔍 Discovering API endpoint...")

        success, output = await self.run_command(
            f"kubectl get service trading-system-cloud-trader -n {self.namespace} -o jsonpath='{{.spec.clusterIP}}'"
        )
        if not success:
            logger.error("❌ Cannot get cloud-trader service IP")
            return False

        service_ip = output.strip()
        self.api_base_url = f"http://{service_ip}:8080"

        logger.info(f"✅ API endpoint discovered: {self.api_base_url}")
        return True

    async def test_api_connectivity(self) -> bool:
        """Test API connectivity and basic endpoints."""
        logger.info("🔌 Testing API connectivity...")

        if not self.api_base_url:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                # Test health endpoint
                async with session.get(f"{self.api_base_url}/healthz", timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"❌ Health check failed: {response.status}")
                        return False

                # Test agents endpoint
                async with session.get(f"{self.api_base_url}/agents/status", timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"❌ Agents status check failed: {response.status}")
                        return False

                logger.info("✅ API connectivity verified")
                return True

        except Exception as e:
            logger.error(f"❌ API connectivity test failed: {e}")
            return False

    async def initialize_agents(self) -> bool:
        """Initialize all AI agents."""
        logger.info("🤖 Initializing AI agents...")

        agents = [
            "deepseek-v3",
            "qwen-adaptive",
            "fingpt-alpha",
            "lagllama-degen",
            "vpin-hft"
        ]

        try:
            async with aiohttp.ClientSession() as session:
                for agent in agents:
                    logger.info(f"🚀 Initializing agent: {agent}")

                    payload = {
                        "agent_id": agent,
                        "action": "initialize",
                        "parameters": {
                            "margin_allocation": 600.0,  # $600 per agent
                            "max_leverage": 10.0,
                            "risk_multiplier": 0.8
                        }
                    }

                    async with session.post(
                        f"{self.api_base_url}/agents/{agent}/initialize",
                        json=payload,
                        timeout=30
                    ) as response:
                        if response.status != 200:
                            logger.error(f"❌ Failed to initialize {agent}: {response.status}")
                            return False

                        result = await response.json()
                        if not result.get("success", False):
                            logger.error(f"❌ Agent {agent} initialization failed: {result}")
                            return False

                        logger.info(f"✅ Agent {agent} initialized successfully")

                logger.info("✅ All agents initialized")
                return True

        except Exception as e:
            logger.error(f"❌ Agent initialization failed: {e}")
            return False

    async def test_mcp_communication(self) -> bool:
        """Test MCP inter-agent communication."""
        logger.info("🔄 Testing MCP communication...")

        try:
            async with aiohttp.ClientSession() as session:
                # Test MCP status
                async with session.get(f"{self.api_base_url}/mcp/status", timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"❌ MCP status check failed: {response.status}")
                        return False

                # Test agent communication
                test_message = {
                    "type": "coordination_test",
                    "sender": "system_init",
                    "recipients": ["deepseek-v3", "qwen-adaptive"],
                    "content": {
                        "message": "System initialization test",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }

                async with session.post(
                    f"{self.api_base_url}/mcp/broadcast",
                    json=test_message,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        logger.error(f"❌ MCP broadcast failed: {response.status}")
                        return False

                    result = await response.json()
                    if not result.get("success", False):
                        logger.error(f"❌ MCP communication test failed: {result}")
                        return False

                logger.info("✅ MCP communication verified")
                return True

        except Exception as e:
            logger.error(f"❌ MCP communication test failed: {e}")
            return False

    async def configure_trading_parameters(self) -> bool:
        """Configure trading system parameters."""
        logger.info("⚙️ Configuring trading parameters...")

        try:
            async with aiohttp.ClientSession() as session:
                # Configure risk management
                risk_config = {
                    "max_drawdown": 0.25,  # 25% max drawdown
                    "max_portfolio_leverage": 2.0,
                    "liquidation_buffer": 0.25,  # 25% buffer
                    "base_sl_pct": 0.03,  # 3% base stop loss
                    "emergency_stop_enabled": True
                }

                async with session.post(
                    f"{self.api_base_url}/risk/configure",
                    json=risk_config,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        logger.error(f"❌ Risk configuration failed: {response.status}")
                        return False

                # Configure market data
                market_config = {
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "timeframes": ["5m", "15m", "1h"],
                    "data_sources": ["aster", "vertex_ai"]
                }

                async with session.post(
                    f"{self.api_base_url}/market/configure",
                    json=market_config,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        logger.error(f"❌ Market configuration failed: {response.status}")
                        return False

                logger.info("✅ Trading parameters configured")
                return True

        except Exception as e:
            logger.error(f"❌ Trading configuration failed: {e}")
            return False

    async def test_telegram_notifications(self) -> bool:
        """Test Telegram notification system."""
        logger.info("📢 Testing Telegram notifications...")

        try:
            async with aiohttp.ClientSession() as session:
                test_notification = {
                    "type": "system_test",
                    "message": "Sapphire Trading System Initialization Complete 🚀",
                    "priority": "high",
                    "include_metrics": True
                }

                async with session.post(
                    f"{self.api_base_url}/notifications/test",
                    json=test_notification,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        logger.warning(f"⚠️ Telegram test notification failed: {response.status}")
                        logger.warning("Continuing with initialization...")
                        return True  # Don't fail on Telegram issues

                    result = await response.json()
                    if result.get("success", False):
                        logger.info("✅ Telegram notifications working")
                    else:
                        logger.warning("⚠️ Telegram notifications may not be working")

                return True

        except Exception as e:
            logger.warning(f"⚠️ Telegram notification test failed: {e}")
            logger.warning("Continuing with initialization...")
            return True

    async def enable_live_trading(self) -> bool:
        """Enable live trading mode."""
        logger.info("🚀 Enabling live trading mode...")

        try:
            async with aiohttp.ClientSession() as session:
                live_config = {
                    "mode": "live",
                    "capital_allocation": 4200.0,  # $4,200 total
                    "agents_enabled": [
                        "deepseek-v3",
                        "qwen-adaptive",
                        "fingpt-alpha",
                        "lagllama-degen",
                        "vpin-hft"
                    ],
                    "auto_start": False,  # Manual start after verification
                    "risk_limits": {
                        "max_position_size": 0.05,  # 5% of capital per position
                        "max_open_positions": 10,
                        "max_leverage_per_agent": 15.0
                    }
                }

                async with session.post(
                    f"{self.api_base_url}/trading/enable",
                    json=live_config,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        logger.error(f"❌ Live trading enable failed: {response.status}")
                        return False

                    result = await response.json()
                    if not result.get("success", False):
                        logger.error(f"❌ Live trading configuration failed: {result}")
                        return False

                logger.info("✅ Live trading mode enabled")
                logger.info("💰 Capital allocated: $4,200 across 7 agents")
                return True

        except Exception as e:
            logger.error(f"❌ Live trading enable failed: {e}")
            return False

    async def run_system_initialization(self) -> bool:
        """Run complete system initialization sequence."""
        logger.info("🚀 STARTING SYSTEM INITIALIZATION")
        logger.info("=" * 60)

        initialization_steps = [
            ("API Discovery", self.get_api_endpoint),
            ("API Connectivity", self.test_api_connectivity),
            ("Agent Initialization", self.initialize_agents),
            ("MCP Communication", self.test_mcp_communication),
            ("Trading Configuration", self.configure_trading_parameters),
            ("Telegram Testing", self.test_telegram_notifications),
            ("Live Trading Enable", self.enable_live_trading),
        ]

        all_passed = True
        results_summary = []

        for step_name, init_func in initialization_steps:
            logger.info(f"\n🔧 Running {step_name}...")
            try:
                success = await init_func()
                status = "✅ PASSED" if success else "❌ FAILED"
                results_summary.append(f"{step_name}: {status}")

                if not success:
                    all_passed = False
                    # Continue with other steps for diagnostics

            except Exception as e:
                logger.error(f"❌ {step_name} crashed: {e}")
                results_summary.append(f"{step_name}: ❌ CRASHED")
                all_passed = False

        logger.info("\n" + "=" * 60)
        logger.info("📊 INITIALIZATION RESULTS SUMMARY")
        logger.info("=" * 60)

        for result in results_summary:
            logger.info(result)

        logger.info("\n" + "=" * 60)
        if all_passed:
            logger.info("🎉 SYSTEM INITIALIZATION COMPLETE!")
            logger.info("🚀 READY FOR LIVE TRADING")
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. 📱 Deploy frontend dashboard")
            logger.info("2. 📊 Test monitoring systems")
            logger.info("3. 🎯 Start live trading manually")
        else:
            logger.error("❌ SYSTEM INITIALIZATION PARTIALLY FAILED")
            logger.error("Manual intervention may be required")

        logger.info("=" * 60)

        return all_passed

async def main():
    initializer = SystemInitializer()
    success = await initializer.run_system_initialization()

    if success:
        logger.info("\n🎯 SYSTEM READY FOR LIVE TRADING")
        logger.info("💎 Sapphire Trading System initialization complete!")
        sys.exit(0)
    else:
        logger.error("\n❌ SYSTEM INITIALIZATION INCOMPLETE")
        logger.error("Review logs and resolve issues")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
