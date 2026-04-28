# Acquirer Microsite 0.1.0

`web/acquirer/` is a static, self-contained acquirer brief intended for
corporate-development reviewers. It distills the eight Wave-4 + Tranche-2
acquisition surfaces, the diligence packet, and the safety posture into a
single page that can be served from any static host.

## What ships

- `web/acquirer/index.html` - single-page brief.
- `web/acquirer/assets/styles.css` - vanilla CSS, no frameworks.
- `web/acquirer/assets/screenshots/` - placeholder PNGs + `.gitkeep`.
- `web/acquirer/requirements.txt` - Playwright pin (operator-only).
- `scripts/ops/render_acquirer_screenshots.py` - dry-run-default screenshot
  harness.

## Posture

- **Static only**. No backend, no API, no database, no SSR.
- **No external JS, no analytics, no tracking pixels**. Self-contained.
- **No real screenshots committed**. Placeholders only; the operator runs
  the harness locally to populate them and publishes them out-of-band.
- **Operator-driven Playwright**. The harness refuses to launch a browser
  unless `SAPPHIRE_PLAYWRIGHT_LOCAL=1` is set; tests cover the dry-run path
  only.
- **Discouraged from search**. `meta robots noindex,nofollow` set on the
  page; the site is meant to be shared as a direct link with named contacts.

## Sections featured on the page

1. Mission - one paragraph.
2. Capabilities - 9 cards covering PRs #331, #334, #372, #373, #374, #376,
   #388, #389, and #386 (the diligence pages combo). Each card has a
   sparkline metric, three quick stats, and a placeholder screenshot.
3. Tech stack - mesh, 4-tier inference, contracts, event spine.
4. Diligence packet - links to `docs/diligence/00-09`.
5. Safety posture - kill switch, confirmation firewall, provenance, no-spend
   posture, live-capital posture, secret handling.
6. Founders + contact.

## Hosting

`/usr/local/bin/python3 -m http.server 8090` from `web/acquirer/` is the
fastest path to view it locally. Cloudflare Pages and Netlify are both fine
for external hosting (zero build step, drag and drop). DNS for
`acquirer.sapphirealpha.xyz` lives in Google Cloud DNS in project
`sapphire-479610` if the operator decides to attach the canonical hostname.

## Tests

- `tests/unit/test_acquirer_microsite_html.py` - 15 cases. Validates file
  shape, link targets, no inline JS, no remote resources, all 8 acquisition
  surfaces named.
- `tests/unit/test_render_acquirer_screenshots_dryrun.py` - 9 cases. Dry-run
  path only; verifies the env-flag gate, idempotent re-runs, JSON plan
  shape, and that Playwright is NOT imported on the safe path.

## Cross-references

- Runbook: `docs/ops/acquirer-microsite-runbook.md`.
- Lane spec: `docs/handoffs/codex-megaprompt-tranche-3-2026-04-28.md` Lane 4.
- Diligence packet: `docs/diligence/00-executive-summary.md`.
- Live-trading ramp memo: `docs/products/live-trading-ramp-memo.md`.

## Provenance

Generator: Codex Tranche 3 Lane 4. Branch:
`feat/acquirer-microsite-and-screenshots`. Generated 2026-04-28 against
canonical SHA `6fe9335f`.
