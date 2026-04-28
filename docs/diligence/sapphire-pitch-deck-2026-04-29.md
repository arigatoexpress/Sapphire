# Sapphire OS — Investor / Corp-Dev Pitch Deck

**File:** `sapphire-pitch-deck-2026-04-29.pptx` (alongside this README)
**Build SHA:** `9074c408`
**Build date:** 2026-04-29
**Default audience:** Palantir Foundry corp-dev (renders cleanly for Robinhood
Cortex or a specialty acquirer with one slide swap — see Slide 8).
**Slide count:** 14 · **Aspect ratio:** 16:9 · **File size:** ~317 KB
**Sidecar:** `sapphire-pitch-deck-2026-04-29.pptx.envelope.json`
(`lib/core/provenance.py` shape, schema_version=1)

## What this is

A 12–14-slide acquisition-grade summary of the Sapphire OS diligence packet
(`docs/diligence/00` through `09-*.md`), the 14 productized surfaces under
`docs/products/*-{0.1.0,0.2.0}.md`, the kill-switch invariants
(`docs/security/kill-switch-invariants.md`), the live-trading ramp memo
(`docs/products/live-trading-ramp-memo.md`), and the competitive landscape
research (`docs/competitive/landscape-2026-04-28.md`). It is intended for a
buyer's diligence team to absorb in roughly 10 minutes before opening the
underlying packet.

## Slide map

| #  | Slide                       | Anchored in                                                   |
|---:|-----------------------------|---------------------------------------------------------------|
|  1 | Title                       | `docs/diligence/00-executive-summary.md`                      |
|  2 | The thesis                  | `docs/diligence/00-executive-summary.md`                      |
|  3 | The intelligence stack      | `docs/diligence/01-architecture.md` (Mermaid → PNG)           |
|  4 | Capabilities matrix         | `docs/products/*-{0.1.0,0.2.0}.md` (14 surfaces)              |
|  5 | Safety posture              | `docs/security/kill-switch-invariants.md`                     |
|  6 | Production traction         | `CLAUDE.md` + `scripts/ops/test_inventory.py`                 |
|  7 | Competitive landscape       | `docs/competitive/landscape-2026-04-28.md`                    |
|  8 | Why Palantir Foundry        | `docs/products/foundry-ontology-0.2.0.md` + Palantir memory   |
|  9 | Live-trading ramp           | `docs/products/live-trading-ramp-memo.md`                     |
| 10 | Team + IP                   | `docs/diligence/09-team-and-process.md`                       |
| 11 | Acquisition rationale       | `docs/diligence/00-executive-summary.md`                      |
| 12 | The ask (POC scoping call)  | Operator memory + `docs/diligence/00-executive-summary.md`    |
| 13 | Appendix · Diligence packet | `docs/diligence/` + `web/acquirer/index.html`                 |
| 14 | Appendix · Provenance       | `lib/core/provenance.py`                                      |

## Honest caveats

- **The deck is paper-honest.** Sapphire is paper-mostly. The $5 live-crypto
  rung is *designed and gated* per `docs/products/live-trading-ramp-memo.md`;
  the deck does not assert an executed fill because no executed-fill artifact
  is resident in the repo at the build SHA.
- **Stock automation remains blocked.** No official Robinhood equities API
  exists; Slide 9 says so plainly.
- **Team slide is brief by design.** Operator edits the team page after build.
- **5,304 tests** is the current count from `scripts/ops/test_inventory.py
  --check-readme` on 2026-04-28 (4,928 unit + 376 plugin). `CLAUDE.md` notes
  5,281 from a 2026-04-28 verification snapshot — both are correct snapshots
  of the same tree at slightly different moments. The deck uses the more
  recent number.

## How to render the deck

```bash
# View directly (macOS Keynote / Powerpoint / LibreOffice Impress)
open docs/diligence/sapphire-pitch-deck-2026-04-29.pptx

# Convert to PDF for diligence email distribution
soffice --headless --convert-to pdf docs/diligence/sapphire-pitch-deck-2026-04-29.pptx

# Verify the file isn't corrupt
python3 -c "from pptx import Presentation; \
  p = Presentation('docs/diligence/sapphire-pitch-deck-2026-04-29.pptx'); \
  print(f'{len(p.slides)} slides, {p.slide_width.inches:.1f}\" x {p.slide_height.inches:.1f}\"')"

# Verify the provenance sidecar
python3 scripts/ops/provenance_verify.py --pretty | grep sapphire-pitch-deck
```

## How to swap the audience slide

Slide 8 (`Why Palantir Foundry corp-dev`) is the only audience-specific slide.
Open `sapphire-pitch-deck-2026-04-29.pptx` in Keynote / PowerPoint and replace
the three card titles + bodies with the appropriate audience pitch. The
generator script's `slide_why_audience()` function in
`/tmp/sapphire-deck-build/build_deck.py` (preserved in the worktree under
the same path) is the canonical source if a fresh render is preferred.

For Robinhood Cortex, lift the alternate framing from the speaker-notes panel
on Slide 8 (paraphrased: broker-agnostic risk explanation that respects
Cortex's no-trade boundary; crypto-specific intelligence; the live-trading
ramp discipline that mirrors Cortex's careful insight-vs-execution split).

## Provenance

- Every slide's notes panel ends with a `Source: <file_path> @ SHA <head>`
  line. The notes panel is included in the file size — open the deck, choose
  "Notes view" or "Notes" in your viewer of choice.
- The sidecar JSON file at `sapphire-pitch-deck-2026-04-29.pptx.envelope.json`
  records `payload_hash`, `source_hashes` for the 22 source files, generator
  identity, and operator metadata.
- Build inputs at HEAD `9074c408`:
  - `docs/diligence/00-09` (10 files)
  - `docs/products/{risk-kernel,provenance-envelopes,foundry-ontology,
    signal-correlator,narrative-synthesis,threat-intel-product,
    customer-dossier,live-trading-ramp-memo}.md` (8 files)
  - `docs/security/kill-switch-invariants.md`
  - `docs/competitive/landscape-2026-04-28.md`
  - `CLAUDE.md`
  - `web/acquirer/index.html`
- Visual identity mirrors the acquirer microsite palette
  (`web/acquirer/assets/styles.css`): `#0b1220` deep navy, `#6da5ff` sapphire
  accent, `#e6ecff` ice text.
- The architecture diagram on Slide 3 is rendered by `matplotlib` from the
  same logical decomposition as the Mermaid block in
  `docs/diligence/01-architecture.md`.

## Constraints honored

- **No fabricated metrics.** Each numeric claim has a repo source (Slide 6
  enumerates them; Slide 14 lists the verification commands).
- **No external company logos.** Competitor names appear as text labels only
  on Slide 7.
- **Honest framing.** Slides 4, 7, 9, 10 each include explicit honest
  concessions where Sapphire is partial / weak / does-not-compete.
- **`[skip ci]` on the commit.** Per repo convention.
- **No-spend.** The deck is rendered locally with python-pptx + matplotlib +
  LibreOffice (offline). Zero hosted-runner minutes consumed.
