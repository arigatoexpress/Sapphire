# Sapphire — Source Adapters

Agent charter for `lib/sources/`.  This directory contains adapters that fetch
and normalize external data into Sapphire-native objects.

## Scope

- `tdr_pro.py` — The DeFi Report Pro podcast RSS adapter.
  - Parses RSS feeds and `podcast:transcript` extensions.
  - Renders Markdown clippings with YAML frontmatter + hub navigation.
  - Generates a master episode index.
- `tdr_pro_email.py` — email-digest variant of the TDR Pro source.
- `brave_browser.py` — CDP automation for authenticated Brave sessions.
- `defillama.py`, `dune.py`, `earnings_calls.py`, `labor.py`, `news.py`,
  `sec_classifier.py`, `sec_edgar.py`, `x_sentiment.py` — other source adapters.

## How to run tests

```bash
python3 -m pytest tests/unit/test_sources_tdr_pro.py -q
python3 -m pytest tests/unit/sources/ -q
```

## Safety boundaries

- All live HTTP is gated by `SAPPHIRE_*_LIVE=1` environment variables.
  Tests use fixtures under `tests/fixtures/`; never hit the network in CI.
- Source adapters return plain dataclasses (`TDRProEpisode`, etc.) and do not
  perform trades, sends, or destructive actions.
- Keep adapters stateless; persistence belongs in the caller (`services/`,
  `scripts/`).

## Stack notes

- Python 3.11+ with `from __future__ import annotations`.
- `lib/source_quality/` registers quality metadata for each source at import
  time.
- New sources should follow the `*Source` + `*Episode`/record dataclass pattern
  used by `tdr_pro.py`.
