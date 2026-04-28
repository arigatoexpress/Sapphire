# Multi-Agent Audit Panel 0.1.0

Date: 2026-04-28

## Summary

The Sapphire Multi-Agent Audit Panel is a read-only trust layer for autonomous
merge operations. Sapphire has been moving quickly through acquisition-oriented
tranches, and many PRs are authored, verified, and merged by agent operators.
That velocity is useful only if the system can explain what changed, why it was
safe enough to merge, and which changes deserve follow-up review. The audit
panel turns merged PR history into a weekly, paste-safe risk report.

The panel does not replace local tests, branch protection, or human judgment on
high-risk surfaces. It closes a different loop: after autonomous work lands, the
panel reviews the merge stream with deterministic heuristics and flags patterns
that are easy for busy operators to miss. A buyer or reviewer can ask, "What has
Sapphire been merging, and did any merge quietly bypass safety controls?" The
panel gives a concrete answer.

## Product Promise

Sapphire can operate autonomously because it does not treat autonomy as an act
of faith. The audit panel is the weekly red-team pass over the merge log. It
looks for oversized changes, weak commit subjects, safety-control edits without
review, missing tests for new modules, scope creep, token-shaped material in
diff metadata, generated data without provenance, merges after failed checks,
and dropped `[skip ci]` markers during no-spend work.

The output is intentionally boring in the best possible way. It is a Markdown
report that can be pasted into an issue, diligence room, or operator thread
without leaking full diffs, PR bodies, secrets, or raw customer data. It lists
PR numbers, short SHAs, titles, file counts, line counts, rule IDs, summarized
evidence, and recommended actions.

## Heuristics

`oversize_diff` catches PRs with more than 2,000 changed lines across more than
15 files. Large changes are not automatically bad, especially during tranche
integration work, but they deserve explicit lane framing and spot checks. A
synthetic example is a "dashboard card" PR that changes 40 files and 3,000
lines across services, docs, plugins, and infra. That is likely too much for
the title to describe honestly.

`weak_commit_message` catches commit subjects shorter than 10 characters or
subjects such as `wip`, `fix`, `update`, and `misc`. Weak subjects make later
forensics harder. The panel does not require poetry; it requires enough context
for a reviewer to understand what was intentionally changed.

`kill_switch_touched_without_review` watches `lib/core/kill_switch.py`,
`lib/core/confirmation_firewall.py`, and `lib/core/risk_kernel.py`. If one of
those files changes without an `@arigatoexpress` review marker, the finding is
critical. The panel is conservative because these files control autonomy and
safety posture. A finding is not a proof of harm; it is a demand for review.

`tests_missing_for_new_module` looks for newly changed Python modules under
`lib/` or `plugins/` without an obvious companion test in `tests/unit/` or
`plugins/claw-sapphire/tests/`. It is intentionally heuristic. It catches the
common failure mode where a new tool or library lands with docs but no proving
test.

`scope_creep` detects narrow subjects with wide file-area spread. A PR titled
"fix dashboard card" that also changes infra, plugins, services, analytics, and
docs will be flagged. Broadly named integration and readiness sweeps are not
treated the same way, because their title already tells reviewers to expect a
multi-area diff.

`secret_signature` scans collected diff metadata for token-shaped strings and
private-key markers. The panel never stores or reports the matched secret value.
It reports a secret-like pattern and tells the operator to confirm, rotate if
real, and purge history if needed.

`provenance_envelope_missing` watches generated JSON under `data/`. If a
`data/<area>/*.json` artifact appears without a sibling `*.envelope.json`, the
panel flags it. This matches Sapphire's tranche discipline: generated
artifacts need provenance so future reviewers know what produced them and which
source files informed them.

`failed_check_overridden` catches PRs whose status rollup appears failed,
timed out, cancelled, or action-required at merge time. This is critical
because autonomous merging must be able to show either green hosted checks or
honest local gate evidence.

`ci_skip_dropped` catches merged subject history without `[skip ci]` during the
no-spend posture. This rule exists because a squash title can drop `[skip ci]`
even when the branch commits carried it. The finding recommends the safe-merge
wrapper or an explicit squash title.

## Scoring

The scorer converts findings into a per-PR risk score in `[0, 1]`. Critical
findings carry the largest weight, high findings carry a smaller but still
substantial weight, and low findings mainly serve as hygiene signals. Confidence
modulates each weight. Multiple findings can stack, but the score caps at
`1.0`.

The panel also emits a histogram with PR count, finding count, clean count,
severity buckets, average score, and max score. This lets the operator separate
one severe PR from a broad degradation in merge hygiene.

## Operating Model

The service runner uses the GitHub CLI. It reads merged PRs for a time window,
collects bounded metadata, runs pure heuristics, writes a Markdown report and a
structured JSON sidecar under `~/.cache/sapphire/audit_panel/`, stamps the JSON
with `lib/core/provenance.py`, and optionally creates or comments on a GitHub
issue labelled `audit-panel`.

When high or critical findings exist, the service opens a findings issue. When
the window is clean or only lower severity, it comments on a rolling summary
issue, creating that issue if needed. The plugin defaults to read-only local
report generation and does not publish issues unless explicitly asked.

Hard caps keep the surface bounded:

- `MAX_PRS_PER_RUN=200`
- `MAX_REPORT_BYTES=50000`
- `MAX_LIVE_GH_API_CALLS_PER_HOUR=30`

The GitHub call cap matters because a naive audit could inspect every PR with
many detail calls. This implementation counts `gh` calls and fails closed if
the cap is exceeded.

## Buyer Framing

The point of the audit panel is not that Sapphire never makes mistakes. The
point is that Sapphire has a mechanism for noticing the specific classes of
mistake that matter for autonomous software operations: scope drift,
insufficient evidence, missing provenance, secret leakage, and safety-control
changes without review. That is a much stronger acquisition story than saying
"the agent checked its own work."

In diligence, this panel should be presented as the operational trust loop:
agents build, tests verify locally, safe-merge discipline controls spend, and
the audit panel reviews the merged stream after the fact. Findings become
operator tasks or follow-up PRs. Clean reports become evidence that the merge
process is stable.

## Limitations

The panel is heuristic, not a formal verifier. It cannot prove that a PR was
safe. It cannot reconstruct every CI state if GitHub metadata is incomplete. It
does not read full diffs into reports, so a confirmed secret investigation may
still require a separate protected workflow. It also cannot decide whether a
large PR was justified; it can only force that question into the open.

Those limits are intentional. The panel is a weekly audit surface, not a
blocking reviewer and not a replacement for CODEOWNERS on trading-critical or
security-critical paths.

## Version 0.1.0 Scope

Version 0.1.0 ships the pure heuristic library, risk scorer, paste-safe
reporter, GitHub CLI service runner, LaunchAgent template, stdin-JSON plugin
tool, registry entry, unit tests, plugin tests, and this product documentation.
It stays read-only by default and does not merge, close, reopen, or modify PRs.
The only GitHub write it can perform is creating or commenting on the audit
panel issue it owns.

## Example Weekly Narrative

A typical weekly report might say that 18 PRs were audited, 14 were clean, two
had medium findings, one had a high finding, and one had a critical finding.
The medium findings might be dropped `[skip ci]` markers on squash titles. The
high finding might be a generated `data/intelligence/report.json` without a
provenance sidecar. The critical finding might be a safety-control file changed
without a review marker.

That report immediately creates an operating queue. The no-spend marker issue
becomes a safe-merge process fix. The provenance issue becomes a tiny PR that
stamps the artifact and documents its source hashes. The safety-control issue
becomes a required human review before the change can be treated as settled.
None of those actions require drama or a broad rewrite. The value of the panel
is that it turns ambiguous trust concerns into small, reviewable next steps.

The report also helps distinguish process flaws from product flaws. A large
diff may be acceptable if it was a planned integration pass with complete tests.
A missing provenance envelope may be a documentation failure, not a runtime
failure. A weak commit message may not change behavior at all. But in aggregate
these findings show whether autonomous operations are becoming easier or harder
to audit.

## Diligence Use

For a diligence reviewer, the panel should be paired with three other artifacts:
the PR list, local verification logs, and the relevant runbook. The PR list
shows the actual merge stream. Verification logs show what commands were run
before merge. The runbook explains what the new surface is supposed to do. The
audit panel then answers whether the merge stream itself followed Sapphire's
rules.

This distinction matters. A buyer does not need to believe that every agent is
perfect. They need to see that the operating system is instrumented to catch
known failure modes and that findings become durable follow-up work. In that
sense, the audit panel is not just a security tool. It is a management surface
for autonomous engineering quality.

## Extension Path

Future versions can add deeper GitHub GraphQL collection, CODEOWNERS mapping,
review-thread resolution awareness, trend charts, and dashboard rendering. They
can also learn from false positives by storing reviewed outcomes in a separate
operator-owned annotation file. Version 0.1.0 avoids that complexity so the
first release remains easy to test: deterministic inputs, deterministic
findings, bounded report output, and one clearly owned issue surface.
