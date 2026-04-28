# Audit Panel Runbook

Date: 2026-04-28

## Purpose

The audit panel is a weekly read-only review of Sapphire merged PR history. It
exists to help Ari and future reviewers answer three questions quickly:

1. What did autonomous agents merge recently?
2. Did any merge touch safety-sensitive surfaces or bypass evidence gates?
3. Which PRs need follow-up review, tests, provenance, or merge-hygiene repair?

The panel is intentionally narrow. It never merges PRs, never pushes commits,
never closes or reopens PRs, never sends Telegram messages, never touches
trading execution, and never prints secret values. It can optionally create or
comment on GitHub issues labelled `audit-panel`; that issue is the only write
surface it owns.

## Files

- `lib/audit_panel/heuristics.py` contains the pure detectors.
- `lib/audit_panel/scorer.py` converts findings into risk scores.
- `lib/audit_panel/reporter.py` renders paste-safe Markdown.
- `services/audit_panel/run.py` collects GitHub metadata through `gh`, writes
  reports, stamps provenance, and optionally publishes an audit issue.
- `services/audit_panel/launchagent/com.sapphire.audit-panel.plist.template`
  is the weekly LaunchAgent template. Do not load it until dry-run output has
  been reviewed.
- `plugins/claw-sapphire/tools/internal/audit_panel.py` exposes stdin-JSON
  actions for local operator and Hermes use.
- `plugins/claw-sapphire/tools/audit_panel.py` is a compatibility shim.

## Safety Posture

Default behavior is read-only. The plugin action `run-once` defaults
`open_issue=false`, which means it writes local cache artifacts only. The
service runner defaults to publishing issues because it is meant to run as the
scheduled panel, but operators can pass `--no-issue` during dry runs.

The runner uses hard caps:

- `MAX_PRS_PER_RUN=200`
- `MAX_REPORT_BYTES=50000`
- `MAX_LIVE_GH_API_CALLS_PER_HOUR=30`

If the GitHub call cap is exhausted, the run fails closed rather than silently
continuing with unbounded API use. Reports are truncated at the byte cap and
the full structured JSON remains in the local sidecar.

## Dry Run

From the Sapphire checkout:

```bash
/usr/local/bin/python3 services/audit_panel/run.py --no-issue
```

Expected result: JSON printed to stdout with `report_path`, `json_path`,
`envelope_path`, `pr_count`, `finding_count`, and `histogram`. The report and
JSON are written under `~/.cache/sapphire/audit_panel/`.

To inspect the latest report through the plugin:

```bash
echo '{"action":"latest-report"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/audit_panel.py
```

To score a synthetic PR without GitHub:

```bash
echo '{"action":"pr-score","number":1,"title":"feat: audit","commits":["feat: audit"]}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/audit_panel.py
```

That example should return a `ci_skip_dropped` finding because the subject lacks
`[skip ci]`.

## Publishing Mode

Publishing mode is still bounded. The panel creates a findings issue only when
there is at least one high or critical finding. Otherwise it comments on the
rolling summary issue titled `Sapphire audit-panel rolling summary`, creating
that issue if needed.

Manual publishing command:

```bash
/usr/local/bin/python3 services/audit_panel/run.py
```

Plugin publishing is explicit:

```bash
echo '{"action":"run-once","open_issue":true}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/audit_panel.py
```

Use the plugin publishing path only when you intentionally want the plugin to
write the audit issue. The default plugin path is local-only.

## LaunchAgent Installation

The committed plist is a template. Review it before copying:

```bash
plutil -lint services/audit_panel/launchagent/com.sapphire.audit-panel.plist.template
```

After dry-run output looks correct, copy the template to the LaunchAgents
directory and load it manually:

```bash
cp services/audit_panel/launchagent/com.sapphire.audit-panel.plist.template \
  ~/Library/LaunchAgents/com.sapphire.audit-panel.plist
launchctl load ~/Library/LaunchAgents/com.sapphire.audit-panel.plist
launchctl list | grep com.sapphire.audit-panel
```

The template fires Monday at 08:15 local time from
`/Users/aribs/Code/Sapphire` and writes logs to
`~/.local/var/log/sapphire/audit-panel.out.log` and
`~/.local/var/log/sapphire/audit-panel.err.log`.

Rollback is simple:

```bash
launchctl unload ~/Library/LaunchAgents/com.sapphire.audit-panel.plist
rm ~/Library/LaunchAgents/com.sapphire.audit-panel.plist
```

Do not unload other Sapphire LaunchAgents while rolling this back.

## Interpreting Findings

Critical findings require immediate operator review. A critical finding may be
a safety-control edit without owner review, token-shaped diff metadata, or a PR
that appears merged after failed checks. Start by reading the PR, confirming
whether the finding is real, and recording the outcome in the audit issue.

High findings usually mean evidence is missing. The most common examples are a
new module without a companion test or a generated data artifact without a
provenance envelope. The preferred response is a focused follow-up PR, not a
large cleanup sweep.

Medium findings are merge hygiene and scope risks. Oversize PRs, scope creep,
and missing `[skip ci]` markers belong here. These should become process
improvements or small wrapper fixes.

Low findings are auditability nits such as weak commit messages. They matter
over time because weak subjects make forensic review slower, but they rarely
require emergency action.

## Troubleshooting

If the runner says `gh command failed`, verify authentication:

```bash
gh auth status -h github.com
```

If no PRs are audited, check the time window. The default is seven days. You can
override with:

```bash
/usr/local/bin/python3 services/audit_panel/run.py --since 2026-04-21 --no-issue
```

If issue creation fails, run with `--no-issue` and preserve the local report.
The local artifacts are still useful evidence, and the JSON sidecar is stamped
with provenance.

If the report is truncated, read the JSON sidecar referenced by stdout. The
Markdown cap protects paste safety and GitHub issue ergonomics; the structured
sidecar contains all findings.

## Verification

Focused checks for this lane:

```bash
/usr/local/bin/python3 -m pytest tests/unit/test_audit_panel_heuristics.py \
  tests/unit/test_audit_panel_scorer.py \
  tests/unit/test_audit_panel_reporter.py \
  tests/unit/test_audit_panel_run.py \
  plugins/claw-sapphire/tests/test_audit_panel.py -q --tb=short
ruff check lib/audit_panel services/audit_panel plugins/claw-sapphire/tools/internal/audit_panel.py \
  plugins/claw-sapphire/tools/audit_panel.py tests/unit/test_audit_panel_heuristics.py \
  tests/unit/test_audit_panel_scorer.py tests/unit/test_audit_panel_reporter.py \
  tests/unit/test_audit_panel_run.py plugins/claw-sapphire/tests/test_audit_panel.py
/usr/local/bin/python3 scripts/validate_tool_registry.py
```

Broader lane verification, when time allows:

```bash
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external
```

## Residual Risk

The audit panel is not an authorization gate. A clean report does not prove
that every merged PR was correct. A finding does not prove wrongdoing. The
panel is best understood as a deterministic weekly reviewer that finds the
classes of merge anomaly Sapphire cares about most.

Future versions should add richer GitHub GraphQL collection, explicit
CODEOWNERS awareness, trend comparisons across weeks, and a dashboard card for
the latest histogram. Version 0.1.0 deliberately stays small, testable, and
easy to reason about.

## Weekly Operator Procedure

Each Monday, review the latest audit issue or local report in this order. First,
read the histogram. If the clean count is high and the max score is low, the
week likely needs no immediate action. Second, read critical and high findings
before anything else. Do not start broad cleanup from medium or low findings
while a safety-control or secret-signature item is still unresolved. Third,
open each flagged PR and compare the panel evidence to the actual PR metadata.
If the finding is real, add a short comment to the audit issue with the chosen
disposition: follow-up PR, accepted with reason, false positive, or operator
review completed.

For a follow-up PR, keep the scope tiny. A provenance finding should generally
produce a sidecar and a test. A missing-test finding should produce focused
tests for the new module. A dropped `[skip ci]` finding should point to the
safe-merge wrapper and does not require rewriting history unless a hosted run
actually spent money. A weak commit message finding is usually a process note
for the next merge, not a reason to churn the repository.

For a false positive, preserve the reason in the issue. Examples include a
fixture JSON under `data/` that is intentionally not generated, a test file
whose name is not directly derivable from the module stem, or a broad tranche
PR whose title honestly described an integration pass. These notes are useful
input for later heuristic tuning.

## Incident Escalation

If `secret_signature` fires, do not paste the suspected value anywhere. Open
the PR in GitHub, inspect the relevant changed file through the protected UI,
and decide whether the token-shaped material is a placeholder or a real secret.
If it is real, rotate the credential first, then decide whether history purge is
required. Record only the credential class and rotation timestamp in the audit
issue.

If `failed_check_overridden` fires, look for local verification evidence in the
PR body or handoff. If evidence exists, add it to the audit issue and decide
whether the hosted failure was expected, skipped by no-spend policy, or a real
regression. If no evidence exists, open a focused verification PR or issue and
rerun the relevant local gates before relying on the merged behavior.

If `kill_switch_touched_without_review` fires, treat it as urgent even if the
diff appears harmless. Confirm whether `@arigatoexpress` reviewed the change
outside GitHub. If not, do not broaden the change. Either obtain review, revert
the safety-control change, or open a follow-up PR that restores the invariant
with tests.

## Data Retention

Local reports live under `~/.cache/sapphire/audit_panel/`. They are operational
artifacts, not source of truth. Keep recent reports during a tranche or
diligence window, but do not commit cache outputs to the repo. If a report needs
to become durable, preserve the GitHub issue URL and the PR numbers it covers.
The JSON sidecar includes a provenance envelope so the local artifact can be
checked while it exists, but the repo should remain clean of weekly generated
audit output.

When sharing reports outside the working thread, prefer the GitHub issue link
over copying local JSON. The Markdown issue is designed for paste safety and
contains enough context for triage. The JSON is for local reproducibility,
debugging, and future dashboard ingestion. Do not attach raw diffs, PR bodies,
or local cache directories to diligence packets unless a human has reviewed the
content for secrets and private operational notes.

Treat this as part of the weekly operator rhythm, not an emergency-only tool.
Routine review makes later diligence calmer and much easier.
