import asyncio
import os
import re
import time
from collections import deque
from typing import Any

import aiohttp
from loguru import logger

# ── Per-Venue Rate Limiter ───────────────────────────────────────────


class VenueRateLimiter:
    """Token-bucket rate limiter per venue.

    Prevents API ban from rapid-fire dispatches. Default: 10 commands/min
    per venue, configurable via env SAPPHIRE_VENUE_RATE_LIMIT_<VENUE>.
    """

    def __init__(self, default_per_minute: int = 10):
        self._default_per_minute = max(1, default_per_minute)
        self._windows: dict[str, deque[float]] = {}
        self._limits: dict[str, int] = {}

    def _get_limit(self, venue: str) -> int:
        if venue not in self._limits:
            env_key = f"SAPPHIRE_VENUE_RATE_LIMIT_{venue}"
            raw = os.getenv(env_key, "").strip()
            self._limits[venue] = max(1, int(raw)) if raw.isdigit() else self._default_per_minute
        return self._limits[venue]

    def check(self, venue: str) -> bool:
        """Return True if the dispatch is allowed; False if rate-limited."""
        now = time.time()
        limit = self._get_limit(venue)
        window = self._windows.setdefault(venue, deque())

        # Purge entries older than 60 seconds
        while window and window[0] < now - 60:
            window.popleft()

        if len(window) >= limit:
            return False

        window.append(now)
        return True

    def get_status(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        result: dict[str, dict[str, Any]] = {}
        for venue, window in self._windows.items():
            # Count active in window
            active = sum(1 for t in window if t >= now - 60)
            result[venue] = {
                "requests_last_60s": active,
                "limit_per_minute": self._get_limit(venue),
                "headroom": max(0, self._get_limit(venue) - active),
            }
        return result


# ── Dead-Letter Tracker ──────────────────────────────────────────────


class UnconfirmedFillTracker:
    """Track dispatched commands that timed out without fill confirmation.

    These represent potential orphaned positions that need reconciliation.
    Persisted in-memory with a fixed-size ring buffer.
    """

    def __init__(self, max_entries: int = 200):
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_entries)

    def record(
        self,
        venue: str,
        symbol: str,
        command: dict[str, Any],
        timeout_seconds: float,
        attempt: int,
        retries: int,
    ) -> None:
        self._entries.append(
            {
                "venue": venue,
                "symbol": symbol,
                "side": command.get("side") or command.get("action", "UNKNOWN"),
                "quantity": command.get("quantity"),
                "dispatched_at": time.time(),
                "timeout_seconds": timeout_seconds,
                "attempt": attempt,
                "retries": retries,
                "reconciled": False,
                "reconciled_at": None,
            }
        )
        logger.warning(
            f"📋 DEAD LETTER: {venue} {symbol} {command.get('side', '?')} — "
            f"fill not confirmed after {timeout_seconds}s (attempt {attempt}/{retries})"
        )

    def reconcile(self, venue: str, symbol: str) -> bool:
        """Mark the most recent unreconciled entry as resolved."""
        for entry in reversed(self._entries):
            if entry["venue"] == venue and entry["symbol"] == symbol and not entry["reconciled"]:
                entry["reconciled"] = True
                entry["reconciled_at"] = time.time()
                return True
        return False

    @property
    def unreconciled_count(self) -> int:
        return sum(1 for e in self._entries if not e["reconciled"])

    def get_unreconciled(self) -> list[dict[str, Any]]:
        return [e for e in self._entries if not e["reconciled"]]

    def get_all(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._entries)[-limit:]

    def format_telegram_status(self) -> str:
        unreconciled = self.get_unreconciled()
        if not unreconciled:
            return "📋 **Dead Letter Queue**\n\nNo unconfirmed fills. All clear."
        lines = [f"📋 **Dead Letter Queue** ({len(unreconciled)} unconfirmed)\n"]
        for entry in unreconciled[-10:]:
            age = time.time() - entry["dispatched_at"]
            age_str = f"{age / 60:.0f}m" if age < 3600 else f"{age / 3600:.1f}h"
            lines.append(
                f"⚠️ {entry['venue']} {entry['symbol']} {entry['side']} — "
                f"{age_str} ago (timeout: {entry['timeout_seconds']}s)"
            )
        return "\n".join(lines)


class ExecutionDispatcher:
    """
    Dispatches high-priority commands from the Hub to the Spokes (Bots).
    Uses persistent HTTP/2 connections via aiohttp.
    """

    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
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
        self._token_cache: dict[str, tuple[str, float]] = {}
        self._venue_allocations: dict[str, float] = {venue: 1.0 for venue in self.bot_urls}
        self._venue_paused_until: dict[str, float] = {}
        self._venue_pause_reason: dict[str, str] = {}
        self._last_dispatch_errors: dict[str, dict[str, Any]] = {}
        # Fill confirmation: maps (VENUE, SYMBOL) → Future resolved by Pub/Sub listener
        self._pending_confirmations: dict[tuple[str, str], asyncio.Future] = {}
        # Dead-letter queue for unconfirmed fills
        self._dead_letters = UnconfirmedFillTracker(
            max_entries=max(50, int(os.getenv("SAPPHIRE_DEAD_LETTER_MAX", "200")))
        )
        # Per-venue rate limiter
        self._rate_limiter = VenueRateLimiter(
            default_per_minute=max(1, int(os.getenv("SAPPHIRE_VENUE_RATE_LIMIT", "10")))
        )

    async def start(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30, connect=5, sock_read=20)
        )
        logger.info("🚀 Execution Dispatcher Started")

    async def stop(self):
        if self.session:
            await self.session.close()

    async def _get_auth_header(self, url: str) -> dict[str, str]:
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

    def _normalize_symbol_for_venue(self, venue: str, symbol: str) -> str:
        """Keep execution symbols venue-native to avoid exchange-side rejects."""
        value = str(symbol or "").strip().upper()
        if not value:
            return value

        venue_key = self._normalize_venue(venue)
        if venue_key == "ASTER":
            # Aster futures endpoints expect USDT-quoted symbols (e.g., SOLUSDT).
            cleaned = re.sub(r"[^A-Z0-9]", "", value)
            if cleaned.endswith("USDT"):
                return cleaned
            if cleaned.endswith(("USDC", "USD")):
                return f"{cleaned[:-4]}USDT" if cleaned.endswith("USDC") else f"{cleaned[:-3]}USDT"
            return f"{cleaned}USDT"

        if venue_key == "LIGHTER":
            # Lighter bot maps to base symbols (e.g., SOL, BTC, ETH).
            cleaned = re.sub(r"[^A-Z0-9]", "", value)
            for suffix in ("USDT", "USDC", "USD", "PERP"):
                if cleaned.endswith(suffix):
                    cleaned = cleaned[: -len(suffix)]
            return cleaned

        return value

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

    def resume_expired_venues(self) -> list[str]:
        now = time.time()
        resumed: list[str] = []
        for venue, paused_until in list(self._venue_paused_until.items()):
            if now >= paused_until:
                self._venue_paused_until.pop(venue, None)
                self._venue_pause_reason.pop(venue, None)
                resumed.append(venue)
        return resumed

    def get_control_state(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        snapshot: dict[str, dict[str, Any]] = {}
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

    def _record_dispatch_error(
        self,
        venue: str,
        reason: str,
        status: int | None = None,
        body: str = "",
    ) -> None:
        self._last_dispatch_errors[self._normalize_venue(venue)] = {
            "reason": str(reason or "").strip() or "unknown",
            "status": int(status) if isinstance(status, int) else None,
            "body": str(body or "").strip()[:320],
            "timestamp": int(time.time()),
        }

    def get_last_dispatch_error(self, venue: str) -> dict[str, Any]:
        return dict(self._last_dispatch_errors.get(self._normalize_venue(venue), {}))

    async def send_command(self, venue: str, command: dict[str, Any]) -> bool:
        """Send a command to a specific bot."""
        if not self.session:
            logger.error("Dispatcher not started!")
            self._record_dispatch_error(venue, "dispatcher_not_started")
            return False

        normalized_venue = self._normalize_venue(venue)
        url = self.bot_urls.get(normalized_venue)
        if not url:
            logger.error(f"No URL configured for venue: {venue}")
            self._record_dispatch_error(normalized_venue, "venue_url_missing")
            return False

        if not self._is_venue_dispatchable(normalized_venue):
            logger.warning(
                f"🚫 Command blocked for {normalized_venue}: allocation={self._venue_allocations.get(normalized_venue, 1.0):.2f}, "
                f"paused={normalized_venue in self._venue_paused_until}"
            )
            self._record_dispatch_error(normalized_venue, "venue_not_dispatchable")
            return False

        # Per-venue rate limiting
        if not self._rate_limiter.check(normalized_venue):
            logger.warning(f"🚫 Rate-limited: {normalized_venue} exceeded dispatch limit")
            self._record_dispatch_error(normalized_venue, "rate_limited")
            return False

        full_url = f"{url}/execute"
        auth_headers = await self._get_auth_header(url)
        allocation = self._venue_allocations.get(normalized_venue, 1.0)

        command_payload = dict(command)
        # Ensure command type is set for bot gateways.
        action = str(command_payload.get("action", "")).strip().upper()
        if "type" not in command_payload and action in {"BUY", "SELL"}:
            command_payload["type"] = "TRADE_EXECUTE"
            command_payload["side"] = action

        raw_symbol = str(command_payload.get("symbol", "")).strip()
        if raw_symbol:
            command_payload["symbol"] = self._normalize_symbol_for_venue(
                normalized_venue, raw_symbol
            )

        quantity = command_payload.get("quantity")
        if allocation < 1.0 and isinstance(quantity, (int, float)) and quantity > 0:
            command_payload["quantity"] = round(float(quantity) * allocation, 8)
            command_payload["allocation_factor"] = allocation

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with self.session.post(
                    full_url, json=command_payload, headers=auth_headers
                ) as val:
                    if val.status == 200:
                        self._last_dispatch_errors.pop(normalized_venue, None)
                        logger.info(f"✅ Command Sent to {normalized_venue}: {command_payload}")
                        return True
                    elif val.status == 403:
                        body = await val.text()
                        logger.error(
                            f"🚫 Permission Denied (403): Ensure Hub service account has 'run.invoker' on {normalized_venue} | {body[:240]}"
                        )
                        self._record_dispatch_error(
                            normalized_venue, "permission_denied", status=403, body=body
                        )
                        return False
                    elif val.status >= 500 and attempt < max_retries:
                        body = await val.text()
                        delay = 0.5 * (2 ** (attempt - 1))
                        logger.warning(
                            f"⚠️ {normalized_venue} returned {val.status}, retrying in {delay:.1f}s (attempt {attempt}/{max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        body = await val.text()
                        logger.error(
                            f"❌ Command Failed {normalized_venue}: status={val.status} body={body[:240]}"
                        )
                        self._record_dispatch_error(
                            normalized_venue,
                            "http_error",
                            status=int(val.status),
                            body=body,
                        )
                        return False
            except (TimeoutError, aiohttp.ClientError) as e:
                if attempt < max_retries:
                    delay = 0.5 * (2 ** (attempt - 1))
                    logger.warning(
                        f"⚠️ Dispatch to {normalized_venue} failed ({e}), retrying in {delay:.1f}s (attempt {attempt}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    f"Dispatch Error ({normalized_venue}) after {max_retries} attempts: {e}"
                )
                self._record_dispatch_error(normalized_venue, "dispatch_exception", body=str(e))
                return False
            except Exception as e:
                logger.error(f"Dispatch Error ({normalized_venue}): {e}")
                self._record_dispatch_error(normalized_venue, "dispatch_exception", body=str(e))
                return False
        return False

    # ── Fill Confirmation ─────────────────────────────────────────

    async def send_and_confirm(
        self,
        venue: str,
        command: dict[str, Any],
        timeout_seconds: float = 30.0,
        retries: int = 1,
    ) -> dict[str, Any]:
        """Send a command and wait for Pub/Sub fill confirmation.

        Returns the fill message_data dict on success, or a dict with
        {"success": False, "error_message": ...} on timeout/failure.

        The Pub/Sub trade listener must call `resolve_fill()` when a
        matching fill arrives to complete the handshake.
        """
        normalized_venue = self._normalize_venue(venue)
        raw_symbol = str(command.get("symbol", "")).strip()
        norm_symbol = self._normalize_symbol_for_venue(normalized_venue, raw_symbol)
        # Use base symbol (strip USDT etc.) for matching
        match_symbol = re.sub(r"(USDT|USDC|USD|PERP)$", "", norm_symbol.upper())
        confirm_key = (normalized_venue, match_symbol)

        for attempt in range(1, retries + 1):
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()
            self._pending_confirmations[confirm_key] = future

            dispatched = await self.send_command(venue, command)
            if not dispatched:
                self._pending_confirmations.pop(confirm_key, None)
                return {
                    "success": False,
                    "error_message": f"Dispatch to {normalized_venue} failed (attempt {attempt})",
                    "platform": normalized_venue,
                    "symbol": raw_symbol,
                }

            try:
                fill_data = await asyncio.wait_for(future, timeout=timeout_seconds)
                logger.info(f"✅ Fill confirmed for {confirm_key} in {timeout_seconds}s window")
                return fill_data
            except TimeoutError:
                if attempt < retries:
                    logger.warning(
                        f"⏳ Fill timeout for {confirm_key} (attempt {attempt}/{retries}), retrying..."
                    )
                else:
                    logger.warning(f"⏳ Fill timeout for {confirm_key} after {retries} attempt(s)")
                    # Record to dead-letter queue for reconciliation
                    self._dead_letters.record(
                        venue=normalized_venue,
                        symbol=raw_symbol,
                        command=command,
                        timeout_seconds=timeout_seconds,
                        attempt=attempt,
                        retries=retries,
                    )
                    return {
                        "success": False,
                        "error_message": f"Fill confirmation timeout after {timeout_seconds}s x {retries}",
                        "platform": normalized_venue,
                        "symbol": raw_symbol,
                    }
            finally:
                self._pending_confirmations.pop(confirm_key, None)

        # Should not reach here, but just in case
        return {
            "success": False,
            "error_message": "Unexpected confirmation loop exit",
            "platform": normalized_venue,
            "symbol": raw_symbol,
        }

    def resolve_fill(self, fill_data: dict[str, Any]) -> bool:
        """Called by the Pub/Sub trade listener to resolve a pending confirmation.

        Returns True if a matching pending confirmation was resolved.
        """
        venue = str(fill_data.get("platform") or fill_data.get("venue") or "").strip().upper()
        raw_symbol = str(fill_data.get("symbol") or "").strip().upper()
        # Strip quote currency for consistent matching
        match_symbol = re.sub(r"(USDT|USDC|USD|PERP)$", "", raw_symbol)

        confirm_key = (venue, match_symbol)
        future = self._pending_confirmations.pop(confirm_key, None)
        if future and not future.done():
            future.set_result(fill_data)
            logger.debug(f"🔗 Fill confirmation resolved for {confirm_key}")
            return True

        # No pending future — try to reconcile a dead-letter entry
        if self._dead_letters.reconcile(venue, match_symbol):
            logger.info(f"🔗 Dead-letter reconciled for {venue}:{match_symbol}")
        return False

    @property
    def pending_confirmation_count(self) -> int:
        """Number of commands waiting for fill confirmation."""
        return len(self._pending_confirmations)

    @property
    def dead_letters(self) -> UnconfirmedFillTracker:
        return self._dead_letters

    @property
    def rate_limiter(self) -> VenueRateLimiter:
        return self._rate_limiter

    def get_hardening_status(self) -> dict[str, Any]:
        """Return combined rate-limit + dead-letter status for APIs/Telegram."""
        return {
            "rate_limiter": self._rate_limiter.get_status(),
            "dead_letters": {
                "total": len(self._dead_letters._entries),
                "unreconciled": self._dead_letters.unreconciled_count,
                "recent": [
                    {
                        "venue": e["venue"],
                        "symbol": e["symbol"],
                        "side": e["side"],
                        "age_seconds": round(time.time() - e["dispatched_at"], 1),
                        "reconciled": e["reconciled"],
                    }
                    for e in self._dead_letters.get_all(limit=10)
                ],
            },
            "pending_confirmations": self.pending_confirmation_count,
        }


# Singleton
dispatcher = ExecutionDispatcher()
