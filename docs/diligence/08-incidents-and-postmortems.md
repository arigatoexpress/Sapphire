# 08 - Incidents And Postmortems

## 2026-04-17 Audit-Doc Credential Exposure

What happened: `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md` records that `docs/technical-audit-2026-04-16.md` was committed with real plist excerpts containing `MOONSHOT_API_KEY` and `KIMI_CLAW_BOT_TOKEN`. The file was later deleted, but historical git content remains. A Proton Drive copy also existed at the absolute path recorded in the runbook.

Blast radius: the repo is private, which narrows but does not eliminate exposure. Any collaborator or system with historical read access could retain a clone. Proton Drive adds account/session risk. The runbook correctly treats revocation as the canonical fix.

Mitigation: document the incident, rotate the dashboard default password, add docs/plist gitleaks coverage, keep secret values out of plists, and centralize rotation procedures. `/Users/aribs/Code/Sapphire/docs/security/2026-04-27-proton-audit.md` records the Proton audit and dashboard basic-auth catch-up.

Prevention: staged gitleaks, `.gitleaks-docs.toml`, local CI, LaunchAgent secret sanitization, and the credential runbook. Remaining action: operator rotation of `MOONSHOT_API_KEY` and `KIMI_CLAW_BOT_TOKEN`, plus deletion of the Proton copy, because the runbook status is still `Awaiting operator rotation`.

## Routine Soak State

What happened: Sapphire has local LaunchAgents and remote-shadow routines. The risk is premature cutover: retiring local routines before scheduled remote artifacts are comparable. `/Users/aribs/Code/Sapphire/docs/org/content-engine-shadow-soak-2026-04-26.md`, `/Users/aribs/Code/Sapphire/docs/org/backtest-weekly-shadow-soak-2026-04-26.md`, and `/Users/aribs/Code/Sapphire/docs/org/threat-refresh-shadow-soak-2026-04-26.md` document soak criteria.

Blast radius: routine drift affects content, backtesting, and threat intel quality. It does not directly execute trades when the documented safety constraints are followed.

Mitigation: `/Users/aribs/Code/Sapphire/scripts/ops/routine_soak_status.py` reports gate progress, and `/Users/aribs/Code/Sapphire/scripts/ops/production_readiness_sweep.py` surfaces routine warnings when external checks are disabled. Local LaunchAgents remain canonical until gates pass.

Prevention: artifact comparison scripts in `/Users/aribs/Code/Sapphire/scripts/ops/compare_content_artifacts.py`, `/Users/aribs/Code/Sapphire/scripts/ops/compare_backtest_artifacts.py`, and `/Users/aribs/Code/Sapphire/scripts/ops/compare_threat_artifacts.py`. The operational principle is simple: shadow first, prove equivalence, then cut over through a PR.

## Hermes Runtime Guard Rollout

What happened: Hermes needed a runtime guard so quick-exec paths could not silently run against the wrong checkout or missing `SAPPHIRE_REPO_PATH`. The guard is implemented in `/Users/aribs/Code/Sapphire/scripts/ops/hermes_runtime_readiness.py` and documented in `/Users/aribs/Code/Sapphire/docs/ops/hermes-runtime-readiness.md`.

Blast radius: without the guard, Telegram/Hermes actions could use stale code, stale skills, or unbounded command execution. That is especially sensitive because Hermes is an operator-facing gateway.

Mitigation: readiness checks verify the LaunchAgent path, repo env, runtime backup, and quick-exec command guard. `/Users/aribs/Code/Sapphire/infra/hermes-sapphire-skills.yaml` inventories Hermes skills and classifies side effects.

Prevention: treat Hermes as constrained reviewer/helper unless Ari explicitly assigns ownership; keep `SAPPHIRE_REPO_PATH` explicit; do not restart or retarget Hermes without a deliberate LaunchAgent gate.

## Legacy Code Archival

What happened: old code under `legacy_code/` created source-tree ambiguity and diligence noise. The cold-tier process copied it to Proton Drive and recorded SHA-256 evidence in `/Users/aribs/Code/Sapphire/docs/ops/legacy-code-cold-tier-2026-04-28.md`, then removed it from git.

Blast radius: low runtime risk, high diligence/readability risk. Keeping obsolete code in the hot repo makes it harder to know what is production.

Mitigation: `/Users/aribs/Code/Sapphire/scripts/ops/storage_tier_sync.py` plans by default and only applies with `--apply --i-mean-it`. `/Users/aribs/Code/Sapphire/STRUCTURE.md` and `/Users/aribs/Code/Sapphire/docs/ops/storage-tier-architecture.md` define where code, warm data, cold archives, and evidence belong.

Prevention: use storage tiers before deletion, record hashes, keep restore instructions, and avoid treating "not in git" as "not preserved." This was a cleanup incident with a good outcome: the repo became more legible without pretending history never existed.

## Cross-Incident Lessons

The incidents share a pattern: Sapphire is safest when it turns operational discomfort into a durable artifact. The credential exposure became a rotation runbook, docs/plist scanning, and LaunchAgent sanitization. Routine uncertainty became soak docs and comparison scripts. Hermes runtime ambiguity became a readiness guard. Legacy-code ambiguity became storage-tier architecture and cold-tier hash evidence.

This is the right pattern for a one-operator autonomy system because memory does not scale. The operator may remember why a routine exists today, but the buyer cannot diligence memory. Files, tests, hashes, and runbooks are transferable. Every future incident should therefore end with one of four outcomes: a code guard, a test, a runbook, or a tracked decision not to automate.

The main unresolved incident is still credential rotation. This packet should not be used as a closing memo until the operator either rotates the named keys and updates the runbook status or explicitly records why the risk is accepted. That is a diligence close condition, not a code TODO. The Proton audit doc deletion is also operator-owned because it lives outside the repo.

The second lesson is that warnings are useful. The readiness sweep's routine-soak and external-mode warnings keep incomplete work visible without blocking local development. A buyer should preserve that distinction. A system with zero warnings because it refuses to inspect hard things is worse than a system with honest warnings and no failures.

The final lesson is that cleanup should be reversible where possible. The legacy-code archival did not just delete a folder; it copied, hashed, documented, and provided restore instructions. That is the operational tone Sapphire should maintain as it grows: decisive, but not cavalier.

A buyer should ask for incident artifacts during diligence, not just summaries. The useful artifacts are runbook status lines, gitleaks output, provider rotation receipts, readiness sweeps, and PRs that installed prevention controls. Sapphire already has most of that structure; the remaining gap is operator-side rotation evidence.

## Evidence

- `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md`
- `/Users/aribs/Code/Sapphire/docs/security/2026-04-27-proton-audit.md`
- `/Users/aribs/Code/Sapphire/scripts/ops/routine_soak_status.py`
- `/Users/aribs/Code/Sapphire/scripts/ops/hermes_runtime_readiness.py`
- `/Users/aribs/Code/Sapphire/docs/ops/legacy-code-cold-tier-2026-04-28.md`
