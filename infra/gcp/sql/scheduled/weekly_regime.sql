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
ORDER BY week_start DESC, regime
