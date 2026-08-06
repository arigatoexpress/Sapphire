# Gemini Phase 3 — status ACK + next handoff

**Date:** 2026-08-06  
**Revision verified live:** `sapphire-alpha-dashboard-00096-rub`  
**source_sha:** `5ed4058` (SPA base `/dashboard/`)  
**Gemini report accepted** with one critical remaining bug (below).

---

## 1) What Gemini completed (ACK — do not redo)

| Item | Evidence |
|---|---|
| Repos synced | Sapphire + sapphire-alpha-dashboard |
| `backend/main.py` merge conflicts resolved | HEAD routes + features retained |
| Deploy + **100% traffic** | revision **00096-rub** |
| Professional Hero Strip | Gemini report + home content |
| HEAD request 404 fix | Gemini report |
| Epistemic state handling | Gemini report |
| **min-instances=0** cost hygiene | Gemini report (confirmed by them) |

Live probes this session:

```text
/api/build → runtime_revision: sapphire-alpha-dashboard-00096-rub
/dashboard HTML ~731B, references /dashboard/assets/dashboard-*.js
/ → ~33KB Evidence / marketing (hero present)
/api/v1/live → still rich (~7.8KB)
min-instances=0 — trust Gemini inventory unless re-check fails
```

---

## 2) CRITICAL remaining P0 — Mission Control still blank

**Root cause (measured, not guessed):**

| URL | Result |
|---|---|
| `GET /dashboard` | 200 HTML shell with `src="/dashboard/assets/dashboard-SO251L4w.js"` |
| `GET /dashboard/assets/dashboard-SO251L4w.js` | **200 `text/html`** body = same ~731B SPA shell (**wrong MIME**) |
| `GET /assets/dashboard-SO251L4w.js` | **200 `application/javascript`** real module (~36KB+) |

So: Vite `base: '/dashboard/'` made HTML point at `/dashboard/assets/*`, but the **static file mount only serves real files under `/assets/*`**. The SPA catchall returns HTML for `/dashboard/assets/*` → browser refuses module (MIME text/html) → **blank Mission Control**.

### Fix (Gemini — do this next, before Evidence fluff)

In `sapphire-alpha-dashboard` `backend/main.py` (and any static helpers):

1. Serve **real files** for **both**:
   - `/assets/{path}`  
   - `/dashboard/assets/{path}`  
   from the same `frontend/dist/assets` (or dist root) tree.  
2. SPA `index.html` fallback **must not** win for `*.js` / `*.css` / `*.map` / `*.woff*`.  
3. Prefer: if file missing under assets → **404 JSON/text**, never HTML shell.  
4. Deploy with `--no-traffic` tag `mc-assets-fix` → verify:

```bash
# after deploy to tag URL (or prod after green):
HTML=$(curl -sL "$BASE/dashboard")
JS=$(echo "$HTML" | grep -oE '/dashboard/assets/[^"]+\.js' | head -1)
curl -sI "$BASE$JS" | tr -d '\r' | grep -i content-type
# MUST contain application/javascript
curl -sL "$BASE$JS" | head -c 20   # MUST look like JS (import/var), not <!doctype
```

5. Only then shift 100% traffic (or if already on 00096, ship new rev and shift).  
6. Optional cleaner long-term: one canonical base — either all `/dashboard/assets` **or** all `/assets` — but **dual serve is the safe hotfix**.

**Done when:** browser paints Mission Control; no console MIME errors; HEAD on asset also not HTML.

---

## 3) Phase 3 remaining (after P0 assets)

### P1 — Data truth UI (handoff already written)

`docs/handoffs/GEMINI-DATA-TRUTH-AND-PUBLIC-SURFACE-2026-08-06.md`

- Live pulse hierarchy  
- Stale desk honesty  
- Public operating rules panel (`projects/grok/data/public_operating_rules.json`)  
- Never invent PnL  

### P1 — Evidence Observatory elevation

Architecture proof, CTAs, honest labels (Gemini’s own Phase 3 list).

### P2 — Paper BQ warehouse

`docs/strategy/PAPER-OUTCOMES-WAREHOUSE-SCHEMA-2026-08-06.md`  
min-instances already 0 — good.

### Not Gemini

| Item | Owner |
|---|---|
| rh-executor reload | Claude |
| Telemetry `desk.*` refresh | Claude + `lib.grok.desk_projection` |
| L2 ARM / Win P0 | Ari |
| Free-reign money | plant only |

---

## 4) Paste for Gemini now (ultra-short)

```text
Phase 3 ACK: 00096-rub live, min-instances=0, hero/HEAD/epistemics accepted.
CRITICAL: /dashboard/assets/*.js returns text/html SPA shell while real JS is at /assets/*.
Fix dual-serve assets (or align base) before Evidence/BQ. Verify MIME application/javascript.
Then data-truth UI: docs/handoffs/GEMINI-DATA-TRUTH-AND-PUBLIC-SURFACE-2026-08-06.md
Pull Sapphire main. No plant money / L2 / secrets.
```

---

## 5) Scoreboard

| Check | Status |
|---|---|
| Cloud Run 00096 100% | ✅ |
| min-instances 0 | ✅ (Gemini) |
| Hero / home | ✅ partial |
| MC paints | ❌ asset path MIME |
| Desk trading intel | ❌ plant stale |
| Evidence elevation | ⏳ remaining |
| BQ paper warehouse | ⏳ remaining |
