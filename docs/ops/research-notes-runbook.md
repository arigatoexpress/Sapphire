# Research Notes Runbook

This runbook covers Research Notes Pipeline 0.1.0. The service is a local, one-shot artifact builder for diligence-ready strategy notes. It is safe for routine local use because it reads only existing local backtest/performance artifacts and writes only under `data/research_notes/`.

## Build

```bash
python3 services/research_notes/build.py
```

Useful deterministic sample command:

```bash
python3 services/research_notes/build.py \
  --as-of-date 2026-04-29 \
  --strategy-slug sapphire-composite \
  --generated-at 2026-04-29T00:00:00+00:00 \
  --context-json '{"market_regime":"fixture"}'
```

## Plugin Actions

- `compose`: return a `ResearchNote` JSON object.
- `render`: compose and write `research-note.pdf`.
- `latest`: return the newest generated PDF metadata.
- `aggregate-summary`: count generated notes by date and strategy.
- `build`: service-equivalent helper for local operators.

Example:

```bash
echo '{"action":"aggregate-summary"}' | python3 plugins/claw-sapphire/tools/research_notes.py
```

## Outputs

Canonical output:

```text
data/research_notes/<YYYY-MM-DD>/<strategy-slug>/research-note.pdf
data/research_notes/<YYYY-MM-DD>/<strategy-slug>/research-note.pdf.envelope.json
```

The envelope records generator metadata, artifact hash, source hashes when the source files are available, and note metadata. Keep the envelope with the PDF whenever the artifact is shared in a diligence packet.

## Verification

```bash
python3 -m compileall -q lib/research_notes services/research_notes plugins/claw-sapphire/tools/internal/research_notes.py plugins/claw-sapphire/tools/research_notes.py
python3 -m pytest tests/unit/test_research_notes_composer.py tests/unit/test_research_notes_visualizations.py tests/unit/test_research_notes_renderer.py -q
python3 -m pytest plugins/claw-sapphire/tests/test_research_notes.py -q
python3 scripts/validate_tool_registry.py
ruff check lib/research_notes services/research_notes plugins/claw-sapphire/tools/internal/research_notes.py plugins/claw-sapphire/tools/research_notes.py tests/unit/test_research_notes_composer.py tests/unit/test_research_notes_visualizations.py tests/unit/test_research_notes_renderer.py plugins/claw-sapphire/tests/test_research_notes.py
git diff --check
```

## Safety Notes

Do not add live market fetches to tests. Do not include customer data, secrets, Telegram tokens, account identifiers, or private logs in context payloads. Do not connect this artifact builder to trade execution. If a note looks stale, rebuild from a fresh completed sweep instead of editing the PDF by hand.
