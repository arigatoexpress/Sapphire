# Adversarial Intelligence Defense Threat Model

Date: 2026-04-28

## Scope

This threat model covers the first Sapphire adversarial intelligence defense
layer:

- `lib/security/adversarial_detectors.py`
- `lib/security/adversarial_telemetry.py`
- `services/adversarial/run.py`

The layer is defensive and read-only by default. It classifies already-collected
records, emits optional `adversarial.detection` telemetry, and writes a
quarantine report only when `SAPPHIRE_ADVERSARIAL_QUARANTINE=1` is set.

## Assets

- Market/trade records used by research or dashboards.
- Telegram channel intelligence records and channel trust scores.
- Oracle observations, TWAP/reference prices, and cross-source composites.
- Threat-intelligence reports, attribution claims, and confidence labels.
- Prompt/RAG content that can reach local or cloud LLM context.
- Event bus telemetry records.
- Optional quarantine report copies under `data/security/adversarial/quarantine/`.

## Trust Boundaries

- External market venues, public chains, and market-making entities are outside
  Sapphire trust.
- Telegram and other messaging apps are outside Sapphire trust.
- Oracle providers are partially trusted only after cross-source reconciliation.
- External threat-intel sources are claims until confidence and collection basis
  are preserved.
- Any prompt, webpage, file, Telegram post, or report text that can enter an
  LLM is untrusted content.
- The local event bus is trusted only for sanitized metadata, not raw sensitive
  records.

## Abuse Paths And Controls

| Abuse path | Real case anchor | Sapphire detector | Default control |
|---|---|---|---|
| Artificial volume through self-trading or reciprocal wash trades | The SEC alleged crypto market makers used self-trading/wash trading and bots to create artificial volume; DOJ later described Gotbit wash-trading tactics and multiple-account evasion. | `WashTradeDetector` | Flag same-account trades and reciprocal round trips; no upstream trade mutation. |
| Bot-amplified pump channel | CFTC warned that WhatsApp, Telegram, and similar apps are used to lure users into crypto pump-and-dump schemes; Xu and Livshits studied 412 Telegram-organized crypto pump events. | `BotPumpedChannelDetector` | Flag pump/profit/bot language and burst coordination; require cross-source confirmation. |
| Oracle manipulation or reference-price outlier | CFTC charged the Mango Markets case as an oracle manipulation scheme where MNGO oracle price jumped over 13x in 30 minutes; CREAM incidents show DeFi collateral/borrow logic can fail around token integration and price derivation. | `OracleAnomalyDetector` | Flag reference divergence and cross-source outliers; do not use outlier source in composite without review. |
| Prompt injection against agent or RAG context | OWASP LLM01 describes direct and indirect prompt injection, including sensitive data disclosure, unauthorized function access, and arbitrary command execution through connected systems. | `PromptInjectionDetector` | Strip or quarantine untrusted content before model context; do not execute tool requests from scanned content. |
| False-flag or overconfident attribution | Mandiant notes that attribution requires confidence discipline and that GRU-linked operations have used personas and feigned extortion to create psychological and attribution effects. | `FalseFlagThreatIntelDetector` | Separate claimed actor, assessed actor, and confidence; downgrade hard claims when confidence is low. |

## Safety Guarantees

- Detectors are pure functions: they do not read environment variables, make
  network calls, send Telegram messages, or place orders.
- The service CLI defaults to printing a JSON report only.
- `--emit` is required before telemetry is published.
- `SAPPHIRE_ADVERSARIAL_QUARANTINE=1` is required before a quarantine report is
  written.
- Quarantine is report-copy-only. It records input path and SHA-256, not raw
  upstream data, and sets `upstream_mutated=false`.
- No detector is on a trading critical path. Findings are advisory control
  signals for review, downweighting, exclusion, or source-quality triage.
- Telemetry sanitizes token-shaped and secret-shaped text before publishing.

## Residual Risk

- Heuristics are conservative and can miss novel manipulation that lacks the
  covered patterns.
- A finding is not proof of fraud or compromise; it is a review trigger.
- Clean baselines are protected by tests, but a real venue, Telegram channel, or
  source may have domain-specific behavior that needs allowlisting in a future
  version.
- Cross-source oracle detection requires at least three source observations in
  a comparable time bucket.
- False-flag detection can only flag inconsistent claim structure; it cannot
  perform strategic attribution.

## Rollback

Revert the PR or remove callers to `services/adversarial/run.py`. Because the
layer does not mutate upstream signal data by default, rollback does not require
data repair. If opt-in quarantine was used, delete only the generated report
copy under the quarantine directory after preserving it if an investigation is
active.

## Sources

- SEC, "SEC Charges Three So-Called Market Makers and Nine Individuals in Crackdown on Manipulation of Crypto Assets Offered and Sold as Securities", 2024-10-09: https://www.sec.gov/newsroom/press-releases/2024-166
- DOJ, "Cryptocurrency Financial Services Firm Gotbit and Founder Plead Guilty to Market Manipulation and Fraud Conspiracy", 2025-03-21: https://www.justice.gov/usao-ma/pr/cryptocurrency-financial-services-firm-gotbit-and-founder-plead-guilty-market
- CFTC, "CFTC Charges Avraham Eisenberg with Manipulative and Deceptive Scheme to Misappropriate Over $110 million from Mango Markets", 2023-01-09: https://www.cftc.gov/PressRoom/PressReleases/8647-23
- C.R.E.A.M. Finance, "C.R.E.A.M. Finance Post Mortem: AMP Exploit", 2021-09-01: https://medium.com/cream-finance/c-r-e-a-m-finance-post-mortem-amp-exploit-6ceb20a630c5
- Immunefi, "Hack Analysis: Cream Finance Oct 2021", 2022-11-09: https://medium.com/immunefi/hack-analysis-cream-finance-oct-2021-fc222d913fc5
- CFTC, "CFTC Warns of Potential Dangers for Messaging App Users", 2024-10-31: https://www.cftc.gov/PressRoom/PressReleases/9005-24
- Xu and Livshits, "The Anatomy of a Cryptocurrency Pump-and-Dump Scheme", arXiv:1811.10109: https://arxiv.org/abs/1811.10109
- Mandiant, "Navigating the Trade-Offs of Cyber Attribution", 2023-01-17: https://cloud.google.com/blog/topics/threat-intelligence/trade-offs-attribution/
- Mandiant, "The GRU's Disruptive Playbook", 2023-08-31: https://cloud.google.com/blog/topics/threat-intelligence/gru-disruptive-playbook
- OWASP GenAI Security Project, "LLM01:2025 Prompt Injection": https://genai.owasp.org/llmrisk/llm01-prompt-injection/
