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
ORDER BY date DESC, symbol
