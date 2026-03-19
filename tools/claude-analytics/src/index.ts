#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { getOverview } from "./tools/get-overview.js";
import { getSessionList, getSessionDetail } from "./tools/get-session.js";
import { getAgentWorkflows } from "./tools/get-agents.js";
import { getCostBreakdown } from "./tools/get-costs.js";
import { getDebugSummary } from "./parsers/debug-parser.js";
import { ClaudeFileWatcher } from "./watchers/file-watcher.js";
import { exec } from "node:child_process";

const CLAUDE_DATA_DIR = process.env.CLAUDE_DATA_DIR ?? `${process.env.HOME}/.claude`;
const DASHBOARD_PORT = process.env.DASHBOARD_PORT ?? "5173";

const server = new McpServer({
  name: "claude-analytics",
  version: "1.0.0",
});

// Start file watcher for real-time events
const watcher = new ClaudeFileWatcher(CLAUDE_DATA_DIR);
watcher.start();

// Tool: Get Overview
server.tool(
  "analytics_overview",
  "Get an overview of Claude Code usage: total sessions, messages, token counts, estimated costs, daily activity trends, and model usage breakdown",
  {},
  async () => {
    try {
      const data = await getOverview(CLAUDE_DATA_DIR);
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Error fetching overview: ${err}` }],
        isError: true,
      };
    }
  }
);

// Tool: Get Session List
server.tool(
  "analytics_sessions",
  "List all Claude Code sessions with summaries: token counts, tool calls, models used, timestamps. Shows per-project session data.",
  {},
  async () => {
    try {
      const data = await getSessionList(CLAUDE_DATA_DIR);
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Error fetching sessions: ${err}` }],
        isError: true,
      };
    }
  }
);

// Tool: Get Session Detail
server.tool(
  "analytics_session_detail",
  "Get detailed info for a specific session: tool call timeline, per-message token usage, and full session summary",
  {
    sessionId: z.string().describe("The session UUID to get details for"),
  },
  async ({ sessionId }) => {
    try {
      const data = await getSessionDetail(CLAUDE_DATA_DIR, sessionId);
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Error fetching session detail: ${err}` }],
        isError: true,
      };
    }
  }
);

// Tool: Get Agent Workflows
server.tool(
  "analytics_agents",
  "Get multi-agent workflow data: subagent trees, tool call chains, token usage per agent, models used in agent orchestration",
  {},
  async () => {
    try {
      const data = await getAgentWorkflows(CLAUDE_DATA_DIR);
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Error fetching agent workflows: ${err}` }],
        isError: true,
      };
    }
  }
);

// Tool: Get Cost Breakdown
server.tool(
  "analytics_costs",
  "Get detailed cost estimates: per-model pricing, token breakdown by type (input/output/cache), daily cost trends",
  {},
  async () => {
    try {
      const data = await getCostBreakdown(CLAUDE_DATA_DIR);
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Error fetching cost breakdown: ${err}` }],
        isError: true,
      };
    }
  }
);

// Tool: Get Debug Summary
server.tool(
  "analytics_debug",
  "Get debug log summary: error counts, recent errors, log level distribution, system health indicators",
  {},
  async () => {
    try {
      const data = await getDebugSummary(CLAUDE_DATA_DIR);
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Error fetching debug summary: ${err}` }],
        isError: true,
      };
    }
  }
);

// Tool: Start Dashboard
server.tool(
  "start_dashboard",
  "Launch the Claude Analytics web dashboard in the default browser. Starts the Vite dev server if not already running.",
  {},
  async () => {
    try {
      const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT ?? process.cwd().replace("/server/dist", "");
      const dashboardDir = `${pluginRoot}/dashboard`;

      // Open the dashboard URL
      exec(`open http://localhost:${DASHBOARD_PORT}`);

      return {
        content: [{
          type: "text",
          text: `Dashboard opening at http://localhost:${DASHBOARD_PORT}\n\nTo start the dev server manually:\n  cd ${dashboardDir} && npm run dev`,
        }],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Error launching dashboard: ${err}` }],
        isError: true,
      };
    }
  }
);

// Start the MCP server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error("Fatal error starting MCP server:", err);
  process.exit(1);
});

// Cleanup on exit
process.on("SIGINT", async () => {
  await watcher.stop();
  process.exit(0);
});
process.on("SIGTERM", async () => {
  await watcher.stop();
  process.exit(0);
});
