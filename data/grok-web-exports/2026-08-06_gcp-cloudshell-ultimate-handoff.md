---
source: grok-web
date: 2026-08-06
type: handoff
topics: [gcp, cloud-shell, masterplan, data-plane, fences, alpha]
title: GCP Cloud Shell ultimate handoff (pointer)
---

# GCP Cloud Shell ultimate handoff — plant densify pointer

**North star:** [`docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md`](../../docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md)  
**Gemini paste:** [`docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md`](../../docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md)  
**Canonical full handoff (repo):**  
[`docs/handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md`](../../docs/handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md)

**Bootstrap (clone + inventory):**  
[`scripts/ops/gcp_cloudshell_bootstrap.sh`](../../scripts/ops/gcp_cloudshell_bootstrap.sh)

## One-liner (Cloud Shell)

```bash
git clone https://github.com/arigatoexpress/Sapphire.git ~/Sapphire  # or git pull
cd ~/Sapphire && bash scripts/ops/gcp_cloudshell_bootstrap.sh
less docs/handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md
```

## Fences (sticky)

- Paper / research / docs / BQ+GCS inventory / PRs: **OK**
- Live trading, money, Telegram sends, secret dumps, orphan DNS edits, traffic cutovers: **NO**
- Designated rails only when plant is later used: RH ••••8144, L2 ≤$10 dens, MOSS grant-gated, paper
- Dust exits: do not re-place; dens SONNY/BINGBONG permanent
- Projects: data work on `tho-ai-agent`; website DNS only on `sapphire-479610`

## NOW board (2026-08-06)

1. Dust exits fill  
2. MOSS grant renew  
3. Win fleet green  
4. AXTI playbook  
5. Dens permanent  

## Holistic improvement priority from Cloud Shell

1. Inventory + BQ freshness + cost posture  
2. Data-plane bootstrap / GCF / scheduled SQL hygiene  
3. Paper code PRs encoding AXTI + dens + free-reign fences  
4. Session notes back into this folder for densify  
5. Vertex batch ladder only after inventory + caps — no always-on endpoints  

## Related exports

- `2026-08-06_alpha-scour-merge.md`  
- `2026-08-05_master-handoff-claude-opus.md`  
- `2026-08-05_fleet-win-recovery-handoff.md`  
- `2026-08-05_alpha-learnings-axti-l2.md`  

Local plant after pull:

```bash
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh
```
