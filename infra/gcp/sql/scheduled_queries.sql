-- Scheduled-query bodies. Each one materializes a summary table that the
-- dashboard can read cheaply. Loaded as scheduled queries via the
-- BigQuery Data Transfer Service (see schedule_queries.sh).

-- ---------------------------------------------------------------
-- 1. Daily signal performance (runs every day at 01:00 UTC)
-- ---------------------------------------------------------------
-- @schedule every 24 hours
CREATE OR REPLACE TABLE `tho-ai-agent.sapphire.daily_performance` AS
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
  AVG(score) AS avg_score,
  CURRENT_TIMESTAMP() AS refreshed_at
FROM `tho-ai-agent.sapphire.trading_signals`
GROUP BY date, symbol
ORDER BY date DESC, symbol;

-- ---------------------------------------------------------------
-- 2. Weekly regime analysis (runs weekly, Mon 02:00 UTC)
-- ---------------------------------------------------------------
-- @schedule every mon 02:00
CREATE OR REPLACE TABLE `tho-ai-agent.sapphire.weekly_regime` AS
SELECT
  DATE_TRUNC(DATE(timestamp), WEEK(MONDAY)) AS week_start,
  regime,
  COUNT(*) AS snapshots,
  AVG(score) AS avg_score,
  AVG(confidence) AS avg_confidence,
  AVG(btc_price_usd) AS avg_btc_price,
  AVG(btc_dominance) AS avg_btc_dominance,
  AVG(avg_funding_8h_pct) AS avg_funding_8h_pct,
  AVG(fear_greed_score) AS avg_fear_greed,
  CURRENT_TIMESTAMP() AS refreshed_at
FROM `tho-ai-agent.sapphire.market_regime`
GROUP BY week_start, regime
ORDER BY week_start DESC, regime;

-- ---------------------------------------------------------------
-- 3. Prediction accuracy rollup (runs daily, 02:00 UTC — after back-fill)
-- ---------------------------------------------------------------
-- @schedule every 24 hours
CREATE OR REPLACE TABLE `tho-ai-agent.sapphire.prediction_accuracy` AS
SELECT
  DATE(timestamp) AS date,
  symbol,
  model,
  COUNT(*) AS total_predictions,
  COUNTIF(accuracy_score IS NOT NULL) AS scored,
  AVG(accuracy_score) AS avg_accuracy,
  AVG(ABS(predicted_move_pct - actual_move_pct)) AS avg_error_pct,
  SAFE_DIVIDE(
    COUNTIF(SIGN(predicted_move_pct) = SIGN(actual_move_pct)
            AND actual_move_pct IS NOT NULL),
    COUNTIF(actual_move_pct IS NOT NULL)
  ) AS direction_accuracy,
  CURRENT_TIMESTAMP() AS refreshed_at
FROM `tho-ai-agent.sapphire.predictions`
GROUP BY date, symbol, model
ORDER BY date DESC, symbol;

-- ---------------------------------------------------------------
-- 4. Threat severity daily trend (runs daily, 03:00 UTC)
-- ---------------------------------------------------------------
-- @schedule every 24 hours
CREATE OR REPLACE TABLE `tho-ai-agent.sapphire.daily_threats` AS
SELECT
  DATE(timestamp) AS date,
  severity,
  COUNT(DISTINCT cve_id) AS cves,
  COUNTIF(exploited) AS exploited_cves,
  COUNTIF(in_kev) AS kev_cves,
  AVG(cvss_score) AS avg_cvss,
  CURRENT_TIMESTAMP() AS refreshed_at
FROM `tho-ai-agent.sapphire.threat_intel`
GROUP BY date, severity
ORDER BY date DESC, severity;
