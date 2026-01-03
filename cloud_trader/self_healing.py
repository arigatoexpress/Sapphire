import asyncio
import logging
import os
import threading
import time
from typing import Callable, Optional

import redis
import requests

logger = logging.getLogger(__name__)


class SelfHealingWatchdog:
    """
    Monitors critical system components and restarts/alerts if they fail.
    Designed to run in a background thread.
    """

    def __init__(self, check_interval=30, loop=None, stall_threshold=600):
        self.check_interval = check_interval
        self.running = False
        self._thread = None
        self._heartbeats = {}  # {component_name: last_timestamp}
        self._stall_threshold = stall_threshold  # Default 10 minutes for slow scans
        self.recovery_callback = None
        self.api_url = "http://localhost:8080/healthz"
        self._loop = loop or (asyncio.get_event_loop() if asyncio.get_event_loop().is_running() else None)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("🛡️ Self-Healing Watchdog started.")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)

    def heartbeat(self, component: str):
        """Register a heartbeat for a component."""
        self._heartbeats[component] = time.time()

    def _run_loop(self):
        while self.running:
            try:
                # 1. Check API health - Disabled to avoid log spam in Cloud Run
                # self._check_api()
                
                # 2. Check for stalls in heartbeats
                self._check_stalls()
                
            except Exception as e:
                logger.error(f"Watchdog loop error: {e}")

            time.sleep(self.check_interval)

    def _check_stalls(self):
        now = time.time()
        for component, last_ts in self._heartbeats.items():
            if now - last_ts > self._stall_threshold:
                logger.error(f"🚨 CRITICAL: Component '{component}' stalled for {int(now - last_ts)}s!")
                if self.recovery_callback:
                    logger.info(f"🔄 Triggering recovery callback for stalled component: {component}")
                    try:
                        import inspect
                        # Check if callback is a coroutine function
                        if inspect.iscoroutinefunction(self.recovery_callback):
                            # Use the stored loop reference
                            if self._loop and self._loop.is_running():
                                asyncio.run_coroutine_threadsafe(self.recovery_callback(component), self._loop)
                            else:
                                # Fallback if no loop or loop stopped
                                asyncio.run(self.recovery_callback(component))
                        else:
                            self.recovery_callback(component)
                    except Exception as e:
                        logger.error(f"Recovery callback failed: {e}")
                # Reset heartbeat to prevent loop spam if recovery is slow
                self._heartbeats[component] = now

    def _check_redis(self):
        # Redis not deployed in Cloud Run - skip check to avoid error spam
        # Only attempt connection if REDIS_URL is explicitly configured
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return  # No Redis configured, skip silently
        try:
            r = redis.from_url(redis_url)
            if not r.ping():
                raise ConnectionError("Redis ping failed")
        except Exception as e:
            logger.warning(f"⚠️ Redis health check failed: {e}")
            pass

    def _check_api(self):
        try:
            # Self-check API
            res = requests.get(self.api_url, timeout=5)
            if res.status_code != 200:
                logger.warning(f"⚠️ API Unhealthy: {res.status_code}")
        except Exception as e:
            logger.error(f"❌ API Unreachable: {e}")


# Legacy support for full service import
def get_self_healing_manager():
    return None


def initialize_graceful_degradation():
    pass


def recover_database_connection():
    pass


def recover_redis_connection():
    pass


def recover_exchange_connection():
    pass


def recover_vertex_ai_connection():
    pass


def recover_feature_store_connection():
    pass
