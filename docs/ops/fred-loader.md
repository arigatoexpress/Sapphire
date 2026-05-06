# FRED/ALFRED Loader

Date: 2026-05-06

Sapphire now has a cache-first FRED/ALFRED observations loader for macro regime
features, backtesting, and future x402-paid reports. It does not run live by
default and does not enable trading, settlement, Telegram sends, or production
data mutation.

## Files

- `lib/macro/fred_loader.py` - typed observations parser, cache-first loader,
  ALFRED realtime-window support, and compact feature-row builder.
- `infra/gcp/schemas/fred_series_observations.json` - future BigQuery table for
  point-in-time observations.
- `infra/gcp/bootstrap_bigquery.sh` - table registration for
  `sapphire.fred_series_observations`.
- `services/macro_intel/run.py` - optional `--fred` writer for
  `data/macro/<YYYY-MM-DD>/fred_observations.jsonl`.
- `services/pipeline/gcp_sync.py` - upload-only transform for
  `raw/fred/<YYYY-MM-DD>/*.ndjson`.
- `infra/gcp/cloud_functions/gcs_to_bq/main.py` - Cloud Function table mapping
  from `raw/fred/` to `sapphire.fred_series_observations`.
- `config/x402_source_registry.json` - source-registry status updated from
  "loader missing" to "loader present, live/backfill pending."

## Safety Gates

Live FRED reads require both:

```bash
export SAPPHIRE_FRED_LIVE=1
export FRED_API_KEY=...
```

Without those values, a cache miss raises a controlled `FredLoaderError`.
Tests use injected fetchers and fixtures; they do not call the live API.

The default cache location is outside the repo:

`~/.cache/sapphire/macro/fred/`

Override with:

```bash
export SAPPHIRE_FRED_CACHE_DIR=/path/to/fred-cache
```

or set `SAPPHIRE_MACRO_CACHE_DIR`, which places FRED payloads under
`$SAPPHIRE_MACRO_CACHE_DIR/fred/`.

## Market-Regime Series

The default series set is intentionally small:

- `DFF` - effective federal funds rate
- `DGS2` - 2-year Treasury yield
- `DGS10` - 10-year Treasury yield
- `T10Y2Y` - 10-year minus 2-year spread
- `CPIAUCSL` - CPI
- `UNRATE` - unemployment rate
- `M2SL` - M2 money stock
- `DTWEXBGS` - broad dollar index
- `VIXCLS` - VIX close
- `BAMLH0A0HYM2` - high-yield spread

## Operator Checks

Offline focused tests:

```bash
python3 -m pytest tests/unit/test_fred_loader.py -q
```

Write cache-backed local artifacts:

```bash
python3 -m services.macro_intel.run run-once --fred
```

Run live FRED pulls for missing cache files:

```bash
SAPPHIRE_FRED_LIVE=1 FRED_API_KEY=... python3 -m services.macro_intel.run run-once --fred
```

Dry-run the upload transform:

```bash
python3 -m services.pipeline.gcp_sync --dry-run --source fred
```

Cache-only feature row sketch:

```bash
python3 - <<'PY'
from lib.macro.fred_loader import FredLoader, macro_feature_row

loader = FredLoader()
snapshots = loader.pull_market_regime_series(cache_only=True)
print(macro_feature_row(snapshots))
PY
```

The next build step is a planned daily backfill/export routine that writes
`fred_series_observations` rows with payload hashes, then exposes those features
to the simulated x402 market-regime endpoint.
