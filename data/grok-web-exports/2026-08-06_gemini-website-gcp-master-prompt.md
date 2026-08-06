---
source: grok-web
date: 2026-08-06
type: handoff
topics: [gemini, cloud-shell, website, gcp, cost, sapphirealpha]
title: Gemini Cloud Shell — website + GCP professionalization prompt
---

# Gemini website + GCP master prompt (pointer)

**Canonical:**  
[`docs/handoffs/GEMINI-CLOUDSHELL-WEBSITE-GCP-MASTER-PROMPT-2026-08-06.md`](../../docs/handoffs/GEMINI-CLOUDSHELL-WEBSITE-GCP-MASTER-PROMPT-2026-08-06.md)

## One-liner diagnosis (2026-08-06)

| Surface | Status |
|---|---|
| `sapphirealpha.xyz/` | 200 ~35KB — Evidence Observatory OK; elevate story/polish |
| `sapphirealpha.xyz/dashboard` | 200 **~701B** — Mission Control SPA **broken/empty** — **P0** |

## Cloud Shell

```bash
git clone https://github.com/arigatoexpress/Sapphire.git ~/Sapphire
git clone https://github.com/arigatoexpress/sapphire-alpha-dashboard.git ~/sapphire-alpha-dashboard
less ~/Sapphire/docs/handoffs/GEMINI-CLOUDSHELL-WEBSITE-GCP-MASTER-PROMPT-2026-08-06.md
# paste that file into Gemini
```

## Order of work

1. Fix `/dashboard` shell/assets  
2. Elevate `/` proof + story  
3. Cost-efficient GCP (min-instances 0, Vertex idle, BQ hygiene)  
4. No-traffic deploys until owner phrase  
