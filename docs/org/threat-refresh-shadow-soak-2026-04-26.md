# Threat-Refresh Remote Shadow Soak

Date: 2026-04-26

## Decision

Move `threat-refresh` from `shadowing` to `soaking` in `infra/org-repos.yaml`.
The local LaunchAgent `com.sapphire.threat-refresh` remains canonical until the
documented soak gate passes and a later PR disables it with rollback notes.

## Evidence

Remote workflow:

- Workflow: `.github/workflows/threat-refresh.yml`
- Manual run id: `24961094947`
- Trigger: `workflow_dispatch` on `main`
- Result: success in 14 seconds
- Artifact: `threat-refresh-24961094947`

Local artifact:

- Path: `data/intelligence/2026-04-26/threats.json`
- Refreshed at: `2026-04-26T15:49:13.043689+00:00`
- Threat count: 15

Remote artifact:

- Path: downloaded GitHub Actions artifact under `/tmp`
- Refreshed at: `2026-04-26T16:10:47.292371+00:00`
- Threat count: 15

Comparator command:

```bash
python3 scripts/ops/compare_threat_artifacts.py \
  --local data/intelligence/2026-04-26/threats.json \
  --remote /tmp/sapphire-threat-shadow.3P6Dcd/threat-refresh-24961094947/data/intelligence/2026-04-26/threats.json \
  --report-out /tmp/sapphire-threat-shadow.3P6Dcd/reports \
  --verbose
```

Comparator result:

- Verdict: WARN
- Rows compared: 15
- PASS rows: 12
- WARN rows: 3
- FAIL rows: 0
- Missing in local: 0
- Missing in remote: 0
- Source count delta: 0

WARN rows were all `published_at` day-offset differences for otherwise matched
CVE IDs. No canonical ID was missing on either side in the close-time comparison.

## Prior Timing Check

The latest scheduled remote artifact before the manual run was created about 1
hour 40 minutes before the local artifact and produced a FAIL due to four
asymmetric CVE IDs. A close-time manual run removed the ID asymmetry, so this is
being treated as timing drift until scheduled soak evidence proves otherwise.

## Soak Gate

Do not retire the local LaunchAgent until all of the following are true:

- At least 24 scheduled remote cycles have completed successfully over 4 days.
- Each sampled local/remote comparison has 0 FAIL rows.
- At least 80 percent of compared rows are PASS, with WARN limited to known
  public-feed timestamp or low-risk metadata drift.
- Missing canonical IDs are 0 in both directions for close-time comparisons.
- Rollback remains a simple re-enable of the local LaunchAgent plist.

## Safety

No LaunchAgent was unloaded or edited. No Telegram message was sent. No secrets,
request bodies, raw payloads, or threat record bodies are included in this note.
