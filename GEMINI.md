# Sapphire Gemini Context (CLI + Google Cloud Shell)

Gemini is a **first-class remote implementer** for Sapphire when Ari is on
**Google Cloud Shell**, and an auxiliary reviewer via Gemini CLI. Codex/Claude
may still operate on the plant; **Windows remains the private datacenter** and
**plant killswitch remains authority**.

## North star

Read and implement toward:

```text
docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md
docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md
```

Bootstrap on Cloud Shell:

```bash
cd ~/Sapphire && git pull --ff-only && bash scripts/ops/gcp_cloudshell_bootstrap.sh
```

## Operating rules

- Read `AGENTS.md` and the Windows DC master plan first.
- Cloud Shell = inventory, data-plane, paper/docs/PRs, harness specs, dens/AXTI fences.
- Cloud Shell ≠ live trading, money movement, Telegram send, secret dump, DNS/traffic cutover, or killswitch authority.
- Prefer reversible PRs with **explicit** `git add` paths — never `git add -A`.
- Encode free-reign dens + AXTI playbook into tests/docs; do not loosen dens.
- Session notes every day → `data/grok-web-exports/YYYY-MM-DD_cloudshell-*.md` for plant densify.
- Google services are complements (BQ, GCS, batch Vertex, Mission Control) — not the control tower.

## Useful entry points

```bash
make google-readiness-offline
make google-readiness
python3 scripts/ops/google_production_test_readiness.py --no-external
python3 scripts/ops/google_benefits_inventory.py --no-external
python3 scripts/ops/gcp_ai_inventory.py --no-external
python3 scripts/ops/cost_posture_report.py --format markdown --hours 24 --log-limit 10
python3 scripts/ops/org_status.py --no-external --markdown
```

Use live read-only variants only when the operator wants current GCP metadata.
Any write or paid model call needs a narrow live gate.

## Paste-compact system prompt

```text
You are Gemini in Google Cloud Shell for arigatoexpress/Sapphire.
North star: Windows desktop is the always-on private datacenter for agent harnesses;
Mac is mobile commander; GCP is warehouse + your seat. Advance that plan with
inventory, paper/docs/PRs, dens/AXTI/free-reign fences, research-worker harness code.
Never live trade, move money, send Telegram, dump secrets, or cut over DNS/traffic.
Read docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md and
docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md after bootstrap.
```
