---
name: claude-analytics
description: MCP server for Claude Code usage analytics — sessions, costs, agents
type: tool
runtime: typescript
deploy_target: mac
dependencies: []
entry_point: src/index.ts
test_command: npm test
build_command: npm run build
---

# Claude Analytics Dashboard

## Purpose
TypeScript MCP server that parses Claude Code session data from ~/.claude/ and exposes real-time analytics via 4 tools.

## MCP Tools
- `analytics_overview` — Daily activity, hourly trends, model breakdown
- `analytics_sessions` — Session list with token/tool stats
- `analytics_session_detail` — Per-session tool timeline
- `analytics_costs` — Per-model pricing breakdown

## Key Files
- `src/index.ts` — MCP server entry, tool definitions
- `src/parsers/stats-parser.ts` — Stats cache parsing with pricing
- `src/parsers/history-parser.ts` — JSONL session parser
- `src/watchers/file-watcher.ts` — Real-time data updates
