# Lighter Reliability Gate

This gate enforces objective production health checks for the `lighter` runtime using Firestore telemetry.

Script:

- `/Users/aribs/Sapphire/scripts/run_lighter_reliability_gate.py`

## What It Checks

1. Freshness
- `equity_snapshots_current/lighter.balance_sync_age_sec`
- `equity_snapshots_current/lighter.position_check_age_sec`
- stale flags: `balance_sync_stale`, `position_check_stale`

2. Risk posture
- `drawdown_pct`
- `position_notional_usd`
- `positions_count`
- cross-check with `live_positions/lighter.position_count`

3. Execution quality (lookback window)
- success rate from `execution_verifications`
- real fills count (`filled_quantity > 0`)
- restricted-jurisdiction errors (warn by default, optional hard-fail)

## Default CI thresholds

Configured in `/Users/aribs/Sapphire/.github/workflows/ci.yml`:

- max balance age: `1200s`
- max position age: `1200s`
- max drawdown: `-10%`
- max position notional: `$8`
- max open positions: `1`
- min success rate (24h): `0.40`
- min real fills (24h): `0`
- restricted jurisdiction errors: warning (not hard fail)

## Local run

```bash
cd /Users/aribs/Sapphire
python3 ./scripts/run_lighter_reliability_gate.py \
  --project sapphire-479610 \
  --platform lighter \
  --lookback-hours 24
```

## Strict mode

To fail on jurisdiction errors:

```bash
python3 ./scripts/run_lighter_reliability_gate.py \
  --project sapphire-479610 \
  --platform lighter \
  --strict-jurisdiction
```

## Control-Plane Lane Guard (sapphirectl)

`/Users/aribs/Sapphire/scripts/sapphirectl.py` now runs a pre-test lane health check before canary/live test execution:

- looks back recent `execution_verifications` for restricted-jurisdiction failures
- marks lane unhealthy when restrictions are present and no successful real fill happened after the latest restriction
- records lane snapshot in Firestore: `execution_lane_health/lighter`

If lane is unhealthy, test execution is skipped and apply returns failed with `test.cmd=["lane-health-check"]`.

Bypass only when intentionally forcing a test:

```bash
python3 /Users/aribs/Sapphire/scripts/sapphirectl.py promote --to canary --skip-lane-health-check
```

### Auto failover hosts

Control plane can automatically fail over to a backup execution host when the requested lane is unhealthy.

Set (or use the committed default at `/Users/aribs/Sapphire/configs/controlplane/sapphirectl.env`):

```bash
export SAPPHIRECTL_FAILOVER_HOSTS="rari@100.87.225.89,rari@100.120.191.1"
```

`sapphirectl` auto-loads env defaults from:

```bash
/Users/aribs/Sapphire/configs/controlplane/sapphirectl.env
```

Behavior:
- requested host stays primary;
- if primary lane is unhealthy and `run_test=true`, `sapphirectl` probes failover hosts for runtime health (`/health` on local gateway);
- first healthy fallback host with trading enabled (`TRADING_ENABLED=1` and `ALLOW_LIVE_TRADING=1`) is selected and recorded in `applied.selected_target_host` and `applied.lane_decision`.
- when fallback is selected, primary host is automatically disarmed (`TRADING_ENABLED=0`, `ALLOW_LIVE_TRADING=0`) before deploy/test to avoid duplicate execution lanes.

Validate failover selection without deploy/restart:

```bash
SAPPHIRECTL_FAILOVER_HOSTS="rari@100.87.225.89,rari@100.120.191.1" \
python3 /Users/aribs/Sapphire/scripts/sapphirectl.py lane-check --target-host rari@100.87.225.89
```

Standby host requirement:
- the standby host must run `lighter-trading` so `/health` on `127.0.0.1:8080` is reachable;
- keep standby safe by default with `TRADING_ENABLED=0` and `ALLOW_LIVE_TRADING=0` until a failover apply explicitly promotes it.

Disable failover for a command:

```bash
python3 /Users/aribs/Sapphire/scripts/sapphirectl.py promote --to canary --disable-auto-failover
```
