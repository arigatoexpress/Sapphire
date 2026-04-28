# Cowork Morning Briefing — 2026-04-28

> **Operator usage**: paste this into a fresh Claude Cowork session in the morning. Cowork is your pair-programmer for the operator-only items that Claude Code and Codex can't do — the ones requiring browser logins, console clicks, real PII, or your own judgment. Cowork's job: draft texts, hold you accountable to the order, verify each step's evidence, take notes that I (Claude Code) can ingest later.

---

## 0. The working agreement

You (Ari) own the actual clicks and approvals. Cowork's job is to:

1. Walk you through each item below in order.
2. Draft any email / message I name in the steps.
3. After each step, ask you to confirm "done + here's the evidence" (a screenshot path, a copied-out string, a yes/no), and append the evidence to a single running notes file at `~/Documents/Cowork/morning-briefing-2026-04-28.md`. If `~/Documents/Cowork/` doesn't exist, that's item 4 below — fix that first.
4. Never proceed past an item without explicit "done" or "skip — reason: …" from you.
5. Never touch any console, secret, or external service on your behalf. You click; Cowork witnesses.

**Posture reminder**: Sapphire's overnight tranches landed 24 PRs and validated the first $5 live BTC trade. The acquisition push is live. Don't grow scope; close loops.

---

## 1. Cowork itself — mount or delete decision (do this first)

**Why first**: nothing else here works smoothly until Cowork can write notes to a real folder. The other items leave artifacts.

**Status**: Cowork's scheduler created 5 cloud tasks on or before 2026-04-27 — `morning-briefing`, `meeting-prep-tomorrow`, `end-of-day-log`, `weekly-downloads-cleanup`, `tho-weekly-service-rollup`. None of them produced local artifacts because the `~/Documents/Cowork/` folder was never persisted. They're either silent in the cloud or never ran. Either way: today you decide.

**Steps**:
1. Open the Cowork sidebar. Confirm whether the 5 scheduled tasks are still listed.
2. **Decision**: do you actually want them? Quick gut check —
   - `morning-briefing` overlaps with your local `sapphire-morning-briefing` (8 AM, in `~/.claude/scheduled-tasks/`). Probably redundant.
   - `meeting-prep-tomorrow` — useful if you have meetings; otherwise empty most days.
   - `end-of-day-log` — useful daily reflection; might double with `evening-digest` (6 PM).
   - `weekly-downloads-cleanup` — low-stakes, useful.
   - `tho-weekly-service-rollup` — useful; doesn't exist anywhere else.
3. **If you want to keep any**: click the Cowork sidebar's "mount folder" affordance, point it at `~/Documents/Cowork/` (create it if it doesn't exist: `mkdir -p ~/Documents/Cowork`), then click "Run now" on each task you keep so it produces its first artifact. Cowork should witness each "Run now" by appending the resulting filename to the notes file.
4. **If you delete any**: do it in the Cowork sidebar UI, and have Cowork log which ones you deleted with timestamps.

**Verify**: `~/Documents/Cowork/` exists and is writable; at least the keep-list tasks have produced one file each, OR all 5 are deleted.

---

## 2. Etai email — read, decide, reply (or wait)

**Status as of midnight**: you sent **Etai Zilberman** (`etaizilberman@gmail.com`, Upwork contractor your mom Celeste hired to build a Notion workspace for THO) a 4-question reply at 2026-04-28 00:20 UTC. As of when this prompt was written, **no reply yet**. The 4 questions were: (1) one-paragraph scope confirmation incl. what "all 11" refers to and the integration boundary with the existing Document Center; (2) Drive access confirmation; (3) Signal number for sensitive comms; (4) propose a first-deliverable date.

**Steps**:
1. Open Gmail, search `from:etaizilberman@gmail.com`. If no new mail since 2026-04-28 00:20 UTC, **wait** — it's < 24h. Move on; come back this evening.
2. **If Etai replied**: forward the reply to Cowork (paste the body), and ask Cowork to draft a same-day response. Cowork's draft should:
   - Acknowledge each of the 4 answers.
   - If Etai's scope overlaps with Project-Go-Forward's existing Document Center + Firestore CRM (1,963 customers, 63 PDF templates, GCS bucket `tho-secure-documents`), **reference the integration analysis memo** that the parallel Codex satellite-repo session is producing today — it'll live at `~/Code/Project-Go-Forward/docs/integration/etai-notion-integration-2026-04-28.md`. Tell Etai you'll share that memo before he writes a single line of Notion structure.
   - Confirm Signal vs WhatsApp (the operator's preference per the memo's section 5: Signal). Send your Signal number once you have his.
   - Lock the first-deliverable date.
3. Cowork helps you copy-edit the draft, then YOU send it.

**Verify**: either "no reply yet, will check again 6 PM" logged, OR sent reply pasted into the notes file.

---

## 3. Read + reply to Mark @ THO ("Joe Blo" empty docs package)

**Status**: Mark Willcott (`mark@texashomeoutlet.com`) reported on 2026-04-27 19:10 UTC that he created a fictitious customer "Joe Blo" in the Document Center, generated a docs package, and **the XFA fields didn't fill out**. Celeste reproduced. **Codex is investigating + fixing in a parallel satellite-repo session right now** (Project-Go-Forward Lane S1 of the supplement tranche). The fix should land before noon.

**Steps**:
1. Open the email thread `Re: Browse Homes | Texas Home Outlet`.
2. Have Cowork draft a brief acknowledgement to Mark + Celeste + Ben:
   > "Got it, this looks like a real bug in the doc-fill path. I'm investigating now and will have a fix in deploy-ready shape today. I'll let you know when the next Cloud Run revision is up so you can re-test Joe Blo (or any fictional customer)."
3. **Don't promise a Cloud Run deploy time** — that's operator-supervised, after Codex's PR lands and you eyeball it.
4. Send the acknowledgement.
5. Set yourself a reminder (or have Cowork schedule a check-in) for **2 PM today** to verify Codex's PR is open + you can review it. The fix lives in `~/Code/Project-Go-Forward/`; PR will be on `arigatoexpress/Project-Go-Forward`.

**Verify**: acknowledgement sent; 2 PM reminder set.

---

## 4. Reply to Celeste — broken `MH-Checklist.pdf` link

**Status**: Celeste sent on 2026-04-27 18:48 UTC: "https://www.texashomeoutlet.com/MH-Checklist.pdf" with the implication that it's broken. The thread also CCs Mike at manufacturedhomes.com, Ben, Mark, Lee.

**Steps**:
1. Click the link. Confirm it 404s (or wherever the failure is).
2. **The texashomeoutlet.com site is hosted somewhere — find out where.** Have Cowork ask you: do you know what CMS / hosting provider serves texashomeoutlet.com? (Probably Squarespace, Wix, or similar — it's not in any of your repos per Codex's earlier audit.)
3. **If you know the CMS**: log in, find the file under `MH-Checklist.pdf`, re-upload (the file probably exists in Drive somewhere — search `MH-Checklist.pdf` in Drive).
4. **If you don't know the CMS**: reply to Celeste asking who has admin access. Cowork drafts: "Hey Celeste — link's broken on my end too. Who has admin on the texashomeoutlet.com site? I'll re-upload the PDF if I can get in, otherwise we should poke whoever does."
5. Have Cowork track the resolution (CMS confirmed, file re-uploaded, link 200s, reply sent saying "fixed").

**Verify**: link returns 200 OR explicit "needs operator with CMS access" recorded in notes.

---

## 5. MOONSHOT_API_KEY rotation

**Why**: Sapphire's `docs/security/credential-rotation-runbook.md` flagged this as overdue. The key is loaded by the inference proxy + various Kimi-tier paths.

**Steps**:
1. Open `https://platform.moonshot.cn/console/api-keys` (or wherever your Moonshot account lives — Kimi Cloud is Moonshot).
2. Generate a new key. **Copy it once** — Moonshot only shows it once.
3. Edit `~/.sapphire/secrets.env`:
   ```bash
   # MAKE A BACKUP FIRST
   cp ~/.sapphire/secrets.env ~/.sapphire/secrets.env.backup-$(date +%Y%m%d-%H%M%S)
   # Then replace the MOONSHOT_API_KEY line
   ```
4. Reload the inference-proxy LaunchAgent so the new key is picked up:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.sapphire.inference-proxy.plist
   launchctl load ~/Library/LaunchAgents/com.sapphire.inference-proxy.plist
   ```
5. Smoke test: `curl -s http://localhost:11435/v1/models | jq '.data | length'` — non-zero.
6. **Revoke the old key** in the Moonshot console.
7. Have Cowork log: rotation timestamp + old-key-last-4 (NOT the full key, just the last 4 chars for an audit trail).

**Verify**: inference-proxy serves; old key revoked.

---

## 6. KIMI_CLAW_BOT_TOKEN rotation

**Steps**: same shape as item 5 but for the Telegram bot token.

1. Open BotFather on Telegram → find the bot → `/revoke` → generate new token.
2. Edit `~/.sapphire/secrets.env`'s `KIMI_CLAW_BOT_TOKEN` line (backup first, same as above).
3. Reload `ai.hermes.gateway` LaunchAgent:
   ```bash
   ~/.local/bin/hermes gateway restart
   ```
   (Or `launchctl` if you prefer.)
4. Smoke test: send `/whoami` to the bot from your Telegram. It should reply.
5. Have Cowork log timestamp + last-4 of old token (NOT full).

**Verify**: bot replies to `/whoami`; old token revoked.

---

## 7. Delete the Proton copy of `technical-audit-2026-04-16.md`

**Why**: per `docs/security/credential-rotation-runbook.md`, the security audit document was duplicated into Proton Drive at `~/Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder/Sapphire-OS/technical-audit-2026-04-16.md`. The repo copy is canonical; the Proton copy is stale and exposes one more surface where the audit could leak.

**Steps**:
1. Open Proton Drive (web or desktop client).
2. Navigate to `Sapphire-OS/technical-audit-2026-04-16.md`.
3. Delete it. Empty trash. (Proton's deleted-items recovery window is usually 30 days, fine.)
4. Verify locally: `ls ~/Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder/Sapphire-OS/ 2>/dev/null` — `technical-audit-2026-04-16.md` should be gone.
5. Have Cowork log the deletion timestamp.

**Verify**: file no longer in Proton.

---

## 8. Robinhood — verify $5 BTC fill, decide on ledger reconciliation

**Status**: at 2026-04-28 04:06 UTC, your $5 BTC limit-buy filled at $76,774.81. Total cost $5.05 incl. $0.04 fee. Account ...5966. Filled notional $5.00, fee $0.04, total $5.05. **First live-capital trade on the hardened path** (PRs #340 / #344). The 14-day Sortino-soak window per the live-trading ramp memo is now ticking.

**Steps**:
1. Open the Robinhood app. Confirm the position appears under Crypto → BTC. Should be 0.00006511 BTC. Note the current mark — note your unrealized P&L for context.
2. **Attribution check**: was this trade YOU pressing the button manually, or did the manual-but-software-assisted gate fire on a confirmation token? The autonomy posture forbids the latter without operator-in-the-loop. Have Cowork ask you to record the answer in the notes file.
3. **Ledger reconciliation decision**: the existing paper PnL view in `data/paper_portfolio.json` doesn't include live trades. Two options:
   - **Option A (preferred for now)**: don't reconcile. Treat live as separate, manual-tracked, $5 / $50 / $500 progression. The 14-day soak just needs Robinhood's app for the data.
   - **Option B (more buildable)**: ask Codex (in tomorrow's Tranche 4) to add a `data/live_portfolio.jsonl` ledger that the dashboard reads alongside paper. Plus a `/live-trading` panel.
4. Decide A or B; Cowork notes the decision and the rationale.

**Verify**: position confirmed in app; attribution recorded; A-or-B noted.

---

## 9. `services/alpha` aiohttp 3.11.11 → 3.13.4+ bump (operator-supervised window)

**Why**: PR #378 closed the orjson + python-dotenv vulns but DEFERRED the alpha-service aiohttp bump because alpha is the trading critical path. With the live $5 trade now validated, this is a fine moment to do the bump in a supervised window.

**Steps**:
1. Read the current pin: `grep aiohttp ~/Code/Sapphire/services/alpha/requirements.txt` — should show `aiohttp==3.11.11`.
2. Branch + edit:
   ```bash
   cd ~/Code/Sapphire
   git checkout -b chore/alpha-aiohttp-bump main
   # Edit services/alpha/requirements.txt:  aiohttp==3.11.11 -> aiohttp==3.13.5
   ```
3. **You watch the alpha logs while you bump**:
   ```bash
   tail -f ~/.local/var/log/sapphire/signal-logger.log    # or wherever alpha logs live
   ```
4. Reinstall in alpha's venv (your existing alpha venv is at `services/alpha/.venv` or similar — confirm):
   ```bash
   ~/Code/Sapphire/services/alpha/.venv/bin/pip install -r ~/Code/Sapphire/services/alpha/requirements.txt
   ```
5. Restart the signal-logger LaunchAgent:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.sapphire.signal-logger.plist
   launchctl load ~/Library/LaunchAgents/com.sapphire.signal-logger.plist
   ```
6. Smoke test: `curl -s http://localhost:18081/health | jq` — `status=ok`.
7. **Watch for 30 minutes** before declaring success. If anything goes red, roll back the requirements line, reinstall, restart.
8. If green: commit the bump with `[skip ci]` and PR. Use the Sapphire safe-merge wrapper if Codex's Tranche 3 Lane 6 has landed it (`scripts/ops/sapphire_safe_merge.sh`); otherwise manual `gh pr merge -t '<title> [skip ci]' --squash --admin --delete-branch`.

**Verify**: signal-logger green for 30 min on aiohttp 3.13.5; PR merged.

**If anything fails**: roll back the line, reinstall, restart, document the failure, do NOT push.

---

## 10. `services/control-plane` pytest 8 → 9 (decide whether to do today)

**Status**: this is a major bump. Lower urgency than aiohttp — pytest only matters at test time, not at runtime. Punt to a slower window unless you have time today.

**Steps if doing today**:
1. Branch + edit `services/control-plane/requirements.txt`: `pytest>=8.0,<9.0` → `pytest>=9.0,<10.0`.
2. Run the control-plane test suite locally — it's small. If anything's red, document and roll back.
3. PR + safe-merge.

**Steps if punting**: tell Cowork to add a single-line item to `~/Documents/Cowork/morning-briefing-2026-04-28.md`: "punted control-plane pytest 9 bump to a later session, reason: low urgency."

---

## 11. Floorplan inventory loading — reply to Mark + Celeste

**Status**: 2026-04-27 19:13–19:35 thread. Mark proposed including all manufacturer floorplans on the Browse page; Celeste asked him to be specific; Mark said "I don't have any specific" so default is "all from all our manufacturers." Codex is closing PR #24 (`feat(inventory): drive floorplan sync + master catalog ingest`) in the satellite-repo session.

**Steps**:
1. Have Cowork draft a single reply to the thread:
   > "Yep, going with 'all manufacturers, all floorplans' as the default. The drive sync PR (#24) is being polished now and should be merge-ready today; once it's in, I'll trigger the master catalog ingest and the Browse page should auto-populate. I'll ping when that lands so you can spot-check."
2. Send.

**Verify**: reply sent.

---

## 12. Closeout — write the morning-briefing notes file

At end of session, have Cowork:
1. Confirm `~/Documents/Cowork/morning-briefing-2026-04-28.md` exists and contains one section per item above with status (DONE / SKIPPED + reason / DEFERRED + when).
2. List any new follow-ups that surfaced during the morning that should go into Tranche 4 of the Codex backlog.
3. Tell you "ready for hand-off to Claude Code" so when you next open Claude Code, you can paste a one-liner like "read `~/Documents/Cowork/morning-briefing-2026-04-28.md` and update memory" and Claude Code can ingest the morning's evidence.

---

## What's deliberately NOT in this prompt

- Anything Codex is currently working on (Sapphire Tranche 3 main megaprompt's 8 lanes; Tranche 3 supplement's 3 satellite-repo lanes). Don't shadow.
- Anything that requires writing code in the Sapphire repo. That's Codex / Claude Code's job.
- The Palantir corp-dev follow-up — punt until they reply.
- Cowork's own task list (already covered in item 1).

---

Now go.
