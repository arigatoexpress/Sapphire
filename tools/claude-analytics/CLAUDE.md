# Claude Analytics MCP

TypeScript MCP server for Claude Code usage metrics — token spend, session cost, model breakdown.

## Status

Built but not deployed as an MCP server. The analytics functionality is now handled by:
- `plugins/claw-sapphire/tools/budget.py` — real-time token tracking per tier
- `plugins/claw-sapphire/lib/token_governor.py` — daily budget enforcement

## Commands

```bash
cd tools/claude-analytics
npm install
npm run build
```

## Code Style

- TypeScript strict mode
- No `any` types
