# Sapphire Flowise Playbook

## Flow 1: Operator Intelligence Copilot (Read-only)

Purpose:
- Give a single conversational surface for platform state and strategy posture.

Nodes:
1. Chat Input
2. HTTP Request (`/api/platform/agent-context?hours=24`)
3. Prompt Template:
   - summarize status, reject-tax, GO/NO-GO, and top lane risks
   - output actions in priority order
4. LLM node
5. Chat Output

## Flow 2: Strategy Review Board

Purpose:
- Daily or ad-hoc ranking of lanes for promote/hold/deprioritize.

Nodes:
1. Trigger / Chat Input
2. HTTP Request (`/api/platform/strategy-ops?days=7`)
3. Prompt Template:
   - produce lane table with score, reject-tax, hard-fail, pnl
   - recommend next action for each lane
4. LLM node
5. Output

## Flow 3: Market Regime Digest

Purpose:
- Combine intel + execution posture into one concise daily brief.

Nodes:
1. Trigger
2. HTTP Request (`/api/platform/intel-summary?hours=24`)
3. HTTP Request (`/api/platform/metrics`)
4. Prompt Template:
   - market regime, catalysts, risk posture, operational posture
5. LLM node
6. Output

## Guardrails

- Keep all tool nodes read-only.
- Do not add private execution tokens in public or shared Flowise environments.
- For private team use, run Flowise behind IAM/private ingress and audit all tool nodes.
