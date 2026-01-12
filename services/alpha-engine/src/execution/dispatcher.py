import asyncio
import json
import os
import time
from typing import Any, Dict

import aiohttp
from loguru import logger


class ExecutionDispatcher:
    """
    Dispatches high-priority commands from the Hub to the Spokes (Bots).
    Uses persistent HTTP/2 connections via aiohttp.
    """

    def __init__(self):
        self.session: aiohttp.ClientSession = None
        self.bot_urls = {
            "DRIFT": os.getenv("BOT_DRIFT_URL", "http://sapphire-bot-drift:8080"),
            "HYPERLIQUID": os.getenv("BOT_HYPERLIQUID_URL", "http://sapphire-bot-hyperliquid:8080"),
            "ASTER": os.getenv("BOT_ASTER_URL", "http://sapphire-bot-aster:8080"),
            "SYMPHONY": os.getenv("BOT_SYMPHONY_URL", "http://sapphire-bot-symphony:8080"),
        }

    async def start(self):
        self.session = aiohttp.ClientSession()
        logger.info("🚀 Execution Dispatcher Started")

    async def stop(self):
        if self.session:
            await self.session.close()

    async def _get_auth_header(self, url: str) -> Dict[str, str]:
        """Fetch OIDC token with caching for low-latency performance."""
        if not os.getenv("K_SERVICE"):
            return {}

        # Basic caching to prevent hammering metadata server
        now = time.time()
        if hasattr(self, "_token_cache") and url in self._token_cache:
            token, expiry = self._token_cache[url]
            if now < expiry:
                return {"Authorization": f"Bearer {token}"}

        try:
            aud = "/".join(url.split("/")[:3])
            token_url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={aud}"
            # Use the persistent session instead of creating a new one
            async with self.session.get(token_url, headers={"Metadata-Flavor": "Google"}) as resp:
                if resp.status == 200:
                    token = await resp.text()
                    if not hasattr(self, "_token_cache"):
                        self._token_cache = {}
                    # Cache for 10 minutes (tokens usually last 1 hour)
                    self._token_cache[url] = (token, now + 600)
                    logger.debug(f"Successfully fetched OIDC token for {aud}")
                    return {"Authorization": f"Bearer {token}"}
                else:
                    logger.error(f"Metadata Server Error {resp.status}: {await resp.text()}")
        except Exception as e:
            logger.error(f"OIDC Token Fetch Error: {e}")
        return {}

    async def send_command(self, venue: str, command: Dict[str, Any]):
        """Send a command to a specific bot."""
        if not self.session:
            logger.error("Dispatcher not started!")
            return

        url = self.bot_urls.get(venue.upper())
        if not url:
            logger.error(f"No URL configured for venue: {venue}")
            return

        full_url = f"{url}/execute"
        auth_headers = await self._get_auth_header(url)

        try:
            async with self.session.post(full_url, json=command, headers=auth_headers) as val:
                if val.status == 200:
                    logger.info(f"✅ Command Sent to {venue}: {command}")
                elif val.status == 403:
                    logger.error(
                        f"🚫 Permission Denied (403): Ensure Hub service account has 'run.invoker' on {venue}"
                    )
                else:
                    logger.error(f"❌ Command Failed {venue}: {val.status}")
        except Exception as e:
            logger.error(f"Dispatch Error ({venue}): {e}")


# Singleton
dispatcher = ExecutionDispatcher()
