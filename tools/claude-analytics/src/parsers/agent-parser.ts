import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import { parseSessionFile, type SessionMessage } from "./history-parser.js";

export interface AgentNode {
  agentId: string;
  parentSessionId: string;
  messageCount: number;
  toolCalls: { name: string; count: number }[];
  models: string[];
  startTime: string;
  endTime: string;
  totalInputTokens: number;
  totalOutputTokens: number;
}

export interface AgentWorkflow {
  sessionId: string;
  project: string;
  agents: AgentNode[];
  totalAgents: number;
}

function extractAgentSummary(agentId: string, messages: SessionMessage[]): AgentNode | null {
  if (messages.length === 0) return null;

  const toolCallMap = new Map<string, number>();
  const modelsSet = new Set<string>();
  let totalInput = 0;
  let totalOutput = 0;

  for (const msg of messages) {
    if (msg.type === "assistant") {
      const usage = msg.message?.usage;
      if (usage) {
        totalInput += usage.input_tokens ?? 0;
        totalOutput += usage.output_tokens ?? 0;
      }
      if (msg.message?.model) modelsSet.add(msg.message.model);

      const content = msg.message?.content;
      if (Array.isArray(content)) {
        for (const block of content) {
          if (block.type === "tool_use") {
            const count = toolCallMap.get(block.name) ?? 0;
            toolCallMap.set(block.name, count + 1);
          }
        }
      }
    }
  }

  const first = messages[0];
  const last = messages[messages.length - 1];

  return {
    agentId,
    parentSessionId: first.sessionId,
    messageCount: messages.length,
    toolCalls: Array.from(toolCallMap.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count),
    models: Array.from(modelsSet),
    startTime: first.timestamp,
    endTime: last.timestamp,
    totalInputTokens: totalInput,
    totalOutputTokens: totalOutput,
  };
}

export async function parseAgentWorkflows(claudeDataDir: string): Promise<AgentWorkflow[]> {
  const projectsDir = join(claudeDataDir, "projects");
  const workflows: AgentWorkflow[] = [];

  try {
    const projectDirs = await readdir(projectsDir);

    for (const projDir of projectDirs) {
      const projPath = join(projectsDir, projDir);
      const projStat = await stat(projPath);
      if (!projStat.isDirectory()) continue;

      // Look for session directories that contain subagents/
      const sessionDirs = await readdir(projPath);
      for (const sessionDir of sessionDirs) {
        const sessionPath = join(projPath, sessionDir);
        const sessionStat = await stat(sessionPath);
        if (!sessionStat.isDirectory()) continue;

        const subagentsPath = join(sessionPath, "subagents");
        try {
          const subagentFiles = await readdir(subagentsPath);
          const agents: AgentNode[] = [];

          for (const agentFile of subagentFiles) {
            if (!agentFile.endsWith(".jsonl")) continue;
            const agentId = agentFile.replace(".jsonl", "").replace("agent-", "");
            const messages = await parseSessionFile(join(subagentsPath, agentFile));
            const summary = extractAgentSummary(agentId, messages);
            if (summary) agents.push(summary);
          }

          if (agents.length > 0) {
            // Derive project name from the encoded directory name
            const project = projDir.replace(/-/g, "/").replace(/^\//, "");
            workflows.push({
              sessionId: sessionDir,
              project,
              agents,
              totalAgents: agents.length,
            });
          }
        } catch {
          // No subagents directory
        }
      }
    }
  } catch {
    // Projects dir may not exist
  }

  return workflows;
}
