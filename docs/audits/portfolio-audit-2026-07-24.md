# Portfolio & Sapphire audit — 2026-07-24

Adversarial review of the whole GitHub portfolio and of Sapphire's own claims.
Every number here was measured in this session, not carried over from a previous
doc. Where a claim could not be verified, it says so.

Method: full test-suite runs, an inverted-index reference scan over 2,301 files,
empirical probing of the security gates, and GitHub API metadata for all 68
repos. Commands are given so each finding can be re-derived or refuted.

---

## 1. The portfolio is 68 repos and the shape is the problem

40 archived, 28 active. Sapphire is 165 MB; the next largest active repo is
34 MB; **20 of the 28 active repos are under 500 KB and 14 are under 100 KB.**

Those 14 sub-100 KB repos total roughly 390 KB — under 0.25% of Sapphire's mass —
and were nearly all created in a nine-day window (2026-07-16 → 07-24):

| Repo | Size | Pushed |
|---|---|---|
| `rh-agentic-bridge` | 4 KB | 07-23 |
| `rhchain-agent-lane` | 9 KB | 07-18 |
| `sovereign-terminal` | 11 KB | 07-21 |
| `moss-agent-lane` | 11 KB | 07-18 |
| `libsim` | 13 KB | 07-16 |
| `home-access-kit` | 15 KB | 07-03 |
| `fleet-lease` | 18 KB | 07-17 |
| `gunnison-fishing-guide` | 23 KB | 07-03 |
| `kimi-guard-evals` | 28 KB | 07-18 |
| `model-council` | 29 KB | 07-17 |
| `remote-gpu-gateway` | 34 KB | 07-16 |
| `moss-wallet-demo` | 51 KB | 07-23 |
| `aegis` | 64 KB | 07-16 |
| `desk-orchestrator` | 77 KB | 07-17 |

**The claim to attack: that these are separate projects.** They are mostly
directories that were given the ceremony of a repo. Each one costs a README, a
license, CI wiring, a dependency surface, an access-control entry, and a slot in
your attention — permanently — to hold a few hundred lines. That overhead is
roughly constant per repo and is being paid ~1x/day.

### Overlap clusters (candidates for consolidation)

Naming already tells you where the duplication is:

- **`sovereign-*`** — `sovereign-chassis`, `sovereign-terminal`,
  `sovereign-windows-worker`. Three repos, one concept.
- **`desk*`** — `deskos` ("verification-first research & forecasting engine")
  and `desk-orchestrator` ("thesis, swarm, policy, Telegram gate"). Both restate
  subsystems Sapphire already has in `lib/analytics/forecast.py` and the agent
  stack.
- **`*-agent-lane`** — `moss-agent-lane`, `rhchain-agent-lane`. Same pattern,
  9 KB and 11 KB. Plus `rh-agentic-bridge` (4 KB) overlapping the latter.
- **LLM infra** — `model-council`, `local-llm-benchmark`, `kimi-guard-evals`,
  `remote-gpu-gateway`. All four restate parts of
  `services/inference-proxy/` (4-tier failover, model routing, benchmarking).
- **Safety libs vs. Sapphire** — `aegis` ("agent-safety firewall") and
  `libcircuit` ("circuit breaker and kill-switch library") duplicate
  `lib/core/kill_switch.py`, `lib/core/confirmation_firewall.py`, and
  `lib/security/`. This is the most consequential overlap: **safety controls
  that exist in two places diverge, and a diverged safety control is worse than
  one control** — Section 2 is exactly that failure mode, observed inside
  Sapphire.
- **Trading** — `quant-perps` vs `services/hyperliquid/`.
- **Dashboards** — `sapphire-alpha-dashboard` vs `services/dashboard/`.

### Recommendation

Not "delete things." The specific asks:

1. **Adopt a promotion rule.** New work starts as a directory inside an existing
   repo. It earns a repo only when it has a distinct release cadence, a distinct
   consumer, or a distinct access boundary. None of the 14 above clears that bar
   today.
2. **Fold the safety libs first** (`aegis`, `libcircuit`). One kill-switch
   implementation, in `lib/core/`, with one test suite. Divergence here has
   already cost you once.
3. **Fold the LLM-infra four** into `services/inference-proxy/` as subpackages.
4. **Pick one name per concept.** `sovereign-*`, `desk*`, `moss-*` and
   `rh*-lane` are four naming schemes for overlapping ideas; that ambiguity is
   what makes the sprawl feel necessary.

Archiving is *not* the same as consolidating — 40 archived repos already show
the pattern of abandoning rather than absorbing. Absorb the code that matters.

---

## 2. Credential exfiltration to the cloud LLM tier — **fixed in this branch**

The highest-severity finding, and it was live.

Sapphire routes non-sensitive prompts to Tier 4 (`api.moonshot.cn`). Two
*different* classifiers guarded that egress, and neither matched raw key
material:

| Probe (bare value, no keyword) | plugin gate | proxy gate |
|---|---|---|
| AWS access key ID | forwarded | forwarded |
| GitHub PAT | forwarded | forwarded |
| Stripe live key | forwarded | forwarded |
| Telegram bot token | forwarded | forwarded |
| OpenAI key | forwarded | forwarded |
| Raw JWT | forwarded | forwarded |
| EVM private key | forwarded | forwarded |
| Slack bot token | forwarded | blocked |
| Tailscale mesh IP | blocked | forwarded |
| Customer PIN | blocked | forwarded |

**10 of 11 secret formats passed the plugin gate; 11 of 12 passed the proxy
gate.** The gates matched the *word* `api_key`, never the *value*. CLAUDE.md
asserted "regex blocks api_key/password/jwt/SSN/CC from T4" — the JWT claim was
simply false for a bare token.

Worse, the repo's own red-team corpus had **13 `xfail` probes** recording these
exact bypasses. The holes were known, documented, and CI stayed green.

### Fix

- New `lib/security/secret_patterns.py` — one canonical rule set, stdlib-only,
  imported by both gates so they cannot drift apart again. Covers ~25 provider
  key shapes plus normalization that defeats homoglyph, zero-width, soft-hyphen,
  percent-encoding, leetspeak, and base64/hex-encoded evasion.
- Both gates now consult it. Result: **11/12 probes blocked, 0 false positives**
  across nine benign control prompts.
- Red-team `xfail` count: **21 → 10**; the classifier's own 13 → 2.
- The 2 that remain are honest limits, asserted as limits in
  `tests/unit/test_secret_patterns.py`: a bare AWS *secret* key is 40 chars of
  shapeless base64, and a semantic description contains no secret at all.

Re-derive: `pytest tests/unit/test_secret_patterns.py tests/unit/test_redteam_corpus.py -q`

### One design note worth keeping

Hardening the keyword rule broke five narrative-engine tests, because
`build_user_prompt()` embeds the instruction *"Do not include secrets,
credentials, raw private payloads"* — **the guardrail's own wording tripped the
guardrail**, silently degrading every live call to `dry-run-safety`. The gate now
scans the injected signal payload rather than the static template. Pinned by
`test_static_prompt_template_does_not_trip_the_sensitivity_gate`.

---

## 3. The test suite was overstating coverage — **fixed in this branch**

Headline before: "7,245 tests." Reality on a clean checkout: **42 collection
errors and a suite that would not run at all**, because nothing installs
dependencies and `pip install -r requirements-test.txt` *fails* on a stock
Debian container (system PyYAML has no RECORD file, so pip aborts).

Any agent opening this repo in a cloud session sees 42 red files and may "fix"
tests that were never broken.

Three distinct integrity problems, all now addressed:

1. **Cannot bootstrap.** Added `scripts/ops/bootstrap_cloud_session.sh` (handles
   the PyYAML and `_cffi_backend` failures) and a `SessionStart` hook so it runs
   automatically on Linux containers.
2. **Silently un-collected files.** `tests/conftest.py::pytest_ignore_collect`
   drops an entire test file when an optional dep is missing — it counts as
   neither passed nor failed, so lost coverage reads as a smaller green suite.
   This hid **57 webhook-receiver tests on the TradingView → trading critical
   path**, because `uvicorn` was in pyproject's `[dev]` extra but not in
   `requirements-test.txt`. Added the pin; added a `pytest_terminal_summary` that
   prints a `NOT COLLECTED` banner so this can never be silent again.
3. **Order-dependent tests.** `test_foundry_readiness` passed alone and failed in
   the full suite; `test_control_plane_news_sources` did the reverse. Both were
   masked. Two environment-coupled tests also failed anywhere but the operator's
   Mac (`test_bootstrap_fresh_mac_dryrun` asserted macOS-only output;
   `test_dashboard_rh_chain_local` read `~/ops-state/rh-chain` from the real
   `$HOME`) — both are now hermetic and assert the correct branch per platform.

**Result: 6,580 passed / 4 failed → 6,701 passed / 0 failed, 21 xfail → 10.**

Still true and worth knowing: the suite retains latent order-sensitivity. A
green run is weaker evidence than the count suggests until `pytest-randomly` is
adopted and the residual coupling is fixed. That is the recommended next step.

---

## 4. The accuracy claim does not survive contact with statistics

CLAUDE.md, `docs/architecture-overview.md`, and — most seriously — a **grant
application** all asserted "**verified** 61.1% overall, BTC 83.3%."

| Slice | Hits | Rate | 95% Wilson CI | p vs coin flip |
|---|---|---|---|---|
| Overall | 22/36 | 61.1% | **[44.9%, 75.2%]** | 0.243 |
| BTC | 10/12 | 83.3% | [55.2%, 95.3%] | 0.039 |
| ETH | 6/12 | 50.0% | [25.4%, 74.6%] | 1.000 |
| SOL | 6/12 | 50.0% | [25.4%, 74.6%] | 1.000 |

- The overall interval **contains 50%.** The result is not distinguishable from
  chance. Calling it "verified" inverts its meaning.
- BTC's p=0.039 is the **best of three** symbols tested. At three comparisons the
  Bonferroni threshold is 0.0167, so it does not survive correction. Leading with
  the winning slice is textbook selection on the dependent variable.
- ETH and SOL are exactly chance, and they are half the sample.
- Reaching ±5% precision at this hit rate needs **n≈370** — about 10x the
  current scored set.

The old wording also contained its own refutation: the grant doc's appendix said
"verify against current output" — the number was flagged as unverified while
being presented as verified.

**Fixed here:** CLAUDE.md and the grant application now carry the interval and
state plainly that no edge is established. The honest pitch is *process* —
scored, timestamped, adversarially reviewed forecasts — not accuracy.

Related: `"80%+ win rate target"` appears in CLAUDE.md, two dashboard pages, and
`pine/SKILL.md`, where it is phrased as an achievement ("v3 Ultra achieves 80%+
win rate"). Nothing measured supports it. Win rate is also the wrong objective —
it is trivially inflated by tight take-profits and wide stops. Judge expectancy.

---

## 5. Documented subsystems with no production caller

An inverted-index scan over 2,301 files (`stem → referencing files`, excluding
self-references) found **84 modules with zero production references**, ~22.9k
lines. Excluding test files and the deliberate `scripts/archived/` cold shelf,
the substantive ones:

**Zero references anywhere — not even a test:**

| LOC | Module | Note |
|---|---|---|
| 92 | `lib/content/data_collector.py` | **documented as stage 1 of the content pipeline** |
| 403 | `lib/core/src/sapphire_core/ai_error_recovery.py` | |
| 154 | `lib/core/src/sapphire_core/health_checker.py` | |
| 406 | `lib/core/src/sapphire_core/test_acts.py` | a `test_` file living outside `tests/` |
| 118 | `lib/agents/src/sapphire_agents/nemoclaw_dispatch.py` | |
| 297 | `services/webhook/src/pair_trading_logic.py` | |
| 485 | `services/aster/src/aster_shield_strategy.py` | service is "paused" |
| 647 | `services/alpha/src/self_improvement/self_improvement_engine.py` | |
| 853 | `services/alpha/src/self_improvement/adaptive_retraining_system.py` | |
| 788 | `services/alpha/src/risk/dynamic_position_sizing.py` | |
| 481 | `services/alpha/src/risk/monte_carlo_sim.py` | |
| 451 | `services/alpha/src/risk/kelly_sizing.py` | |
| 217 | `services/pipeline/routine_controller.py` | |

**Test-only (a test imports it; nothing in production does)** — 30 modules,
~11k lines, including several the module map presents as headline capabilities:
`lib/core/security_monitor.py`, `lib/chain/coinmetrics.py`,
`lib/content/thesis_engine.py`, `lib/content/draft_generator.py`,
`lib/analytics/self_optimizer.py`, `lib/telegram/login_widget.py`,
`lib/chains/cross_chain/pyth_hermes_divergence.py`,
`lib/core/src/sapphire_core/{acts_orchestrator,episodic_memory,sapphire_neural_cache}.py`.

**Why this matters more than the line count.** ~1,720 lines of risk machinery
(Kelly sizing, Monte Carlo, dynamic position sizing) exist in a trading system
and nothing calls them. Tests passing on that code produce *confidence without
coverage of anything that runs*. It is the same failure as §3: the number goes
up, the assurance does not.

**Not recommended for deletion:** `scripts/archived/` (94 files, 916 KB).
`docs/ops/monorepo-purge-leftovers.md` explicitly designates it an in-git cold
shelf and says do not mass-delete. That decision is respected here.

**Recommended:** for each module above, decide *wire it or delete it* — and
delete the tests along with the code. A test for unreachable code is a liability:
it costs maintenance and pays no assurance. Start with `lib/content/`, where the
documentation actively misleads.

Re-derive: the scan script is small; rebuild it by indexing every identifier in
`*.py|md|yaml|json|sh|toml|plist|html` and mapping module stems to referrers.

---

## 6. Smaller true things

- **CLAUDE.md counts had drifted on six of eight.** Tests 7,245→7,334, files
  439→459, dashboard pages 52→46, plists 29→33, pine 5→25, analytics modules
  24→25, plugin tools 118→117 (and the file contradicted itself, saying 118 in
  one place and 117 in another). Corrected, with a note to trust the tree.
- **"7 quant strategies" counted the `Strategy` ABC and the `StrategyParams`
  dataclass as strategies.** There are 5. Padding a count with scaffolding is a
  small dishonesty that makes every other count untrustworthy.
- **447 markdown files** for one repo. Not audited in depth here; flagged because
  documentation that no one can read is documentation that drifts — as §4 and §6
  demonstrate.
- **`lib/security/pii_redactor.py` is *not* a third redundant classifier** — it
  serves dashboard output redaction and is genuinely used. Checked and cleared.

---

## What changed in this branch

| Area | Before | After |
|---|---|---|
| Core suite | 6,580 pass / 4 fail | **6,701 pass / 0 fail** |
| Red-team xfails | 21 | **10** |
| Secret formats reaching cloud tier | 10/11 (plugin), 11/12 (proxy) | **1/12** |
| Webhook critical-path tests running | 0 (silently un-collected) | **57** |
| Cloud container bootstrap | fails | **automatic via SessionStart** |
| Egress classifiers | 2, divergent | **1 canonical + 2 thin callers** |

Files: `lib/security/secret_patterns.py` (new),
`tests/unit/test_secret_patterns.py` (new),
`scripts/ops/bootstrap_cloud_session.sh` (new),
`plugins/claw-sapphire/lib/sensitivity_classifier.py`,
`services/inference-proxy/app.py`, `lib/synthesis/narrative_engine.py`,
`tests/conftest.py`, `requirements-test.txt`, `.claude/settings.json`,
`tests/fixtures/redteam/sensitivity_classifier_probes.json`, `CLAUDE.md`,
`docs/grants/apollo-accelerator-application.md`, and three test files.

## What was deliberately not done

- No repos consolidated or archived. That is a portfolio decision with real
  consequences and it is yours to make; §1 gives the evidence and a rule.
- No dead code deleted. §5 names it with line counts; several items may be
  intentional work-in-progress, and deleting a service's risk engine on a
  reference scan alone is not a call to make unilaterally.
- `scripts/archived/` untouched, per existing documented policy.
- Order-dependence in the suite is characterized, not eliminated — that needs
  `pytest-randomly` and a focused pass.
