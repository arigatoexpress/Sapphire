# Threat Intel Sweep Runbook

Run by the cloud routine **Sapphire threat intel sweep** (cron `0 11 * * *`,
11:00 UTC = 05:00 America/Denver). Also the manual fallback if the routine
is paused.

## Goal

Pull the CISA Known Exploited Vulnerabilities (KEV) catalog and the GitHub
Security Advisories that affect Sapphire's direct dependencies. If any
critical-or-exploited CVE not previously surfaced is detected, open a
single GitHub issue summarizing the new threats. If no new critical
threats appear, exit 0 silently.

## Critical Safety

- **Read-only.** Do not modify any tracked file, do not push any branch,
  do not merge any PR, do not run any deploy.
- **Public-data sources only.** CISA KEV is a public JSON feed; GitHub
  Advisories use the public `gh api` endpoint. Do not attempt to access
  any vendor portal that requires credentials.
- **One issue per new-CVE-set per day, idempotent.** Compute a
  fingerprint over the sorted CVE IDs in the new-criticals set; if an
  open issue with `fingerprint=<FP>` already exists, exit 0 silently.
- **Never duplicate** the merged-PR-#299 patterns: the body should
  reference the runbook by name, never include secret values, and never
  echo internal authentication tokens from `gh`.
- **No emojis** in titles, branches, commits, or issue bodies.
- **Cloud-only execution.** Do not assume cyber-threat-bot is checked
  out, the local Mac is up, or any LaunchAgent is reachable.

## Steps

1. `gh auth status` must succeed. Otherwise exit 0 with no commit and
   log "no gh auth, skipping".

2. Fetch the CISA KEV catalog:
   ```bash
   curl -fsSL \
     https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json \
     -o /tmp/kev.json
   ```
   If the curl fails, exit 0 with a log line; do not open an issue
   about CISA being down (that would be noise).

3. Identify critical entries:
   - `vulnerabilities[].requiredAction != ""`
   - `vulnerabilities[].knownRansomwareCampaignUse == "Known"`
     OR added to KEV in the past 7 days (`dateAdded > today - 7d`).
   - Cap at the 10 most severe entries (sort by `dateAdded` desc).

4. Cross-reference with Sapphire's dependencies. Read top-level package
   names from each of these manifests if they exist:
   ```bash
   {
     # requirements.txt-style files: take the package name before any
     # version specifier or comment
     for f in requirements.txt requirements-test.txt \
              services/*/requirements.txt clients/*/requirements.txt; do
       [ -f "$f" ] && grep -hoE '^[a-zA-Z0-9_.-]+' "$f"
     done
     # pyproject.toml: parse project dependency arrays only. Grep/regex over
     # the whole TOML file captures unrelated quoted strings such as Ruff
     # rule codes and workspace paths.
     [ -f pyproject.toml ] && python3 - <<'PY'
import re
import tomllib
from pathlib import Path
data = tomllib.loads(Path("pyproject.toml").read_text())
project = data.get("project", {})
deps = list(project.get("dependencies", []))
for values in (project.get("optional-dependencies", {}) or {}).values():
    deps.extend(values)
for dep in deps:
    name = re.split(r'\s*(?:[<>=!~]=?|;|\[)', dep, maxsplit=1)[0].strip()
    if name:
        print(name)
PY
   } | sort -u > /tmp/sapphire-deps.txt
   ```
   For each KEV entry, check whether its `vendorProject` or affected
   product overlaps lexically with `/tmp/sapphire-deps.txt`. Mark
   matches as `RELEVANT_TO_SAPPHIRE: true`. The remainder are general
   awareness only.

5. Fetch GitHub Security Advisories that affect Sapphire dependencies:
   ```bash
   gh api 'repos/arigatoexpress/Sapphire/dependabot/alerts?state=open&per_page=100' \
     --jq '.[] | {ghsa_id: .security_advisory.ghsa_id, severity: .security_advisory.severity, package: .dependency.package.name, summary: .security_advisory.summary, created_at: .created_at}' \
     > /tmp/sapphire-ghas.json
   ```
   If the call fails (alerts may be disabled), proceed without GHAS data
   and note it in the issue.

6. Compute the new-critical set:
   - From step 3: KEV entries flagged `RELEVANT_TO_SAPPHIRE: true` OR
     ransomware-campaign-known.
   - From step 5: GHAS alerts with severity `critical` or `high`.
   - Sort by CVE ID, sha1 the joined string, take first 12 chars
     as `FP`.

7. Idempotency check:
   ```bash
   gh issue list --state open --label threat-intel-sweep \
     --search "fingerprint=$FP" --json number,title,body --limit 5
   ```
   If any result has `fingerprint=$FP` literally in its body, exit 0
   silently.

8. If no new criticals at all, exit 0 silently.

9. Open one issue:
   - Title: `Threat intel sweep: <N_CRIT> critical threats detected`
   - Labels: `threat-intel-sweep`, `security`.
   - Body sections:
     1. `## Summary` — total CISA KEV new-critical count (last 7d),
        Sapphire-relevant subset count, GHAS critical+high count.
     2. `## CISA KEV — Sapphire-relevant` — table: CVE ID, vendor,
        product, dateAdded, ransomware-known, requiredAction.
     3. `## GHAS critical/high` — table: GHSA ID, package, severity,
        summary, created_at.
     4. `## CISA KEV — general awareness` — bulleted list of the
        non-Sapphire-relevant criticals from step 3 (max 10).
     5. `## Fingerprint` — single line `fingerprint=<FP>`.
     6. `## Suggested next action` — one short sentence prioritizing
        Sapphire-relevant items first.

10. Supersede older open sweep issues conservatively.

    The exact-fingerprint check in step 7 prevents duplicate issues for
    identical CVE sets. A newer sweep can still partially supersede an
    older open issue when some CVEs carry forward and others age out. After
    creating the new issue, inspect older open issues with the same label:

    ```bash
    gh issue list --state open --label threat-intel-sweep \
      --json number,title,body,createdAt --limit 20
    ```

    Comment and close an older issue as superseded only when all of these
    are true:

    - the older issue is more than 24 hours old and is not the issue just
      opened;
    - every ransomware-known CVE in the older issue is present in the new
      issue, or the older issue has no ransomware-known CVE that is absent
      from the new issue;
    - any unresolved blocker in the older issue is represented in the new
      issue, for example GHAS/Dependabot visibility unavailable;
    - neither issue contains a Sapphire-relevant dependency or deployment
      exposure that is absent from the other issue.

    Use a short comment such as:

    ```text
    Closing as superseded by #<new_issue>. The newer sweep carries the
    still-relevant ransomware-known set and the same unresolved blocker;
    no older Sapphire-relevant dependency or deployment exposure is being
    dropped.
    ```

    If the comparison is ambiguous, leave both issues open and add a
    triage comment rather than closing automatically.

11. Print a one-line status summary to stdout: either
    `threat-intel-sweep: clear` or
    `threat-intel-sweep: <N_CRIT> criticals, issue #<num>`.

## Closure Criteria

This section makes step 10 deterministic enough for an autonomous agent
to execute without human adjudication. Step 10 narrates the *what*; this
section binds the *how* — every term has a single observable definition
and the rules evaluate to a strict close-or-keep-open verdict.

### Definitions

The agent MUST compute these from the issues themselves and the live
repo. Do not infer values from memory.

* **`threat-intel-sweep`-labeled issue.** Any issue returned by
  `gh issue list --state open --label threat-intel-sweep --json
  number,title,body,createdAt,comments`. The set the rules operate on.
* **Ransomware-known set (per issue).** The set of CVE IDs in that
  issue's body whose KEV row has `knownRansomwareCampaignUse == "Known"`.
  In practice this is the union of the ransomware-flagged rows in the
  `## CISA KEV — Sapphire-relevant` table plus any ransomware-flagged
  rows in `## CISA KEV — general awareness`. Extract by literal CVE-ID
  match against the most recent CISA KEV catalog (`/tmp/kev.json` from
  step 2). If the catalog is unreachable, treat the ransomware-known set
  as **unknown** and skip the auto-close path entirely — fall through to
  the "leave both open" branch.
* **Critical set (per issue).** The union of all CVE IDs surfaced in the
  issue body across the `## CISA KEV — Sapphire-relevant`,
  `## GHAS critical/high`, and `## CISA KEV — general awareness`
  sections. Used for the soft rule below.
* **Fingerprint.** The 12-char `fingerprint=<FP>` token from the issue's
  `## Fingerprint` section (step 9 emits this verbatim). Two issues with
  identical fingerprints are duplicates, not supersession candidates;
  the duplicate is handled by step 7 and never reaches this section.
* **Sapphire's stack.** The deduplicated package-name list produced by
  step 4 plus the literal vendor/product strings present in:
  * `pyproject.toml` (project + optional dependencies, parsed via the
    `tomllib` block in step 4 — not a regex over the whole TOML);
  * every `requirements*.txt` and `services/*/requirements.txt` and
    `clients/*/requirements.txt`;
  * every `Dockerfile` and `Dockerfile.*` reachable under `services/`,
    `clients/`, and the repo root (case-insensitive `apt-get install`,
    `pip install`, `RUN` lines and base-image `FROM` lines);
  * every `package.json` reachable (root + `tools/*/package.json` +
    `services/*/package.json` + `lib/*/package.json`); inspect the
    `dependencies`, `devDependencies`, and `peerDependencies` keys, not
    a substring grep over the whole file.
  A CVE is "in Sapphire's stack" iff its `vendorProject` or affected
  product appears (case-insensitive substring) in this stack list.
* **Aged-out CVE.** A CVE in the older issue's critical set that is
  **absent** from the newer issue's critical set.
* **Operator override.** A comment on the older issue (any author, any
  position) whose body contains the literal token `do-not-supersede`.
  The token match is case-insensitive but exact — `donotsupersede` and
  `do not supersede` do **not** match. Override force-keeps the issue
  open regardless of every other rule below.

### Hard rule (auto-close)

Auto-close an open `threat-intel-sweep`-labeled issue **only when all of
the following hold**:

1. The issue is more than 24 hours old (`createdAt < now - 24h`).
2. It is not the issue just opened in step 9.
3. **No** comment on the issue contains `do-not-supersede`.
4. The older issue's ransomware-known set is a subset (proper or equal)
   of the newer issue's ransomware-known set — i.e. every
   ransomware-known CVE carried forward.
5. **Every** aged-out CVE (older.critical_set − newer.critical_set) is
   *not* in Sapphire's stack as defined above. If any aged-out CVE is
   in the stack, do **not** auto-close — surface the gap in a triage
   comment instead.

### Soft rule (supersede + close on partial overlap)

If the hard rule does not apply but the older issue still looks
substantially superseded, auto-close when **all** of the following hold:

1. The issue is more than 24 hours old.
2. No `do-not-supersede` comment exists.
3. `len(older.critical_set ∩ newer.critical_set) / len(older.critical_set)
   ≥ 0.75` — at least 75% of the prior critical set carries forward.
4. The prior issue's open blocker is captured verbatim in the newer
   issue. The canonical example: the GHAS/Dependabot
   visibility/disabled-alerts language. Detect by searching the newer
   issue's body for the substring "Dependabot" *and* either "disabled"
   or "unavailable" or "admin:repo_hook". If the older issue tracks a
   different blocker (operator-defined Sapphire-relevant follow-up,
   patched-but-unverified note, etc.) and that text is not present in
   the newer issue, do **not** auto-close — leave open.
5. No aged-out CVE is in Sapphire's stack (same check as hard rule
   condition 5).

### Operator override

A `do-not-supersede` comment on the older issue keeps it open
**regardless** of the hard rule, the soft rule, or any future rule.
This is the single escape hatch — operators can pin an issue open
without explaining why. The override is per-issue; commenting on the
*newer* issue has no effect on closure of the older one.

### Closure comment template

When either rule fires, the agent MUST close with a single comment of
this exact shape (substitute angle-bracket fields):

```text
Closing as superseded by #<NEW>. <RULE> applied: <RATIONALE>. The
ransomware-known set carried forward, the prior open blocker
(<BLOCKER>) is tracked verbatim in the newer issue, and no aged-out
CVE is in Sapphire's stack (`pyproject.toml`, `requirements*.txt`,
`Dockerfile*`, `package.json` checked).
```

`<RULE>` is `Hard rule` or `Soft rule (≥75% carry-forward)`.
`<BLOCKER>` is the verbatim blocker phrase (e.g. `GHAS/Dependabot
visibility unavailable`).

### Worked example: #393 → #479

This is the canonical case study that motivated the rule.

* **#393** (opened 2026-04-28, closed-as-superseded 2026-04-30):
  4 critical threats. Ransomware-known set = {PaperCut NG/MF,
  JetBrains TeamCity, Microsoft Exchange Server}. Critical set
  included the ransomware trio plus 7 non-ransomware CVEs:
  CVE-2025-29635, CVE-2024-7399, CVE-2024-57728, CVE-2024-57726,
  CVE-2026-39987, CVE-2026-33825 (MS Defender), CVE-2026-20131
  (Cisco FMC). Open blocker = GHAS/Dependabot visibility unavailable.
  Fingerprint = `5e2d12c40dee`.
* **#479** (opened 2026-04-29): 3 critical threats. Ransomware-known
  set = {PaperCut NG/MF, JetBrains TeamCity, Microsoft Exchange Server}
  — identical to #393's. 6 of #393's 7 non-ransomware CVEs reappear;
  CVE-2026-33825 and CVE-2026-20131 aged out. Open blocker = same
  GHAS/Dependabot disabled language. Fingerprint = `214076175a1e`.

Apply the **Hard rule** to #393 with #479 as the newer issue:

1. Age: 2026-04-30 − 2026-04-28 > 24h. ✅
2. Not the just-opened issue. ✅
3. No `do-not-supersede` comment on #393. ✅
4. Ransomware-known(#393) = Ransomware-known(#479) → subset. ✅
5. Aged-out CVEs = {CVE-2026-33825, CVE-2026-20131}. Stack-check:
   `MS Defender` and `Cisco Secure Firewall Management Center` (FMC)
   absent from `pyproject.toml`, `requirements*.txt`, every service
   `Dockerfile`, `tools/claude-analytics/package.json`. ✅

All five hold ⇒ auto-close #393 with the closure-comment template.
This matches the human triage that landed on 2026-04-30
(`5e2d12c40dee` → `214076175a1e`) verbatim.

If, hypothetically, CVE-2026-20131 had affected `cisco-fmc-client`
and that package were in `services/security_pipeline/requirements.txt`,
condition 5 would fail and the agent would leave #393 open with a
triage comment naming the in-stack aged-out CVE.

## Routine Prompt Diff

The autonomous closure logic above only fires if the cloud routine
prompt for `Sapphire threat intel sweep` instructs the agent to run
step 10 *and* the Closure Criteria evaluation after step 9. The
routine prompt currently lives at `claude.ai/code/routines` (managed
via the `RemoteTrigger` MCP) and is **not** stored in this repo. A
local mirror of the same name lives at
`~/.claude/scheduled-tasks/threat-intel-sweep/SKILL.md`, but that
mirror runs the cyber-threat-bot Markdown sweep and never opens
issues — it is *not* the routine that owns the closure path.

When the operator next edits the cloud routine prompt, append an
explicit instruction such as:

```text
After step 9 of docs/ops/threat-intel-sweep-runbook.md, evaluate the
"Closure Criteria" section against every other open issue with the
threat-intel-sweep label. Apply the Hard rule first; if it does not
fire, apply the Soft rule. Honor any do-not-supersede operator
override. For each close that fires, post the Closure comment
template verbatim and call `gh issue close <N>`. If neither rule
applies, leave the older issue open and post a single triage comment
that names the divergence.
```

No code change is required — the runbook is the contract; the
routine prompt is the dispatcher. Update one without the other and
the closure path becomes dormant (rule documented, never executed)
or undefined (routine asks for a section that does not exist).

## Required tools

`Bash`, `Read`, `Glob`, `Grep`, plus `gh` and `curl` on PATH. No write or
edit tools.

## Out of scope

- Generating per-CVE remediation briefs. The issue surfaces; humans
  pursue.
- Patching dependencies. That's `dependency-drift-digest` plus human
  review.
- MITRE ATT&CK enrichment. Belongs in a separate weekly runbook.
- Any vendor-portal queries that require authentication.

## Dependabot alerts fetcher (closes issue #393)

Issue #393 noted that the inline `gh api` call on step 5 was unreachable
in some environments (missing scope, gh-cli version drift, or a
transiently-disabled Dependabot surface). The new
`scripts/ops/dependabot_alerts_fetch.py` wraps that call with
**explicit token validation, pagination handling, and a paste-safe
markdown digest** so the runbook (or any operator) can fetch alerts in
one command:

```bash
# Full JSON envelope (default):
python3 scripts/ops/dependabot_alerts_fetch.py

# Paste-safe markdown digest only (suitable for issue bodies):
python3 scripts/ops/dependabot_alerts_fetch.py --markdown-only

# Structured JSON without the markdown payload:
python3 scripts/ops/dependabot_alerts_fetch.py --json-only

# Different repo:
python3 scripts/ops/dependabot_alerts_fetch.py --repo arigatoexpress/cyber-threat-bot

# Different alert state:
python3 scripts/ops/dependabot_alerts_fetch.py --state fixed
```

### Contracts

* **Read-only.** The script only reads the GitHub API. It never opens
  PRs, creates issues, modifies tracked files, or pushes branches. The
  threat-intel runbook is responsible for converting the script's
  output into an issue body when needed.
* **Token validation first.** A missing or unscoped token surfaces as
  a non-zero exit with a sanitized error message — not as an empty
  alert list.
* **Paste-safe summary.** The markdown digest contains severity
  buckets, ecosystem counts, and a bounded top-N table (default 10).
  No token values, no repository secrets, no PII.
* **Pagination handled.** The script calls `gh api --paginate`, so a
  repo with >30 alerts does not silently truncate.
* **Subprocess-injected for testability.** All `gh` calls go through a
  `Runner` callable. The unit suite at
  `tests/unit/test_dependabot_alerts_fetch.py` (21 cases) mocks
  `gh api` end-to-end so the tests never spawn a real `gh` process.

### When the runbook should call it

Replace step 5 (the inline `gh api` call) with:

```bash
python3 scripts/ops/dependabot_alerts_fetch.py --json-only \
  > /tmp/sapphire-ghas.json
```

The structured JSON output mirrors the original `--jq`-projected shape
closely enough that step 6 (compute the new-critical set) can read
`alerts[*]` without code changes. If the script exits non-zero, log
the error and proceed without GHAS data — same fallback as the
original step 5.

### Error envelope handling

When Dependabot is disabled for a repo, `gh api` returns
`{"message": "..."}` instead of a list. The fetcher detects this and
exits with `DependabotFetchError: gh api returned error envelope: ...`,
so the runbook does not silently believe the repo has zero alerts.
This is the failure mode that #393 was originally about.

## Issue #393 readiness verifier

When a threat-intel issue is already open and the remaining work is to
verify whether the issue can be commented or closed, run the read-only
readiness helper:

```bash
python3 scripts/ops/threat_intel_issue_393_readiness.py --markdown-only
```

The helper produces a paste-safe evidence block for issue #393. It:

* runs the Dependabot alerts fetcher and records whether GHAS data is
  available, unavailable, or skipped;
* fetches the current CISA KEV catalog and checks the runbook's
  critical-candidate window against Sapphire dependency manifests;
* scans repo/config evidence only for the ransomware-linked products
  called out in issue #393: PaperCut NG/MF, JetBrains TeamCity,
  Microsoft Exchange Server, and Cisco Secure Firewall Management
  Center.

Use the helper's `readiness.recommendation` field as follows:

* `ready_to_close` means CISA/dependency checks are clear,
  repo/config deployment evidence is absent for the named products, and
  Dependabot alerts were available with zero critical/high open alerts.
* `comment_with_evidence_ghas_unavailable_or_nonzero` means the
  CISA/deployment checks are clear, but GHAS/Dependabot still needs a
  repo-admin decision or a nonzero alert follow-up before closing.
* `keep_open_action_required` means the helper found a dependency or
  repo/config deployment signal that needs remediation or human review.

For offline tests or incident retrospectives, save a CISA KEV payload and
pass it explicitly:

```bash
python3 scripts/ops/threat_intel_issue_393_readiness.py \
  --kev-json /tmp/kev.json \
  --as-of 2026-04-28 \
  --markdown-only
```

## Related

* `docs/products/customer-dossier-0.2.0.md` — paired cohort surface
  that now uses cell-suppression + per-tenant hash isolation; same
  acquirer-readability theme.
* `tests/unit/test_dependabot_alerts_fetch.py` — full mock-driven
  test suite for the fetcher.
