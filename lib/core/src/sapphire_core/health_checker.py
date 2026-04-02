#!/usr/bin/env python3
"""
Sapphire Health Checker
Monitors all system components and sends Telegram alerts
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

import aiohttp
from telegram import Bot

# Configuration
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Endpoints to monitor
ENDPOINTS = [
    ('Dashboard', 'https://sapphirealpha.xyz/health'),
    ('Gateway', 'https://sapphire-gateway-267358751314.us-central1.run.app/health'),
    ('PM Hub', 'https://agentic-pm-hub-267358751314.us-central1.run.app/health'),
    ('Pi 1 Workbench', 'http://10.0.0.1:18891/health'),
    ('Pi 2 Trading', 'http://10.0.0.2:18888/status'),
]

# Thresholds
TIMEOUT_SECONDS = 10
ALERT_COOLDOWN_MINUTES = 15

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HealthChecker:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None
        self.last_alert = {}  # Track when we last sent alert for each service
        
    async def check_endpoint(self, name, url):
        """Check if endpoint is healthy"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=TIMEOUT_SECONDS) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return True, data
                    else:
                        return False, f"HTTP {resp.status}"
        except asyncio.TimeoutError:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)[:100]
    
    def should_send_alert(self, name):
        """Check if we should send alert (cooldown)"""
        now = datetime.now()
        last_alert = self.last_alert.get(name)
        
        if last_alert is None:
            return True
        
        minutes_since = (now - last_alert).total_seconds() / 60
        return minutes_since > ALERT_COOLDOWN_MINUTES
    
    async def send_alert(self, name, status, details):
        """Send Telegram alert"""
        if not self.bot or not CHAT_ID:
            logger.warning("Telegram not configured, skipping alert")
            return
        
        emoji = "🟢" if status else "🔴"
        status_text = "HEALTHY" if status else "DOWN"
        
        message = f"""
{emoji} <b>Sapphire Alert: {name}</b>

Status: {status_text}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC

Details: {details}

{'✅ Service is back online!' if status else '⚠️ Please investigate immediately.'}
        """.strip()
        
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode='HTML'
            )
            self.last_alert[name] = datetime.now()
            logger.info(f"Alert sent for {name}")
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    async def check_all(self):
        """Check all endpoints"""
        logger.info("Starting health checks...")
        results = []
        
        for name, url in ENDPOINTS:
            healthy, details = await self.check_endpoint(name, url)
            results.append((name, healthy, details))
            
            status = "✅" if healthy else "❌"
            logger.info(f"{status} {name}: {'OK' if healthy else details}")
            
            # Send alert if down and cooldown passed
            if not healthy and self.should_send_alert(name):
                await self.send_alert(name, healthy, details)
            # Send recovery alert if was down and now up
            elif healthy and name in self.last_alert:
                await self.send_alert(name, healthy, "Service recovered")
                del self.last_alert[name]  # Clear alert state
        
        return results
    
    async def run_continuous(self, interval_seconds=300):
        """Run health checks continuously"""
        logger.info(f"Starting continuous monitoring (interval: {interval_seconds}s)")
        
        while True:
            try:
                await self.check_all()
            except Exception as e:
                logger.error(f"Error during health check: {e}")
            
            logger.info(f"Sleeping for {interval_seconds} seconds...")
            await asyncio.sleep(interval_seconds)

def main():
    """Main entry point"""
    # Validate configuration
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)
    
    if not CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID not set")
        sys.exit(1)
    
    checker = HealthChecker()
    
    # Run once or continuously based on argument
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        asyncio.run(checker.check_all())
    else:
        # Default: run continuously every 5 minutes
        interval = int(sys.argv[1]) if len(sys.argv) > 1 else 300
        asyncio.run(checker.run_continuous(interval))

if __name__ == '__main__':
    main()