# Sapphire OS — Collaborator Pack

This directory is the onboarding packet for anyone joining Sapphire as a
collaborator, reviewer, or red-team researcher. Read it top-to-bottom the first
time; after that, treat it as a reference.

## What's in here

1. **[collaborator-pack.md](collaborator-pack.md)** — the main developer pack.
   What Sapphire is, the architecture, how to get a dev environment running,
   repo layout, git/CI flow, how to ask questions. Start here.

2. **[ai-redteam-scope.md](ai-redteam-scope.md)** — scope, rules of
   engagement, and reporting workflow for researchers pentesting the
   open-source model layer (inference proxy, sensitivity classifier, Jinja2
   backdoor detection, Ollama blob integrity, hermes-agent routing).

3. **[first-week-checklist.md](first-week-checklist.md)** — a concrete
   day-by-day path for a new collaborator: what to read, what to run, where to
   file a first PR.

## Authoritative references outside this directory

- **[CLAUDE.md](../../CLAUDE.md)** — project map + commands. The agent reads
  this on every session; humans should too.
- **[README.md](../../README.md)** — marketing-facing architecture + metrics.
- **[docs/architecture-overview.md](../architecture-overview.md)** — module
  wiring diagram.
- **[docs/nist-alignment.md](../nist-alignment.md)** — NIST CSF control map.
- **[.github/CODEOWNERS](../../.github/CODEOWNERS)** — review-gated paths.
- **[.github/pull_request_template.md](../../.github/pull_request_template.md)**
  — every PR must fill this out.

## If something is out of date

The counts and claims in these docs were verified on **2026-04-19**. If you
notice drift, open a PR correcting it — the "docs match reality" invariant is
as load-bearing as the tests.
