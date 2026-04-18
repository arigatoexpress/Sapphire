-- Sapphire BigQuery views + scheduled-query DDL.
-- Run via: bq query --use_legacy_sql=false < views.sql
-- Or load individual queries into the BigQuery Data Transfer Service as
-- scheduled queries (see schedule_queries.sh).

-- =============================================================
-- View: signals_enriched
-- Joins regime context + funding context for any signal.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_signals_enriched` AS
SELECT
  s.signal_id,
  s.symbol,
  s.action,
  s.direction,
  s.score,
  s.confidence,
  s.original_confidence,
  -- Confidence lift from regime-aware enhancer
  SAFE_SUBTRACT(s.confidence, s.original_confidence) AS confidence_lift,
  s.source,
  s.price_at_signal,
  s.outcome,
  s.pnl_usd,
  s.flags,
  s.regime AS signal_regime,
  -- Latest regime snapshot at or before signal time
  r.regime   AS observed_regime,
  r.score    AS regime_score,
  r.confidence AS regime_confidence,
  r.btc_price_usd,
  r.btc_dominance,
  r.avg_funding_8h_pct,
  r.fear_greed_score,
  r.fear_greed_label,
  s.timestamp
FROM `tho-ai-agent.sapphire.trading_signals` s
LEFT JOIN `tho-ai-agent.sapphire.market_regime` r
  ON DATE(s.timestamp) = DATE(r.timestamp)
;

-- =============================================================
-- View: daily_signal_performance (keeps on-the-fly; scheduled query persists)
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_daily_performance` AS
SELECT
  DATE(timestamp) AS date,
  symbol,
  COUNT(*) AS total_signals,
  COUNTIF(outcome = 'win') AS wins,
  COUNTIF(outcome = 'loss') AS losses,
  COUNTIF(outcome IS NULL OR outcome = 'open') AS open_trades,
  SAFE_DIVIDE(COUNTIF(outcome = 'win'), COUNTIF(outcome IN ('win', 'loss'))) AS win_rate,
  SUM(pnl_usd) AS daily_pnl_usd,
  AVG(IF(outcome = 'win', pnl_usd, NULL)) AS avg_win_usd,
  AVG(IF(outcome = 'loss', pnl_usd, NULL)) AS avg_loss_usd,
  SAFE_DIVIDE(
    SUM(IF(outcome = 'win', pnl_usd, 0)),
    ABS(SUM(IF(outcome = 'loss', pnl_usd, 0)))
  ) AS profit_factor,
  AVG(confidence) AS avg_confidence,
  AVG(score) AS avg_score
FROM `tho-ai-agent.sapphire.trading_signals`
WHERE outcome IS NOT NULL
GROUP BY date, symbol
ORDER BY date DESC, symbol
;

-- =============================================================
-- View: prediction_accuracy
-- Only after actual_price_24h is back-filled (nullable for now).
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_prediction_accuracy` AS
SELECT
  DATE(timestamp) AS date,
  symbol,
  model,
  COUNT(*) AS total_predictions,
  COUNTIF(accuracy_score IS NOT NULL) AS scored,
  AVG(accuracy_score) AS avg_accuracy,
  AVG(ABS(predicted_move_pct - actual_move_pct)) AS avg_error_pct,
  -- Directional accuracy (sign match)
  COUNTIF(SIGN(predicted_move_pct) = SIGN(actual_move_pct)
          AND actual_move_pct IS NOT NULL) AS direction_correct,
  COUNTIF(actual_move_pct IS NOT NULL) AS direction_total,
  SAFE_DIVIDE(
    COUNTIF(SIGN(predicted_move_pct) = SIGN(actual_move_pct)
            AND actual_move_pct IS NOT NULL),
    COUNTIF(actual_move_pct IS NOT NULL)
  ) AS direction_accuracy
FROM `tho-ai-agent.sapphire.predictions`
GROUP BY date, symbol, model
ORDER BY date DESC, symbol
;

-- =============================================================
-- View: regime_transitions
-- Consecutive regime runs and their durations.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_regime_transitions` AS
WITH labeled AS (
  SELECT
    regime,
    score,
    confidence,
    timestamp,
    LAG(regime) OVER (ORDER BY timestamp) AS prev_regime
  FROM `tho-ai-agent.sapphire.market_regime`
)
SELECT
  timestamp AS transition_at,
  prev_regime AS from_regime,
  regime AS to_regime,
  score,
  confidence
FROM labeled
WHERE prev_regime IS NOT NULL
  AND prev_regime != regime
ORDER BY transition_at DESC
;

-- =============================================================
-- View: threat_severity_trend
-- Daily threat intel counts by severity.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_threat_severity_trend` AS
SELECT
  DATE(timestamp) AS date,
  severity,
  COUNT(DISTINCT cve_id) AS cves,
  COUNTIF(exploited) AS exploited_cves,
  COUNTIF(in_kev) AS kev_cves,
  AVG(cvss_score) AS avg_cvss
FROM `tho-ai-agent.sapphire.threat_intel`
GROUP BY date, severity
ORDER BY date DESC, severity
;

-- =============================================================
-- View: leads_funnel
-- Lead pipeline snapshot by grade + status.
-- =============================================================
CREATE OR REPLACE VIEW `tho-ai-agent.sapphire.v_leads_funnel` AS
SELECT
  DATE(timestamp) AS date,
  grade,
  status,
  COUNT(*) AS leads,
  AVG(score) AS avg_score,
  SUM(permit_value_usd) AS total_permit_value_usd,
  COUNTIF(contacted) AS contacted
FROM `tho-ai-agent.sapphire.leads`
GROUP BY date, grade, status
ORDER BY date DESC, grade, status
;
