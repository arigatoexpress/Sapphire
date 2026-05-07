# AgentWiki x402 MCP

Use this local MCP surface when an agent needs to discover, quote, fetch, or
audit Sapphire AgentWiki x402 artifacts through the authenticated dashboard
routes.

## Tools

- `wiki_search` - search the static rights-labeled AgentWiki seed registry.
- `wiki_quote` - return quote, rights, and payment requirement context.
- `wiki_fetch_paid` - call the x402 content route. Without a payment header or
  explicit `simulate_payment=true`, this returns the HTTP 402 requirement.
- `wiki_receipt` - read non-secret x402 receipt records from the local JSONL
  ledger.

## Local Command

```bash
python3 /Users/aribs/Code/Sapphire/tools/agentwiki_x402_mcp/server.py
```

The server reads dashboard auth from `SAPPHIRE_DASHBOARD_PASSWORD`,
`AUTH_PASSWORD`, or `~/.config/sapphire-secrets/dashboard_password`.

## Safety

This MCP does not crawl, bypass paywalls, settle payments, trade, send
Telegram messages, or mutate production systems. Simulated payment headers are
only built when a caller explicitly passes `simulate_payment=true`, and the raw
header is never returned in tool output.
