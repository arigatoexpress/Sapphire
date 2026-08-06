> **UPDATE 2026-08-06 later:** Phase 3 setup landed revision **00096-rub**, min-instances=0. Remaining critical: `/dashboard/assets` MIME — see `GEMINI-PHASE3-STATUS-AND-NEXT-2026-08-06.md`.

# Gemini Cloud Shell — Phase 3 Masterplan + Prompt
# Post–Phase 2: website professionalization + cost-efficient GCP warehouse

**Date:** 2026-08-06  
**Paste this entire file into Gemini in Google Cloud Shell.**  
**Repos:**  
- Public product: `arigatoexpress/sapphire-alpha-dashboard` → https://sapphirealpha.xyz  
- Plant monorepo: `arigatoexpress/Sapphire` (scripts, policy, grok project — **read**, don't own free-reign)  

**You are:** Gemini = **public product + GCP efficiency + evidence warehouse** lead.  
**You are not:** trading sole writer, Mac plant process manager, Windows L2 ARM, secret owner, THO ops.

---

## 0) Situation after Phase 2 (trust this baseline)

### Plant (NOT your job — Claude / Grok / Ari)

| Item | Status |
|---|---|
| free-reign `gate_order` in executor (via=free_reign only) | wired + operator accepted |
| genome closes (`auto_estimate`) | wired |
| Grok bridge :19998 mac-bridge + densify | green |
| rh-executor **process reload** | Claude usage-limited mid-probe — **do not steal this** |
| Win P0 / L2 ARM | blocked — **never ARM** |

### Public / GCP (YOUR lane)

Live probe ~2026-08-06 late afternoon:

| URL | Observation |
|---|---|
| `/dashboard` HTML | still ~701B SPA shell (expected for Vite) |
| `/assets/dashboard-*.js` | **200 `application/javascript`** — Phase 2 win vs prior HTML-404 |
| `/assets/dashboard-*.css` | **200 `text/css`** |
| `/dashboard/assets/*` | still HTML fallback (base path tension — verify which base production uses) |
| `/` Evidence Observatory | keep & elevate; never fake KPIs |
| Cloud Run project | **`sapphire-479610`** for sapphirealpha.xyz DNS+site |
| Warehouse project | **`tho-ai-agent`** for BQ/GCS/batch — **no site DNS there** |

**Phase 2 likely fixed asset MIME on `/assets/*`.** Phase 3 proves the **browser actually paints Mission Control**, then elevates product quality + cost hygiene.

North star (do not contradict):

```text
Sapphire/docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md
Sapphire/docs/strategy/HOLISTIC-BLINDSPOTS-AND-LEVERAGE-2026-08-06.md
Sapphire/projects/grok/README.md
```

Prior prompts (superseded for *this* phase by THIS file):

```text
GEMINI-CLOUDSHELL-WEBSITE-GCP-MASTER-PROMPT-2026-08-06.md  # Phase 1–2 website+cost
GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md              # general plant/GCP
```

---

## 1) Absolute fences (unchanged, non-negotiable)

- **No live trading**, order place/cancel, money movement, THO funds.  
- **No** Hermes/Telegram sends; **no** killswitch authority; **no** L2 ARM.  
- **No** secret dumps (SA JSON, tokens, cookies) into chat or git.  
- Public Cloud Run stays **`PUBLIC_READ_ONLY=true`**, `ENABLE_INTERNAL_JOBS=false`.  
- Never publish wallets, balances, positions, hostnames, ports, raw prompts, raw errors.  
- DNS edits **only** on **`sapphire-479610`** for `sapphirealpha.xyz` — never orphan zone on `tho-ai-agent`.  
- No always-on Vertex endpoints; no `min-instances>0` without explicit budget note + owner phrase.  
- **No** `git add -A` — explicit paths only.  
- **No** editing Mac `ops-state/telegram-bot/executor.py` or free-reign money paths.  
- Traffic shift to 100% only after no-traffic tag verify **or** owner phrase if already partially live.

---

## 2) Phase 3 goals (ordered — finish or block before next)

### P0 — Prove Mission Control actually works

1. Record live baseline:
   ```bash
   curl -sS -o /dev/null -w 'home:%{http_code} size:%{size_download}\n' https://sapphirealpha.xyz/
   curl -sS -o /dev/null -w 'dash:%{http_code} size:%{size_download}\n' https://sapphirealpha.xyz/dashboard
   curl -sS -I https://sapphirealpha.xyz/assets/dashboard-C2nRiei_.js | tr -d '\r' | head -15
   # replace hash from current HTML:
   curl -sL https://sapphirealpha.xyz/dashboard | grep -oE 'src="[^"]+\.js"' | head
   curl -sS https://sapphirealpha.xyz/api/health
   curl -sS https://sapphirealpha.xyz/api/build | head -c 2000; echo
   gcloud run revisions list --service=sapphire-alpha-dashboard --region=us-central1 --project=sapphire-479610 --limit=8
   ```
2. **Browser-truth check** (Cloud Shell or local headless if available):
   - Open `/dashboard` — must show **visible Mission Control UI** (not blank root).  
   - Console: no failed module loads / wrong MIME.  
   - If blank: fix **base path** (`vite base` `/` vs `/dashboard/`) + FastAPI static routes so the HTML's asset URLs and the server agree. Prefer **one** canonical URL:
     - either SPA at `/dashboard/` with `base: '/dashboard/'` and assets under `/dashboard/assets/*`  
     - or SPA at `/dashboard` with assets at `/assets/*` and marketing never steals `/assets/*`  
   - Do **not** leave both half-working.
3. Deploy path if code change needed:
   ```bash
   # build → deploy with --no-traffic --tag phase3-mc
   # curl the tag URL for /dashboard + JS MIME
   # only then traffic shift (or request owner phrase)
   ```
4. Mobile ~390px: no horizontal overflow on `/` and `/dashboard`.

**Done when:** Ari can open sapphirealpha.xyz/dashboard and see real MC chrome (nav/panels/text), not empty shell; JS/CSS MIME correct; short session note with revision id.

### P1 — Evidence Observatory elevation (marketing honesty)

On `/` (Research OS / Evidence Observatory):

1. Keep existing voice: *system that shows its work* — anti-slop.  
2. Architecture proof strip: Mac commander · Win private DC · GCP warehouse · public face — **roles only**, no internal hostnames.  
3. Verified vs estimated labeling on every number.  
4. Stale/offline plant telemetry → `not observed` — never synthetic markets.  
5. CTAs that work: Mission Control, research/evidence, status — no dead links.  
6. Optional: one **sanitized** public evidence card fed from existing PUBLIC_READ_ONLY APIs (no new wallet surface).

**Done when:** `/` feels professional product, not stub; Lighthouse-ish readability; no fake KPIs.

### P1 — GCP cost posture (efficiency)

Project **`sapphire-479610`** (site) + **`tho-ai-agent`** (data) separately:

```bash
cd $SAPPHIRE_DIR
python3 scripts/ops/cost_posture_report.py --format markdown --hours 48 --log-limit 10 || true
python3 scripts/ops/gcp_ai_inventory.py 2>/dev/null || true
gcloud run services describe sapphire-alpha-dashboard --region=us-central1 --project=sapphire-479610 \
  --format='yaml(spec.template.metadata.annotations,spec.template.spec.containers[0].resources)'
```

Actions:

| Action | Rule |
|---|---|
| Cloud Run **min-instances → 0** | default unless budget note says otherwise |
| Right-size memory/CPU | based on describe; no hero overprovision |
| Delete/only-list ancient no-traffic revs | list first; delete only obvious junk after note |
| Vertex | **batch only**; no always-on endpoints |
| GCS lifecycle on data lake | cold/nearline for old prefixes if safe |
| BQ | no new always-on slots; query on demand |
| Orphan DNS | confirm NS only on sapphire-479610 |

**Done when:** session note `docs` or densify export with before/after min-instances, revision, cost script output (redact project numbers if noisy).

### P2 — Warehouse for *paper* outcomes (not live trading)

On **`tho-ai-agent`** only:

1. Design (or extend) a **paper/research** BQ dataset table for:
   - regime digests  
   - paper strategy run summaries  
   - sanitized public counters (no positions/wallets)  
2. Prefer **batch load from GCS** or scheduled query — not a new Cloud Run sole-writer.  
3. Document schema in Sapphire monorepo under `docs/` or `projects/grok/data/` — no secrets.  
4. Wire **read-only** public API only if already patterned; else stop at warehouse design + dry load.

**Done when:** schema + one dry load or "blocked on missing export path" note — **zero** live order coupling.

### P2 — Ops hygiene

1. Push session note to **both** repos as appropriate:
   - dashboard: only product code  
   - Sapphire: `data/grok-web-exports/YYYY-MM-DD_gemini-phase3-*.md`  
2. `git pull` Sapphire first — plant exports and blindspots updated today.  
3. Update `/api/build` visible revision if deploy happens.  
4. README one-liner on dashboard if public UX changed (honest).

---

## 3) Bootstrap (first 10 minutes)

```bash
gcloud auth login   # if needed
gcloud config set project sapphire-479610
gcloud config set run/region us-central1

export DASH_DIR="${DASH_DIR:-$HOME/sapphire-alpha-dashboard}"
if [[ -d "$DASH_DIR/.git" ]]; then git -C "$DASH_DIR" pull --ff-only origin main
else git clone https://github.com/arigatoexpress/sapphire-alpha-dashboard.git "$DASH_DIR"; fi

export SAPPHIRE_DIR="${SAPPHIRE_DIR:-$HOME/Sapphire}"
if [[ -d "$SAPPHIRE_DIR/.git" ]]; then git -C "$SAPPHIRE_DIR" pull --ff-only origin main
else git clone https://github.com/arigatoexpress/Sapphire.git "$SAPPHIRE_DIR"; fi

cd "$SAPPHIRE_DIR"
bash scripts/ops/gcp_cloudshell_bootstrap.sh || true
python3 scripts/ops/cost_posture_report.py --format markdown --hours 24 --log-limit 5 || true

# Read monorepo state (do not execute plant money paths)
sed -n '1,80p' projects/grok/NEXT.md
sed -n '1,60p' projects/grok/STATUS_LUNCH.md 2>/dev/null || true
```

---

## 4) Out of scope (explicit)

| Topic | Owner |
|---|---|
| rh-executor reload / free-reign / genome | Claude plant |
| Win P0 acceptance / L2 ARM | Ari at desk |
| GROK_BRIDGE_URL / :19998 | already green — leave |
| THO website / client funds | never |
| Always-on GPU on GCP | never |

---

## 5) Report format (end of Phase 3)

1. **Mission Control:** blank or painted? revision id? asset MIME samples  
2. **Evidence `/`:** what changed (bullets)  
3. **Cost:** min-instances before/after; any Vertex/GCS actions  
4. **Warehouse:** schema path or blocked reason  
5. **Commits / SHAs** (dashboard + Sapphire exports)  
6. **What you did NOT touch** (plant money, DNS orphan, secrets)  
7. **Ask Ari only if:** traffic shift needs phrase, budget exception, or product copy preference  

---

## 6) Success scoreboard

| Check | Green |
|---|---|
| `/dashboard` visible UI in browser | yes |
| JS/CSS correct MIME | yes |
| `/` professional + honest labels | yes |
| min-instances 0 (or justified) | yes |
| no secrets / no trading | yes |
| densify export on Sapphire main | yes |
| plant free-reign / executor | untouched |

---

## 7) Ultra-short kickoff (if context warm)

```text
Phase 3 masterplan: docs/handoffs/GEMINI-PHASE3-WEBSITE-GCP-MASTERPLAN-2026-08-06.md
Prove /dashboard paints (not just JS MIME), elevate Evidence Observatory, cost min-instances=0,
optional paper BQ warehouse. No trading, no plant executor, no L2 ARM. Pull both repos first.
```
