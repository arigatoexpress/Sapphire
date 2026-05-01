# megaeth-ingest

Real-time MegaETH (Ethereum L2, ~10ms blocks) ingestion. Subscribes to `newHeads`
and (optionally) filtered `logs` over WSS, batches events through a bounded
async queue, and forwards to the Sapphire signal-logger at
`http://127.0.0.1:18081/api/signals`.

## Why batched + queued

MegaETH ships ~100x more new-head events per minute than Ethereum L1. A
synchronous POST per block backpressures the WS reader. This service uses a
bounded `asyncio.Queue` and a worker task — slow signal-logger drops the
oldest pending events instead of blocking the WS.

## Read-only + gated

- `SAPPHIRE_MEGAETH_INGEST_ENABLED` defaults to `0` (forwarder disabled, WS still
  runs so reconnect logic stays warm).
- Killswitch file `~/.sapphire/megaeth_ingest_pause` instantly suspends
  forwarding. Healthcheck surfaces `paused: true`.
- LaunchAgent plist is shipped but **not** auto-loaded. Operator activates.

## Files

| Path | Role |
|------|------|
| `src/megaeth_ingest/main.py` | Entrypoint, signal handlers |
| `src/megaeth_ingest/config.py` | Env + YAML config loading |
| `src/megaeth_ingest/ws_client.py` | WSS subscriber + reconnect loop |
| `src/megaeth_ingest/forwarder.py` | Bounded queue + signal-logger POST worker |
| `src/megaeth_ingest/health.py` | aiohttp `/health` endpoint |
| `launchagent/com.sapphire.megaeth-ingest.plist` | macOS LaunchAgent template |

See `README.md` for activation runbook.
