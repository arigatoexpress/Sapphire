import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from loguru import logger


class ExecutionDispatcher:
    """
    Dispatches high-priority commands from the Hub to the Spokes (Bots).
    Uses persistent HTTP/2 connections via aiohttp.
    """

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        default_bot_urls = {
            "ASTER": os.getenv("BOT_ASTER_URL", "http://sapphire-bot-aster:8080"),
            "LIGHTER": os.getenv("BOT_LIGHTER_URL", "http://sapphire-bot-lighter:8080"),
        }
        enabled_venues_raw = os.getenv("ENABLED_VENUES", "").strip()
        if enabled_venues_raw:
            enabled_venues = {
                self._normalize_venue(token)
                for token in re.split(r"[,;|\s]+", enabled_venues_raw)
                if token.strip()
            }
            self.bot_urls = {
                venue: url
                for venue, url in default_bot_urls.items()
                if venue in enabled_venues and str(url or "").strip()
            }
        else:
            self.bot_urls = default_bot_urls
        self._token_cache: Dict[str, Tuple[str, float]] = {}
        self._venue_allocations: Dict[str, float] = {venue: 1.0 for venue in self.bot_urls}
        self._venue_paused_until: Dict[str, float] = {}
        self._venue_pause_reason: Dict[str, str] = {}

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

    def _normalize_venue(self, venue: str) -> str:
        normalized = str(venue or "").strip().upper()
        if normalized in {"LIGHT", "L2", "LT"}:
            normalized = "LIGHTER"
        return normalized

    def set_venue_allocation(self, venue: str, allocation: float) -> float:
        normalized = self._normalize_venue(venue)
        if normalized not in self.bot_urls:
            raise ValueError(f"Unknown venue: {venue}")
        bounded = max(0.0, min(1.0, float(allocation)))
        self._venue_allocations[normalized] = bounded
        return bounded

    def pause_venue(self, venue: str, reason: str = "", cooldown_seconds: int = 900) -> float:
        normalized = self._normalize_venue(venue)
        if normalized not in self.bot_urls:
            raise ValueError(f"Unknown venue: {venue}")
        paused_until = time.time() + max(1, int(cooldown_seconds))
        self._venue_paused_until[normalized] = paused_until
        self._venue_pause_reason[normalized] = reason or "manual pause"
        return paused_until

    def resume_venue(self, venue: str) -> bool:
        normalized = self._normalize_venue(venue)
        had_pause = normalized in self._venue_paused_until
        self._venue_paused_until.pop(normalized, None)
        self._venue_pause_reason.pop(normalized, None)
        return had_pause

    def resume_expired_venues(self) -> List[str]:
        now = time.time()
        resumed: List[str] = []
        for venue, paused_until in list(self._venue_paused_until.items()):
            if now >= paused_until:
                self._venue_paused_until.pop(venue, None)
                self._venue_pause_reason.pop(venue, None)
                resumed.append(venue)
        return resumed

    def get_control_state(self) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        snapshot: Dict[str, Dict[str, Any]] = {}
        for venue, url in self.bot_urls.items():
            paused_until = self._venue_paused_until.get(venue)
            snapshot[venue] = {
                "url": url,
                "allocation": self._venue_allocations.get(venue, 1.0),
                "paused": bool(paused_until and paused_until > now),
                "paused_until": paused_until,
                "pause_reason": self._venue_pause_reason.get(venue, ""),
            }
        return snapshot

    def _is_venue_dispatchable(self, venue: str) -> bool:
        now = time.time()
        paused_until = self._venue_paused_until.get(venue)
        if paused_until and now >= paused_until:
            self.resume_venue(venue)

        if venue in self._venue_paused_until:
            return False

        return self._venue_allocations.get(venue, 1.0) > 0.0

    async def send_command(self, venue: str, command: Dict[str, Any]) -> bool:
        """Send a command to a specific bot."""
        if not self.session:
            logger.error("Dispatcher not started!")
            return False

        normalized_venue = self._normalize_venue(venue)
        url = self.bot_urls.get(normalized_venue)
        if not url:
            logger.error(f"No URL configured for venue: {venue}")
            return False

        if not self._is_venue_dispatchable(normalized_venue):
            logger.warning(
                f"🚫 Command blocked for {normalized_venue}: allocation={self._venue_allocations.get(normalized_venue, 1.0):.2f}, "
                f"paused={normalized_venue in self._venue_paused_until}"
            )
            return False

        full_url = f"{url}/execute"
        auth_headers = await self._get_auth_header(url)
        allocation = self._venue_allocations.get(normalized_venue, 1.0)

        command_payload = dict(command)
        quantity = command_payload.get("quantity")
        if allocation < 1.0 and isinstance(quantity, (int, float)) and quantity > 0:
            command_payload["quantity"] = round(float(quantity) * allocation, 8)
            command_payload["allocation_factor"] = allocation

        try:
            async with self.session.post(full_url, json=command_payload, headers=auth_headers) as val:
                if val.status == 200:
                    logger.info(f"✅ Command Sent to {normalized_venue}: {command_payload}")
                    return True
                elif val.status == 403:
                    logger.error(
                        f"🚫 Permission Denied (403): Ensure Hub service account has 'run.invoker' on {normalized_venue}"
                    )
                    return False
                else:
                    logger.error(f"❌ Command Failed {normalized_venue}: {val.status}")
                    return False
        except Exception as e:
            logger.error(f"Dispatch Error ({normalized_venue}): {e}")
            return False


# Singleton
dispatcher = ExecutionDispatcher()
