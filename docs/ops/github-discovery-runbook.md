# GitHub Discovery Runbook

Run by the cloud routine **Sapphire github discovery** (cron `0 13 * * 1`,
13:00 UTC Monday = 07:00 America/Denver). Also the manual fallback if
the routine is paused.

## Goal

Survey the user's recently starred repositories and a curated set of
trending technical topics relevant to Sapphire. Identify high-value
synergies — repos that look like they could plug into existing
Sapphire surfaces (trading, content, intel, payments, agents). If any
high-confidence synergy is found, open one weekly digest issue. If
nothing scores high, exit 0 silently.

## Critical Safety

- **Read-only.** Do not star, fork, clone, modify, or comment on any
  external repository. The only side effect is one labeled issue.
- **One issue per ISO week.** Compute the ISO week stamp and refuse to
  re-open if an issue tagged with the same `iso_week=` already exists.
- **No external content fetching beyond gh API.** Do not download
  repository contents in bulk; the runbook only consumes README
  metadata and topic tags via the public `gh api` endpoint.
- **No emojis** in titles, branches, commits, or issue bodies.
- **Cloud-only execution.** Do not depend on local
  `~/Code/Sapphire/data/starred_repos/` paths; the cloud env starts
  with no Sapphire data directory.

## Steps

1. `gh auth status` must succeed. Otherwise exit 0 with no commit and
   log "no gh auth, skipping".

2. Compute the ISO week stamp:
   ```bash
   WEEK=$(date -u +'%G-W%V')
   ```

3. Idempotency check:
   ```bash
   gh issue list --state open --label github-discovery \
     --search "$WEEK" --json number,title,body --limit 5
   ```
   If any result contains `iso_week=$WEEK` in its body, exit 0 silently.

4. Fetch the user's most recently starred repos (last 50):
   ```bash
   gh api 'users/arigatoexpress/starred?per_page=50' \
     --jq '.[] | {full_name, description, language, stargazers_count, topics, updated_at, pushed_at}' \
     > /tmp/recent-starred.json
   ```

5. Fetch trending topics from a fixed allowlist of relevance to
   Sapphire's surfaces. For each topic, query the GitHub search API
   for repos updated in the last 30 days, capped at 10 per topic:
   ```
   topics: trading-bot, algorithmic-trading, llm-agent, agentic-ai,
           ontology, data-fabric, palantir-foundry, bigquery-pipeline,
           stablecoin, x402, model-context-protocol
   ```
   Use:
   ```bash
   for topic in trading-bot algorithmic-trading llm-agent agentic-ai \
                ontology data-fabric palantir-foundry bigquery-pipeline \
                stablecoin x402 model-context-protocol; do
     since=$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat())
PY
)
     gh api "search/repositories?q=topic:$topic+pushed:>$since&sort=stars&order=desc&per_page=10" \
       --jq '.items[] | {full_name, description, language, stargazers_count, pushed_at}' \
       >> /tmp/trending.json
   done
   ```

6. Score candidates. For each repo from steps 4 and 5, compute a simple
   relevance score:
   - +2 if topic includes any of: `trading`, `agent`, `ontology`,
     `intel`, `foundry`, `mcp`, `x402`.
   - +1 if `language` is `Python`, `TypeScript`, `Rust`, or `Solidity`.
   - +1 if `stargazers_count >= 500` AND `pushed_at` within last 30d.
   - +1 if `description` contains any of: `agentic`, `ontology`,
     `pipeline`, `workflow`, `LLM`, `monorepo`, `factory`.

   Take the top 10 by score. Cap each at 1 line of description (truncate
   to 140 chars).

7. If no candidate scores >= 3, exit 0 silently.

8. Open one issue:
   - Title: `GitHub discovery digest: <WEEK> (<N> high-relevance repos)`
   - Labels: `github-discovery`, `chore`.
   - Body sections:
     1. `## Summary` — count of starred-recent considered, count of
        trending considered, count surfaced.
     2. `## High-relevance repos` — table: full_name, language,
        stargazers, score, one-line description.
     3. `## Suggested integration points` — for each repo, one short
        sentence linking it to a Sapphire surface (e.g., "could feed
        lib/intel/lead_enricher with prospect-discovery patterns").
     4. `## ISO week stamp` — single line `iso_week=<WEEK>`.

9. Print a one-line status summary to stdout: either
   `github-discovery: nothing high-relevance` or
   `github-discovery: <N> repos surfaced, issue #<num>`.

## Required tools

`Bash`, `Read`, `Glob`, `Grep`, plus `gh` on PATH.

## Out of scope

- Auto-starring or auto-cloning anything. Discovery is informational.
- Generating per-repo deep dives. The digest surfaces; humans pursue.
- Maintaining a persistent starred-repos history; this runs weekly and
  is bounded by the issue label search.
