# Paper outcomes warehouse schema (GCP BQ — research only)

**For Gemini Phase 3 P2 / later.**  
**Not** live trading sole-writer. **Not** public wallet store.

## Dataset (suggested)

Project: `tho-ai-agent` (warehouse)  
Dataset: `sapphire_research`  
Location: `US`

## Tables

### `paper_strategy_runs`

| Column | Type | Notes |
|---|---|---|
| run_id | STRING | uuid |
| strategy_id | STRING | e.g. RegimeAwareRSI |
| symbol | STRING | BTC, ETH, … |
| started_at | TIMESTAMP | |
| ended_at | TIMESTAMP | |
| sortino | FLOAT64 | nullable |
| sharpe | FLOAT64 | nullable |
| max_dd | FLOAT64 | nullable |
| n_trades | INT64 | |
| paper_only | BOOL | must be TRUE |
| source | STRING | win_worker \| mac_lab \| backtest |
| ingested_at | TIMESTAMP | |

### `regime_digests`

| Column | Type |
|---|---|
| as_of | TIMESTAMP |
| symbol | STRING |
| regime_label | STRING |
| fit | FLOAT64 |
| source | STRING |

### `public_surface_audits`

| Column | Type |
|---|---|
| checked_at | TIMESTAMP |
| issue_count | INT64 |
| issues_json | STRING |
| live_status | STRING |
| desk_updated_at | STRING |

## Load path

1. Plant/Win writes JSONL → GCS `gs://…/sapphire-research/…`  
2. BQ load job / scheduled query  
3. Public site may only read **aggregates** via existing PUBLIC_READ_ONLY patterns — never raw positions  

## Explicit non-goals

- Live RH fills as source of public PnL tiles  
- Storing API keys or wallet private material  
