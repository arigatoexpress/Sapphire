# Sapphire System Failover

This runbook is for the expected case where the Windows GPU machine is offline
but Sapphire should keep operating through Mac-local inference, optional Pi
tiers, and Cloud Run services.

## Current Contract

The local inference proxy exposes:

- `GET /health` for the legacy tier health payload.
- `GET /failover/status` for the operator failover contract.
- `GET /metrics` for per-tier request counters.

`/failover/status` treats Windows downtime as degraded, not down, when either:

- a local fallback tier is healthy: `pi-rari1`, `pi-rari2`, or `mac-local`; or
- non-sensitive cloud fallback is healthy: `kimi-cloud`.

Cloud fallback remains sensitivity-gated. Sensitive prompts must stay on local
tiers; if Windows and Mac/Pi are all unavailable, sensitive inference should
fail closed instead of leaking to cloud.

## Read-Only Checks

Local inference posture:

```bash
/usr/local/bin/python3 scripts/ops/system_failover_status.py --json
```

Local plus Cloud Run posture:

```bash
/usr/local/bin/python3 scripts/ops/system_failover_status.py --probe-gcp --json
```

Expected Windows-offline healthy-degraded state:

```json
{
  "ok": true,
  "mode": "local_failover",
  "active_route": "mac-local",
  "windows_offline": true,
  "fallback_ready": true
}
```

Strict primary-required check, useful before GPU-heavy jobs:

```bash
/usr/local/bin/python3 scripts/ops/system_failover_status.py --require-primary --json
```

This should fail while Windows is offline.

Authenticated local dashboard posture:

- `/observability` includes the System Failover panel.
- `GET /api/system-failover-status` returns the same local failover envelope
  without probing or mutating GCP.

Windows-bound dry-run work leases are also guarded. When
`/api/autonomy/continuous-intelligence/lease-preview?target_runtime=windows-gpu`
sees `windows_offline=true`, it returns zero leases with
`runtime_guard.status=blocked` until the primary tier is healthy again.

## Safe Next Steps During Windows Downtime

1. Keep GPU-only jobs paused or reroute only exact Mac-supported models.
2. Keep public/GCP surfaces running and verify with `--probe-gcp`.
3. Enable Pi tiers only after a live probe confirms the device is reachable.
4. Restart the local inference proxy after code updates:

```bash
launchctl kickstart -k gui/$(id -u)/com.sapphire.inference-proxy
```

Do not `bootout` the proxy as a first move.
