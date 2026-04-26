# Sapphire OS — AI / Open-Source Model Red-Team Scope

*This is the scope-of-engagement document for researchers pentesting the
open-source model layer inside Sapphire. Read
[collaborator-pack.md](collaborator-pack.md) first for project context.*

---

## 1. Why this engagement exists

Sapphire runs **28 open-source LLMs** on a private GPU node (`100.71.10.48`,
RTX 5070 Ti 16 GB), routed through a **4-tier sensitivity-gated proxy**, with
a **first-party model-integrity scanner** that fingerprints Ollama blobs and
searches Jinja2 templates for known backdoor patterns. All of that is
**self-attesting at runtime, with no third-party adversarial validation yet.**

We want a red-teamer to find the gaps. That's the engagement.

## 2. Assets in scope

### 2.1 Primary attack surface

| Surface | Location | What we want tested |
|---|---|---|
| **Sensitivity classifier** | `plugins/claw-sapphire/lib/sensitivity_classifier.py` | Bypasses: prompts that smuggle secrets / PII past the regex and get forwarded to the cloud tier (T4). |
| **Jinja2 template scanner** | `lib/security/model_monitor.py` (`SCAN_PATTERNS`) | Known-pattern evasion: backdoor templates that don't trip any of the 7 detectors. |
| **Ollama blob integrity** | `lib/security/model_monitor.py` (`fingerprint_blobs`) | Weight tampering that preserves SHA-256 but changes behavior (adversarial fine-tuning, low-rank merges). |
| **Inference proxy routing** | `services/inference-proxy/app.py` | Routing manipulation: prompts that force downgrade to a weaker tier, or escalate to a tier with relaxed gates. |
| **Hermes-agent skill routing** | `~/.hermes/skills/sapphire/*` (14 skills) | Skill-selection confusion: adversarial prompts that make the agent invoke a skill it shouldn't. |
| **Prompt-injection resilience** | `plugins/claw-sapphire/lib/nemotron.py` + all tool stdin JSON paths | Indirect prompt injection via market data, threat intel feeds, on-chain text fields, Foundry-returned rows. |
| **Token governor** | `plugins/claw-sapphire/lib/token_governor.py` | Budget exhaustion attacks — forcing unbounded model usage. |

### 2.2 Model list

The GPU node runs 28 models. The model aliases the proxy exposes (see
`CLAUDE.md` § Inference Proxy):

| Alias | Underlying model | Tier |
|---|---|---|
| `fast`, `quick` | `nemotron-mini:latest` | T1 GPU / T2 Pi |
| `auto`, `balanced` | `hermes3:8b` | T1 GPU |
| `deep` | `qwen3:14b` | T1 GPU |
| `code` | `gemma4:latest` | T1 GPU |
| `reason` | `deepseek-r1:14b` | T1 GPU (GPU-only) |
| `qwen-reason` | `qwen3.5:9b` | T1 GPU |
| `qwen3.6` | `qwen3.6:27b` | T3 Mac exact fallback until Windows install |
| `cascade`, `moe` | `nemotron-cascade-2` | T1 GPU |
| `large` | `qwen2.5:32b` | T1 GPU (GPU-only) |
| `kimi` | Kimi Cloud (Moonshot) | T4 cloud — sensitivity-gated |

All T1–T3 models are open-source and reproducible locally with
`ollama pull <name>`. You do **not** need GPU or Tailscale access to start —
run the stack on your laptop, hit the same attack surface.

### 2.3 Explicitly out of scope

- **Live trading path** — `services/alpha/`, `services/webhook/`,
  `lib/portfolio/robinhood.py`, `lib/trading/`. These handle real money.
  Don't touch.
- **Production Telegram bot / hermes-agent gateway** — use a test bot you
  spin up yourself.
- **Smart contracts** — `contracts/SapphireSignalVerifier.sol`,
  `contracts/SapphirePaymentGate.sol`. Separate engagement.
- **Physical attacks** on the mesh (Mac / Windows / Pis).
- **Social engineering** against Ari, THO client Mark, or other
  collaborators.
- **Denial-of-service / sustained load tests** against any live service.
- **Exfiltration of real secrets** — if a finding requires real credentials
  to demonstrate, stop, document the theoretical path, and coordinate.
- **Cloud provider attacks** (GCP, Moonshot, Cloudflare) — out of scope and
  against their ToS.

## 3. Rules of engagement

### 3.1 The hard rules

1. **Reproduce locally.** Anything you find should be reproducible on a
   laptop. If you need mesh access, coordinate first.
2. **Never run destructive actions against shared infrastructure.** No
   deletes, no writes to `data/` on the live mesh, no `launchctl unload`
   against running LaunchAgents.
3. **Never exfiltrate real user or operator data.** Synthetic fixtures only.
4. **Respect the kill switch.** If Ari tells you to stand down, stop
   immediately and write up what you were doing.
5. **One finding per PR / issue.** Don't bundle. Each finding needs its own
   report so it can be triaged and fixed independently.
6. **No automated scanners against the live mesh without coordination.**
   Nuclei, ZAP, sqlmap, etc. — fine locally, coordinate before live.
7. **Assume everything you touch is tamper-evident.** `data/system_events.jsonl`
   is append-only. Don't try to cover tracks.

### 3.2 Disclosure window

- **Critical / exploitable now** (remote code exec, secret exfil, classifier
  bypass that ships to prod): **24-hour** coordinated disclosure to Ari, then
  patch window.
- **High / moderate** (prompt injection with bounded impact, scanner
  evasion with theoretical impact): **14-day** disclosure + patch window.
- **Informational** (hardening suggestions, docs drift): file as a normal
  issue, no embargo.

Public writeups, conference talks, or blog posts require Ari's review
**before publication**. Credit model in § 6.

## 4. Suggested research paths (ranked by impact)

### 4.1 Sensitivity classifier bypass *(highest impact)*

**Goal:** Get a prompt through the classifier to tier T4 (Kimi Cloud) that
contains material Sapphire's policy says must stay local — an API key, a JWT,
a trading signal, a customer identifier.

**File:** `plugins/claw-sapphire/lib/sensitivity_classifier.py` — regex
patterns. (Note: the proxy also has its own regex gate at
`services/inference-proxy/app.py`. Test both.)

**Attack ideas:**
- Unicode homoglyphs for `api_key`, `password`, `jwt` regex strings
- Base64 / rot13 / hex encoding of sensitive strings
- Semantic leak without literal-string match ("my authentication blob is
  `eyJhbGc...`")
- Injection via tool outputs (market data field containing a fake JWT)
- Prompt templating that splits the sensitive string across turns

**Deliverable:** PR extending the classifier's detection + a test case per
bypass.

### 4.2 Jinja2 backdoor detector gaps

**Goal:** Craft Ollama Modelfile Jinja2 templates that execute adversarial
behavior and slip past `lib/security/model_monitor.py`'s `SCAN_PATTERNS`.

**File:** `lib/security/model_monitor.py`. The detector currently looks for
~7 patterns (command substitution, filter chains, literal `{{ ... }}`
eval-equivalents, …). Gaps probably exist in:
- Python-format-spec-style abuse
- Nested template includes
- Whitespace-trim-modifier edge cases
- Jinja2 custom filter registration via Modelfile `SYSTEM` blocks

**Deliverable:** PR adding new `SCAN_PATTERNS` + a corpus of adversarial
templates under `tests/fixtures/model_backdoors/` with a unit test per
pattern.

### 4.3 Model weights integrity

**Goal:** Show a concrete adversarial-fine-tune or merge that preserves the
blob SHA-256 set that `model_monitor.fingerprint_blobs()` records at baseline,
but changes behavior (different safety refusal pattern, different tool-call
output, different refusal on CSAM probes — whatever's measurable).

**Caveat:** Ollama fingerprints individual blobs. A real attack either
tampers in-place (breaks SHA) or swaps a blob (breaks SHA). The subtle case
is: *an attacker who can get a model with matching SHAs accepted into the
local model store by name collision or registry poisoning.* That's the
scenario we want analyzed.

**Deliverable:** Threat-model writeup + if possible a repro against a
self-built tampered blob. No need to weaponize.

### 4.4 Indirect prompt injection via market data

**Goal:** Get a signal.generated event payload containing adversarial text
(e.g., in a coin description, on-chain memo, or news headline) that causes
the downstream content engine or trading brain to take an unintended action.

**Files:**
- `lib/content/data_collector.py`
- `lib/chain/providers/*` (all the on-chain data providers — Whale Alert,
  Santiment memos)
- `plugins/claw-sapphire/tools/internal/predict.py`
- `plugins/claw-sapphire/tools/trading_brain.py`

**Attack ideas:**
- Unicode direction-override in market data strings
- Instruction-smuggling via tool JSON output fields
- Delimiter confusion in the Nemotron system prompt boundary
  (`plugins/claw-sapphire/lib/nemotron.py`)

**Deliverable:** Repro + sanitization PR.

### 4.5 Hermes-agent skill selection confusion

**Goal:** Induce the Telegram operator bot (hermes-agent, NousResearch) to
invoke a skill the operator didn't request.

**Files:** `~/.hermes/skills/sapphire/*.md` (14 skills — cyber-intel,
inference-tier, kimi-delegate, macro-data, paper-trading, regional-intel,
repo-discovery, system-health, system-ops, tho-operations, threat-intel,
trading-analysis, trading-brain, trading-signals).

**Deliverable:** Adversarial prompt corpus + hardening suggestions for skill
selection logic.

### 4.6 Token-governor exhaustion

**Goal:** Craft an input flow that drives the token governor past its budget
such that a legitimate downstream request is starved.

**File:** `plugins/claw-sapphire/lib/token_governor.py`.

**Deliverable:** Repro + a rate-limit or per-source quota PR.

## 5. Reporting workflow

### 5.1 Non-sensitive finding
1. Open a GitHub issue using the `bug.md` template (see
   `.github/ISSUE_TEMPLATE/bug.md`).
2. Add the `security` label.
3. Fill out "Blast radius" — be honest; under-stating it is worse than
   over-stating.
4. Open a PR referencing the issue.

### 5.2 Sensitive / embargoed finding
1. **Do not open a GitHub issue.**
2. Telegram-DM Ari with:
   - One-line severity
   - One-paragraph description
   - Reproduction hash (don't paste the actual exploit prompt / payload —
     a cryptographic hash that you can later disclose is enough for
     coordination)
3. Ari will respond with a private channel to exchange the full report.
4. After patch ships + embargo window, co-author a public writeup if you
   want it in the bag.

### 5.3 What a good report looks like

```
Title: <surface> — <one-line>          e.g., "Sensitivity classifier — unicode homoglyph bypass"

Severity: [Critical | High | Medium | Low | Informational]

Summary:
  One paragraph. What is possible that shouldn't be?

Reproduction:
  1. Steps or commands someone else can run.
  2. Expected vs. actual.
  3. Environment (laptop / mesh / Ollama version).

Impact:
  Concrete consequence. "An attacker with ability X could achieve outcome Y."
  Not "this is bad" — what happens?

Suggested fix:
  Patch sketch or PR reference.

Credit:
  How do you want to be credited in the CHANGELOG / security advisory?
```

## 6. Credit + compensation

### 6.1 Credit (default)
- Findings ship in a `SECURITY.md` changelog inside the repo.
- First public writeup (after embargo) names the researcher. Attribution in
  any patched code is at the researcher's choice.
- Pattern additions to `lib/security/model_monitor.py` are attributed in a
  header comment on the new rule.

### 6.2 Compensation
Sapphire is pre-revenue. Default compensation structure is:
- Public credit + co-authored advisory.
- Right of first pitch on any resulting conference talk / paper.
- **Bounty / paid engagement** is negotiable directly with Ari. Bring the
  scope, the timeline, and the deliverable; get a written agreement before
  starting paid work.

## 7. Shortest path to a first finding

If you want to ship something in your first week:

1. **Day 1:** `git clone`, `make install`, `make install-hooks`, `make
   doctor`, `make test-all`. Pull `nemotron-mini` and `hermes3:8b` via
   Ollama.
2. **Day 2:** Read `lib/security/model_monitor.py` line-by-line. Read
   `plugins/claw-sapphire/lib/sensitivity_classifier.py`. Read the tests for
   both.
3. **Day 3:** Pick **one** surface from § 4 (§ 4.1 is the highest-impact
   single-laptop engagement). Build an adversarial test fixture. Run it
   against the current code. If it passes, document a bypass.
4. **Day 4–5:** Write the report (§ 5.3), open a PR with the fix, file the
   issue with the `security` label.

First PR doesn't need to be a critical bypass. A documented hardening
improvement + a regression test is a perfectly fine first contribution and
gets you into the review loop.

## 8. Contact

- **Ari (primary):** Telegram. DM for engagement kickoff, sensitive
  disclosures, scope questions, paid-engagement terms.
- **Repo:** `github.com/arigatoexpress/Sapphire` — issues for non-sensitive
  reports, PRs for everything.
- **Secure disclosure:** ask Ari for preferred channel (Signal / age /
  something else) — **don't put the exploit payload in the first Telegram
  message**; send a hash first.

---

*This document is a living scope. If you find the ROE too restrictive for a
research path you care about, open a discussion — we'd rather widen the
scope than have good work happen outside it.*
