import asyncio
import json
import os
from typing import Any

import requests
import websockets

# Configuration via environment variables
SUI_WS_URL = os.getenv("SUI_WS_URL", "wss://fullnode.mainnet.sui.io:443")
EVENT_TYPE = os.getenv("MOVE_EVENT_TYPE")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if EVENT_TYPE is None:
    raise SystemExit("MOVE_EVENT_TYPE environment variable not set")

async def send_alert(event: Any) -> None:
    """Send event data to a webhook if configured."""
    if not WEBHOOK_URL:
        print("Webhook not configured; event:\n", json.dumps(event, indent=2))
        return
    try:
        resp = requests.post(WEBHOOK_URL, json=event, timeout=10)
        resp.raise_for_status()
        print(f"Alert delivered: {resp.status_code}")
    except Exception as exc:
        print(f"Failed to deliver alert: {exc}")

async def listen() -> None:
    """Subscribe to Move event type and forward events."""
    filter_payload = {"MoveEventType": EVENT_TYPE}
    sub_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "suix_subscribeEvent",
        "params": [filter_payload],
    }

    async with websockets.connect(SUI_WS_URL) as ws:
        await ws.send(json.dumps(sub_msg))
        raw = await ws.recv()
        resp = json.loads(raw)
        sub_id = resp.get("result")
        if not sub_id:
            raise RuntimeError(f"Subscription failed: {resp}")
        print(f"Subscribed with id {sub_id} for {EVENT_TYPE}")
        while True:
            msg = await ws.recv()
            event = json.loads(msg)
            await send_alert(event)

if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("Exiting")
