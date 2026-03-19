import { parseAgentWorkflows } from "../parsers/agent-parser.js";

export async function getAgentWorkflows(claudeDataDir: string) {
  const workflows = await parseAgentWorkflows(claudeDataDir);

  return {
    workflows: workflows.map((w) => ({
      sessionId: w.sessionId,
      project: w.project,
      totalAgents: w.totalAgents,
      agents: w.agents.map((a) => ({
        agentId: a.agentId,
        messages: a.messageCount,
        inputTokens: a.totalInputTokens.toLocaleString(),
        outputTokens: a.totalOutputTokens.toLocaleString(),
        topTools: a.toolCalls.slice(0, 5),
        models: a.models,
        startTime: a.startTime,
        endTime: a.endTime,
      })),
    })),
    totalWorkflows: workflows.length,
    totalAgents: workflows.reduce((sum, w) => sum + w.totalAgents, 0),
  };
}
