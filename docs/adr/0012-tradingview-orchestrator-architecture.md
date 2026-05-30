# ADR 0012 — TradingView orchestrator architecture

- **Status**: accepted
- **Date**: 2026-04-30
- **Authors**: Sapphire ops
- **Related**: ADR 0003 (trading critical path CODEOWNERS gate),
  ADR 0004 (bounded LLM tools via env-flag), ADR 0005 (provenance
  envelopes), `docs/ops/tradingview-orchestrator-runbook.md`

## Context

The TradingView orchestrator surface (`lib/trading/tradingview_orchestrator.py`,
`lib/trading/pine_templates.py`, `scripts/ops/tradingview_ta_capture.py`,
`services/windows_tv_agent/`, and the `/api/tradingview/orchestrator/*`
endpoints in `services/dashboard/app.py`) was built in a tight window from
the 2026-04-29 evening tranche through the 2026-04-30 morning closeout. It
turns the local TradingView Desktop instance on the Mac commander into a
captured, scriptable TA rendering engine for Sapphire — driving symbol /
timeframe / indicator state, taking screenshots, pulling OHLCV summaries,
and round-tripping Pine Script through the editor.

A runbook exists at `docs/ops/tradingview-orchestrator-runbook.md` covering
the operator-facing surface (CLI invocation, dashboard endpoints, the
mutation gate, scheduled jobs). The runbook is the manual; this ADR is
the rationale. Several of the design choices look idiosyncratic at a
glance — read-only by default for everything scheduled, a single env
flag gating every mutation, the Windows agent shipping in a state called
`agent_only` — and we want future contributors to understand WHY before
they unwind any of it.

The orchestrator touches the trading critical path indirectly: a Pine
script that the orchestrator writes can fire an alert that POSTs to
`services/webhook/src/receiver.py` and feeds the live signal pipeline.
That coupling is what makes the contract pin and the mutation gate
load-bearing rather than ornamental.

## Decision

We codify seven decisions that govern the orchestrator surface.

### DECISION 1 — TradingView is a TA rendering engine, not a stateful database

We drive TradingView **deliberately** (set symbol → capture → store)
rather than trying to keep a Sapphire-side mirror in sync with TV's
state via watchlist reconciliation.

**Why**: a previous lane (Gemini, 2026-04-29) attempted to reconcile
the active TV watchlist against a Sapphire-side canonical list. The
attempt hit `tv watchlist get` returning the *active view* (the
pane currently focused in the desktop UI) rather than a stable union
of all watchlists. The reconciliation was non-deterministic — the
"current state" depended on which pane the user last clicked. Driving
deliberately (set the symbol we want, capture, move on) is robust
against that flake because each capture step is a closed subgraph:
`setup_chart(sym) → screenshot/ohlcv/values → next symbol`. The
captured artifact is the source of truth, not TV's in-memory pane
state.

This is reflected in the `capture_sweep` and `capture_symbol_deep`
methods, which both write a manifest with `schema_version`,
`generated_at`, and a per-symbol record — so the artifact stands on
its own.

### DECISION 2 — Single mutation gate via `SAPPHIRE_TV_MUTATION_ENABLED=1`

Every TV-mutating method on `TradingViewOrchestrator` (`set_symbol`,
`set_timeframe`, `setup_chart`, `apply_indicator_stack`, `pine_open`,
`pine_set_from_file`, `pine_compile`, `pine_save`, `pine_promote`,
`alert_create`, `alert_delete`, …) refuses unless
`SAPPHIRE_TV_MUTATION_ENABLED=1` is set in the process environment
(or `mutation_enabled=True` is passed at construction). The refusal
is a structured `{"mutated": False, "reason": "..."}` return — not
an exception — so callers can detect it cleanly.

**Why**: TV is shared, single-user, and stateful. A misconfigured
agent or a copy-pasted script that calls `set_symbol("BTCUSD")`
silently changes what the operator sees on screen. By gating every
mutation through one env flag, we force an explicit operator step
("yes, I want this script to be allowed to push buttons") and keep
the read-only path absolutely safe — the same script run without the
flag never touches TV's state. This mirrors ADR 0004's "bounded LLM
tools via env-flag" pattern: `SAPPHIRE_<TOOL>_LIVE=1` is the canonical
shape for all of Sapphire's "engage the dangerous mode" toggles.

### DECISION 3 — Pine generator emits webhook-contract JSON, not free-form strings

`lib/trading/pine_templates.py::render_sapphire_watch_indicator`
emits Pine v5 source whose `alert(...)` calls produce a JSON body
that exactly matches the schema parsed by
`services/webhook/src/receiver.py::TradingViewAlert.from_webhook` —
`symbol`, `action` (∈ {long, short, exit_long, exit_short}), `price`,
`time`, `strategy`, `source`, `interval`, `exchange`. A contract test
at `tests/unit/test_pine_to_webhook_contract.py` pins the field names
on both sides so generator drift is caught at PR time.

**Why**: the generator and the receiver live in different parts of
the tree (`lib/` vs `services/webhook/`) and the path between them
goes through a third-party (TradingView fires the webhook). Drift is
silent: TV compiles the Pine source fine, fires the alert fine, and
the receiver returns HTTP 400 — which the operator only sees if they
are watching the receiver logs at exactly the wrong moment. Pinning
the contract in a unit test is much cheaper than recovering from a
day of dropped alerts. This is the "Pine Script as RPC client" view
of the codepath.

### DECISION 4 — Read-only by default for scheduled jobs

The two scheduled LaunchAgents that drive the orchestrator —
`com.sapphire.tradingview-ta-capture` (every 4 hours, sweep capture)
and `com.sapphire.tradingview-pine-batch` (daily, Pine
generate-batch + server-side validate) — both run **without** the
`SAPPHIRE_TV_MUTATION_ENABLED` env var. Mutation is reserved for
manual operator action (a one-off CLI invocation with the flag, or
the dashboard "promote" endpoint).

**Why**: scheduled mutation is a drift accumulator. A 4-hourly cron
that walks symbols accumulates state changes in TV that the operator
did not authorize and may not notice for days. By contrast, scheduled
read-only capture is idempotent — it produces a manifest, writes
artifacts to disk, and exits. The operator's view of the TV desktop is
unchanged. When mutation is genuinely required (e.g. promoting a
generated Pine into the editor), the operator runs it by hand with
the flag set and watches it happen.

### DECISION 5 — Windows TV agent ships in `agent_only` state by default

`services/windows_tv_agent/server.py` exposes a read-only health and
CDP-status endpoint. By default `WINDOWS_TV_AGENT_CDP_REQUIRED=0`,
which means the agent reports `status="agent_only"` (process is up,
TV CDP is not reachable) rather than `status="degraded"`. This
matches the canonical Sapphire topology: TradingView Desktop runs on
the **Mac commander** (100.x.x.w), not on the Windows host
(100.x.x.z) which serves Ollama / webhook / research.

Sites that DO run TV on Windows can set
`WINDOWS_TV_AGENT_CDP_REQUIRED=1` and the agent will require a
reachable CDP endpoint to report `healthy`.

**Why**: shipping `degraded` as the default produced spurious WARN
noise in monitoring (`tradingview-cdp` is unreachable!) on every
single agent poll, drowning out genuine signal. `agent_only` is the
truthful state — the agent process is up; TV is just not local.
Operators who want the strict check can opt in with one env var.

### DECISION 6 — Artifact path-traversal guarded at the dashboard endpoint

The `/api/tradingview/orchestrator/artifacts/<path:artifact_path>`
endpoint in `services/dashboard/app.py` resolves
`(base / artifact_path).resolve()` and then calls
`.relative_to(base.resolve())`. A `ValueError` returns HTTP 400
`invalid_path`, which blocks `../../etc/passwd`-style escapes from
ever reading a file outside `data/tradingview_ta/`.

**Why**: the dashboard is single-shared-password auth (one
`AUTH_PASSWORD` env var, no per-user accounts). A leaked password is
a full read of every endpoint. Defence-in-depth says we don't trust
the auth layer alone for any endpoint that takes a filesystem path
from the URL — even one that is conceptually scoped to a known root.
The `relative_to` check is two lines and impossible to forget.

### DECISION 7 — Pine generation is content-addressable

Pine output goes to `pine/generated/<slug>.pine` plus a
`<slug>.json` sidecar with `schema_version="sapphire.pine_template.v1"`,
`generated_at`, `byte_size`, and the originating template name /
parameters. The directory is gitignored (see `.gitignore` line 118).
The `slug` is derived from the symbol via `_SAFE_NAME_RE` so the same
input always produces the same path.

**Why**: hand-authored Pine sources live under `pine/standalone/`
and are first-class repository artifacts (committed, reviewed,
versioned). Generated Pine should not pollute that surface — every
regen would produce a noisy diff and the question "is this the
hand-written one or the generated one" would have no clean answer.
By gitignoring `pine/generated/`, regeneration is free; by writing
a sidecar with `schema_version`, future format changes can be
detected (the loader in `list_generated()` filters out entries whose
schema does not match). The sidecar also doubles as a provenance
envelope (consistent with ADR 0005) — every generated `.pine` file
has a verifiable record of how and when it was emitted.

## Consequences

- **Positive**:
  - **Clear safety boundary**. Every TV mutation goes through one
    env flag (Decision 2). Operators reading `tradingview_orchestrator.py`
    can grep for `MUTATION_ENV` and see every gated method in one
    glance.
  - **Webhook drift is caught in CI**, not in production (Decision 3).
    The contract test fails the build if either side moves a field name.
  - **Scheduled jobs are safe to run on a sleepy Mac** (Decision 4).
    The operator can leave the laptop closed and the LaunchAgents do
    not corrupt the TV state.
  - **Multi-host topology is honest** (Decision 5). Monitoring shows
    `agent_only` on Windows, `healthy` on the Mac commander, and the
    operator can read that as "everything is in its right place"
    rather than "something is broken".
  - **Generated artifacts are disposable** (Decision 7). Regenerating
    Pine for the top-N symbols nightly produces zero git noise.
- **Negative**:
  - The mutation gate adds one env-var step to every interactive
    "drive TV from a script" session. Forgetting it produces a
    structured `{"mutated": False}` return that callers must check
    — silent no-ops are possible if a caller doesn't.
  - Read-only by default (Decision 4) means scheduled jobs *cannot*
    refresh the indicator stack on the chart automatically; an
    operator has to do that. This is the cost of the safety property.
  - Decision 1 means we have no Sapphire-side single-source-of-truth
    for "what is currently on the TV chart". If a contributor expects
    one, they will have to read this ADR before going hunting for it.
- **Neutral**:
  - The `pine/generated/` directory is gitignored, so it does not
    appear in `git ls-files` and a contributor cloning the repo will
    not see any artifacts until they run a generation step.
  - The dashboard path-traversal check is a defense-in-depth measure
    — it does not replace the auth layer, it backstops it.

## Alternatives Considered

- **Watchlist reconciliation as the source of truth** (Decision 1):
  rejected — the Gemini 2026-04-29 lane established that
  `tv watchlist get` returns the active view, not a stable union, so
  reconciliation is non-deterministic. Captured-artifact-as-truth
  decouples Sapphire from TV's UI state.
- **Per-method permission flags** (Decision 2): rejected — a flag
  per mutating method (e.g.
  `SAPPHIRE_TV_ALLOW_SET_SYMBOL=1`) is finer-grained but exposes a
  combinatorial explosion of "did I set the right subset of flags"
  questions. The single-flag design was deliberately chosen for
  legibility, matching ADR 0004's pattern.
- **Pine generator emits Sapphire-internal JSON, with a translator
  layer in front of the webhook** (Decision 3): rejected — a
  translator adds a moving part with no upside. The webhook contract
  is the natural shape for Pine to emit, and the contract test
  enforces it.
- **Scheduled mutation with a "drift detector" that reverts**
  (Decision 4): rejected — every drift detector grows fingers
  (excludes, override env vars, "this is OK actually" lists) and
  becomes a maintenance liability. Read-only by default never grows
  fingers.
- **Always-strict CDP requirement on the Windows agent**
  (Decision 5): rejected — produces spurious `degraded` WARNs on
  every poll because the canonical topology runs TV on the Mac.
  The opt-in flag is a one-line override for sites that genuinely
  need the strict check.
- **Trust the dashboard auth layer for path safety** (Decision 6):
  rejected — single-shared-password auth is one leak away from
  arbitrary read. The `relative_to` check is two lines and removes
  the entire class of path-traversal bugs from this endpoint.
- **Commit generated Pine into `pine/standalone/` alongside
  hand-authored sources** (Decision 7): rejected — would pollute the
  curated surface, break `git blame` semantics on Pine sources, and
  make every nightly regeneration a noisy PR.

## References

- Orchestrator: `lib/trading/tradingview_orchestrator.py`
- Pine generator: `lib/trading/pine_templates.py`
- CLI driver: `scripts/ops/tradingview_ta_capture.py`
- Windows agent: `services/windows_tv_agent/server.py`
- Dashboard endpoints: `services/dashboard/app.py`
  (`/api/tradingview/orchestrator/*`)
- Webhook receiver (contract counterparty):
  `services/webhook/src/receiver.py`
- Contract test: `tests/unit/test_pine_to_webhook_contract.py`
- Scheduled jobs:
  `infra/launchagents/com.sapphire.tradingview-ta-capture.plist`,
  `infra/launchagents/com.sapphire.tradingview-pine-batch.plist`
- Operator runbook: `docs/ops/tradingview-orchestrator-runbook.md`
- CDP setup: `docs/tradingview-cdp-setup.md`
