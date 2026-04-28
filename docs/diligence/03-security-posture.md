# 03 - Security Posture

Sapphire's security posture is explicit, imperfect, and unusually inspectable for a one-operator system. Secrets are not meant to live in plists or source: the credential map in `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md` points model keys to `~/.sapphire/secrets.env`, operational secrets to `~/.config/sapphire-secrets/`, and Hermes bot material to `~/.hermes/.env` plus the operator secret directory. LaunchAgent sanitization is documented in `/Users/aribs/Code/Sapphire/docs/ops/launchagent-secret-sanitization.md`, while repo checks run through `.gitleaks.toml`, `.gitleaks-docs.toml`, and `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py`.

The 2026-04-17 incident is documented rather than hidden. `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md` records that a technical-audit document included real `MOONSHOT_API_KEY` and `KIMI_CLAW_BOT_TOKEN` values in historical commits and a Proton Drive copy. The runbook status remains `Awaiting operator rotation`, which is the honest state until the operator rotates both keys and deletes the Proton copy. `/Users/aribs/Code/Sapphire/docs/security/2026-04-27-proton-audit.md` records the follow-up Proton audit and dashboard default-password remediation.

Hermes is treated as a constrained runtime rather than an all-powerful agent. `/Users/aribs/Code/Sapphire/scripts/ops/hermes_runtime_readiness.py` checks whether the Hermes gateway points at the correct runtime checkout, whether the quick-exec guard is present, and whether `SAPPHIRE_REPO_PATH` is set. `/Users/aribs/Code/Sapphire/docs/ops/hermes-runtime-readiness.md` explains the expected runtime shape. This reduces the chance that Telegram or Hermes uses a stale clone or bypasses repo-local safety logic.

The confirmation firewall is the human authorization layer. `/Users/aribs/Code/Sapphire/lib/core/confirmation_firewall.py` classifies read-only, self-modifying, system-modifying, external-send, financial, and destructive actions; destructive actions require delay, and financial auto-approval is constrained to paper/dry-run cases. The kill switches are separate. `/Users/aribs/Code/Sapphire/lib/core/security_kill_switch.py` writes a cloud-routing kill flag and stops external paths; `/Users/aribs/Code/Sapphire/lib/core/kill_switch.py` covers core execution shutdown. The public Risk Kernel 0.1.0 in `/Users/aribs/Code/Sapphire/lib/core/risk_kernel/` adds an evaluable decision surface with policy-by-policy verdicts.

Sensitivity and egress controls are present in the inference lane. `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/gemini_ooda.py` screens prompts through the sensitivity classifier before live Gemini calls and falls back to dry-run safety modes. `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py` prevents sensitive fallthrough to Kimi Cloud when all local tiers are exhausted. The dashboard also refuses known default basic-auth passwords in `/Users/aribs/Code/Sapphire/services/dashboard/app.py`, with static guardrails in `/Users/aribs/Code/Sapphire/tests/unit/test_security_catchup_controls.py`.

SOC-2-flavoured control map:

| Area | Sapphire Control | Evidence |
|---|---|---|
| CC1 control environment | Single operator, explicit runbooks, no-spend PR discipline | `/Users/aribs/Code/Sapphire/CLAUDE.md`, `/Users/aribs/Code/Sapphire/docs/ops/codex-lead-operating-model.md` |
| CC2 communication | Diligence docs, runbooks, readiness sweeps | `/Users/aribs/Code/Sapphire/docs/ops/production-readiness-matrix-runbook.md` |
| CC3 risk assessment | Risk Kernel, confirmation firewall, kill switches | `/Users/aribs/Code/Sapphire/docs/products/risk-kernel-0.1.0.md` |
| CC4 monitoring | Production-readiness sweep and local CI | `/Users/aribs/Code/Sapphire/scripts/ops/production_readiness_sweep.py` |
| CC5 control activities | Pre-commit, gitleaks, Bandit, local verifier | `/Users/aribs/Code/Sapphire/.pre-commit-config.yaml` |
| CC6 logical access | Secret files outside repo, dashboard auth hardening | `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md` |
| CC7 system operations | LaunchAgents and routine soaks | `/Users/aribs/Code/Sapphire/infra/launchagents/` |
| CC8 change management | Branch + PR + local CI merge evidence | `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py` |
| CC9 risk mitigation | Incident runbook and provenance verification | `/Users/aribs/Code/Sapphire/lib/core/provenance.py` |

## Diligence Readout

The security story is strongest where it admits concrete incidents. The 2026-04-17 credential exposure is uncomfortable, but the repo now has a better posture because it turned a leak into a rotation runbook, docs/plist scanning, LaunchAgent sanitization, and readiness checks. An acquirer should not ask whether Sapphire has never made a mistake; it should ask whether mistakes become controls. The file evidence says yes.

The remaining security risk is operator-completed rotation. Until `MOONSHOT_API_KEY` and `KIMI_CLAW_BOT_TOKEN` are revoked and replaced at their providers, the runbook should remain `Awaiting operator rotation`. That is not a code blocker; it is a credential lifecycle task. During diligence, the operator should show provider-side revocation timestamps, the updated secret-file mtimes, and a clean post-rotation smoke. This packet intentionally does not claim that step is done.

The second risk is mutation authority. Sapphire has a confirmation firewall and risk kernel, but not every future live mutation path should be assumed wired to both. The correct acquisition plan is to keep trading, Telegram sends, cloud writes, and LaunchAgent retargeting read-only or dry-run until a path-level audit proves: risk evaluated, confirmation requested when required, kill switch respected, provenance stamped, and event emitted. That is the acceptance checklist for any future live console.

The third risk is agent sprawl. The Hermes skill inventory and tool registry mitigate it by classifying capability and narrowing the agent-facing manifest. The buyer should preserve that discipline. Adding twenty tools because a model can call them would reduce, not increase, Sapphire's value. The product moat is not "lots of tools"; it is controlled autonomy with evidence.

The close checklist for security diligence should be concrete: rotate the two open incident credentials, show provider revocation timestamps, rerun changed-file and full-history secret scans with redaction, prove default dashboard auth returns 401, run Hermes readiness, run production readiness, and inspect one Risk Kernel red-team test. If any item cannot be shown, it should become a dated exception with an owner.

The positive signal is that Sapphire already distinguishes "manual gate," "dry-run," "read-only," "paper," and "live." That vocabulary should be preserved in UI labels, API responses, docs, and PR bodies because it is how the system avoids accidental escalation.

## Evidence

- `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md`
- `/Users/aribs/Code/Sapphire/lib/core/confirmation_firewall.py`
- `/Users/aribs/Code/Sapphire/lib/core/security_kill_switch.py`
- `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/gemini_ooda.py`
- `/Users/aribs/Code/Sapphire/tests/unit/test_security_catchup_controls.py`
