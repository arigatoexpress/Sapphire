"""
Firestore-backed execution idempotency guard.

Prevents duplicate trade execution when:
  • Pub/Sub redelivers a message after a bot crash/restart (main risk)
  • A bot instance restarts mid-execution and the signal TTL hasn't expired
  • Future: multiple bot replicas racing on the same signal

Memory-first for speed (O(1) hot-path), Firestore as durable backing store.

Firestore collection: ``signal_executions``
Document ID:         ``{signal_id}_{platform}``  (sanitized — no slashes)

Document fields:
  signal_id    str      Originating TradeSignal ID
  platform     str      "lighter" | "aster" | …
  status       str      "executing" | "executed" | "failed"
  symbol       str
  order_id     str      Filled in on completion (may be empty)
  created_at   datetime
  expires_at   datetime Created_at + TTL (informational; use Firestore TTL policy to purge)
"""

import logging
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_COLLECTION = "signal_executions"
_DEFAULT_TTL_SECONDS = 900  # 15 min — matches in-memory dedupe window


class ExecutionIdempotency:
    """
    Two-layer idempotency guard: in-memory (fast) + Firestore (durable).

    The Firestore write uses `create()` which raises ``AlreadyExists`` if the
    document already exists — giving atomic check-and-claim semantics without
    a separate read.

    Gracefully degrades to memory-only if Firestore is unavailable.
    """

    def __init__(
        self,
        platform: str,
        firestore_client=None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self.platform = platform
        self._db = firestore_client
        self._ttl_seconds = ttl_seconds
        # Fast in-memory cache: signal_id → unix timestamp of claim
        self._cache: dict[str, float] = {}

    # ── Public API ────────────────────────────────────────────────────

    async def claim(self, signal_id: str, symbol: str) -> bool:
        """
        Attempt to claim exclusive execution rights for *signal_id*.

        Returns True  → caller should proceed with trade execution.
        Returns False → duplicate; caller should skip.
        """
        self._evict_stale()

        # Fast path: already in memory
        if signal_id in self._cache:
            logger.warning(
                "🔁 Idempotency[%s]: duplicate signal skipped (memory): %s",
                self.platform,
                signal_id,
            )
            return False

        # Durable path: try to claim in Firestore
        if self._db is not None:
            claimed = await self._firestore_claim(signal_id, symbol)
            if not claimed:
                logger.warning(
                    "🔁 Idempotency[%s]: duplicate signal skipped (Firestore): %s",
                    self.platform,
                    signal_id,
                )
                return False

        # Claimed — record in memory
        self._cache[signal_id] = time.time()
        return True

    async def mark_executed(self, signal_id: str, order_id: str = "") -> None:
        """Update Firestore status to 'executed' after a successful trade."""
        if self._db is None:
            return
        try:
            doc_ref = self._db.collection(_COLLECTION).document(
                self._doc_id(signal_id)
            )
            await doc_ref.update(
                {"status": "executed", "order_id": order_id}
            )
        except Exception as exc:
            logger.debug(
                "Idempotency[%s]: could not mark executed (%s): %s",
                self.platform,
                signal_id,
                exc,
            )

    async def mark_failed(self, signal_id: str, error: str = "") -> None:
        """Update Firestore status to 'failed' — allows retry on next delivery."""
        # Remove from memory so a legitimate retry can proceed
        self._cache.pop(signal_id, None)
        if self._db is None:
            return
        try:
            doc_ref = self._db.collection(_COLLECTION).document(
                self._doc_id(signal_id)
            )
            await doc_ref.update({"status": "failed", "error": error[:500]})
        except Exception as exc:
            logger.debug(
                "Idempotency[%s]: could not mark failed (%s): %s",
                self.platform,
                signal_id,
                exc,
            )

    async def warm_from_firestore(self) -> int:
        """
        Load recent signal IDs from Firestore into memory on startup.
        Prevents re-execution of signals that fired just before a restart.
        Returns number of IDs loaded.
        """
        if self._db is None:
            return 0
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._ttl_seconds)
            # Use FieldFilter keyword form (Firestore SDK ≥ 2.11) to avoid
            # positional-argument deprecation warnings; fall back for older SDKs.
            try:
                from google.cloud.firestore_v1.base_query import FieldFilter as _FF
                query = (
                    self._db.collection(_COLLECTION)
                    .where(filter=_FF("platform", "==", self.platform))
                    .where(filter=_FF("status", "==", "executed"))
                    .where(filter=_FF("created_at", ">=", cutoff))
                )
            except ImportError:  # older Firestore SDK (<2.11)
                query = (
                    self._db.collection(_COLLECTION)
                    .where("platform", "==", self.platform)
                    .where("status", "==", "executed")
                    .where("created_at", ">=", cutoff)
                )
            docs = query.stream()
            count = 0
            async for doc in docs:
                data = doc.to_dict() or {}
                sid = data.get("signal_id", "")
                if sid:
                    self._cache[sid] = time.time()
                    count += 1
            if count:
                logger.info(
                    "Idempotency[%s]: warmed %d recent signal IDs from Firestore",
                    self.platform,
                    count,
                )
            return count
        except Exception as exc:
            logger.warning(
                "Idempotency[%s]: could not warm cache from Firestore: %s",
                self.platform,
                exc,
            )
            return 0

    # ── Internals ─────────────────────────────────────────────────────

    async def _firestore_claim(self, signal_id: str, symbol: str) -> bool:
        """
        Atomically create the idempotency doc.
        Returns True if created (caller can proceed), False if already exists.
        """
        try:
            from google.api_core.exceptions import AlreadyExists
        except ImportError:
            # Firestore not available — degrade gracefully
            return True

        now = datetime.now(timezone.utc)
        doc_ref = self._db.collection(_COLLECTION).document(self._doc_id(signal_id))
        try:
            await doc_ref.create(
                {
                    "signal_id": signal_id,
                    "platform": self.platform,
                    "symbol": symbol,
                    "status": "executing",
                    "order_id": "",
                    "created_at": now,
                    "expires_at": now + timedelta(seconds=self._ttl_seconds),
                }
            )
            return True
        except AlreadyExists:
            return False
        except Exception as exc:
            # Network error, quota, etc. — fail open (allow execution)
            # to avoid blocking trades on infrastructure issues.
            logger.warning(
                "Idempotency[%s]: Firestore claim error (failing open): %s",
                self.platform,
                exc,
            )
            return True

    def _doc_id(self, signal_id: str) -> str:
        """Sanitize signal_id + platform into a valid Firestore document ID."""
        safe = signal_id.replace("/", "_").replace(".", "_")[:150]
        return f"{safe}_{self.platform}"

    def _evict_stale(self) -> None:
        cutoff = time.time() - self._ttl_seconds
        stale = [k for k, ts in self._cache.items() if ts < cutoff]
        for k in stale:
            self._cache.pop(k, None)
