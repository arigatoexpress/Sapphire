# Data & Monitoring Toolkit

This toolkit bootstraps feature ingestion, embedding pipelines, and observability for the autonomous trader stack. Everything here is optional but provides battle-tested defaults for standing up analytics fast.

## Feast Feature Store (historical + streaming)

1. Install extras (prefer virtualenv):
   ```bash
   pip install feast==0.44.1 pandas sentence-transformers
   ```
2. Initialise the repo:
   ```bash
   cd infra/data_toolkit/feast_repo
   feast apply
   ```
3. Materialise 24h of features into the online store:
   ```bash
   feast materialize-incremental $(date +%Y-%m-%d)
   ```

The repo ships with:

| File | Purpose |
| --- | --- |
| `feature_store.yaml` | Minimal local registry + SQLite online store |
| `entities.py` | Defines `Market` entity keyed by symbol |
| `features.py` | Rolling volatility, funding rate, and sentiment embeddings |
| `repo_config.py` | Helper to load the feature store programmatically |

`cloud_trader.data.feature_pipeline` exposes helpers:

```python
from cloud_trader.data import build_feature_repo, load_feature_df

store = build_feature_repo("infra/data_toolkit/feast_repo")
rows = [{"symbol": "BTCUSDT", "event_timestamp": datetime.utcnow()}]
df = load_feature_df("infra/data_toolkit/feast_repo", ["market_features:price"], rows)
```

## Embedding Pipeline Stub

`pipelines/embeddings.py` demonstrates how to:

- Pull raw market + news data (placeholder `load_raw_events`).
- Generate sentence embeddings using `sentence-transformers` (CPU-friendly).
- Write features to Feast or dump to Parquet for offline training.

Run it manually:

```bash
python infra/data_toolkit/pipelines/embeddings.py --output data/embeddings.parquet
```

## Observability Stack

### Prometheus & Grafana

1. Launch stack:
   ```bash
   docker compose -f infra/data_toolkit/monitoring/docker-compose.yml up -d
   ```
2. Point Prometheus to scrape:
   - `run_live_trader`: `/metrics` (enabled via `prometheus-fastapi-instrumentator`)
   - `run_orchestrator`: `/metrics`
   - llama.cpp: `--metrics-port`
   - vLLM: `/metrics` (start with `--openai-api-metrics`) 
3. Import the Grafana dashboard from `monitoring/grafana.json` (latency, PnL, risk guardrails).

### Panel Dashboard

`notebooks/pnl_trace_template.ipynb` + `panel_dashboard.py` illustrate how to surface PnL, drawdown, reasoning trail in the browser:

```bash
panel serve infra/data_toolkit/monitoring/panel_dashboard.py --autoreload
```

The Panel app reads Redis Streams and renders live PnL/exposure indicators plus the reasoning feed. Pass a custom Redis URL via `?redis=redis://...` query parameter if needed.

## Suggested Prometheus Alerts

| Alert | Condition | Action |
| --- | --- | --- |
| `HighLatency` | `trading_loop_latency_ms > 500` for 3m | Inspect logs, scale replicas |
| `PortfolioDrawdown` | Exposure / balance > `MAX_PORTFOLIO_LEVERAGE` | Trigger kill switch |
| `RedisStreamLag` | Consumer lag > 200 msgs | Rebalance workers |

## Notebook Templates

- `notebooks/pnl_trace_template.ipynb`: seeded with pandas + plotly cells for analysing cumulative PnL and Sortino.
- Add more templates (drawdown attribution, strategy comparison) as you iterate.

## Cleaning Up

```bash
docker compose -f infra/data_toolkit/monitoring/docker-compose.yml down
rm -rf infra/data_toolkit/feast_repo/data
```

> Pro tip: commit only configuration. Outputs (parquet, sqlite) should stay out of git.

