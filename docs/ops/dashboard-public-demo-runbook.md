# Dashboard Public Demo Runbook

This runbook describes the buyer-safe dashboard demo workflow. The goal is to
prepare static demo artifacts without exposing secrets, local paths, customer
data, or real screenshots with sensitive dashboard state.

## Safety Model

The public-demo readiness lane is intentionally conservative:

- No trading critical-path code is touched.
- No browser is launched by the readiness script.
- No dashboard server is required for the default workflow.
- No live external calls are made.
- No real screenshots are committed.
- Redaction happens in memory and in ignored `build/` artifacts.

The readiness script is `scripts/ops/dashboard_public_demo_readiness.py`. Its
redaction manifest is `config/dashboard_public_demo_redactions.json`.

## Default Workflow

From the Sapphire repo root:

```bash
/usr/local/bin/python3 scripts/ops/dashboard_public_demo_readiness.py --pretty
```

This writes two ignored files under `build/dashboard-public-demo/`:

```text
dashboard-public-demo-plan.json
dashboard-public-demo-redaction-report.json
```

The plan lists the dashboard routes that are safe to capture later. The
redaction report scans configured diligence and microsite source files, applies
the manifest patterns in memory, and verifies that committed acquirer screenshot
files are zero-byte placeholders.

The current safe-route plan starts with `/showcase`, the unified dashboard for
friend, buyer, engineer, and operator demo paths. It includes Sapphire command
surfaces, satellite frontend links, adjacent project coverage, and the read-only
safety posture. Treat it as the first capture unless a specific diligence
request asks for a narrower page.

Use `--no-write` when you only want stdout:

```bash
/usr/local/bin/python3 scripts/ops/dashboard_public_demo_readiness.py --no-write --pretty
```

## Redaction Manifest

The manifest declares:

- safe routes for a static public demo,
- source files to scan,
- screenshot placeholder directories,
- sensitive regex patterns,
- forbidden literals after redaction,
- output filenames.

The current sensitive patterns redact:

- absolute `/Users/...` paths,
- secret-shaped assignments such as `token=value` or `AUTH_PASSWORD=value`,
- bearer tokens,
- credentialed URLs,
- private email addresses.

The manifest allows credential names to appear in explanatory prose, but it
blocks assignment-shaped leaked values such as `MOONSHOT_API_KEY=value`.

## Screenshot Policy

The committed files in `web/acquirer/assets/screenshots/` must remain empty
placeholders. The readiness script fails when it finds a non-empty image in that
directory. Real screenshots can be produced locally with
`scripts/ops/render_acquirer_screenshots.py`, but they should be reviewed and
published out of band, not committed back to the repo.

Dry-run screenshot plan:

```bash
/usr/local/bin/python3 scripts/ops/render_acquirer_screenshots.py --dry-run
```

Live screenshot capture is operator-only and separately gated:

```bash
SAPPHIRE_PLAYWRIGHT_LOCAL=1 \
  /usr/local/bin/python3 scripts/ops/render_acquirer_screenshots.py --live
```

Only run the live path after reviewing the readiness report and launching the
dashboard with a non-weak local auth password. Avoid credentialed browser URLs;
use browser auth handling or headers.

## Release Checklist

Before sharing a public dashboard demo with a buyer:

1. Run the readiness script and confirm `ok: true`.
2. Review `build/dashboard-public-demo/dashboard-public-demo-redaction-report.json`.
3. Confirm screenshot placeholders are still zero-byte files in git.
4. If live screenshots are needed, capture them locally and review them outside
   the repo before publishing.
5. Run focused tests:

```bash
/usr/local/bin/python3 -m pytest tests/unit/test_dashboard_public_demo_readiness.py tests/unit/test_render_acquirer_screenshots_dryrun.py tests/unit/test_acquirer_microsite_html.py -q
```

6. Run the feasible local gates used for this lane:

```bash
ruff check scripts/ops/dashboard_public_demo_readiness.py tests/unit/test_dashboard_public_demo_readiness.py
git diff --check
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external
```

## Failure Triage

If the readiness report fails on a source file, inspect the
`forbidden_after_redaction` field first. That means a forbidden literal survived
redaction and the source or manifest needs a focused fix.

If it fails on a screenshot, remove the real capture from the tracked screenshot
directory and regenerate only in an ignored or external export location.

If redaction counts are high, that is not automatically a failure. The diligence
packet intentionally references repo paths and operational artifacts. The
question is whether the redacted preview is buyer-safe after the configured
patterns run.

## Rollback

Rollback is a normal PR revert. The lane adds a script, a manifest, tests, and
this runbook. It does not alter dashboard routes, dashboard templates, trading
code, runtime services, or screenshot capture behavior.
