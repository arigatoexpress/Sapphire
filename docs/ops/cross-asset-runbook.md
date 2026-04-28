# Cross-Asset Correlation Runbook

As of 2026-04-28, the cross-asset system is an offline-safe intelligence
surface. It computes rolling cross-asset correlations, deterministic regime
labels, breakdown events, and lead/lag summaries. It does not execute trades,
does not send Telegram messages, and does not require live network access in
the default path.

## Components

- `lib/cross_asset/correlation_matrix.py`: pure Pearson, Spearman, Kendall,
  rolling matrix construction, and breakdown event detection.
- `lib/cross_asset/regime_detector.py`: deterministic regime labels and
  optional one-sample transition smoothing.
- `lib/cross_asset/sources.py`: cache-first OHLCV adapters for OpenBB-like
  assets and Hyperliquid-derived assets.
- `lib/cross_asset/lead_lag.py`: lagged pair correlation ranking.
- `services/cross_asset/run.py`: one-shot or daemon loop that builds snapshots,
  writes artifacts, and optionally publishes local event-bus events.
- `services/dashboard/templates/pages/cross_asset.html`: authenticated dashboard
  page.
- `plugins/claw-sapphire/tools/internal/cross_asset_intel.py`: stdin-JSON plugin
  surface for agents.

## Safety Defaults

The default posture is cache or deterministic dry-run. A live source pull only
happens when both conditions are true:

1. The caller passes a live flag, for example `--live` or `"live": true`.
2. The environment has `SAPPHIRE_CROSS_ASSET_LIVE=1`.

If either condition is absent, the adapters read cache first and then use
deterministic synthetic OHLCV rows. This is intentional. It keeps the dashboard,
plugin, and tests useful without hidden external calls. It also prevents a
future agent from turning an intelligence panel into a silent market-data
poller.

The daemon only publishes local event-bus events when called with `--publish`.
The default `--once` run writes artifacts and exits. No route or plugin action
publishes to the event bus.

## One-Shot Operation

From the Sapphire repo or this worktree:

```bash
python3 services/cross_asset/run.py --once
```

Useful variants:

```bash
python3 services/cross_asset/run.py --once --assets BTC,ETH,SOL,SPY,QQQ,DXY
python3 services/cross_asset/run.py --once --output-root /tmp/sapphire-cross-asset
SAPPHIRE_CROSS_ASSET_LIVE=1 python3 services/cross_asset/run.py --once --live
python3 services/cross_asset/run.py --once --publish
```

Use live mode only when the local OpenBB service or other configured adapters
are expected to be reachable. Live mode is not required for tests, dashboard
smoke checks, or plugin validation.

## Daemon Operation

The daemon loop runs once per interval:

```bash
python3 services/cross_asset/run.py --interval-seconds 3600
```

In production, prefer a LaunchAgent or scheduler that calls the command with an
explicit output root and without live mode unless a separate operator decision
has enabled the market-data path. This lane intentionally does not ship or load
a LaunchAgent. If a future PR adds one, it should ship a template only and
should not call `launchctl load` from an agent script.

## Artifact Layout

The service writes to:

```text
data/cross_asset/YYYY-MM-DD/matrix.json
data/cross_asset/YYYY-MM-DD/matrix.json.envelope.json
data/cross_asset/YYYY-MM-DD/regimes.jsonl
data/cross_asset/YYYY-MM-DD/breakdowns.jsonl
data/cross_asset/YYYY-MM-DD/lead_lag.json
```

`matrix.json` contains the current multi-window matrix, source summary, and
snapshot provenance. `regimes.jsonl` appends one provenance-stamped regime row
per run. `breakdowns.jsonl` appends provenance-stamped breakdown rows. `lead_lag`
contains the latest lag ranking. The matrix sidecar is written with
`lib/core/provenance.write_envelope_sidecar`.

Do not commit generated `data/cross_asset` artifacts unless a future release
explicitly asks for checked-in fixtures. Operational data belongs in local data
or cache paths, not in product code commits.

## Dashboard

The page is `/cross-asset`. It is protected by the existing dashboard basic auth
decorator. The API endpoints are:

```text
GET /api/cross-asset-matrix?window=7d&method=pearson
GET /api/cross-asset-regime
GET /api/cross-asset-breakdowns
```

The dashboard builds a cache-first snapshot in process and caches it for 300
seconds. It does not request live mode. If the snapshot fails, the route returns
a paste-safe unavailable payload rather than leaking local paths or secrets.

When verifying the dashboard locally, set a non-weak auth password first:

```bash
AUTH_PASSWORD=test-password X402_ENABLED=0 python3 services/dashboard/app.py
```

Then authenticate through the browser or test client. Avoid credentialed URLs in
browser smoke checks; use normal browser credential handling or auth headers.

## Plugin Tool

The plugin accepts stdin JSON:

```bash
printf '{"action":"status"}' | python3 plugins/claw-sapphire/tools/cross_asset_intel.py
printf '{"action":"matrix","window":"7d","method":"spearman","assets":["BTC","ETH","SPY"]}' | python3 plugins/claw-sapphire/tools/cross_asset_intel.py
printf '{"action":"regime"}' | python3 plugins/claw-sapphire/tools/cross_asset_intel.py
printf '{"action":"breakdowns","limit":5}' | python3 plugins/claw-sapphire/tools/cross_asset_intel.py
printf '{"action":"lead-lag","limit":5}' | python3 plugins/claw-sapphire/tools/cross_asset_intel.py
```

The `status` action does not fetch sources. It reports caps, default assets,
cache root, valid actions, and the live env-gate state. Matrix/regime/breakdown
actions build a snapshot but remain cache or dry-run unless the caller requests
live mode and the env gate is present.

## Interpreting Regimes

`risk_on_correlated`: risk assets have high positive co-movement and dollar
pressure is not dominating. This is the easiest environment for broad beta
interpretations, though it does not imply a trade.

`risk_on_decorrelated`: risk assets are still somewhat positive, but dispersion
is high. Treat single-asset drivers as more important.

`risk_off_flight_to_dollar`: risk assets remain linked but move against the
dollar bloc. Watch for DXY or JPY pressure dominating crypto/equity reads.

`crisis_correlation_spike`: broad absolute correlations are high enough that
asset-specific diversification may be failing. Treat as an escalation signal for
human review and risk dashboards, not an execution instruction.

`regime_uncertain`: the honest fallback. It can mean insufficient data, mixed
evidence, stale sources, or a matrix that does not fit the deterministic rules.

## Breakdown Triage

Breakdown events are ranked by absolute z-score. Start with the top pair and
ask:

1. Is the source summary fresh enough for the pair?
2. Is the event a breakdown or a spike?
3. Does the move agree with the current regime label?
4. Is the pair important to current Sapphire theses?
5. Is this a one-snapshot anomaly or persistent across runs?

For a persistent BTC/SPY breakdown, compare the cross-asset page with the
investment-intel and sovereign-thesis pages. For a dollar-driven event, compare
with macro data before turning it into narrative. For Hyperliquid-related pairs,
remember that this lane consumes public-feed-style data only; it does not touch
wallets or authenticated exchange endpoints.

## Verification

Focused lane checks:

```bash
python3 -m pytest tests/unit/test_cross_asset_correlation_matrix.py tests/unit/test_cross_asset_regime_detector.py tests/unit/test_cross_asset_sources.py tests/unit/test_cross_asset_run.py tests/unit/test_dashboard_cross_asset_routes.py -q
python3 -m pytest plugins/claw-sapphire/tests/test_cross_asset_intel.py -q
python3 scripts/validate_tool_registry.py
ruff check lib/cross_asset services/cross_asset plugins/claw-sapphire/tools/internal/cross_asset_intel.py plugins/claw-sapphire/tools/cross_asset_intel.py tests/unit/test_cross_asset_correlation_matrix.py tests/unit/test_cross_asset_regime_detector.py tests/unit/test_cross_asset_sources.py tests/unit/test_cross_asset_run.py tests/unit/test_dashboard_cross_asset_routes.py plugins/claw-sapphire/tests/test_cross_asset_intel.py
git diff --check
```

Feasible broader gates for this lane:

```bash
python3 scripts/ops/production_readiness_sweep.py --no-external
python3 scripts/ops/local_ci_verify.py --quiet
```

If broader gates fail outside this lane, record the blocker and do not repair
unrelated files from this worktree.

## Troubleshooting

If `/cross-asset` loads but the heatmap is empty, check the matrix endpoint
first:

```bash
curl -s -H "Authorization: Basic <redacted>" \
  "http://127.0.0.1:5000/api/cross-asset-matrix?window=7d&method=pearson"
```

Do not paste real credentials into chat or docs. In tests, use Flask's test
client. In a browser, use normal auth prompts.

If the endpoint returns `matrix: null`, the likely causes are unsupported window
or method selection, insufficient observations, or an exception while building
the snapshot. The endpoint should fall back to an available matrix when possible.
If all matrices are absent, run:

```bash
python3 services/cross_asset/run.py --once --assets BTC,ETH,SPY,DXY --output-root /tmp/cross-asset-debug
```

If this succeeds, the dashboard issue is likely import path or auth setup. If
this fails, inspect the exception locally and keep the fix inside
`lib/cross_asset`, `services/cross_asset`, or dashboard glue unless the evidence
clearly points elsewhere.

If live mode appears to do nothing, verify both gates. `--live` alone is not
enough:

```bash
SAPPHIRE_CROSS_ASSET_LIVE=1 python3 services/cross_asset/run.py --once --live
```

If `SAPPHIRE_CROSS_ASSET_LIVE=1` is set but OpenBB is unavailable, the adapter
may fall back or fail depending on cache state. That is acceptable. Do not add
test expectations that require OpenBB or internet availability.

If plugin tests import the wrong `lib` package, check whether
`plugins/claw-sapphire/lib` is shadowing the repo root namespace. The
`cross_asset_intel` tool evicts that plugin-local shadow before importing
`lib.cross_asset`. Preserve that pattern if the tool grows.

## Cache Management

Adapter caches live under `~/.cache/sapphire/cross_asset/` by default. They are
operator-local optimization artifacts. They are safe to regenerate and should
not be committed. When debugging a stale read, prefer pointing the command at a
temporary output root or monkeypatching the cache root in tests. Avoid deleting
large cache trees during multi-agent work unless Ari explicitly asks for a cache
cleanup.

The cache stores normalized OHLCV JSON rows per adapter and asset. A corrupt
cache file is ignored and replaced by dry-run rows unless live mode can refresh
it. This design prevents a single bad file from breaking the dashboard. It also
means an operator should check source summaries before interpreting a surprising
matrix. A synthetic row source is useful for UI availability, but it is not live
market evidence.

## Event-Bus Handling

`run.py --publish` emits:

```text
regime.shift.detected
correlation.breakdown
```

These names are intentionally lane-local and do not replace older event types.
Publishing is optional so a dashboard read cannot create regime events as a side
effect. If future routines depend on the events, schedule the daemon with
`--publish` and document the schedule, output root, rollback, and expected event
volume in the same PR.

If Redis is unavailable, Sapphire's event bus can write to its JSONL fallback.
That is still a local mutation. Use it only from the daemon path, not from page
loads or plugin status checks.

## Incident Response

If a false crisis label appears, first check sample coverage and source summary.
A matrix generated from synthetic or stale cache rows should not drive external
messaging. Second, compare the current matrix to the previous `matrix.json` for
the same date. Third, inspect breakdown event z-scores. A crisis label without
supporting breakdowns may indicate broad but stable high correlation rather
than a fresh transition.

If a breakdown table floods with events, reduce the queried asset universe or
raise the sigma threshold in a follow-up patch. Do not hot-edit the production
daemon without a branch. A flood is usually a symptom of a bad input source,
timestamp mismatch, or duplicated synthetic data.

If an operator asks whether the regime should affect trades, the correct answer
for this release is: not directly. This lane supplies context. Any execution or
position-sizing integration would be a separate CODEOWNERS-sensitive change and
must respect Sapphire's trading safety posture.

## Integration Notes

Do not integrate directly with `lib/correlator` in this lane. The integration
pass can consume both outputs later:

- cross-source signal confidence from Tranche 3,
- cross-asset matrix and regime label from this lane,
- narrative synthesis from Lane 1,
- macro and regulatory context from other Tranche 4 lanes.

The clean contract today is JSON-friendly dataclasses and plugin actions. Keep
that contract stable. A future integration should import from `lib.cross_asset`
or read `data/cross_asset`, not duplicate the correlation math.

## Rollback

Rollback is a PR revert. The lane adds new modules, a new service package, a new
dashboard page and route, a new plugin tool pair, docs, tests, and one registry
entry. It does not mutate existing trading behavior. To disable operational use
without reverting code, stop scheduling `services/cross_asset/run.py`, remove
the dashboard nav link in a follow-up PR, and leave cached artifacts untouched
until the operator decides whether to archive them.
