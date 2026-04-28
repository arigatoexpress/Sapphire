# Acquirer microsite runbook

This runbook is the operator's reference for the static acquirer microsite at
`web/acquirer/` and the dashboard screenshot harness at
`scripts/ops/render_acquirer_screenshots.py`. Both ship in Tranche 3 Lane 4
of the Sapphire OS acquisition push and exist for one purpose: to give a
Palantir / Robinhood corp-dev reviewer a self-contained, link-following,
screenshot-grounded view of what they would be acquiring.

The site is deliberately simple. There is no JavaScript framework, no build
step, no analytics, no tracking pixel, no font CDN, no Tailwind CDN, and no
backend. The whole thing is a single HTML file, a single CSS file, a folder
of placeholder PNGs, and a Python harness that can populate those PNGs from
a local dashboard run.

## Files at a glance

```
web/acquirer/
  index.html                # the page
  assets/styles.css         # vanilla CSS (no frameworks)
  assets/screenshots/       # placeholder PNGs + .gitkeep
  requirements.txt          # Playwright pin (operator-only)
scripts/ops/
  render_acquirer_screenshots.py
                            # boots dashboard locally and screenshots pages
docs/products/
  acquirer-microsite-0.1.0.md
                            # short product blurb linking to this runbook
```

## Audience and intent

The audience is a corporate-development reviewer who has roughly twenty
minutes. They land on the page, scan the eight Wave-4 + Tranche-2 capability
cards, click into the diligence packet (`docs/diligence/00-09`), read the
live-trading ramp memo, and form an informed opinion. They should not need
to ask the operator anything during that twenty minutes.

The intent of the screenshot harness is to back the capability cards with
real screenshots from a running Sapphire dashboard. By default the harness
runs in dry-run mode (writes a JSON plan, never imports Playwright); going
live is gated by an explicit env flag because Playwright pulls a ~300 MB
Chromium binary and we do not want CI to ever do that automatically.

## Section: serving the site locally

The site is a static directory. The simplest way to view it is the stdlib
HTTP server:

```bash
cd ~/Code/Sapphire/web/acquirer
/usr/local/bin/python3 -m http.server 8090
```

Open `http://127.0.0.1:8090/` in a browser. Use `Ctrl+C` to stop. The
server is read-only and serves the directory verbatim. There is no
authentication; this is acceptable because the directory contains no
secrets and the screenshots committed to the repo are zero-byte
placeholders.

If you want a tiny bit more polish (404 page, MIME type tuning) `npx serve`
works too, but the stdlib server is sufficient and dependency-free.

## Section: hosting the site externally

Two paved-road choices, both free to start, both static-only:

### Cloudflare Pages

1. Create a new Pages project in the Cloudflare dashboard.
2. Connect the Sapphire repo (or upload a tarball of `web/acquirer/`).
3. Build command: leave blank.
4. Build output directory: `web/acquirer`.
5. Deploy. Cloudflare will issue a `*.pages.dev` URL.
6. Optional: add the production custom domain
   `acquirer.sapphirealpha.xyz` in the Pages project. DNS lives in Google
   Cloud DNS (project `sapphire-479610`); add a CNAME pointing to the
   Pages target. The TLS cert is issued automatically.

### Netlify

1. New site -> Deploy manually.
2. Drag `web/acquirer/` onto the upload target.
3. Netlify hosts at a `*.netlify.app` URL.
4. Optional custom domain: same DNS path as Cloudflare; add a CNAME.

Either host is acceptable. The site is genuinely portable: any static host
works because there are no headers, no redirects, no SSR, and no API calls.

## Section: rendering real screenshots

The repo only commits zero-byte placeholders. To populate them with real
screenshots you must run the harness locally. The harness boots the
dashboard, navigates to each authenticated page, and writes a full-page PNG
into `web/acquirer/assets/screenshots/`.

### One-time setup (operator only)

```bash
cd ~/Code/Sapphire
/usr/local/bin/python3 -m pip install -r web/acquirer/requirements.txt
/usr/local/bin/python3 -m playwright install chromium    # ~300 MB
```

The Playwright Chromium download is large. It lands under
`~/Library/Caches/ms-playwright/` on macOS. CI never installs it because
neither pyproject.toml nor any service requirements pin Playwright.

### Running the dashboard

The harness expects the dashboard listening on `http://127.0.0.1:8080`.
From the worktree:

```bash
cd ~/Code/Sapphire/services/dashboard
AUTH_PASSWORD=sapphire /usr/local/bin/python3 app.py
```

Leave that running in another terminal. The dashboard requires the
`AUTH_PASSWORD` env var or it crashes on import (this is a deliberate
fail-closed). The same value will be propagated to Playwright via an
optional `X-Auth-Password` header (see the harness source).

### Running the harness

Default is dry-run (safe, no Playwright imported):

```bash
/usr/local/bin/python3 scripts/ops/render_acquirer_screenshots.py
```

This prints a JSON document describing what the live run would do and
writes a `plan.dry-run.json` next to the planned screenshots. Inspect it
before going live.

Going live:

```bash
SAPPHIRE_PLAYWRIGHT_LOCAL=1 \
  /usr/local/bin/python3 scripts/ops/render_acquirer_screenshots.py --live
```

Without `SAPPHIRE_PLAYWRIGHT_LOCAL=1` the harness raises immediately. This
is the env-flag gate; you cannot accidentally launch a browser by running
the script without intent.

The harness captures these pages in order:

- `/` (home)
- `/sovereign-thesis`
- `/threat-intel`
- `/customer-dossier`
- `/diligence`
- `/sovereign-thesis-story`
- `/observability` (lands in Tranche 3 Lane 2; the harness skips gracefully
  if the route does not exist)

Each capture writes a full-page PNG with a deterministic filename. The
filenames are referenced in `web/acquirer/index.html`; if you rename a file
you must update the HTML or the page will show a broken `img`.

### Troubleshooting

If a navigation times out, the harness prints the URL and the exception to
stderr and continues with the next page. Bump the timeout with
`--timeout-ms 30000` for slow first paints (e.g. Playwright cold start, or
a freshly booted dashboard hitting cold caches).

If `chromium` is missing the harness raises a clear error. Re-run
`python3 -m playwright install chromium` and try again.

If a page returns auth-required, double-check that the dashboard is up
with the same `AUTH_PASSWORD` you exported in your shell.

## Section: editing the site

The HTML and CSS are intentionally hand-rolled. Edit `index.html` for
content and `assets/styles.css` for visual tuning. Keep the constraints
intact:

- No `<script>` blocks anywhere. Tests assert this.
- No inline `on*` event handlers. Tests assert this.
- All `<img>` sources start with `assets/screenshots/`. Tests assert this.
- All `<link rel="stylesheet">` references stay under `assets/`. Tests
  assert this.
- All anchors are either `#hash`, `../path`, `assets/path`, or `./path`.
  Tests assert this.
- Every PNG referenced has a placeholder file with the same name. Tests
  assert this.
- The mandatory section ids are present:
  `mission`, `capabilities`, `tech-stack`, `diligence`, `safety`, `contact`.
- Each of the 8 Wave-4 + Tranche-2 PRs is named in a card
  (`#331`, `#334`, `#372`, `#373`, `#374`, `#376`, `#388`, `#389`),
  plus `#386` for the diligence-pages combo card.

If a test starts failing after a content edit, run
`/usr/local/bin/python3 -m pytest tests/unit/test_acquirer_microsite_html.py -q`
and read the assertion. The tests are intentionally specific so that the
constraints are enforced rather than aspirational.

## Section: deploying updates

There is no CI deploy. The site is rebuilt and pushed by the operator on
demand. Rough cadence:

1. Open a PR that edits `web/acquirer/index.html` or `assets/styles.css`.
2. Verify locally:
   `/usr/local/bin/python3 -m pytest tests/unit/test_acquirer_microsite_html.py -q`
3. Render fresh screenshots if the dashboard has changed:
   `SAPPHIRE_PLAYWRIGHT_LOCAL=1 python3 scripts/ops/render_acquirer_screenshots.py --live`
4. Merge the PR (admin squash with `[skip ci]` per the Tranche 3 protocol).
5. Re-deploy to Cloudflare Pages or Netlify by uploading the new
   `web/acquirer/` directory or pushing the change.

The screenshots are NOT committed. The repo only carries zero-byte
placeholders so that diffs stay clean and so that committers do not have
to install Playwright. If you want shareable screenshots you publish them
out-of-band to the chosen host's asset bucket.

## Section: privacy posture

The site has zero analytics. There is no Google Analytics, no Plausible,
no Fathom, no Cloudflare Web Analytics, no Mixpanel, no Hotjar, no
Sentry, and no error-reporting beacon. The page does not even fetch
`favicon.ico` from a CDN; you can drop a local one into `assets/` if you
want one. The intent is that a buyer who lands here is observed only by
the operator's hosting provider's standard request logs, never by a
third-party tracker, and never tied to an identity beyond an IP address.

The `noindex,nofollow` meta tag is set on the page so that search engines
do not crawl the brief into public archives. The site is intended to be
shared as a direct link with named contacts, not discovered organically.

## Section: failure modes and rollback

The site is a directory. Rolling back is a `git revert` of the offending
commit, followed by a redeploy. There is no migration, no schema, no
state. If a card is wrong, edit the card. If the harness is broken, run
the dry-run and fix the JSON plan first; the live path is the easiest to
diagnose because it is a thin wrapper around Playwright's stable API.

If a screenshot turns out to leak a secret (operator name, tenant id, raw
PII), do NOT commit it. Treat the captured PNG the same way you treat
secrets at rest: rotate the underlying value, regenerate the screenshot
with the redacted dashboard, and replace the placeholder. The repo
defaults protect you here because we do not commit the real screenshots.

## Section: linking from elsewhere

The acquirer brief is intentionally NOT linked from the public README. It
is a brief, not a marketing site. To share it with a contact, send the
direct URL of your chosen host. The diligence packet links inside the
site point back at `docs/diligence/00-09` in the source repo so that a
reviewer who wants the raw evidence can follow along in the codebase
itself.

## Cross-references

- Lane spec: `docs/handoffs/codex-megaprompt-tranche-3-2026-04-28.md` Lane 4.
- Product blurb: `docs/products/acquirer-microsite-0.1.0.md`.
- Diligence packet: `docs/diligence/00-executive-summary.md` ... `09-team-and-process.md`.
- Live-trading ramp memo: `docs/products/live-trading-ramp-memo.md`.
- Kill-switch invariants (Lane 5): `docs/security/kill-switch-invariants.md`.
- Risk kernel public surface: `docs/products/risk-kernel-0.1.0.md`.
- Provenance envelopes: `docs/products/provenance-envelopes-0.1.0.md`.
