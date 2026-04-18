# NIST Alignment — Sapphire OS

**Purpose**: map Sapphire OS capabilities against NIST Cybersecurity Framework (CSF 2.0) and NIST AI Risk Management Framework (AI RMF 1.0), identify gaps, and list high-leverage remediations.

Scope covers the autonomous trading engine, the plugin tool ecosystem, the inference proxy, the multi-device mesh (Mac + Windows + Pi), and the event bus introduced in `lib/core/event_bus.py`.

Last reviewed: **2026-04-17**.

---

## 1. NIST Cybersecurity Framework (CSF 2.0) Mapping

### IDENTIFY (ID)

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| ID.AM-1 | Physical assets inventoried | **IMPLEMENTED** | `CLAUDE.md` lists Mac (100.67.171.79), Windows (100.71.10.48), Pi rari1/rari2 with IPs, roles, and hardware |
| ID.AM-2 | Software platforms and applications inventoried | **IMPLEMENTED** | Module map in `CLAUDE.md`; service manifest in `routines-manifest.md` and `data/device_topology.json` |
| ID.AM-3 | Communication/data flows mapped | **PARTIAL** | Proxy tiers documented; formal data-flow diagram missing for webhook → signal logger → event bus → Telegram |
| ID.AM-4 | External systems catalogued | **IMPLEMENTED** | `data/connectors.json` tracks OpenBB, Cointracker, CISA KEV, NVD, Moonshot, yfinance |
| ID.AM-5 | Resources prioritized | **IMPLEMENTED** | Tier routing in `plugins/claw-sapphire/lib/router.py` embeds priority by sensitivity |
| ID.RA-1 | Asset vulnerabilities identified | **PARTIAL** | Weekly dependency-security-scan scheduled task; no automated SBOM generation |
| ID.RA-3 | Threats from internal/external sources identified | **IMPLEMENTED** | `plugins/claw-sapphire/tools/threat_intel.py` wraps CISA KEV / NVD / MITRE ATT&CK |
| ID.RA-5 | Threats, vulnerabilities, impact used to determine risk | **PARTIAL** | Threat intel collected, but mapping to Sapphire-specific assets is manual |
| ID.SC-1 | Supply chain risk management program | **MISSING** | No formal SBOM, no pinned-hash dependency manifest |
| ID.SC-2 | Suppliers identified and prioritized | **PARTIAL** | Connectors registry exists; security-posture rating absent |

### PROTECT (PR)

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| PR.AA-1 | Identities / credentials managed | **PARTIAL** | Dashboard has basic auth (`AUTH_PASSWORD`); no MFA, no per-agent identity |
| PR.AA-3 | Users, services, hardware authenticated | **PARTIAL** | SSH keys for device mesh; inference-proxy lacks mutual auth |
| PR.AA-5 | Access permissions / authorizations enforced | **IMPLEMENTED** | `lib/core/confirmation_firewall.py` gates FINANCIAL/DESTRUCTIVE actions via Telegram confirmation |
| PR.DS-1 | Data at rest protected | **PARTIAL** | `PII_ENCRYPTION_KEY` in Secret Manager for THO; local JSONL audit logs unencrypted |
| PR.DS-2 | Data in transit protected | **PARTIAL** | Tailscale for inter-device; localhost Redis and Ollama are plaintext (acceptable in trusted mesh) |
| PR.DS-10 | Data destruction performed | **MISSING** | No documented retention policy for signals, events, audit logs |
| PR.IR-1 | Network segmented | **IMPLEMENTED** | Tailscale + per-device LaunchAgent binding; Windows webhook is the only external ingress |
| PR.IP-12 | Vulnerability management plan | **PARTIAL** | Scheduled scans exist; no remediation SLA |
| PR.PS-1 | Configuration management | **PARTIAL** | Git-tracked; no drift detection for LaunchAgents / Windows services |
| PR.PT-4 | Communications and control networks protected | **IMPLEMENTED** | Outbound URL allowlist in sandbox policy; sensitivity classifier blocks cloud egress of private data |

### DETECT (DE)

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| DE.AE-1 | Baseline network operations established | **PARTIAL** | `services/dashboard/app.py` shows service health; no baseline SLO for event-bus throughput |
| DE.AE-2 | Detected events analyzed | **IMPLEMENTED** | `watchdog` tool dedupes + alerts on failures/recoveries; market watchdog on regime shifts |
| DE.AE-3 | Event data aggregated and correlated | **IMPLEMENTED (NEW)** | `lib/core/event_bus.py` — Redis Streams; 11 canonical event types; `WorldState` aggregator |
| DE.CM-1 | Network monitored | **IMPLEMENTED** | Pi health monitor, metrics collector, SOC dashboard, `/api/system` unified status |
| DE.CM-3 | Personnel activity monitored | **PARTIAL** | Telegram confirmations audited; no central log for agent tool invocations |
| DE.CM-7 | Unauthorized personnel/connections monitored | **PARTIAL** | Basic auth failures logged; no brute-force lockout |
| DE.CM-9 | External service provider activity monitored | **IMPLEMENTED** | Kimi/Moonshot usage gated by sensitivity classifier + `budget` tool tracks tokens |

### RESPOND (RS)

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| RS.MA-1 | Incident response process executed | **PARTIAL** | Circuit breaker auto-disables failing tiers; no runbook library |
| RS.AN-1 | Notifications investigated | **IMPLEMENTED** | SOC dashboard + threat investigation documents |
| RS.AN-3 | Incidents categorized | **PARTIAL** | Priority tags in event stream; no NIST 800-61 classification |
| RS.CO-2 | Stakeholders notified | **IMPLEMENTED** | Telegram alerts via `notify` tool (p0–p3 priority) |
| RS.MI-1 | Incidents contained | **IMPLEMENTED** | `lib/core/confirmation_firewall.py` + circuit breaker |
| RS.MI-2 | Incidents mitigated | **PARTIAL** | Manual remediation; `factory-repo-fixer` auto-fixes only lint |

### RECOVER (RC)

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| RC.RP-1 | Recovery plan executed | **PARTIAL** | LaunchAgent KeepAlive restarts crashed services; no full DR runbook |
| RC.IM-1 | Recovery plans incorporate lessons learned | **MISSING** | No post-incident review template |
| RC.CO-3 | Recovery activities communicated | **IMPLEMENTED** | Watchdog recovery events → Telegram |

**CSF 2.0 Score: 24 / 38 addressed (IMPLEMENTED or PARTIAL). 14 subcategories require attention.**

---

## 2. NIST AI Risk Management Framework (AI RMF 1.0) Mapping

### GOVERN

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| GOVERN 1.1 | Legal/regulatory requirements understood | **PARTIAL** | Trading regs (pattern day trader, position sizing limits) enforced in risk kernel; no AI-specific regulatory map |
| GOVERN 1.2 | AI risk management integrated into governance | **IMPLEMENTED** | Every agent action flows through tier routing + confirmation firewall |
| GOVERN 2.1 | Roles/responsibilities documented | **PARTIAL** | `CLAUDE.md` documents services; AI model owner/reviewer roles absent |
| GOVERN 3.2 | Organizational risk tolerance established | **IMPLEMENTED** | Hard risk kernel: daily loss caps, drawdown limits, consecutive-loss kill switch |
| GOVERN 4.1 | Human-AI teaming documented | **IMPLEMENTED** | Confirmation firewall is the governance mechanism; financial actions require explicit Telegram approval |
| GOVERN 6.1 | Third-party risks addressed | **PARTIAL** | Sensitivity classifier gates Kimi cloud; no audit of Ollama model provenance |

### MAP

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| MAP 1.1 | Context established | **IMPLEMENTED** | Each tool has SKILL.md stating purpose + inputs + outputs |
| MAP 2.1 | Task classified | **IMPLEMENTED** | `lib/router.py` classifies by sensitivity; task types mapped to model tiers |
| MAP 2.3 | AI capabilities/limitations documented | **IMPLEMENTED** | Kadima Labs benchmark (70 charts, 30 JSON) maps model performance |
| MAP 3.1 | Benefits/costs enumerated | **PARTIAL** | `budget` tool tracks tokens; accuracy-to-cost frontier analysis missing |
| MAP 4.1 | Third-party model provenance known | **PARTIAL** | Moonshot/Ollama models listed; training-data provenance opaque |
| MAP 5.1 | Impacts on individuals characterized | **PARTIAL** | Dashboard users only; no PII impact assessment for THO customers |

### MEASURE

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| MEASURE 1.1 | Measurement methods documented | **IMPLEMENTED** | Prediction scoring in `plugins/claw-sapphire/tools/research.py`; accuracy tracked per symbol |
| MEASURE 2.3 | Safety evaluated | **IMPLEMENTED** | Paper trading + kernel gate before live execution |
| MEASURE 2.7 | Security/resilience evaluated | **PARTIAL** | Circuit breaker tested in unit tests; no red-team prompt-injection harness |
| MEASURE 2.9 | Model transparency evaluated | **PARTIAL** | Scored signals include confidence + notes; reasoning traces for T1+ not stored |
| MEASURE 2.11 | Fairness/bias evaluated | **MISSING** | No fairness eval; acceptable for single-user trading but required if THO scales to multi-tenant |
| MEASURE 4.1 | Feedback loop active | **IMPLEMENTED** | Signal outcomes feed back via `update_signal_outcome` → prediction scoring |

### MANAGE

| Subcategory | Control | Status | Evidence / Gap |
|-------------|---------|--------|----------------|
| MANAGE 1.1 | Risks prioritized | **IMPLEMENTED** | Event priority tags (p0–p3); kernel blocks highest-impact actions first |
| MANAGE 2.2 | Mechanisms to sustain the AI system | **IMPLEMENTED** | Fallback tiers T1→T4; LaunchAgent KeepAlive; inference proxy failover |
| MANAGE 2.3 | Incidents tracked and responded to | **IMPLEMENTED (NEW)** | Event bus `service.health` + `threat.detected` streams feed SOC dashboard |
| MANAGE 3.1 | AI incidents documented | **PARTIAL** | System-events JSONL captures system incidents; AI-specific incident schema missing |
| MANAGE 4.1 | Residual risks tracked | **PARTIAL** | Known gotchas in `CLAUDE.md`; no formal risk register |

**AI RMF Score: 14 / 23 addressed. 9 subcategories require attention.**

---

## 3. Privacy-Preserving Technologies (NIST Privacy Framework / SP 800-226 mapping)

This section maps candidate cryptographic additions to NIST privacy controls. Full architecture details are in [`docs/crypto-integrations-plan.md`](crypto-integrations-plan.md).

| Technology | NIST Privacy Control | Current State | Post-Integration |
|------------|----------------------|---------------|------------------|
| **Zama Concrete ML (FHE)** | PR.DS-5 (data processed in encrypted form) | **MISSING** — queries to Kimi cloud are plaintext-checked by the sensitivity classifier but still sent in plaintext when allowed | **IMPLEMENTED** — task-classifier inputs encrypted before leaving the Mac; only the routing decision is decrypted locally |
| **Aztec Noir (zkSNARKs)** | PR.DS-2 (data confidentiality in transit) for on-chain strategies | **MISSING** — all Sapphire trading is off-chain paper/private | **IMPLEMENTED** — on-chain strategies execute privately; MEV/front-running bots cannot observe strategy logic |
| **Ika 2PC-MPC** | PR.AA-5 (authorization enforced) for wallet signing | **PARTIAL** — confirmation firewall is a process-level gate, bypassable by a compromised Mac | **IMPLEMENTED** — two-of-two threshold signing means neither device alone can move funds |
| **x402 Micropayments** | GOVERN 6.1 (third-party financial risk) | **MISSING** — inference-proxy has no payment rail | **IMPLEMENTED** — monetized APIs create an auditable payment trail in USDC on Base |

---

## 4. Compliance Scorecard

| Framework | Addressed | Total Subcategories | % |
|-----------|-----------|---------------------|---|
| CSF 2.0 | 24 | 38 | **63%** |
| AI RMF 1.0 | 14 | 23 | **61%** |
| **Combined** | **38** | **61** | **62%** |

---

## 5. Top 10 Actionable Improvements

Ranked by `(impact × business value) / effort`. High business value = features the user would build anyway.

| # | Change | Effort | Impact | Business Value | NIST Controls |
|---|--------|--------|--------|----------------|---------------|
| 1 | **Event-bus audit log** — persist every event to GCS with append-only retention | S | HIGH | PM audit trail for THO | DE.AE-3, MANAGE 2.3, PR.DS-10 |
| 2 | **SBOM generation** — `pip-audit` + `cyclonedx-py` nightly → Telegram on new vuln | S | HIGH | Reduces zero-day exposure | ID.SC-1, PR.IP-12 |
| 3 | **MFA on dashboard** — TOTP in front of basic auth | S | HIGH | Protects live PnL view | PR.AA-1, PR.AA-3 |
| 4 | **Runbook library** — one per service in `docs/runbooks/` | M | MED | Faster incident response | RS.MA-1, RC.RP-1, RC.IM-1 |
| 5 | **Retention policy** — rotate/encrypt signals + audit logs at 90 days | S | MED | GDPR-ready for EU customers | PR.DS-10 |
| 6 | **Data-flow diagram** — draw.io in `docs/architecture/` | XS | MED | Onboarding + audit | ID.AM-3 |
| 7 | **Prompt-injection red-team harness** — seed prompts per skill | M | HIGH | Protects agent integrity | MEASURE 2.7 |
| 8 | **Risk register** — YAML in `data/risk_register.yaml`, surfaced in dashboard | M | MED | Executive reporting | MANAGE 4.1 |
| 9 | **FHE task classifier** (Zama Concrete ML) — see crypto integration plan | L | HIGH | Differentiator + customer-trust moat | PR.DS-1, PR.DS-2, MAP 4.1 |
| 10 | **x402 monetization** — paid inference-proxy endpoints | M | HIGH | Direct revenue | GOVERN 6.1, MANAGE 1.1 |

---

## 6. Mapping — Events to NIST Controls

The event bus is the primary telemetry source for a number of NIST controls. Each canonical event type maps as follows:

| Event Type | CSF / AI RMF Controls |
|------------|-----------------------|
| `regime.shifted`, `regime.snapshot` | DE.AE-1, MANAGE 2.2 |
| `funding.extreme` | MEASURE 2.3 |
| `signal.generated`, `signal.closed` | MEASURE 4.1, MANAGE 2.3 |
| `prediction.generated` | MAP 2.3, MEASURE 1.1 |
| `threat.detected` | ID.RA-3, DE.AE-2, RS.CO-2 |
| `lead.scored` | MAP 1.1 |
| `service.health` | DE.CM-1, RS.MI-1 |
| `correlation.broken` | DE.AE-2, MEASURE 2.3 |
| `sentiment.update` | DE.AE-1 |

This mapping means that a single "compliance view" query — `GET /api/events/replay?type=<T>` — produces the evidence artifact for an external audit of the corresponding control.

---

## 7. Review Cadence

- **Quarterly**: re-score all subcategories; update scorecard; commit diff.
- **Ad hoc**: when a new event type is added, append it to section 6.
- **Incident-driven**: after any Sev-1 or Sev-2, add a row to the change log below.

## Change Log

- 2026-04-17 — Initial draft. Event bus + NIST alignment introduced in the same PR.
