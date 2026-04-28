# Sapphire Signal Correlation Engine — 0.1.0

**Status:** Tranche 3, ships in `feat/signal-correlation-engine`.
**Audience:** Acquirer corp-dev / Foundry-aligned engineering reviewer / Sapphire operator.

> *"Five distinct alpha feeds, one unified edge_score per (symbol, timeframe), with a corroborated_by array naming each contributing source. This is THE differentiator a buyer will recognize."*

## Why this exists

Tranche 2 shipped FIVE distinct signal feeds:

| Source | Path | What it captures |
|---|---|---|
| TradingView webhooks | `data/signals/<date>.jsonl` | Pine-script strategy alerts (RSI/MACD/momentum, regime-aware) |
| Telegram channel intel | `~/.sapphire/telegram_intel_signals.jsonl` | @glassnode-grade analyst posts, classified bullish/bearish |
| Hyperliquid public feed | `~/.sapphire/hyperliquid_signals.jsonl` | Microstructure: trade imbalance, depth-drop, persistent BBO skew |
| Threat-intel sweep | `data/threat_intel/sapphire_signals.json` | CVE-impacted-asset bearish bias |
| Convergence watchlist | `world_knowledge/research/.../convergence_watchlist.json` | Long-thesis tier (conservative/growth/speculative) |

Plus the two prediction streams the platform already had:

| Source | Path | What it captures |
|---|---|---|
| Kronos forecast | `data/intelligence/<date>/predictions.json` | 24-bar OHLCV ML projection per asset |
| TA scanner | `data/trading_predictions.jsonl` | RSI/MACD/BB/MA composite per asset |

And one more, optional:

| Source | Path | What it captures |
|---|---|---|
| Sovereign-thesis snapshot | `data/sovereign-thesis/latest.json` | Cypherpunk/Austrian thesis composite per asset |

**The whole was greater than the sum of the parts ONLY in the operator's head.** Every one of those streams was independently valuable, but a corp-dev reviewer asking *"how do these intel surfaces fuse into a single trading edge?"* had no answer to point to. The answer was: *"the operator does it intuitively."* Not buyer-readable.

The Signal Correlation Engine is the missing piece. It fuses all of the above into a single payload per `(symbol, timeframe)`:

```json
{
  "symbol": "BTC",
  "timeframe": "1h",
  "edge_score": 0.78,
  "consensus": "AGREE_BULL",
  "corroborated_by": ["tradingview", "telegram_intel", "convergence_watchlist", "kronos_forecast"],
  "divergent_sources": [],
  "bull_sources": ["tradingview", "telegram_intel", "convergence_watchlist", "kronos_forecast"],
  "bear_sources": [],
  "neutral_sources": ["hyperliquid_public_feed"],
  "freshness_seconds": 38.0,
  "contributing": 5,
  "raw_score": 0.71,
  "agreement_multiplier": 1.30,
  "contradict_factor": 1.0,
  "total_weight": 5.05,
  "generated_at": "2026-04-29T03:14:00+00:00",
  "provenance_envelope": {
    "generator": "lib.correlator.engine",
    "version": "0.1.0",
    "weights_signature": { "...": "..." }
  }
}
```

This is what a Palantir / Robinhood corp-dev reviewer wants to see when they ask "what's the signal layer?". One number, one consensus, one provenance trail, and an explicit list of who contributed.

## What the consensus labels mean

| Label | Trigger |
|---|---|
| `AGREE_BULL` | ≥ 2 sources bull, 0 bear |
| `AGREE_BEAR` | ≥ 2 sources bear, 0 bull |
| `PARTIAL_BULL` | 1 source bull, 0 bear |
| `PARTIAL_BEAR` | 1 source bear, 0 bull |
| `CONTRADICT` | Both bulls and bears non-zero |
| `NEUTRAL` | All present sources are neutral |
| `INSUFFICIENT_DATA` | No sources present (or all stale) |

## Worked example: BTC, 1h horizon

Consider a moment where:

- TradingView webhook fires `direction=long, confidence=0.82` (recent breakout above the 50-MA).
- Telegram intel reader picks up an @glassnode post with `label=bullish, confidence=0.6`.
- Hyperliquid public feed reports `kind=trade_imbalance_buy, confidence=0.4` (sell pressure exhausted).
- Convergence watchlist has BTC in `growth_satellite` tier → bull bias at confidence 0.65.
- Kronos forecast emits `direction=bullish, confidence=0.74` for the next 24 bars.
- Threat-intel has nothing for BTC.
- Sovereign-thesis composite has BTC at `+0.4` → bull at confidence 0.4.

Default weights (per `lib.correlator.scoring.DEFAULT_SOURCE_WEIGHTS`):

| Source | Weight | Direction | Confidence | Freshness | Contribution |
|---|--:|--:|--:|--:|--:|
| kronos_forecast | 1.30 | +1 | 0.74 | 1.00 | +0.962 |
| ta_scanner | 1.15 | (—) | (—) | (—) | (none — TA stream not the same as TradingView in this example) |
| tradingview | 1.00 | +1 | 0.82 | 0.95 | +0.779 |
| hyperliquid_public_feed | 0.85 | +1 | 0.40 | 1.00 | +0.340 |
| telegram_intel | 0.70 | +1 | 0.60 | 0.99 | +0.416 |
| convergence_watchlist | 0.55 | +1 | 0.65 | 0.85 | +0.304 |
| sovereign_thesis | 0.50 | +1 | 0.40 | 0.92 | +0.184 |
| Total weight (denom) | 5.05 | | | | sum = +2.985 |
| Raw blended score | | | | | +2.985 / 5.05 = 0.591 |
| Agreement multiplier (5 bull, no bear, +0.10/extra, capped 1.40) | | | | | × 1.40 |
| Contradict factor (no bear sources) | | | | | × 1.00 |
| Final clamped edge_score | | | | | **+0.78** |

Buyer-friendly summary in one sentence:

> *"Five of seven configured sources agree this BTC 1h horizon is bullish, none disagree, and the blended score of +0.78 (after the agreement bonus and freshness decay) puts this at the top of the unified edge_score ranking — corroborated_by names every contributor for full audit."*

## Read-only by construction

The engine is a strict signal *consumer*. It does not:

- Open a network socket. All sources read disk snapshots under `data/` or `~/.sapphire/`.
- Write back to source streams. Adapters never call `write_text`, `xadd`, or `bus.publish` on upstream files.
- Trigger orders. Output is intel-only; the paper trader, dashboards, and live capital ramp decide what to do with it.
- Run any LLM. Pure stdlib + PyYAML for the config loader.

The daemon at `services/correlator/run.py` writes:

- `data/correlated_signals/<YYYY-MM-DD>/signals.jsonl` (append-only)
- A sibling `signals.jsonl.envelope.json` provenance envelope
- Optionally publishes to the event bus on topic `signal.correlated` (gated by `SAPPHIRE_CORRELATOR_LIVE_BUS=1`)

Every emitted row carries `provenance_envelope` inline AND lives next to the daily envelope sidecar — buyer can audit any row back to a specific (commit_sha, weights_signature, contributing_sources) tuple.

## Caps (from the Tranche 3 prompt)

| Cap | Value | Where |
|---|--:|---|
| `MAX_SOURCES_PER_CORRELATION` | 16 | engine input fan-in (lowest-weight sources dropped first) |
| `MAX_CORRELATIONS_PER_HOUR` | 1200 | service runner emission rate |
| `FRESHNESS_HARD_LIMIT_SECONDS` | 86400 | sources older than 24h are silently dropped — never treated as bear pressure from staleness |
| `EDGE_SCORE_BOUND` | (-1.0, +1.0) | clamped at output |

These match the engine's published constants exactly. Tests assert each cap (`tests/unit/test_correlator_engine.py::test_caps_match_spec`).

## Tunability

Drop a YAML at `~/.sapphire/correlator_weights.yaml`:

```yaml
source_weights:
  tradingview: 1.0
  telegram_intel: 0.6
  kronos_forecast: 1.4
freshness_half_life_seconds: 21600
agreement_bonus_per_extra: 0.1
max_agreement_multiplier: 1.4
contradict_penalty: 0.45
```

All keys are optional. Missing keys fall back to the defaults baked into `lib.correlator.scoring.DEFAULT_SOURCE_WEIGHTS`. Malformed YAML or missing files fall back to defaults silently — the loader never raises.

A new source name (e.g. `coinglass_oi: 0.4`) auto-registers when its adapter is added — the scoring layer treats unknown source names as weight-0 (silently ignored). This is intentional: adding an adapter is a code change AND a config change, and the config-only path is conservative.

## What this enables for an acquirer

- **Single-pane-of-glass alpha.** The /performance dashboard and the new /diligence page can both surface a unified edge_score table without operator intuition.
- **Provenance back to a SHA.** Every correlated signal references the commit-sha-derived weights_signature plus the on-disk source files at fusion time. A buyer's data-eng team can replay any historical correlation deterministically.
- **Multi-modal alpha story.** Microstructure + sentiment + ML forecast + thesis bias is the multi-modal pitch a Palantir Foundry reviewer recognizes immediately. This module is the seam where it lands.
- **Cap-bounded, no-spend-by-default.** Mirrors `gemini_ooda` and `vertex_eval` — caps, dry-run defaults, no live network at module load. Reviewer-friendly.

## Versioning

`0.1.0` ships:

- 8 disk-snapshot adapters
- pure scoring math with property-test invariants (monotonicity, bound, symmetry)
- engine + service + plugin tool + LaunchAgent template + tests + docs
- registry entry: `infra/tool-registry.yaml::signal_correlator (status: internal)`

`0.2.0` (out of scope, captured in the runbook backlog):

- Symbol/timeframe alias table (BTC-USD↔BTC, 1h↔60m) lifted to config
- Per-pair custom weights (e.g. weight Hyperliquid heavier on perps, lighter on spot ETFs)
- `signal.correlated` event subscribers on the dashboard SSE stream
- BigQuery sync via the foundry ingestion lane (Lane 3 of Tranche 3)
