# Control Plane Runbook

Last reviewed: 2026-04-29

This runbook covers `services/control-plane/` and
`com.sapphire.control-plane`, the local-first FastAPI service that backs the
Sapphire project board, task queue, event stream, router overview, Kimi PM
bridge, and Telegram webhook intake.

The control plane is coordination infrastructure. It may create or mutate local
tasks, but it must not authorize trading, send Telegram test messages, rotate
secrets, or bypass the operator's no-spend posture. Mutation routes fail closed
when `CONTROL_PLANE_TOKEN` is absent.

## Ownership

| Item | Path |
|---|---|
| Service | `services/control-plane/` |
| FastAPI app | `services/control-plane/app/main.py` |
| Settings | `services/control-plane/app/config.py` |
| Store backend | `services/control-plane/app/control_plane_backend.py` |
| Kimi bridge | `services/control-plane/app/kimi_bridge.py` |
| Event stream | `services/control-plane/app/event_stream.py` |
| LaunchAgent | `infra/launchagents/com.sapphire.control-plane.plist` |
| Stdout log | `/Users/aribs/autonomy-status/logs/control_plane.log` |
| Stderr log | `/Users/aribs/autonomy-status/logs/control_plane.err` |
| Default local URL | `http://127.0.0.1:8082` |

## Surface Map

Read-only pages and APIs:

| Surface | Purpose |
|---|---|
| `/health` | Runtime mode, store kind, revision, and status. |
| `/projects` | Operator project board shell. |
| `/organization` | Local organization and workspace overview. |
| `/architecture` | Runtime topology and queue routability. |
| `/logbook` | Event timeline, decisions, handoffs, incidents, and verifications. |
| `/status` | Health-focused frontend view. |
| `/api/projects/overview` | Project inventory plus control-plane summary. |
| `/api/control/overview` | Task queue, executor, and event summary. |
| `/api/router/overview` | Local executor membership and quota shape. |

Mutation APIs:

| Surface | Gate |
|---|---|
| `/api/control/tasks` | `X-Control-Token` header. |
| `/api/control/tasks/{task_id}` | `X-Control-Token` header. |
| `/api/control/tasks/lease` | `X-Control-Token` header. |
| `/api/control/tasks/{task_id}/complete` | `X-Control-Token` header. |
| `/api/control/tasks/{task_id}/fail` | `X-Control-Token` header. |
| `/api/kimi/pm` write actions | Kimi bridge token verification. |
| `/telegram/webhook` | `TELEGRAM_WEBHOOK_SECRET` when configured. |

## Normal Operation

Check launchd:

```bash
launchctl list com.sapphire.control-plane
```

Check health without using credentials:

```bash
curl -fsS http://127.0.0.1:8082/health | python3 -m json.tool
```

Expected shape:

```json
{
  "status": "ok",
  "service": "sapphire-control-plane",
  "runtime_mode": "local",
  "store": "memory",
  "revision": "local"
}
```

Inspect logs:

```bash
tail -n 200 /Users/aribs/autonomy-status/logs/control_plane.log
tail -n 200 /Users/aribs/autonomy-status/logs/control_plane.err
```

Read the queue without mutation:

```bash
curl -fsS http://127.0.0.1:8082/api/control/overview | python3 -m json.tool
```

Exercise the fail-closed token gate without changing state:

```bash
curl -sS -o /tmp/control-plane-create.out -w '%{http_code}\n' \
  -H 'Content-Type: application/json' \
  -d '{"title":"dry run should not create without token"}' \
  http://127.0.0.1:8082/api/control/tasks
cat /tmp/control-plane-create.out
```

The expected result is `503` when no token is configured, or `403` when a token
is configured but the request is missing or invalid. A `200` here means the
write gate has regressed and must be treated as a release blocker.

## Token Handling

The service resolves the control token from
`CONTROL_PLANE_SHARED_TOKEN` or `CONTROL_PLANE_TOKEN`. Do not print the token.
When an operator needs to perform a real local task mutation, load the token
from the approved secret file or shell session and pass only the header:

```bash
curl -fsS \
  -H "X-Control-Token: $CONTROL_PLANE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"operator-approved task","created_by":"operator"}' \
  http://127.0.0.1:8082/api/control/tasks | python3 -m json.tool
```

Use the mutation command only for operator-approved queue work. Do not create
tasks that authorize live trading, Telegram sends, cloud writes, or credential
rotation.

## Store Backends

Local LaunchAgent configuration currently sets `USE_IN_MEMORY_STORE=true`.
That is acceptable for dashboard coordination and operator-visible status, but
it means a process restart clears in-memory task state. The durable task store
lives behind `AGENTIC_CONTROL_PLANE_STORE_BACKEND=sqlite` or the gated
Postgres path in `control_plane_backend.py`.

For durable local testing:

```bash
AGENTIC_CONTROL_PLANE_STORE_BACKEND=sqlite \
AGENTIC_CONTROL_PLANE_DB_PATH=/tmp/sapphire-control-plane.db \
CONTROL_PLANE_TOKEN=local-test-token \
uvicorn app.main:app --host 127.0.0.1 --port 8082
```

The Postgres path is experimental and requires
`AGENTIC_CONTROL_PLANE_STORE_POSTGRES_EXPERIMENTAL=true`; do not enable it in
the LaunchAgent without a dedicated migration PR and rollback note.

## Kimi Bridge

The Kimi bridge at `/api/kimi/pm` supports read actions such as `overview`,
`list_tasks`, `list_agents`, `get_task`, and `list_events`. Write actions such
as `create_task`, `update_task`, `sync_board`, `cleanup_stale_agents`, and
`set_executor_policy` require a valid control token.

Smoke a read action:

```bash
curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"action":"overview"}' \
  http://127.0.0.1:8082/api/kimi/pm | python3 -m json.tool
```

Smoke a write denial:

```bash
curl -sS -o /tmp/kimi-write-denied.out -w '%{http_code}\n' \
  -H 'Content-Type: application/json' \
  -d '{"action":"create_task","title":"should be denied"}' \
  http://127.0.0.1:8082/api/kimi/pm
cat /tmp/kimi-write-denied.out
```

Expected result: non-`200` with an unauthorized error unless the operator
provided a valid `X-Control-Token` header.

## Common Failures

### Health Returns Nothing

1. Check launchd status.
2. Read stderr for import or port-bind failures.
3. Confirm no other process owns port 8082:

   ```bash
   lsof -nP -iTCP:8082 -sTCP:LISTEN
   ```

4. If the LaunchAgent is loaded but wedged, use `launchctl kickstart` only
   after saving the last 200 log lines.

### Mutation Route Returns 503

This is usually correct: the token is not configured, so the control plane
refuses writes. Set `CONTROL_PLANE_TOKEN` only in the approved LaunchAgent or
operator shell. Do not weaken `_require_control_token`.

### Queue Looks Stalled

Open `/api/control/overview` and inspect `queue_routability`. If queued tasks
exist but no executor is eligible, check runtime policy and registered agent
capabilities. Do not mark tasks completed manually unless the executor actually
finished the work.

### Telegram Webhook Returns 403

`TELEGRAM_WEBHOOK_SECRET` is configured and the incoming header did not match.
This is a good failure. Confirm the secret at the Telegram webhook registration
side; do not log or paste the secret.

## Safety Notes

- Read-only endpoints may be used for dashboards and readiness checks.
- Write endpoints require `X-Control-Token`; never add token bypasses for local
  convenience.
- Telegram webhook tests must stay synthetic unless the operator explicitly
  asks for a live send or live webhook mutation.
- Task creation is not trade approval. Trading routes still require their own
  risk kernel, confirmation firewall, and kill switch gates.
- Do not enable Postgres or Cloud SQL in the LaunchAgent without a reviewed
  migration and rollback path.
- Do not store the control token in repo files, plist literals, screenshots, or
  issue comments.

## Escalation

Escalate when:

- `/health` is unavailable for more than one restart attempt.
- A mutation route returns `200` without a valid `X-Control-Token`.
- Queue routability reports work but no eligible executor for more than one
  operating window.
- The Kimi bridge accepts a write action without a valid token.
- The Telegram webhook accepts mismatched secrets.

Include the health payload, `launchctl list` output, last 200 stdout/stderr
lines, the exact endpoint path, and whether the command was read-only or a
token-gated mutation.
