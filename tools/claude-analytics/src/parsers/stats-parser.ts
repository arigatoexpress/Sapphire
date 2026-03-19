import { readFile } from "node:fs/promises";
import { join } from "node:path";

export interface DailyActivity {
  date: string;
  messageCount: number;
  sessionCount: number;
  toolCallCount: number;
}

export interface DailyModelTokens {
  date: string;
  tokensByModel: Record<string, number>;
}

export interface ModelUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadInputTokens: number;
  cacheCreationInputTokens: number;
  webSearchRequests: number;
  costUSD: number;
  contextWindow: number;
  maxOutputTokens: number;
}

export interface LongestSession {
  sessionId: string;
  duration: number;
  messageCount: number;
  timestamp: string;
}

export interface StatsCache {
  version: number;
  lastComputedDate: string;
  dailyActivity: DailyActivity[];
  dailyModelTokens: DailyModelTokens[];
  modelUsage: Record<string, ModelUsage>;
  totalSessions: number;
  totalMessages: number;
  longestSession: LongestSession;
  firstSessionDate: string;
  hourCounts: Record<string, number>;
  totalSpeculationTimeSavedMs: number;
}

const MODEL_PRICING: Record<string, { input: number; output: number; cacheRead: number; cacheCreate: number }> = {
  "claude-opus-4-6": { input: 15, output: 75, cacheRead: 1.5, cacheCreate: 3.75 },
  "claude-opus-4-5-20251101": { input: 15, output: 75, cacheRead: 1.5, cacheCreate: 3.75 },
  "claude-sonnet-4-5-20250929": { input: 3, output: 15, cacheRead: 0.3, cacheCreate: 0.75 },
  "claude-haiku-4-5-20251001": { input: 0.8, output: 4, cacheRead: 0.08, cacheCreate: 0.2 },
};

function estimateCost(modelId: string, usage: ModelUsage): number {
  const pricing = MODEL_PRICING[modelId] ?? MODEL_PRICING["claude-sonnet-4-5-20250929"];
  const inputCost = (usage.inputTokens / 1_000_000) * pricing.input;
  const outputCost = (usage.outputTokens / 1_000_000) * pricing.output;
  const cacheReadCost = (usage.cacheReadInputTokens / 1_000_000) * pricing.cacheRead;
  const cacheCreateCost = (usage.cacheCreationInputTokens / 1_000_000) * pricing.cacheCreate;
  return inputCost + outputCost + cacheReadCost + cacheCreateCost;
}

export async function parseStatsCache(claudeDataDir: string): Promise<StatsCache> {
  const filePath = join(claudeDataDir, "stats-cache.json");
  const raw = await readFile(filePath, "utf-8");
  return JSON.parse(raw) as StatsCache;
}

export function computeCostBreakdown(stats: StatsCache): Record<string, { cost: number; tokens: number }> {
  const breakdown: Record<string, { cost: number; tokens: number }> = {};
  for (const [modelId, usage] of Object.entries(stats.modelUsage)) {
    const totalTokens = usage.inputTokens + usage.outputTokens + usage.cacheReadInputTokens + usage.cacheCreationInputTokens;
    breakdown[modelId] = {
      cost: estimateCost(modelId, usage),
      tokens: totalTokens,
    };
  }
  return breakdown;
}

export function computeTotalCost(stats: StatsCache): number {
  let total = 0;
  for (const [modelId, usage] of Object.entries(stats.modelUsage)) {
    total += estimateCost(modelId, usage);
  }
  return total;
}
