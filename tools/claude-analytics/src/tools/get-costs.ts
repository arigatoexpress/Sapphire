import { parseStatsCache, computeCostBreakdown, type StatsCache } from "../parsers/stats-parser.js";

const MODEL_PRICING: Record<string, { input: number; output: number; cacheRead: number; cacheCreate: number }> = {
  "claude-opus-4-6": { input: 15, output: 75, cacheRead: 1.5, cacheCreate: 3.75 },
  "claude-opus-4-5-20251101": { input: 15, output: 75, cacheRead: 1.5, cacheCreate: 3.75 },
  "claude-sonnet-4-5-20250929": { input: 3, output: 15, cacheRead: 0.3, cacheCreate: 0.75 },
  "claude-haiku-4-5-20251001": { input: 0.8, output: 4, cacheRead: 0.08, cacheCreate: 0.2 },
};

function getModelPrice(modelId: string) {
  return MODEL_PRICING[modelId] ?? MODEL_PRICING["claude-sonnet-4-5-20250929"];
}

function estimateDailyCost(stats: StatsCache): Array<{ date: string; cost: number; tokensByModel: Record<string, number> }> {
  return stats.dailyModelTokens.map((day) => {
    let dayCost = 0;
    for (const [modelId, tokens] of Object.entries(day.tokensByModel)) {
      const pricing = getModelPrice(modelId);
      // Daily tokens are output tokens approximation; use average pricing
      const avgPrice = (pricing.input + pricing.output) / 2;
      dayCost += (tokens / 1_000_000) * avgPrice;
    }
    return {
      date: day.date,
      cost: dayCost,
      tokensByModel: day.tokensByModel,
    };
  });
}

export async function getCostBreakdown(claudeDataDir: string) {
  const stats = await parseStatsCache(claudeDataDir);
  const modelBreakdown = computeCostBreakdown(stats);
  const dailyCosts = estimateDailyCost(stats);

  const totalCost = Object.values(modelBreakdown).reduce((sum, m) => sum + m.cost, 0);

  const perModel = Object.entries(stats.modelUsage).map(([modelId, usage]) => {
    const pricing = getModelPrice(modelId);
    return {
      model: modelId,
      displayName: modelId.replace("claude-", "").replace(/-\d{8}$/, ""),
      pricing: {
        inputPerMillion: `$${pricing.input}`,
        outputPerMillion: `$${pricing.output}`,
        cacheReadPerMillion: `$${pricing.cacheRead}`,
        cacheCreatePerMillion: `$${pricing.cacheCreate}`,
      },
      tokens: {
        input: usage.inputTokens.toLocaleString(),
        output: usage.outputTokens.toLocaleString(),
        cacheRead: usage.cacheReadInputTokens.toLocaleString(),
        cacheCreate: usage.cacheCreationInputTokens.toLocaleString(),
      },
      costs: {
        input: `$${((usage.inputTokens / 1_000_000) * pricing.input).toFixed(4)}`,
        output: `$${((usage.outputTokens / 1_000_000) * pricing.output).toFixed(4)}`,
        cacheRead: `$${((usage.cacheReadInputTokens / 1_000_000) * pricing.cacheRead).toFixed(4)}`,
        cacheCreate: `$${((usage.cacheCreationInputTokens / 1_000_000) * pricing.cacheCreate).toFixed(4)}`,
        total: `$${modelBreakdown[modelId].cost.toFixed(4)}`,
      },
    };
  });

  return {
    totalEstimatedCost: `$${totalCost.toFixed(4)}`,
    perModel,
    dailyCosts,
    period: {
      from: stats.firstSessionDate,
      to: stats.lastComputedDate,
    },
  };
}
