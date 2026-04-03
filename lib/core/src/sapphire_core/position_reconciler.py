"""
Position reconciliation cron.

Detects drift between what Sapphire's venue bots believe they hold and what
was last durably recorded in Firestore.  Fires Telegram alerts on mismatch.

Architecture
------------
* Bots write a position snapshot to Firestore ``live_positions/{platform}``
  on every ``_position_publish_loop`` tick (every ~10 s).
* Alpha-engine subscribes to the ``position-updates`` Pub/Sub topic, calling
  ``handle_position_update()`` on each message to keep an in-memory snapshot.
* ``run_forever()`` wakes up every ``reconcile_interval`` seconds and calls
  ``run_check()``, which:
    1. Checks every known platform for stale Pub/Sub updates.
    2. Reads Firestore ``live_positions`` and compares position counts against
       the in-memory snapshot.
  Drift descriptions are returned so the caller can alert (e.g. Telegram).

Graceful degradation
--------------------
If Firestore is unavailable the reconciler logs a warning and skips the
Firestore comparison pass — Pub/Sub staleness detection still works.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_COLLECTION = "live_positions"


class PositionReconciler:
    """
    Two-signal reconciler: Pub/Sub freshness + Firestore vs in-memory diff.

    Parameters
    ----------
    firestore_client:
        Async Firestore client (``google.cloud.firestore_v1.AsyncClient``).
        Pass ``None`` to run in Pub/Sub-only mode (no Firestore comparison).
    stale_threshold_seconds:
        How long a platform may go without a Pub/Sub update before being
        flagged as stale.  Default: 120 s (2 min — twice the publish interval).
    reconcile_interval:
        How often to run a full reconciliation pass.  Default: 900 s (15 min).
    """

    def __init__(
        self,
        firestore_client=None,
        *,
        stale_threshold_seconds: int = 120,
        reconcile_interval: int = 900,
    ) -> None:
        self._db = firestore_client
        self._stale_threshold = stale_threshold_seconds
        self._reconcile_interval = reconcile_interval
        # platform → {received_at: float, count: int, positions: list}
        self._snapshots: dict[str, dict] = {}

    # ── Pub/Sub feed ──────────────────────────────────────────────────

    def handle_position_update(self, data: dict) -> None:
        """
        Update the in-memory snapshot for a platform.

        Call this from the alpha-engine's ``position-updates`` Pub/Sub handler.
        Thread-safe for asyncio single-threaded use.
        """
        platform = str(data.get("platform", "")).strip()
        if not platform:
            return
        positions = data.get("positions", [])
        self._snapshots[platform] = {
            "received_at": time.monotonic(),
            "count": len(positions),
            "positions": positions,
        }
        logger.debug(
            "PositionReconciler: updated snapshot for %s (%d positions)",
            platform,
            len(positions),
        )

    # ── Reconciliation logic ─────────────────────────────────────────

    async def run_check(self) -> list[str]:
        """
        Run one reconciliation pass.

        Returns
        -------
        list[str]
            Human-readable drift descriptions (empty list = all clear).
        """
        drifts: list[str] = []
        now = time.monotonic()

        # ── 1. Pub/Sub freshness check ─────────────────────────────
        for platform, snap in list(self._snapshots.items()):
            age_seconds = now - snap["received_at"]
            count = snap["count"]
            if count > 0 and age_seconds > self._stale_threshold:
                drifts.append(
                    f"📡 **{platform}** position updates stale for "
                    f"{age_seconds / 60:.1f} min "
                    f"({count} position(s) last known) — bot may be DOWN or "
                    f"``_position_publish_loop`` has stopped."
                )
                logger.warning(
                    "PositionReconciler: stale updates from %s (%.0fs ago, %d pos)",
                    platform,
                    age_seconds,
                    count,
                )

        # ── 2. Firestore vs in-memory diff ────────────────────────
        if self._db is None:
            return drifts

        try:
            docs = self._db.collection(_COLLECTION).stream()
            async for doc in docs:
                data = doc.to_dict() or {}
                platform = str(data.get("platform", doc.id)).strip()
                fs_count: int = int(data.get("position_count", 0))

                snap = self._snapshots.get(platform)

                if snap is None:
                    # Never received a Pub/Sub update for this platform
                    if fs_count > 0:
                        drifts.append(
                            f"🔴 **{platform}** Firestore shows {fs_count} "
                            f"position(s) but *no Pub/Sub updates received* — "
                            f"bot may never have started or crashed early."
                        )
                        logger.error(
                            "PositionReconciler: %s has %d Firestore positions "
                            "but zero Pub/Sub updates",
                            platform,
                            fs_count,
                        )
                else:
                    mem_count = snap["count"]
                    if abs(fs_count - mem_count) > 0:
                        drifts.append(
                            f"⚠️ **{platform}** position count drift — "
                            f"Firestore: {fs_count}, live (Pub/Sub): {mem_count}. "
                            f"Check for missed fills or un-persisted closures."
                        )
                        logger.warning(
                            "PositionReconciler: %s count mismatch fs=%d mem=%d",
                            platform,
                            fs_count,
                            mem_count,
                        )

        except Exception as exc:
            # Non-critical: Firestore pass fails → log only, still return staleness drifts
            logger.warning(
                "PositionReconciler: Firestore read error (skipping diff pass): %s",
                exc,
            )

        return drifts

    # ── Long-running cron ─────────────────────────────────────────────

    async def run_forever(
        self,
        on_drift: Callable[[str], Awaitable[None]],
    ) -> None:
        """
        Infinite reconciliation loop.

        Parameters
        ----------
        on_drift:
            Async callback invoked once per drift description string.
            Typically ``lambda msg: telegram.send_message(msg, priority="high")``.
        """
        logger.info(
            "PositionReconciler: starting (interval=%ds, stale_threshold=%ds)",
            self._reconcile_interval,
            self._stale_threshold,
        )

        # Initial delay before first check (let bots start publishing first).
        await asyncio.sleep(min(120, self._reconcile_interval))

        while True:
            try:
                drifts = await self.run_check()
                if not drifts:
                    logger.debug("PositionReconciler: all clear")
                for drift_msg in drifts:
                    try:
                        await on_drift(drift_msg)
                    except Exception as cb_exc:
                        logger.warning(
                            "PositionReconciler: on_drift callback error: %s", cb_exc
                        )
            except Exception as exc:
                logger.error("PositionReconciler: unexpected error: %s", exc)

            await asyncio.sleep(self._reconcile_interval)

    # ── Introspection ─────────────────────────────────────────────────

    def status(self) -> dict:
        """Return current reconciler state for health/debug endpoints."""
        now = time.monotonic()
        return {
            "platforms": {
                platform: {
                    "position_count": snap["count"],
                    "seconds_since_update": round(now - snap["received_at"], 1),
                }
                for platform, snap in self._snapshots.items()
            },
            "stale_threshold_seconds": self._stale_threshold,
            "reconcile_interval_seconds": self._reconcile_interval,
        }
