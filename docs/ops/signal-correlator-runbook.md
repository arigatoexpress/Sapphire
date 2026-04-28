# Sapphire Signal Correlator — Operator Runbook

**Service:** `com.sapphire.signal-correlator` LaunchAgent (template only — not loaded by default).
**Entry point:** `services/correlator/run.py`.
**Plugin tool:** `plugins/claw-sapphire/tools/internal/signal_correlator.py` (and `tools/signal_correlator.py` shim).
**Version:** 0.1.0.
**Owner:** sapphire (Ari).

This runbook is the operator-side reference for the cross-source signal correlator. It covers (a) how to wake the daemon up, (b) how to read what it emits, (c) how to tune it without touching code, (d) what to do when something looks off, and (e) the safety rails that bound the surface.

---

## 0. Preflight

Before invoking anything live:

```bash
cd ~/Code/Sapphire
ruff check .
/usr/local/bin/python3 -m pytest tests/unit/test_correlator_engine.py tests/unit/test_correlator_sources.py tests/unit/test_correlator_scoring.py tests/unit/test_correlator_run.py -q
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/test_signal_correlator.py -q
/usr/local/bin/python3 scripts/validate_tool_registry.py
```

Expect:

- ruff: no issues
- 85 unit tests passing in ~0.2s
- 15 plugin tests passing in ~0.05s
- registry: 43 tools, 0 errors

If any block is red, stop and inspect — the daemon is read-only, so a broken local check usually points at a drift in one of the upstream signal-feed schemas (most often Kronos).

---

## 1. Quick start (no LaunchAgent, ad-hoc)

```bash
cd ~/Code/Sapphire
# Single tick — fuses the default universe (BTC/ETH/SOL × 1h+4h, SPY/TSLA × 1d).
/usr/local/bin/python3 services/correlator/run.py run-once

# View today's emission:
ls -la data/correlated_signals/$(date -u +%Y-%m-%d)/
cat data/correlated_signals/$(date -u +%Y-%m-%d)/signals.jsonl | head -3
cat data/correlated_signals/$(date -u +%Y-%m-%d)/signals.jsonl.envelope.json
```

Or via the plugin tool:

```bash
echo '{"action": "correlate-once", "pairs": [["BTC", "1h"], ["ETH", "4h"]]}' \
  | python3 plugins/claw-sapphire/tools/internal/signal_correlator.py | jq .
```

The plugin tool returns the full `CorrelatedSignal` dict with metadata (caps, rate-limit state, version) plus the `signals` array. Same payload the daemon writes to disk.

---

## 2. Universe and pair vocabulary

Default universe (in `services/correlator/run.py::DEFAULT_UNIVERSE`):

```
("BTC", "1h"), ("BTC", "4h"),
("ETH", "1h"), ("ETH", "4h"),
("SOL", "1h"), ("SOL", "4h"),
("SPY", "1d"), ("TSLA", "1d"),
```

The plugin tool accepts arbitrary pairs (capped at 32/call). To extend the daemon's universe, edit `DEFAULT_UNIVERSE` or pass a custom universe in a wrapper script. There is no runtime config for the universe (intentional — adding a pair is a code change).

Symbol aliases (handled silently in `lib.correlator.sources._SYMBOL_ALIAS`):

- `BTC-USD` → `BTC`
- `ETH-USD` → `ETH`
- `SOL-USD` → `SOL`
- `BTCUSD`, `BTCUSDT` → `BTC` (and equivalent for ETH/SOL)

If a source emits a symbol the alias table doesn't recognize, the engine treats it as an opaque symbol — the per-source adapter is the right place to add canonicalization, not the engine.

---

## 3. Config — `~/.sapphire/correlator_weights.yaml`

The single tunable surface. All keys optional. Missing file or unparseable YAML → defaults silently used.

```yaml
# Per-source weight overrides. Unknown keys are silently ignored.
source_weights:
  tradingview: 1.00
  telegram_intel: 0.70
  hyperliquid_public_feed: 0.85
  threat_intel: 0.40
  convergence_watchlist: 0.55
  sovereign_thesis: 0.50
  kronos_forecast: 1.30
  ta_scanner: 1.15

# Half-life of the freshness decay (seconds). 6h = 21600.
# A source 6h old contributes half its full weight; 24h old, ~1/16th.
freshness_half_life_seconds: 21600

# Agreement bonus: each additional concurring source raises the score by
# this multiplier delta, capped at max_agreement_multiplier.
agreement_bonus_per_extra: 0.10
max_agreement_multiplier: 1.40

# Contradiction dampener: when both bull and bear sources are present,
# the blended score is multiplied by this factor.
contradict_penalty: 0.45
```

To verify the resolved config:

```bash
echo '{"action": "weights"}' | python3 plugins/claw-sapphire/tools/internal/signal_correlator.py
```

Returns the path it consulted, whether it exists, and every resolved field.

---

## 4. Provenance & audit

Every emitted `signals.jsonl` row carries an inline `provenance_envelope`:

```json
{
  "generator": "lib.correlator.engine",
  "version": "0.1.0",
  "symbol": "BTC",
  "timeframe": "1h",
  "sources": ["tradingview", "telegram_intel", "kronos_forecast", "..."],
  "weights_signature": {
    "source_weights": {"tradingview": 1.0, "...": "..."},
    "freshness_half_life_seconds": 21600.0,
    "agreement_bonus_per_extra": 0.1,
    "max_agreement_multiplier": 1.4,
    "contradict_penalty": 0.45
  },
  "generated_at": "2026-04-29T03:14:00+00:00"
}
```

And a sibling `<jsonl_path>.envelope.json` carries the daily file-level envelope:

```json
{
  "generator": "services.correlator.run",
  "version": "0.1.0",
  "schema_version": 1,
  "wrote_at": "2026-04-29T03:14:00+00:00",
  "artifact": "signals.jsonl",
  "signals_appended": 8,
  "ttl_seconds": 604800,
  "expires_at": "2026-05-06T03:14:00+00:00"
}
```

A buyer's data engineer can replay any historical correlation deterministically by:

1. Checking out the commit at the time of `wrote_at` (the weights signature is enough to identify it; `git log` to find the right SHA).
2. Restoring the source files referenced in `provenance_envelope.sources` for that timestamp.
3. Re-running `correlate_once` with the resolved weights.

The output should match byte-for-byte.

---

## 5. LaunchAgent install (optional, OFF by default)

The plist template lives at:

```
services/correlator/launchagent/com.sapphire.signal-correlator.plist.template
```

To install:

```bash
cp services/correlator/launchagent/com.sapphire.signal-correlator.plist.template \
   ~/Library/LaunchAgents/com.sapphire.signal-correlator.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.sapphire.signal-correlator.plist
launchctl kickstart -k gui/$UID/com.sapphire.signal-correlator
```

The default plist runs `services/correlator/run.py daemon --poll-interval-seconds 60`. It does NOT enable `SAPPHIRE_CORRELATOR_LIVE_BUS` — that gate keeps the LaunchAgent's first 24h soak silent (no event bus pressure on the dashboard). Once you trust the rate (~1 emission/source/min, ~480/hour for the default 8-pair universe), flip the env var:

```bash
launchctl setenv SAPPHIRE_CORRELATOR_LIVE_BUS 1
launchctl kickstart -k gui/$UID/com.sapphire.signal-correlator
```

To uninstall:

```bash
launchctl bootout gui/$UID/com.sapphire.signal-correlator
rm ~/Library/LaunchAgents/com.sapphire.signal-correlator.plist
```

Logs:

- `~/Library/Logs/sapphire/signal-correlator.log`
- `~/Library/Logs/sapphire/signal-correlator.err`

---

## 6. Operations — what to watch

Hourly:

- `~/.cache/sapphire/correlator/counters.json` — emission counter, monotonically increasing.
- `data/correlated_signals/<today>/signals.jsonl` — line count grows by 8/min (one per pair).
- `data/correlated_signals/<today>/signals.jsonl.envelope.json` — `signals_appended` cumulative.

Red flags:

| Symptom | Likely cause | Mitigation |
|---|---|---|
| `signals_appended` plateaus | Daemon stopped | `launchctl print gui/$UID/com.sapphire.signal-correlator` and check exit status |
| Every row `consensus = INSUFFICIENT_DATA` | All upstream signal feeds gone stale (>24h) | Restart upstream daemons; check `data/signals/`, `~/.sapphire/hyperliquid_signals.jsonl` mtimes |
| Every row `consensus = CONTRADICT` for one symbol | One source is misclassifying direction | Inspect `bull_sources` / `bear_sources` lists; the rogue source is usually the one alone on the minority side |
| `edge_score` always 0 | weights file has all-zero `source_weights` | `echo '{"action": "weights"}' \| python3 ... ` to verify |
| Rate-limit reached | The 1200/hour cap has tripped | Reduce universe size or accept the soft cap (it's a feature) |

---

## 7. Plugin tool — full action surface

```bash
# Correlate a custom set of pairs.
echo '{"action": "correlate-once", "pairs": [["BTC", "1h"]]}' \
  | python3 plugins/claw-sapphire/tools/internal/signal_correlator.py

# Read today's emissions back from disk (read-only).
echo '{"action": "latest"}' \
  | python3 plugins/claw-sapphire/tools/internal/signal_correlator.py

# Read a specific date.
echo '{"action": "latest", "date": "2026-04-28"}' \
  | python3 plugins/claw-sapphire/tools/internal/signal_correlator.py

# Tool-side counters + version.
echo '{"action": "status"}' \
  | python3 plugins/claw-sapphire/tools/internal/signal_correlator.py

# Resolved config (path, exists, every field).
echo '{"action": "weights"}' \
  | python3 plugins/claw-sapphire/tools/internal/signal_correlator.py

# Optional event bus publish — requires BOTH the action arg AND the env flag.
SAPPHIRE_CORRELATOR_LIVE_BUS=1 echo '{"action": "correlate-once", "live_bus": true}' \
  | python3 plugins/claw-sapphire/tools/internal/signal_correlator.py
```

---

## 8. Adding a new source

1. Add a class in `lib/correlator/sources.py` mirroring the existing adapters:

```python
@dataclass
class CoinglassOISource:
    name: str = "coinglass_oi"
    path: Path = field(default_factory=lambda: REPO_ROOT / "data" / "chain" / "coinglass_oi.jsonl")

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        ...
```

2. Register it in `available_sources()` and `build_default_sources()`.
3. Add a default weight in `lib/correlator/scoring.py::DEFAULT_SOURCE_WEIGHTS`.
4. Add an adapter test in `tests/unit/test_correlator_sources.py` (≥ 2 cases: present, missing).
5. Update this runbook + the product doc.

The engine, scoring, plugin tool, and daemon need NO changes — they all enumerate sources from the registry.

---

## 9. Safety posture (recap)

- **Read-only.** No writes to source streams. Adapters never call `write_*`.
- **No live network.** All sources read disk snapshots.
- **No secrets at module load.** No `~/.sapphire/secrets.env` access anywhere in this lane.
- **Fail closed on rate.** When the 1200/hour cap is hit, `run_once` returns `ok: False` rather than dropping signals or exceeding the cap.
- **Provenance envelope on every artifact.** Both inline (per row) and sidecar (per file).
- **No autonomous trading.** Output is intel-only; downstream consumers (paper trader, dashboards) decide what to do with it.

---

## 10. Backlog (for 0.2.0)

- Lift the symbol-alias table to YAML config so a buyer / operator can add `BTC-PERP` etc. without code.
- Per-pair custom weights (e.g. weight Hyperliquid heavier on perps, lighter on spot ETFs).
- Wire `signal.correlated` events into the dashboard SSE stream and the observability page (Lane 2 of Tranche 3).
- Foundry sync — write each correlated signal as an ontology object (Lane 3 of Tranche 3).
- Acquirer microsite screenshot — the `/observability` view of the live correlator (Lane 4).
- Soak-window chart on the dashboard: rolling 24h `edge_score` per `(symbol, timeframe)`.
