# OpenBB API Runbook

Last reviewed: 2026-04-30

## Triage Quickstart

Failure mode addressed: the OpenBB compatibility API on `127.0.0.1:6900` is
unreachable, returning errors, or a downstream dashboard reports stale data.

```bash
launchctl list com.sapphire.openbb-api
```

```bash
curl -fsS http://127.0.0.1:6900/api/v1/openbb/providers | python3 -m json.tool
```

```bash
tail -n 100 /Users/aribs/autonomy-status/logs/openbb_api.err
```

If the providers route returns HTTP 200 with a non-empty list, the daemon is
healthy; the failure is on a specific provider route, not the daemon. If the
TCP port is closed, jump to `TCP Port Is Closed`.

Live monitors: `/readiness` matrix; production-readiness sweep TCP probe on
`127.0.0.1:6900`.
On-call escalation: data/intel owner; p3 unless dashboard pages are degraded,
then p2.

This runbook covers the local OpenBB compatibility REST API launched by
`infra/launchagents/com.sapphire.openbb-api.plist` on `127.0.0.1:6900`.

The service is a local market-data compatibility wrapper. It should be treated
as read-mostly infrastructure for research and status probes. It must not place
orders, mutate brokerage accounts, or become a hidden live-trading path.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.openbb-api.plist` |
| FastAPI wrapper | `services/openbb_api/server.py` |
| Launch command | `python3 -m uvicorn services.openbb_api.server:app --host 127.0.0.1 --port 6900` |
| Stdout | `/Users/aribs/autonomy-status/logs/openbb_api.log` |
| Stderr | `/Users/aribs/autonomy-status/logs/openbb_api.err` |
| Health probe used by readiness sweep | TCP check on `127.0.0.1:6900` |

## What It Serves

`services/openbb_api/server.py` imports the OpenBB REST app from
`openbb_core.api.rest_api` and adds one Sapphire-specific helper route:

```text
GET /api/v1/openbb/providers
```

That route returns the provider names from OpenBB's command map and is safe for
local health checks. Other `/api/v1/...` routes are OpenBB's REST surface and
may require provider-specific dependencies or network access depending on the
request.

## Normal Operation

Check launchd:

```bash
launchctl list com.sapphire.openbb-api
```

Probe the local wrapper route:

```bash
curl -fsS http://127.0.0.1:6900/api/v1/openbb/providers | python3 -m json.tool
```

Check logs:

```bash
tail -n 100 /Users/aribs/autonomy-status/logs/openbb_api.log
tail -n 100 /Users/aribs/autonomy-status/logs/openbb_api.err
```

Check the port without invoking a provider:

```bash
python3 - <<'PY'
import socket
with socket.create_connection(("127.0.0.1", 6900), timeout=3):
    print("openbb-api tcp ok")
PY
```

## Common Failures

### TCP Port Is Closed

1. Confirm launchd state:

   ```bash
   launchctl list com.sapphire.openbb-api
   ```

2. Read stderr for missing OpenBB imports or Python-version mismatch:

   ```bash
   tail -n 200 /Users/aribs/autonomy-status/logs/openbb_api.err
   ```

3. Confirm the plist still points at the intended Python interpreter and
   canonical checkout:

   ```bash
   plutil -p infra/launchagents/com.sapphire.openbb-api.plist
   ```

4. Restart only after reading the failure:

   ```bash
   launchctl kickstart -k gui/$(id -u)/com.sapphire.openbb-api
   ```

### Provider Route Fails But Port Is Open

The service can be healthy while a provider-specific OpenBB command fails. Do
not treat a single data-provider error as a daemon outage. Check:

- Whether the route uses a provider requiring credentials.
- Whether the provider is temporarily unavailable.
- Whether the request triggered an optional dependency path.

The readiness sweep intentionally uses a TCP check so production readiness is
not blocked by a third-party market-data provider.

### OpenBB Package Generation Breaks

Do not regenerate or vendor OpenBB packages inside Sapphire during incident
response. The Sapphire wrapper is intentionally thin; fix dependency drift in a
dedicated PR with local tests and rollback notes.

## Safety Notes

- Bind to `127.0.0.1` only.
- Do not expose this service publicly.
- Do not add order-execution routes to this compatibility API.
- Do not commit provider credentials, `.env` files, or logs.
- Prefer the local TCP/provider-list probes for health; provider-specific quote
  calls can be noisy and network-dependent.

## Escalation

Escalate when:

- The service fails to boot after a plist kickstart.
- OpenBB imports fail after a dependency update.
- A downstream dashboard depends on a provider route that has changed shape.

Include the exact route, HTTP status, stderr excerpt, Python interpreter from
the plist, and the latest production-readiness OpenBB check result.
