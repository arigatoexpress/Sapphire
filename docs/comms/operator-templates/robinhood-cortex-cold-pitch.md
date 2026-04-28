---
name: Robinhood corp-dev / Cortex first-touch cold pitch
audience: Robinhood Cortex team lead, corp-dev, or crypto product lead (Foundry-equivalent target)
when_to_use: First-touch outreach to Robinhood, mirroring the Palantir cold-pitch shape but tuned to retail-trading + crypto-native posture.
placeholders: ["{{first_name}}", "{{their_role}}", "{{their_team}}", "{{microsite_url}}", "{{diligence_pr_url}}"]
last_updated: 2026-04-29
provenance_sha: 1bcf221a
---

# Single-engineer crypto-native autonomy stack — possible Cortex / corp-dev fit?

Hi {{first_name}},

I'm a solo engineer running Sapphire OS — an operational control plane for trading research, risk-gated autonomy, and intelligence work. It runs against Robinhood Crypto's v2 order endpoint today, and the first $5 BTC live-capital fill cleared on 2026-04-28 through a manually-confirmed gate that I built specifically because I wasn't going to give a one-engineer project unattended order-submit authority.

I think there's a {{their_team}}-shaped fit here. The pitch:

1. **Operational trust at the model layer.** Every artifact (signal, prediction, draft order) is provenance-stamped — generator, source hashes, prompt hash, model, time, TTL. The risk kernel evaluates a versioned decision envelope before any mutation. Live execution is dry-run by default; one-order confirmation tokens unlock single fills, not loops.
2. **Crypto-native by build, not bolt-on.** The system was hardened for Robinhood Crypto specifically — Ed25519-signed REST, UUID `client_order_id`, just-in-time quote guarding, $5 / $50 / $500 cap ladder with 14-day Sortino-soak gates between rungs. Not a stocks system that learned crypto.
3. **Retail-intelligence surface.** TradingView webhook intake, RSI/MACD/BB/MA/ATR scanner, autonomous prediction engine (61.1% overall accuracy across 36 scored predictions, 83.3% on BTC). Paper portfolio runs continuously; live capital is gated behind the same evidence the paper engine produces.

The primary ask is an integration POC — does Cortex want a partner who's already built the operational guardrails Robinhood would otherwise have to build internally for any third-party signal venue? IP licensing or acqui-hire are second-order paths if the technical review lands.

Diligence packet (10 docs covering architecture, security, data, ops, financials, roadmap): {{diligence_pr_url}}.

Acquirer microsite: {{microsite_url}}.

I'm one person with a working system that respects safety. That's both the strength and the structural reality the conversation has to address.

—Ari

## Notes for the operator (NOT in the sent message)

- Why this works: leads with a concrete proof point (the $5 fill), differentiates from the Palantir pitch by emphasizing retail/crypto-native rather than enterprise-data-fabric, addresses the solo-engineer reality up front rather than hiding it.
- Common edits: swap the Cortex team name based on the actual recipient — corp-dev gets a slightly different second paragraph (less product-y, more capability-y). The 83.3% BTC accuracy is real per CLAUDE.md but verify it's still current before sending.
- Tone calibration: harder than the Palantir pitch — Robinhood's culture is more direct. Avoid the "operational trust" abstraction-first opening that the Palantir version uses; lead with concrete trades and concrete endpoints. Drop a line if it sounds enterprise-y.
- Do NOT reference the $50 or $500 rungs as live targets — they're capped phases, not goals. Frame as ladder/scaffolding.
