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
   for f in pyproject.toml requirements.txt requirements-test.txt \
            services/*/requirements.txt clients/*/requirements.txt; do
     [ -f "$f" ] && cat "$f" | grep -oE '^[a-zA-Z0-9_-]+' | sort -u
   done > /tmp/sapphire-deps.txt
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

10. Print a one-line status summary to stdout: either
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
