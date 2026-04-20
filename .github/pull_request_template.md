<!--
Sapphire OS pull request template.
Keep it honest — what changed, why, and how it was verified.
-->

## Summary
<!-- 1-3 bullets. What does this PR do and why? -->

-

## Type
- [ ] feat — new user-visible capability
- [ ] fix — bug fix
- [ ] refactor — no behavior change
- [ ] infra — CI, build, dev env
- [ ] docs — docs only
- [ ] security — hardening or CVE fix

## Risk touch points
<!-- Tick any that apply. An unticked box means "this PR does NOT touch this." -->
- [ ] Trading execution / risk kernel / position sizing
- [ ] Webhook or any external-facing service
- [ ] Secrets / auth / credentials
- [ ] Data files under `data/` (non-runtime)
- [ ] On-chain contracts / deployments
- [ ] LaunchAgents / scheduled tasks

## Verification
<!-- Paste the output, not a claim. -->
- [ ] `ruff check .` clean (or diff explained)
- [ ] `pytest tests/unit/ -q` passes locally
- [ ] `pytest plugins/claw-sapphire/tests/ -q` passes (if plugin touched)
- [ ] Manual check: <!-- e.g., curl dashboard, Telegram round-trip, service logs -->

## Rollback plan
<!-- For infra/trading/contract PRs: how do you revert if this breaks prod? -->

## Linked issues / docs
<!-- #123, docs/..., Linear... -->
