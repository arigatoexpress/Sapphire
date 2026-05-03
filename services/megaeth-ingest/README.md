# megaeth-ingest

Real-time MegaETH (Ethereum L2, ~10ms blocks via centralized sequencer)
ingestion service. Subscribes to `newHeads` and config-driven `logs` over
WSS, batches into a bounded queue, and forwards enriched events to the
Sapphire signal-logger.

**Status:** read-only, gated. LaunchAgent plist is **not** auto-loaded.
Operator activates manually after soak.

## Architecture sketch

```
  MegaETH WSS (~10ms blocks)
          │
          ▼
   MegaEthWsClient ──► reconnect w/ exp. backoff
          │              (cap = reconnect_max_sec)
          ▼
   enrich_event(timestamp, chain_id, kind, ...)
          │
          ▼
   EventForwarder.enqueue()  ◄── drop-oldest if queue full
          │                       (never blocks WS reader)
          ▼
   asyncio.Queue (queue_max = 4096)
          │
          ▼
   forwarder worker  ──► POST {signal_logger_url}/api/signals
                              + {"secret": WEBHOOK_SECRET}
```

The WS reader and forwarder worker are decoupled by the queue — that's the
core backpressure-defense for a chain whose block rate is ~100x Ethereum L1.

## Env vars

| Variable | Default | Description |
|---|---|---|
| `SAPPHIRE_MEGAETH_WSS` | `wss://carrot.megaeth.com/ws` | MegaETH testnet WSS endpoint |
| `SAPPHIRE_MEGAETH_CHAIN_ID` | `6342` | MegaETH testnet chain id (used for event enrichment) |
| `SAPPHIRE_MEGAETH_HEALTH_PORT` | `8788` | Health server bind port (loopback only) |
| `SAPPHIRE_MEGAETH_SIGNAL_LOGGER_URL` | `http://127.0.0.1:18081/api/signals` | Where ingested events are POSTed |
| `WEBHOOK_SECRET` | _empty_ | Required by signal-logger — service POSTs `{"secret": <value>, ...}` |
| `SAPPHIRE_MEGAETH_INGEST_ENABLED` | `0` | Forwarder gate. `0` = WS runs but events are dropped. |
| `SAPPHIRE_MEGAETH_QUEUE_MAX` | `4096` | Bounded queue capacity |
| `SAPPHIRE_MEGAETH_RECONNECT_BACKOFF` | `2.0` | Initial reconnect backoff seconds |
| `SAPPHIRE_MEGAETH_RECONNECT_MAX` | `60.0` | Max reconnect backoff seconds |
| `SAPPHIRE_MEGAETH_LOG_FILTERS` | _empty_ | JSON list of `{addresses, topics}` filters (alternative to YAML) |
| `SAPPHIRE_MEGAETH_KILLSWITCH` | `~/.sapphire/megaeth_ingest_pause` | Killswitch file path |
| `SAPPHIRE_MEGAETH_LOG_LEVEL` | `INFO` | Python logging level |

YAML config at `config/megaeth.yaml` is also honored. Env vars take precedence.
A starter is at `config/megaeth.yaml.example`.

## Run locally

```bash
# 1. Install deps (in the repo's venv)
pip install -r services/megaeth-ingest/requirements.txt

# 2. Soak with forwarding OFF (default) — confirm WS connects & /health populates
PYTHONPATH=services/megaeth-ingest/src:. \
  python3 -m megaeth_ingest.main

# 3. In another shell:
curl http://127.0.0.1:8788/health
# {
#   "ok": true,
#   "ws_connected": true,
#   "paused": false,
#   "forwarding_enabled": false,
#   "last_block": 12345678,
#   "lag_seconds": 0.012,
#   "chain_id": 6342,
#   "queue_size": 0,
#   "queue_max": 4096,
#   "stats": {...}
# }

# 4. Once the WS metrics look stable, enable forwarding:
SAPPHIRE_MEGAETH_INGEST_ENABLED=1 WEBHOOK_SECRET="$WEBHOOK_SECRET" \
PYTHONPATH=services/megaeth-ingest/src:. \
  python3 -m megaeth_ingest.main
```

## Healthcheck format

`GET http://127.0.0.1:8788/health` returns JSON:

```json
{
  "ok": true,
  "ws_connected": true,
  "paused": false,
  "forwarding_enabled": true,
  "last_block": 12345678,
  "last_block_at": "2026-04-30T20:14:33.012345+00:00",
  "lag_seconds": 0.012,
  "chain_id": 6342,
  "wss_url": "wss://carrot.megaeth.com/ws",
  "queue_size": 3,
  "queue_max": 4096,
  "stats": {
    "connect_attempts": 1,
    "connect_failures": 0,
    "new_heads_received": 8421,
    "logs_received": 0,
    "enqueued": 8421,
    "forwarded": 8418,
    "dropped_full_queue": 0,
    "dropped_paused": 0,
    "dropped_disabled": 0,
    "post_failures": 0,
    "last_error": null
  }
}
```

## Killswitch

```bash
# Pause forwarding (WS stays connected so reconnect logic doesn't go cold):
touch ~/.sapphire/megaeth_ingest_pause

# Resume:
rm ~/.sapphire/megaeth_ingest_pause
```

While paused: `paused: true` in `/health`, `dropped_paused` increments per
event, `forwarded` does not.

## Activation runbook (LaunchAgent)

Plist files exist at:
- `services/megaeth-ingest/launchagent/com.sapphire.megaeth-ingest.plist`
- `infra/launchagents/com.sapphire.megaeth-ingest.plist`

Neither is auto-loaded. To activate:

1. **Soak in foreground** — run the service in a terminal for 10+ minutes;
   confirm `/health` shows steady block lag <100ms and zero `connect_failures`
   bursts beyond expected reconnect cadence.
2. **Set `WEBHOOK_SECRET`** for the LaunchAgent. Either edit the plist
   in-place to add a `WEBHOOK_SECRET` key, or export it from a wrapper shell
   script that `ProgramArguments` invokes. **Do not commit the secret.**
3. **Stage the plist** —
   `cp services/megaeth-ingest/launchagent/com.sapphire.megaeth-ingest.plist \
       ~/Library/LaunchAgents/`
4. **Load** —
   `launchctl load ~/Library/LaunchAgents/com.sapphire.megaeth-ingest.plist`
5. **Verify** — `curl http://127.0.0.1:8788/health` until `ws_connected:true`.
6. **Enable forwarding** — only after step 5 is green:
   `launchctl setenv SAPPHIRE_MEGAETH_INGEST_ENABLED 1` (or edit the plist
   value to `1` and re-load).
7. **Sanity-check the signal-logger** — `tail -f data/signals/*.jsonl` should
   start showing `source: "megaeth-ingest"` rows.

To deactivate: `launchctl unload ~/Library/LaunchAgents/com.sapphire.megaeth-ingest.plist`.

## Performance notes

- Testnet `newHeads` rate is roughly one event every 10–20 ms = **50–100
  msg/sec** sustained on the public sequencer.
- `queue_max=4096` ≈ 40–80 seconds of headroom before drop-oldest engages.
- Worker uses a single long-lived `aiohttp.ClientSession` with a 5s timeout.
- Each forwarded payload is ~1–2 kB (raw block header) → ~50–200 kB/s
  outbound to signal-logger when forwarding is on.
- If you observe sustained `dropped_full_queue > 0`, signal-logger is the
  bottleneck — bump `queue_max` only as a stopgap; the real fix is to
  pre-aggregate (e.g. one event per 100 blocks) before forwarding.

## Known limits / not-yet

- Logs subscription requires `addresses` — wide-open `logs` would melt the
  queue at MegaETH's block rate. Add filters in `config/megaeth.yaml`.
- Service is not added to `dispatch.py` startup list yet (gated rollout).
- No live mainnet endpoint default — set `SAPPHIRE_MEGAETH_WSS` explicitly
  if/when MegaETH ships mainnet.
