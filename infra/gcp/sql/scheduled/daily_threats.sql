CREATE OR REPLACE TABLE `tho-ai-agent.sapphire.daily_threats` AS
SELECT
  DATE(timestamp) AS date,
  severity,
  COUNT(DISTINCT cve_id) AS cves,
  COUNTIF(exploited) AS exploited_cves,
  COUNTIF(in_kev)   AS kev_cves,
  AVG(cvss_score)   AS avg_cvss,
  CURRENT_TIMESTAMP() AS refreshed_at
FROM `tho-ai-agent.sapphire.threat_intel`
GROUP BY date, severity
ORDER BY date DESC, severity
