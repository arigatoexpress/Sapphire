import { createReadStream } from "node:fs";
import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import { createInterface } from "node:readline";

export interface TokenUsage {
  input_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
  output_tokens: number;
  service_tier?: string;
  inference_geo?: string;
}

export interface ToolUseContent {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface TextContent {
  type: "text";
  text: string;
}

export interface ToolResultContent {
  type: "tool_result";
  tool_use_id: string;
  content: string;
}

export type MessageContent = ToolUseContent | TextContent | ToolResultContent;

export interface SessionMessage {
  parentUuid: string | null;
  isSidechain: boolean;
  userType: string;
  cwd: string;
  sessionId: string;
  version: string;
  gitBranch: string;
  type: "user" | "assistant" | "queue-operation";
  message: {
    role?: "user" | "assistant";
    model?: string;
    content?: string | MessageContent[];
    usage?: TokenUsage;
    stop_reason?: string;
  };
  uuid: string;
  timestamp: string;
  requestId?: string;
  permissionMode?: string;
}

export interface SessionSummary {
  sessionId: string;
  project: string;
  startTime: string;
  endTime: string;
  messageCount: number;
  userMessageCount: number;
  assistantMessageCount: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCacheReadTokens: number;
  totalCacheCreateTokens: number;
  toolCalls: { name: string; count: number }[];
  models: string[];
}

export async function parseSessionFile(filePath: string): Promise<SessionMessage[]> {
  const messages: SessionMessage[] = [];
  const fileStream = createReadStream(filePath, { encoding: "utf-8" });
  const rl = createInterface({ input: fileStream, crlfDelay: Infinity });

  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      const parsed = JSON.parse(line) as SessionMessage;
      messages.push(parsed);
    } catch {
      // Skip malformed lines
    }
  }
  return messages;
}

export function summarizeSession(messages: SessionMessage[]): SessionSummary | null {
  if (messages.length === 0) return null;

  const firstMsg = messages.find((m) => m.type !== "queue-operation");
  if (!firstMsg) return null;

  const toolCallMap = new Map<string, number>();
  const modelsSet = new Set<string>();
  let totalInput = 0;
  let totalOutput = 0;
  let totalCacheRead = 0;
  let totalCacheCreate = 0;
  let userCount = 0;
  let assistantCount = 0;

  for (const msg of messages) {
    if (msg.type === "user") userCount++;
    if (msg.type === "assistant") {
      assistantCount++;
      const usage = msg.message?.usage;
      if (usage) {
        totalInput += usage.input_tokens ?? 0;
        totalOutput += usage.output_tokens ?? 0;
        totalCacheRead += usage.cache_read_input_tokens ?? 0;
        totalCacheCreate += usage.cache_creation_input_tokens ?? 0;
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

  const lastMsg = messages[messages.length - 1];
  const toolCalls = Array.from(toolCallMap.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);

  return {
    sessionId: firstMsg.sessionId,
    project: firstMsg.cwd,
    startTime: firstMsg.timestamp,
    endTime: lastMsg.timestamp,
    messageCount: messages.length,
    userMessageCount: userCount,
    assistantMessageCount: assistantCount,
    totalInputTokens: totalInput,
    totalOutputTokens: totalOutput,
    totalCacheReadTokens: totalCacheRead,
    totalCacheCreateTokens: totalCacheCreate,
    toolCalls,
    models: Array.from(modelsSet),
  };
}

export async function listProjectSessions(claudeDataDir: string): Promise<string[]> {
  const projectsDir = join(claudeDataDir, "projects");
  const sessions: string[] = [];

  try {
    const projectDirs = await readdir(projectsDir);
    for (const projDir of projectDirs) {
      const projPath = join(projectsDir, projDir);
      const projStat = await stat(projPath);
      if (!projStat.isDirectory()) continue;

      const files = await readdir(projPath);
      for (const file of files) {
        if (file.endsWith(".jsonl")) {
          sessions.push(join(projPath, file));
        }
      }
    }
  } catch {
    // Projects dir may not exist
  }
  return sessions;
}
