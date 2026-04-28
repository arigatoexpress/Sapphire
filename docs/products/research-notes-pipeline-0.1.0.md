# Research Notes Pipeline 0.1.0

Research Notes Pipeline turns Sapphire's local backtest sweep, closed-trade performance summary, and operator context into a buyer-readable PDF memo. The output is designed for diligence and review: it explains what the local evidence says, what could invalidate it, and what to watch next. It does not fetch live data, expose customer data, send Telegram messages, or authorize live trading.

## Product Surface

- `lib/research_notes/`: composition, chart rendering, PDF rendering, and note discovery.
- `services/research_notes/build.py`: one-shot builder that enumerates completed local sweeps before producing a note.
- `plugins/claw-sapphire/tools/research_notes.py`: stdin JSON plugin shim.
- `data/research_notes/<date>/<strategy>/research-note.pdf`: generated artifact with a sibling provenance envelope.

The core object is `ResearchNote`. It contains a thesis, counter-thesis, metrics, evidence bullets, invalidators, next steps, caveat, source paths, and provenance metadata.

## Safety Model

The pipeline is offline by design. It reads existing local artifacts through `lib.analytics.backtest_results` and `lib.analytics.strategy_performance`, or accepts explicit JSON fixtures from the plugin. It never calls market APIs, never reads secrets, never touches trading execution, and never sends external messages.

Every rendered PDF gets `research-note.pdf.envelope.json` via `lib.core.provenance`. The caveat is intentionally visible: this is a research-only artifact, not a trade instruction or customer-facing claim of future returns.

## Interfaces

Build a note from latest local artifacts:

```bash
python3 services/research_notes/build.py
```

Compose only:

```bash
echo '{"action":"compose","context":{"market_regime":"risk-on"}}' \
  | python3 plugins/claw-sapphire/tools/research_notes.py
```

Render a PDF:

```bash
echo '{"action":"render","as_of_date":"2026-04-29","strategy_slug":"sapphire-composite"}' \
  | python3 plugins/claw-sapphire/tools/research_notes.py
```

Inspect generated artifacts:

```bash
echo '{"action":"latest"}' | python3 plugins/claw-sapphire/tools/research_notes.py
echo '{"action":"aggregate-summary"}' | python3 plugins/claw-sapphire/tools/research_notes.py
```

## Known Limits

Matplotlib is used for charts when installed. On minimal local environments, the renderer falls back to a deterministic ReportLab vector chart so tests and sample generation stay offline and reproducible. The PDF is deterministic-ish: ReportLab invariant mode stabilizes document metadata, while file mtimes in the envelope naturally reflect generation time.

