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
