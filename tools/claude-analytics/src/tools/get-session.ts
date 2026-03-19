import { listProjectSessions, parseSessionFile, summarizeSession } from "../parsers/history-parser.js";

export async function getSessionList(claudeDataDir: string) {
  const sessionFiles = await listProjectSessions(claudeDataDir);
  const summaries = [];

  for (const file of sessionFiles) {
    const messages = await parseSessionFile(file);
    const summary = summarizeSession(messages);
    if (summary) summaries.push(summary);
  }

  summaries.sort((a, b) => b.startTime.localeCompare(a.startTime));

  return {
    sessions: summaries.map((s) => ({
      sessionId: s.sessionId,
      project: s.project,
      startTime: s.startTime,
      endTime: s.endTime,
      messages: s.messageCount,
      userMessages: s.userMessageCount,
      assistantMessages: s.assistantMessageCount,
      inputTokens: s.totalInputTokens.toLocaleString(),
      outputTokens: s.totalOutputTokens.toLocaleString(),
      cacheReadTokens: s.totalCacheReadTokens.toLocaleString(),
      cacheCreateTokens: s.totalCacheCreateTokens.toLocaleString(),
      topTools: s.toolCalls.slice(0, 5),
      models: s.models,
    })),
    totalSessions: summaries.length,
  };
}

export async function getSessionDetail(claudeDataDir: string, sessionId: string) {
  const sessionFiles = await listProjectSessions(claudeDataDir);
  const matchingFile = sessionFiles.find((f) => f.includes(sessionId));

  if (!matchingFile) {
    return { error: `Session ${sessionId} not found` };
  }

  const messages = await parseSessionFile(matchingFile);
  const summary = summarizeSession(messages);

  // Build a timeline of tool calls
  const toolTimeline = messages
    .filter((m) => m.type === "assistant" && Array.isArray(m.message?.content))
    .flatMap((m) => {
      const content = m.message.content as Array<{ type: string; name?: string; id?: string }>;
      return content
        .filter((c) => c.type === "tool_use")
        .map((c) => ({
          timestamp: m.timestamp,
          tool: c.name,
          toolCallId: c.id,
          model: m.message.model,
        }));
    });

  // Token usage per message
  const tokenTimeline = messages
    .filter((m) => m.type === "assistant" && m.message?.usage)
    .map((m) => ({
      timestamp: m.timestamp,
      inputTokens: m.message.usage!.input_tokens,
      outputTokens: m.message.usage!.output_tokens,
      cacheRead: m.message.usage!.cache_read_input_tokens,
      cacheCreate: m.message.usage!.cache_creation_input_tokens,
    }));

  return {
    summary,
    toolTimeline,
    tokenTimeline,
    totalMessages: messages.length,
  };
}
