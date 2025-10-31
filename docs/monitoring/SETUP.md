# Monitoring Stack Setup

This guide outlines an opinionated stack for observability and analytics.

## Prometheus & Grafana

1. Deploy Prometheus alongside the trader service using the example `docker-compose`:

   ```yaml
   prometheus:
     image: prom/prometheus:v2.53.0
     volumes:
       - ./prometheus.yml:/etc/prometheus/prometheus.yml
     ports:
       - "9090:9090"
   grafana:
     image: grafana/grafana:11.1.0
     ports:
       - "3000:3000"
   ```

2. Scrape targets:
   - `cloud_trader` FastAPI metrics (`/metrics` exposed automatically via `prometheus-fastapi-instrumentator`).
   - `risk-orchestrator` metrics (`/metrics`).
   - llama.cpp (`--metrics-port 9091`) and vLLM (`--metrics-port 8001`).

3. Dashboards:
   - Latency histogram (P95, P99)
   - Decision throughput per stream
   - Redis Stream depth

## Panel Dashboard

Install Panel and serve the example dashboard:

```bash
pip install panel==1.4.5 hvplot pandas
panel serve dashboards/pnl_panel.py --autoreload
```

`dashboards/pnl_panel.py` (example):

See `dashboards/pnl_panel.py` for an auto-refreshing example driven by `/streams/positions`.

## Feast + Embeddings

- Initialise repo via `cloud_trader.data.build_feature_repo()`.
- Store on-chain metrics in the `onchain_metrics` entity for low-latency retrieval.
- Embed headlines with `embed_news_headlines` before writing to the feature store.

## Jupyter Notebooks

Use the provided notebook templates in `notebooks/`:

- `pnl_trace.md`: walkthrough for loading Redis stream data into Pandas.
- `feature_exploration.md`: example Feast feature inspection.

Launch via:

```bash
pip install jupyterlab
jupyter lab --notebook-dir notebooks
```

## Alerting

- Configure Grafana alerts when:
  - `trader:decisions` stream stalls (>60s without entries)
  - Max drawdown exceeds threshold (derived from `positions` stream)
  - Model inference latency > 500ms (Prometheus histogram)

## References

- Prometheus FastAPI Instrumentator – https://github.com/trallnag/prometheus-fastapi-instrumentator
- Panel documentation – https://panel.holoviz.org/
- Feast quickstart – https://docs.feast.dev/

