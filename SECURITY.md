# Security policy

Sapphire OS runs on-prem trading, intelligence, and content infrastructure
for a single operator. Surface area that touches capital movement, PII,
credentials, or on-chain state is considered security-critical.

## Reporting a vulnerability

**If the finding is sensitive, embargoed, or directly exploitable against the
running mesh, do NOT open a GitHub issue.** GitHub issues are world-readable.

Instead:

1. Telegram-DM the operator (`@arigatoexpress` on GitHub — ask via a private
   channel for the Telegram handle).
2. The first message should include severity, a one-paragraph description,
   and a reproduction *hash* (e.g., `sha256sum of the payload` — NOT the
   payload itself). This lets us coordinate without leaking the exploit.
3. The operator will respond with a private channel (Signal, age-encrypted
   mail) for the full report.

For **non-sensitive findings** (hardening suggestions, scanner-rule gaps,
drift between code and docs): open a GitHub issue with the `security` label
and fill out the `bug` issue template.

## Disclosure windows

| Severity | Private coordination window before public | Patch SLA |
|---|---|---|
| **Critical** (RCE, secret exfil, classifier bypass reaching prod) | 24 hours | 7 days |
| **High** (prompt-injection with bounded impact, scanner evasion with theoretical impact) | 14 days | 30 days |
| **Medium / Low / Informational** | No embargo | Best-effort |

Public writeups, talks, or blog posts naming Sapphire require operator review
before publication during the embargo. After the embargo ends, the researcher
owns the disclosure narrative.

## What's in scope

The primary audit surface — for both external researchers and Dependabot /
CI scanners — is enumerated in
[docs/onboarding/ai-redteam-scope.md](docs/onboarding/ai-redteam-scope.md).
Concrete highlights:

- **Inference proxy + sensitivity classifier**
  (`services/inference-proxy/app.py`,
  `plugins/claw-sapphire/lib/sensitivity_classifier.py`) — bypasses that
  route sensitive content to the T4 cloud tier.
- **Model integrity** (`lib/security/model_monitor.py`) — Ollama blob
  SHA-256 + Jinja2 backdoor scanner.
- **Secret storage and auth** — SOPS + age at rest, Ed25519-signed
  Robinhood Crypto, Tailscale mesh with 6 ACL trust zones.
- **Webhook surface** (`services/webhook/`) — only external-facing HTTP
  endpoint; runs on the Windows node.
- **Trading / risk kernel** (`lib/core/`, `lib/analytics/risk_engine.py`,
  `lib/portfolio/robinhood.py`) — circuit breaker, confirmation firewall,
  kill switches.
- **On-chain contracts** (`contracts/SapphireSignalVerifier.sol`,
  `contracts/SapphirePaymentGate.sol`) — Robinhood Chain (Arbitrum Orbit
  testnet, chain ID 46630).

## What's out of scope

- Denial-of-service or sustained load against any live service.
- Social engineering against the operator, client contacts, or collaborators.
- Physical attacks on the mesh nodes (Mac, Windows GPU, Raspberry Pis).
- Exfiltration of real user data or credentials — use synthetic fixtures.
- Cloud-provider attacks (GCP, Moonshot, Cloudflare Tunnel, Tailscale
  infrastructure) — against their ToS and outside our authority.

## Automated scanning

Sapphire's own CI scans the codebase on every push + PR:
- `gitleaks` (secrets) — `.github/workflows/ci.yml`
- `bandit` (Python SAST) — `.github/workflows/security.yml`, daily
- `trivy` (filesystem CVE / IaC) — daily, SARIF uploaded to GitHub Security
- `osv-scanner` (CVE lookup) — daily

Plus the first-party runtime stack: `lib/security/dependency_scanner.py`
(OSV.dev + CycloneDX 1.6 SBOM), `lib/security/model_monitor.py` (model
integrity), `lib/security/network_mapper.py` (Tailscale topology).

## Credit + compensation

- Findings ship in a `CHANGELOG`-style security advisory section of this
  repo (to be created with first accepted finding).
- Rule contributions to `lib/security/model_monitor.py` are attributed in a
  header comment on the added detection.
- Paid bounty engagements are negotiable directly with the operator. Bring
  a scope, timeline, and deliverable; get a written agreement before paid
  work begins.

---

*Questions about scope, rules of engagement, or setup: read
[docs/onboarding/ai-redteam-scope.md](docs/onboarding/ai-redteam-scope.md) or
DM the operator.*
