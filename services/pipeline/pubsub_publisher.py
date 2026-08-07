"""Pub/Sub publisher for real-time Sapphire events.

Each topic has a BigQuery subscription that auto-inserts messages into the
matching table (see infra/gcp/bootstrap_pubsub.sh). Message payloads MUST
match the BQ table schema (extra fields are dropped).

Publishers are best-effort: if Pub/Sub is unreachable, we log and move on —
the hourly batch sync (gcp_sync.py) will still catch the event from local
JSONL files. This keeps the trading pipeline from stalling on GCP outages.

Usage:
    from services.pipeline.pubsub_publisher import publish_signal, publish_regime
    publish_signal({"signal_id": ..., "symbol": ..., ...})
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

PROJECT = os.environ.get("GCP_PROJECT", "sapphire-479610")
ENABLED = os.environ.get("SAPPHIRE_PUBSUB", "1") == "1"

TOPICS = {
    "signals": "sapphire-signals",
    "regime": "sapphire-regime-changes",
    "predictions": "sapphire-predictions",
    "threats": "sapphire-threats",
    "alerts": "sapphire-alerts",
}


# ---------------------------------------------------------------------------
# Lazy client — avoids import of google-cloud-pubsub when SAPPHIRE_PUBSUB=0
# ---------------------------------------------------------------------------

_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            try:
                from google.cloud import pubsub_v1

                _client = pubsub_v1.PublisherClient()
            except Exception as e:
                log.warning("pubsub client init failed: %s", e)
                _client = False
    return _client or None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def publish(kind: str, payload: dict[str, Any]) -> bool:
    """Publish a dict to the topic for `kind`. Returns True on enqueue success."""
    if not ENABLED:
        return False
    topic = TOPICS.get(kind)
    if not topic:
        log.warning("unknown pubsub kind: %s", kind)
        return False

    client = _get_client()
    if not client:
        return False

    # Ensure ingested_at is always present
    payload.setdefault("ingested_at", _now_iso())

    topic_path = f"projects/{PROJECT}/topics/{topic}"
    try:
        future = client.publish(topic_path, json.dumps(payload, default=str).encode("utf-8"))
        future.add_done_callback(lambda f: _log_result(kind, f))
        return True
    except Exception as e:
        log.warning("pubsub publish failed (%s): %s", kind, e)
        return False


def _log_result(kind: str, future) -> None:
    try:
        future.result(timeout=5.0)
    except Exception as e:
        log.warning("pubsub %s future failed: %s", kind, e)


# ---------------------------------------------------------------------------
# Convenience wrappers matching the BQ schemas
# ---------------------------------------------------------------------------


def publish_signal(row: dict) -> bool:
    return publish("signals", row)


def publish_regime(row: dict) -> bool:
    return publish("regime", row)


def publish_prediction(row: dict) -> bool:
    return publish("predictions", row)


def publish_threat(row: dict) -> bool:
    return publish("threats", row)


def publish_alert(row: dict) -> bool:
    return publish("alerts", row)


if __name__ == "__main__":
    # Smoke test: publish a single regime snapshot
    logging.basicConfig(level=logging.INFO)
    now = _now_iso()
    ok = publish_regime(
        {
            "snapshot_id": f"smoke-{int(datetime.now().timestamp())}",
            "regime": "TRANSITION",
            "score": 0.05,
            "confidence": 0.3,
            "reasoning": ["pubsub smoke test"],
            "btc_price_usd": 77000.0,
            "btc_dominance": 57.3,
            "timestamp": now,
            "ingested_at": now,
        }
    )
    print("published:", ok)
