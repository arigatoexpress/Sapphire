import { parseStatsCache, computeTotalCost, computeCostBreakdown } from "../parsers/stats-parser.js";
import { listProjectSessions } from "../parsers/history-parser.js";

export async function getOverview(claudeDataDir: string) {
  const stats = await parseStatsCache(claudeDataDir);
  const totalCost = computeTotalCost(stats);
  const costBreakdown = computeCostBreakdown(stats);
  const sessionFiles = await listProjectSessions(claudeDataDir);

  const modelSummaries = Object.entries(costBreakdown).map(([model, data]) => ({
    model: model.replace("claude-", "").replace(/-\d{8}$/, ""),
    modelId: model,
    estimatedCost: `$${data.cost.toFixed(4)}`,
    totalTokens: data.tokens.toLocaleString(),
  }));

  return {
    overview: {
      totalSessions: stats.totalSessions,
      totalMessages: stats.totalMessages.toLocaleString(),
      estimatedTotalCost: `$${totalCost.toFixed(4)}`,
      firstSession: stats.firstSessionDate,
      lastComputed: stats.lastComputedDate,
      projectSessionFiles: sessionFiles.length,
    },
    dailyActivity: stats.dailyActivity,
    dailyModelTokens: stats.dailyModelTokens,
    modelSummaries,
    longestSession: {
      sessionId: stats.longestSession.sessionId,
      messages: stats.longestSession.messageCount.toLocaleString(),
      durationHours: (stats.longestSession.duration / 3600).toFixed(1),
      date: stats.longestSession.timestamp,
    },
    hourlyDistribution: stats.hourCounts,
  };
}
