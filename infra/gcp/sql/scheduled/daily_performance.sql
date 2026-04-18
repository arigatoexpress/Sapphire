CREATE OR REPLACE TABLE `tho-ai-agent.sapphire.daily_performance` AS
SELECT
  DATE(timestamp) AS date,
  symbol,
  COUNT(*) AS total_signals,
  COUNTIF(outcome = 'win') AS wins,
  COUNTIF(outcome = 'loss') AS losses,
  COUNTIF(outcome IS NULL OR outcome = 'open') AS open_trades,
  SAFE_DIVIDE(COUNTIF(outcome = 'win'), COUNTIF(outcome IN ('win','loss'))) AS win_rate,
  SUM(pnl_usd) AS daily_pnl_usd,
  AVG(IF(outcome = 'win',  pnl_usd, NULL)) AS avg_win_usd,
  AVG(IF(outcome = 'loss', pnl_usd, NULL)) AS avg_loss_usd,
  SAFE_DIVIDE(
    SUM(IF(outcome = 'win',  pnl_usd, 0)),
    ABS(SUM(IF(outcome = 'loss', pnl_usd, 0)))
  ) AS profit_factor,
  AVG(confidence) AS avg_confidence,
  AVG(score)      AS avg_score,
  CURRENT_TIMESTAMP() AS refreshed_at
FROM `tho-ai-agent.sapphire.trading_signals`
GROUP BY date, symbol
ORDER BY date DESC, symbol
