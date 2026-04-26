# Test Coverage Audit — 2026-04-26

Snapshot of `lib/` and `plugins/claw-sapphire/lib/` line coverage from the `tests/unit/` suite, plus actionable next-step recommendations for autonomous test-writer agents.

## Method

Ran the in-tree `coverage.py` (already pinned via `requirements-test.txt`) against the full unit suite, scoped to source modules under `lib/` and `plugins/claw-sapphire/lib/`:

```bash
/usr/local/bin/python3 -m coverage run \
    --source=lib,plugins/claw-sapphire/lib \
    -m pytest tests/unit/ -q --tb=no
/usr/local/bin/python3 -m coverage report \
    --skip-covered --sort=cover --show-missing > /tmp/coverage.txt
```

Total: 2,209 unit tests passed in 64s. Aggregate coverage of measured sources: **60%** (5,657 of 14,109 statements uncovered).

The plugin tests under `plugins/claw-sapphire/tests/` were not part of this run (they use a separate fixture set), so any 0% on `plugins/claw-sapphire/lib/*` reflects the *unit suite's* view, not the actual plugin module coverage. The gap table below already discounts that — plugin libs that are tested by the plugin suite (e.g. `technical_analysis.py`, `router.py`, `token_governor.py`) are excluded from the rank.

Scoring: `criticality × uncovered_lines`. Buckets:

- **High (×3)** — `lib/analytics/`, `lib/chain/`, `lib/content/`, `lib/portfolio/`, `lib/security/`, `plugins/claw-sapphire/lib/`
- **Medium (×2)** — `lib/intel/`, `lib/foundry/`, `lib/payments/`, `lib/agents/`
- **Low (×1)** — `lib/telegram/`, `lib/trading/` (mostly stubs), `services/*` (integration-tested elsewhere)

CODEOWNERS-protected paths excluded from this rank: `lib/analytics/strategies.py`, `lib/analytics/risk_engine.py`, `lib/portfolio/robinhood.py`, `lib/trading/`, `lib/security/*`, `lib/core/kill_switch.py`, `lib/core/confirmation_firewall.py`, `lib/core/security_monitor.py`, `contracts/`.

## Top 10 gaps by score

| Module                                     | Criticality | Stmts | Covered | Uncovered | Score |
|--------------------------------------------|-------------|-------|---------|-----------|-------|
| `lib/intel/market_intelligence.py`         | Medium      | 566   | 178     | 388       | 776   |
| `lib/content/report_generator.py`          | High        | 311   | 87      | 224       | 672   |
| `lib/analytics/factors.py`                 | High        | 159   | 0       | 159       | **477** ← covered |
| `lib/analytics/correlation.py`             | High        | 316   | 180     | 136       | 408   |
| `lib/analytics/liquidation.py`             | High        | 119   | 0       | 119       | 357   |
| `lib/chain/coinmetrics.py`                 | High        | 88    | 0       | 88        | 264   |
| `lib/chain/intelligence.py`                | High        | 289   | 196     | 93        | 279   |
| `lib/content/thesis_engine.py`             | High        | 72    | 0       | 72        | 216   |
| `lib/content/data_collector.py`            | High        | 50    | 0       | 50        | 150   |
| `lib/content/draft_generator.py`           | High        | 45    | 0       | 45        | 135   |

Honorable mentions (not in top 10 but flagged for awareness):

- `lib/analytics/deflated_sharpe.py` — High, 0% (30 stmts × 3 = 90). Small surface, easy win.
- `lib/content/visualizations.py` — High, 0% (47 stmts).
- `lib/content/__main__.py` — High, 0% (56 stmts) — CLI entry point, exercised manually by `python3 -m lib.content`.
- `lib/core/src/sapphire_core/telegram_bot.py` — Medium, 12% (245 uncovered). Out of scope for this audit (legacy bot).

## Action taken

Wrote `tests/unit/test_factors.py` covering `lib/analytics/factors.py`:

- **31 new tests** added.
- Module coverage went from **0% → 97%** (159 stmts, 4 uncovered: log statements + a degenerate-input branch).
- Full unit suite: 2,209 → 2,240 passing, 1 skipped, 21 xfailed (no regressions).

Branches exercised:

- Pure-math helpers — `_safe_pct_change` (positive return / negative return / too-few-prices / zero old-price), `_realized_vol` (constant flat, oscillating, too-few-prices, zero-prefix filtered by `prices[i-1] > 0` guard), `_cross_sectional_z` (basic z-scores, None-fill, < 2 valid → all-zero, zero-variance fallback to std=1).
- Cache lifecycle — `_cache_set` / `_cache_get` (hit, miss, TTL expiry via `monkeypatch.setattr(time.monotonic)`).
- HTTP boundary — `_fetch_market_data` (cache-hit short-circuit, `_http_get` raises → `None`, success caches result).
- `CrossSectionalFactors.compute` — 2-asset rank, unknown-symbol skip, all-fetch-fail → all-zero composite, volatility z-score inversion (low-vol asset outranks high-vol on the volatility factor), full-universe report cache, single-asset dispersion = 0.
- `to_dict` serialization — required keys, asset-count, factor-name list, z-score rounding to 3 decimals; empty-report degenerate path.

`lib/analytics/factors.py` was selected because:

- 0% coverage (highest absolute gap among non-protected `lib/analytics/`).
- Pure dependency on stdlib + a single `_http_get` boundary that monkey-patches cleanly.
- Output drives the `/factors` dashboard view (read by humans, used to inform discretionary trading) — silent breakage would compound over weeks.
- Not on the CODEOWNERS critical path; no `services/alpha`, no kill-switch, no risk engine.

## Recommended next gaps

Three concrete follow-ups, ordered by effort × value:

1. **`lib/analytics/liquidation.py` (0% → high crit, 119 stmts).** Same shape as factors: pure scoring math (`_score_asset`, `_risk_label`) plus one HTTP boundary (`HyperliquidClient.meta_and_asset_ctxs`). Tests should monkeypatch the client and exercise the four risk bands (LOW / MODERATE / HIGH / CRITICAL), the funding-component thresholds at `_FUNDING_EXTREME_8H` / `_FUNDING_CRITICAL_8H`, the OI baseline lookup, and the `alert` text emission for `CRITICAL` and top-2 `HIGH` cases. Feasible in a single test file; ~120 LOC of tests should hit > 90%.

2. **`lib/analytics/deflated_sharpe.py` (0% → high crit, 30 stmts).** Tiny module — ~30 statements implementing the López de Prado Deflated Sharpe Ratio. Pure NumPy-style math with no IO. Plug in a known-Sharpe + known-strategy-count input and assert against the closed-form expected DSR. One test file, ~50 LOC, gets you to 100% trivially.

3. **`lib/content/thesis_engine.py` (0% → high crit, 72 stmts) + `lib/content/draft_generator.py` (0%, 45 stmts).** These two are tightly coupled — the engine emits a `Thesis` object that the generator consumes. Test them together in one file: feed a synthetic event stream, assert the thesis ranks events by event-bus priority + recency, then assert the draft generator emits a Markdown skeleton with the right section headers. Both are pure-Python, no LLM calls in the hot path — `lib/content/data_collector.py` (also 0%) would make a natural third companion.

Beyond these three, the highest-leverage follow-up is adding plugin-side coverage to the unit run (export `PYTHONPATH` and include `plugins/claw-sapphire/tests/` in the same `coverage run`) so the audit reflects the *actual* health of `plugins/claw-sapphire/lib/`. Today, those modules read as 0% in the unit-suite report despite having dedicated plugin tests — a misleading data point that future agents will trip over.
