# Codex Supplement — Tranche 3 — THO Satellite-Repo Cleanup — 2026-04-28

> **Operator usage**: paste this into a SEPARATE Codex session from the Tranche 3 main megaprompt. The two run in parallel without conflict because this supplement targets `~/Code/Project-Go-Forward` (THO client PM) and the main Tranche 3 prompt targets `~/Code/Sapphire` only. Each Codex session must scope itself to its own repo path and not cross-contaminate.

---

## 0. Mission

You are Codex, working on the **Project-Go-Forward** monorepo at `~/Code/Project-Go-Forward` (GitHub `arigatoexpress/Project-Go-Forward`). The operator is asleep and granted full autonomy for THO-side cleanup work that surfaced in his email backlog overnight. Three concrete deliverables:

1. **Fix the "Joe Blo empty doc-fill" bug** Mark reported on 2026-04-27 19:10 UTC — Document Center generated a docs package but the XFA fields didn't fill out.
2. **Close out PR #24** (`feat(inventory): drive floorplan sync + master catalog ingest`) — open with Codex automated-review feedback that needs addressing.
3. **Author the Etai-Notion integration analysis memo** so the operator and Etai have a shared, written boundary between THO's existing Document Center / CRM and the new Notion workspace. This prevents the parallel-source-of-truth fork that the operator flagged in his 2026-04-28 00:20 UTC reply to Etai.

The mental model: **don't grow new surface area; close the loops the operator left open in his inbox last night.**

If your runtime supports parallel sub-agents, dispatch all three lanes concurrently. If not, do them sequentially in the order listed.

---

## 1. Non-negotiable constraints

1. **No-spend posture mirrors Sapphire**: every commit ends with `[skip ci]`. After admin-merging any PR, run `gh -R arigatoexpress/Project-Go-Forward run list --limit 5 --json status,databaseId` and cancel anything queued.
2. **Do NOT touch live Cloud Run** unless explicit operator confirmation in the PR body — Project-Go-Forward serves THO production at `project-go-forward-691674245427.us-central1.run.app` (revision 26, 1,963 real customers in Firestore). All work is local + branch + PR + admin-merge; deployment of revision 27+ is operator-owed.
3. **Do NOT modify Firestore live data** under any circumstance. Every test runs against the Firestore emulator OR mocks. If a test would write to a real collection, refuse and document.
4. **Do NOT touch real customer PII**. The "Joe Blo" repro is fictional; do not pull real customer records to reproduce. If a real-data repro is unavoidable, describe what the operator should do and stop.
5. **Do NOT touch the Sapphire monorepo from this session**. The other Codex session has 8 lanes in flight there; cross-contamination would create rebase pain.
6. **Do NOT touch any other satellite repo** (`hermes-agent`, `regional-intel-workbench`, `tradingview-mcp-v2`, `claw-code`, `Cointracker`, `cyber-threat-bot`).
7. **No new prod dependencies** unless absolutely required for a test fixture; document if so.
8. **Branch + worktree per lane**. Each lane gets its own worktree at `~/Code/_worktrees/pgf-<branch>` so Sapphire's `~/Code/_worktrees/sapphire-*` worktrees stay clean.
9. **Open PR but DO NOT auto-merge** unless local verification is green (`pytest`, any local lint configured, deterministic doc-render smoke). When green, admin-squash-merge with `gh -R arigatoexpress/Project-Go-Forward pr merge <N> --squash --admin --delete-branch -t "<subject> [skip ci]"` (explicit `-t` is mandatory — Tranche 2 dropped `[skip ci]` exactly this way on Sapphire #388).

---

## 2. State at start

```bash
cd ~/Code/Project-Go-Forward
git fetch --all --quiet
git checkout main 2>&1
git pull --quiet
git rev-parse --short HEAD
gh -R arigatoexpress/Project-Go-Forward pr list --state open --json number,title,headRefName --jq '.[] | "\(.number) \(.title) — \(.headRefName)"'
gh -R arigatoexpress/Project-Go-Forward issue list --state open --limit 10 --json number,title --jq '.[] | "#\(.number) \(.title)"'
ls
cat README.md | head -80
```

Reference reading (skim before any lane):

- `README.md` — repo conventions
- `tests/` — existing test layout
- `docs/INTEGRATION_GUIDE.md` (if present) — Drive / Firestore / GCS integration boundary
- The Cloud Run deployment runbook (find via `find . -name '*deploy*'`)

The full email context for THO is in the Sapphire memory note at `~/.claude/projects/-Users-aribs/memory/project_etai_zilberman_tho_notion_2026-04-28.md` if you have read access.

---

## 3. Lanes

### LANE S1 — Reproduce + fix the "Joe Blo empty doc-fill" bug

**Why it matters**: Mark @ THO reported on 2026-04-27 19:10 UTC that creating a fictitious customer "Joe Blo", clicking through to docs, and generating a package produced a doc package whose XFA fields did NOT fill out. Celeste reproduced. This is a **regression in the customer flow** — likely either a) the docs-generation handler isn't pulling the customer record, b) the XFA template-fill code has a field-name mismatch with current customer schema, or c) the doc package is being generated before the customer write commits.

**Worktree + branch**: `~/Code/_worktrees/pgf-doc-fill-bug` on `fix/document-center-empty-doc-fill`.

**Steps**:
1. **Reproduce locally**. Find the docs-package generation entrypoint (probably in `app/api/documents.py` or similar; grep for "docs_package", "document_package", "generate_docs"). Use the Firestore emulator + GCS local emulator if available; if not, mock both. Create a fictitious "Joe Blo" customer fixture and exercise the package-generation path.
2. **Capture the failure** — diff what the generated PDFs SHOULD contain (per the customer fixture) vs what they actually contain. Document the root cause: (a) record fetch race, (b) field-name mismatch, or (c) something else.
3. **Fix the root cause**. If it's a field-name mismatch, fix the template-fill mapper. If it's a race, add proper await/commit. If it's something else, explain and fix.
4. **Add a regression test** in `tests/` that pins the fix: build the same fictitious-customer fixture, exercise the package generation, assert the PDF fields ARE populated.
5. **Verify**: full `pytest tests/` passes; new regression test passes; PDF byte-comparison or text-extract assertion is deterministic (no flaky timestamps).

**Files to read first**:
- `app/api/documents.py` (or wherever doc-generation lives)
- `app/services/pdf_template_fill.py` (or similar)
- `app/models/customer.py`
- `tests/test_documents.py`
- Memory's THO production state note (in Sapphire's `MEMORY.md`): "63 PDF templates, XFA form filling, GCS bucket tho-secure-documents".

**Constraints**:
- **No real customer data**. Fixture-only.
- **No live GCS uploads** in tests; mock the storage client.
- **No deployment**. Operator approves Cloud Run revision 27+.
- If the bug turns out to be in a Sapphire-side dependency (e.g. `lib/foundry/` if PGF imports from Sapphire), STOP and write a discovery note instead of cross-repo modifying.

**Verification (from inside the worktree)**:
```bash
pytest tests/ -q --tb=short
```
The full PGF suite (currently 93 passing per Sapphire memory) MUST still pass.

**PR title**: `fix(documents): repair empty XFA fill on package generation`

---

### LANE S2 — Close out PR #24 (`feat(inventory): drive floorplan sync + master catalog ingest`)

**Why it matters**: Open PR #24 has Codex automated-review feedback that hasn't been addressed (per the operator's email backlog of 2026-04-27 20:29–20:43 UTC). The PR adds Drive floorplan sync to a master catalog. The operator (Mark, Celeste) discussed scope on 2026-04-27 19:13–19:35 — Celeste asked Mark to be "super specific about exactly the floorplans you want included" but Mark said "I don't have any specific" so the conclusion is "all from all manufacturers".

**Worktree + branch**: `~/Code/_worktrees/pgf-pr-24-finish` on `feat/inventory-floorplan-sync-finish` (rebase off PR #24's head).

**Steps**:
1. **Read the PR**: `gh -R arigatoexpress/Project-Go-Forward pr view 24 --json title,body,headRefName,baseRefName,mergeStateStatus,reviewDecision`
2. **Pull review comments**: `gh -R arigatoexpress/Project-Go-Forward pr view 24 --comments` and `gh api repos/arigatoexpress/Project-Go-Forward/pulls/24/comments`. Identify each Codex-bot blocker.
3. **Check out the PR's branch into your worktree**: `git fetch origin pull/24/head:pr-24 && git checkout -b feat/inventory-floorplan-sync-finish pr-24` (adjust as needed).
4. **Address each blocker**. Don't refactor unrelated code; only touch what the bot flagged.
5. **Add 1 test per resolved blocker** so the issue can't regress.
6. **Verify** locally; push; the original PR #24 will update with new commits OR you open a fresh PR and close #24 with a comment pointing at the new one (operator's choice — default to updating #24 if its branch is one you control; otherwise open a new PR).

**Constraints**:
- **No scope creep beyond the bot blockers**. The PR's design is approved; just close the review loop.
- **Do not auto-merge** even if everything goes green — the operator wants to eyeball this one because it touches the live customer catalog ingestion.
- **Floorplan policy**: per the email thread, "all floorplans from all our manufacturers" is the implicit scope. Don't add a UI for per-floorplan opt-out unless the bot specifically flagged it as missing.

**Verification**:
```bash
pytest tests/ -q --tb=short
```

**PR title**: keep the original `feat(inventory): drive floorplan sync + master catalog ingest` (just push commits onto the existing PR if you can).

---

### LANE S3 — Etai-Notion ↔ THO integration analysis memo

**Why it matters**: Etai Zilberman (etaizilberman@gmail.com), an Upwork contractor hired by Celeste, is building a Notion workspace for THO. The existing Project-Go-Forward Document Center + Firestore CRM already provides the same logical surfaces (customer state, document templates, drive integration). The operator flagged the parallel-source-of-truth risk in his 2026-04-28 00:20 UTC reply to Etai. This lane writes the **integration analysis memo** that gives the operator and Etai a shared, written boundary — what does Notion own, what does Project-Go-Forward own, and what's the read/write contract between them.

**Worktree + branch**: `~/Code/_worktrees/pgf-etai-integration-memo` on `docs/etai-integration-memo`.

**Files to write**:
- `docs/integration/etai-notion-integration-2026-04-28.md` — the memo itself. ≥ 2,000 words. Sections:
  1. **Executive summary** — one paragraph: who, what, why now, and the one-sentence recommendation.
  2. **Current Project-Go-Forward capabilities** — what already exists. Customer record schema (1,326 ENROLLED, 629 LEAD, 8 CLOSED), 63 PDF templates, GCS bucket `tho-secure-documents`, JWT auth, prefix search on `_name_lower`, deal creation form, document generation from deals, customer analytics tab. Cite file paths.
  3. **Notion's likely scope** (inferred from Etai's email + Celeste's framing) — workspace for "all 11" (employees? accounts?), including team docs, process pages, possibly customer notes.
  4. **The parallel-source-of-truth risk** — 3 concrete examples where the same datum (customer status, document template, deal stage) could end up in both systems and drift. For each, articulate the failure mode.
  5. **Recommended boundary**: a clean line. The operator's hint in his 4-question reply was "what's the integration boundary between Notion and the existing Drive spreadsheets / Document Center". Three options to evaluate:
      - **Option A — Notion as system-of-record for team/process, PGF as system-of-record for customers/docs.** Boundary: customer data NEVER lives in Notion; team SOPs / playbooks NEVER live in PGF.
      - **Option B — Notion as front-end UX, PGF as backend.** Notion embeds PGF dashboard pages; customer reads/writes happen via API. This requires Etai to wire Notion's API blocks to PGF endpoints.
      - **Option C — Drive sheets as the bridge.** Both Notion and PGF read from / write to a small set of Drive sheets that are the actual source of truth. Most fragile but fastest to ship.
      - For each option: pros, cons, integration cost, time-to-deliver, who owns what when something breaks.
  6. **Recommendation** — pick one option with reasoning. Default to **Option A** unless the analysis surfaces something unexpected, because it's the cleanest separation and the operator already flagged "two parallel sources of truth" as the thing he wants to avoid.
  7. **Concrete next steps for Etai**: a 5-bullet list aligned with the operator's 4-question email reply (scope confirmation, Drive access, Signal channel, milestone date) — this section is what the operator can paste into his next email to Etai.
  8. **Concrete next steps for the operator**: rotation/integration items that PGF needs (e.g. expose a bounded customer-search API for Notion to call, document the JWT/HMAC auth flow so Etai's Notion plugin can use it).
  9. **Open questions** — be honest about what you don't know. What does "all 11" mean? What is Etai's actual deliverable (kanban-style ops board? CRM front-end? team wiki?). Flag for the operator.
- `docs/integration/etai-notion-integration.envelope.json` — provenance envelope (mirror Sapphire's `lib/core/provenance.py` shape if PGF doesn't have one yet; else create a minimal `{generator, model, prompt_hash, source_hashes, ttl, version}` JSON sidecar).

**Constraints**:
- **Honest scope inference**: Etai has not yet replied to the operator's 4-question email. You're inferring from one email + Celeste's framing. Mark inferred items explicitly with "(inferred — confirm with Etai)" so the operator can edit before sharing.
- **No code changes**. This is a docs-only PR.
- **Buyer-readable AND operator-readable**: this is the kind of memo that, if THO were ever acquired or if PGF's IP were ever reviewed for due diligence, would be a clear historical artifact of the integration thinking.
- **Provenance-stamped** so when the operator forwards this to Etai or Mark, the SHA of the analyzed code state is provable.
- **No real customer data** in examples; fabricate fictional examples.

**Verification**:
- `markdownlint docs/integration/etai-notion-integration-2026-04-28.md` if available
- Word count ≥ 2,000
- Every file path cited resolves to a real file in the repo (check with `test -e`)

**PR title**: `docs(integration): etai-notion vs project-go-forward boundary analysis`

---

## 4. Verification protocol

Each lane's PR opens only after:
- `pytest tests/ -q --tb=short` is green (when applicable)
- Any new test files run cleanly in isolation
- Markdown lints clean (when applicable)
- The change is scoped to ONLY what the lane authorized — no drive-by edits

---

## 5. PR template

Each PR body must include:
- **What this enables** — operator + Etai + acquirer framing
- **Safety posture** — no live data, no Cloud Run deploy, no real PII, no live GCS
- **Local verification** — command outputs (or trimmed tails)
- **Files changed** — file list
- **Follow-ups not in this PR** — be honest

---

## 6. Merge protocol

```bash
git -C ~/Code/Project-Go-Forward worktree remove ~/Code/_worktrees/pgf-<branch> --force

TITLE=$(gh -R arigatoexpress/Project-Go-Forward pr view <N> --json title --jq '.title')
SUBJECT="${TITLE} [skip ci]"

gh -R arigatoexpress/Project-Go-Forward pr merge <N> --squash --admin --delete-branch -t "$SUBJECT"

git -C ~/Code/Project-Go-Forward pull --quiet

# Cancel any queued / in-progress hosted runs
gh -R arigatoexpress/Project-Go-Forward run list --limit 5 --json databaseId,status --jq '.[] | select(.status=="queued" or .status=="in_progress")'
# If any results, cancel: gh -R arigatoexpress/Project-Go-Forward run cancel <id>
```

---

## 7. Closeout deliverable

After the last lane merges (or skips), write **one** handoff doc at `~/Code/Project-Go-Forward/docs/handoffs/codex-supplement-tranche-3-thosat-2026-04-29-report.md` and commit it directly to main with `[skip ci]`. The doc MUST include:

1. **Final main SHA** + open PR/issue counts.
2. **Per-lane status table** — lane name, PR number, files changed, test delta, key design decisions, caveats.
3. **Verification at handoff** — command tails.
4. **Operator-owed actions** — anything the operator needs to do (deploy revision 27, share the integration memo with Etai, address open inferred-scope questions).
5. **Skipped lanes** with reasoning.
6. **Squash-merge subject audit** — confirm every Tranche 3 supplement squash subject ended with `[skip ci]`.

---

## 8. Posture reminders

- **Don't grow new surface area**. Every lane closes a loop the operator already opened.
- **THO production is real customer data** — every choice errs toward "preserve". When in doubt, document and stop, don't act.
- **The Etai memo is the highest-leverage deliverable in this prompt** — it converts a known-unknown ("how do these two systems coexist?") into a written, share-able artifact. If you only ship one of three lanes, ship Lane S3.
- **Don't touch Sapphire** from this session.
- **Don't deploy to Cloud Run**.

Now go.
