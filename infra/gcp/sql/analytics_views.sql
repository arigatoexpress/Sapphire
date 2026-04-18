-- Sapphire analytics views — layered on top of views.sql.
-- Apply with: bq query --use_legacy_sql=false < analytics_views.sql

-- =============================================================
-- v_signals_latest — most recent row per signal_id (de-dup view)
-- Signals are append-only; closes produce a second row with outcome/pnl.
-- Use this whenever you want "the current state of signal X".
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_signals_latest` AS
WITH ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY signal_id
      ORDER BY
        CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END DESC,
        ingested_at DESC
    ) AS rn
  FROM `tho-ai-agent.sapphire.trading_signals`
)
SELECT * EXCEPT(rn)
FROM ranked
WHERE rn = 1
;

-- =============================================================
-- v_signals_by_regime — performance segmented by observed regime.
-- Joins through the latest regime snapshot at signal time.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_signals_by_regime` AS
SELECT
  COALESCE(s.regime, 'UNKNOWN') AS regime,
  s.symbol,
  COUNT(*) AS total_signals,
  COUNTIF(s.outcome = 'win')  AS wins,
  COUNTIF(s.outcome = 'loss') AS losses,
  COUNTIF(s.outcome IS NULL OR s.outcome = 'open') AS open_trades,
  SAFE_DIVIDE(
    COUNTIF(s.outcome = 'win'),
    COUNTIF(s.outcome IN ('win','loss'))
  ) AS win_rate,
  SUM(s.pnl_usd) AS total_pnl_usd,
  AVG(s.confidence) AS avg_confidence,
  AVG(s.score)      AS avg_score
FROM `tho-ai-agent.sapphire.v_signals_latest` s
GROUP BY regime, symbol
ORDER BY total_signals DESC
;

-- =============================================================
-- v_confidence_calibration — win rate by confidence bucket.
-- Shows whether 80% confidence signals actually win ~80% of the time.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_confidence_calibration` AS
SELECT
  CASE
    WHEN confidence >= 0.9 THEN '[0.9,1.0]'
    WHEN confidence >= 0.8 THEN '[0.8,0.9)'
    WHEN confidence >= 0.7 THEN '[0.7,0.8)'
    WHEN confidence >= 0.6 THEN '[0.6,0.7)'
    WHEN confidence >= 0.5 THEN '[0.5,0.6)'
    ELSE '[0,0.5)'
  END AS confidence_bucket,
  COUNT(*) AS signals,
  COUNTIF(outcome = 'win')  AS wins,
  COUNTIF(outcome = 'loss') AS losses,
  SAFE_DIVIDE(
    COUNTIF(outcome = 'win'),
    COUNTIF(outcome IN ('win','loss'))
  ) AS win_rate,
  AVG(confidence) AS avg_confidence,
  SUM(pnl_usd)    AS total_pnl_usd
FROM `tho-ai-agent.sapphire.v_signals_latest`
WHERE outcome IN ('win','loss')
GROUP BY confidence_bucket
ORDER BY confidence_bucket DESC
;

-- =============================================================
-- v_inference_tier_efficiency — cost/latency/success per inference tier.
-- Rolled up over the last 7 days of telemetry.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_inference_tier_efficiency` AS
SELECT
  tier,
  model,
  COUNT(*) AS snapshots,
  SUM(requests)    AS total_requests,
  SUM(success)     AS total_success,
  SUM(errors)      AS total_errors,
  SAFE_DIVIDE(SUM(success), SUM(requests)) AS success_rate,
  AVG(avg_latency_ms) AS avg_latency_ms,
  SUM(cost_usd)    AS total_cost_usd,
  SAFE_DIVIDE(SUM(cost_usd), NULLIF(SUM(success), 0)) AS cost_per_success_usd,
  MAX(timestamp)   AS last_observed_at
FROM `tho-ai-agent.sapphire.inference_metrics`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY tier, model
ORDER BY total_requests DESC
;

-- =============================================================
-- v_service_uptime_24h — per-service uptime over the last 24 hours.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_service_uptime_24h` AS
SELECT
  service_name,
  host,
  COUNT(*) AS probes,
  COUNTIF(status = 'healthy')  AS healthy,
  COUNTIF(status = 'degraded') AS degraded,
  COUNTIF(status = 'down')     AS down,
  SAFE_DIVIDE(COUNTIF(status = 'healthy'), COUNT(*)) AS uptime_pct,
  AVG(response_ms)  AS avg_response_ms,
  MAX(timestamp)    AS last_probe_at,
  ARRAY_AGG(DISTINCT error IGNORE NULLS LIMIT 5) AS recent_errors
FROM `tho-ai-agent.sapphire.service_health`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY service_name, host
ORDER BY uptime_pct ASC, service_name
;

-- =============================================================
-- v_open_threats — active critical threats still "open" (hot CVEs).
-- Most recent snapshot per CVE, filtered to HIGH/CRITICAL + exploited/KEV.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_open_threats` AS
WITH latest AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY cve_id ORDER BY timestamp DESC) AS rn
  FROM `tho-ai-agent.sapphire.threat_intel`
)
SELECT
  cve_id,
  severity,
  cvss_score,
  exploited,
  in_kev,
  source,
  description,
  published_at,
  modified_at,
  timestamp AS last_seen_at
FROM latest
WHERE rn = 1
  AND severity IN ('CRITICAL','HIGH')
  AND (exploited OR in_kev OR cvss_score >= 8.5)
ORDER BY cvss_score DESC, last_seen_at DESC
;

-- =============================================================
-- v_prediction_vs_signal_overlap — does the predictor agree with the signal?
-- Joins same-day same-symbol predictions to signals and compares direction.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_prediction_vs_signal_overlap` AS
WITH signals AS (
  SELECT DATE(timestamp) AS d, symbol, direction AS signal_dir,
         AVG(confidence) AS sig_conf, SUM(pnl_usd) AS sig_pnl,
         COUNT(*) AS sig_count
  FROM `tho-ai-agent.sapphire.v_signals_latest`
  GROUP BY d, symbol, direction
),
preds AS (
  SELECT DATE(timestamp) AS d, symbol, direction AS pred_dir,
         AVG(confidence) AS pred_conf, AVG(predicted_move_pct) AS pred_move,
         COUNT(*) AS pred_count
  FROM `tho-ai-agent.sapphire.predictions`
  GROUP BY d, symbol, direction
)
SELECT
  COALESCE(s.d, p.d)           AS date,
  COALESCE(s.symbol, p.symbol) AS symbol,
  s.signal_dir,
  p.pred_dir,
  CASE
    WHEN s.signal_dir IS NULL OR p.pred_dir IS NULL THEN 'no_overlap'
    WHEN s.signal_dir = p.pred_dir                  THEN 'agree'
    ELSE                                                  'disagree'
  END AS consensus,
  s.sig_conf,
  p.pred_conf,
  p.pred_move,
  s.sig_count,
  p.pred_count,
  s.sig_pnl
FROM signals s
FULL OUTER JOIN preds p USING (d, symbol)
ORDER BY date DESC, symbol
;

-- =============================================================
-- v_trading_dashboard — single-row summary for the live dashboard header.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_trading_dashboard` AS
WITH latest_regime AS (
  SELECT regime, score, confidence, btc_price_usd, btc_dominance,
         avg_funding_8h_pct, fear_greed_score, fear_greed_label, timestamp
  FROM `tho-ai-agent.sapphire.market_regime`
  ORDER BY timestamp DESC
  LIMIT 1
),
today_perf AS (
  SELECT
    COUNT(*) AS signals_today,
    COUNTIF(outcome = 'win')  AS wins_today,
    COUNTIF(outcome = 'loss') AS losses_today,
    SUM(pnl_usd) AS pnl_today_usd,
    AVG(confidence) AS avg_confidence_today
  FROM `tho-ai-agent.sapphire.v_signals_latest`
  WHERE DATE(timestamp) = CURRENT_DATE()
),
open_positions AS (
  SELECT COUNT(*) AS open_positions
  FROM `tho-ai-agent.sapphire.v_signals_latest`
  WHERE outcome IS NULL OR outcome = 'open'
)
SELECT
  r.regime,
  r.score                AS regime_score,
  r.confidence           AS regime_confidence,
  r.btc_price_usd,
  r.btc_dominance,
  r.avg_funding_8h_pct,
  r.fear_greed_score,
  r.fear_greed_label,
  r.timestamp            AS regime_observed_at,
  t.signals_today,
  t.wins_today,
  t.losses_today,
  t.pnl_today_usd,
  t.avg_confidence_today,
  o.open_positions,
  CURRENT_TIMESTAMP()    AS generated_at
FROM latest_regime r
CROSS JOIN today_perf t
CROSS JOIN open_positions o
;
