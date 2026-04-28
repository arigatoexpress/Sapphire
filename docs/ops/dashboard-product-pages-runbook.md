# Dashboard product pages — operator runbook

This runbook covers the product surfaces shipped in Wave 4 and Wave 6 of the
Sapphire dashboard: `/threat-intel`, `/customer-dossier`, `/diligence`, and
`/sovereign-thesis/story`. These pages
are *read-only*, *authenticated*, *paste-safe*, and *snapshot-only* —
they do not mutate upstream systems at request time. This runbook tells you
how to keep the snapshots fresh, how to triage failures, and how to
verify the safety contract before each release.

## Quick reference

| Page | API | Source data | Refresh agent |
|---|---|---|---|
| `/threat-intel` | `/api/threat-intel` | `data/intelligence/<date>/threats.json` | `services/dashboard/refresh_threats.py` (LaunchAgent, every 4h) |
| `/customer-dossier` | `/api/customer-dossier` | `data/tho_intel/dossier_*.json` | manual / scheduled (operator-driven) |
| `/diligence` | `/api/diligence-summary`, `/api/risk-kernel-summary`, `/api/provenance-summary`, `/api/test-suite-health`, `/api/launchagent-summary` | `docs/diligence/00-09`, risk/provenance/test metadata, `launchctl list` labels | none |
| `/sovereign-thesis/story` | `/api/investments/thesis` | `lib.intel.sovereign_thesis` report | none |

All pages inherit the dashboard's basic-auth (`AUTH_USERNAME` /
`AUTH_PASSWORD`). The cookies are not shared — each request must
present the basic-auth header.

The Wave 6 pages follow the same auth contract. They are GET-only and should
return 405 for POST/PUT/PATCH/DELETE unless Flask itself changes routing
behavior.

## /threat-intel — operations

### Normal operation

The Mac LaunchAgent `com.sapphire.threat-refresh` invokes
`services/dashboard/refresh_threats.py` every 4 hours. The script:

1. Resolves a `cyber-threat-bot` binary or the `native` fallback.
2. Pulls the latest CISA KEV feed, NVD CVE batch, MITRE ATT&CK index,
   and Dark Reading RSS.
3. Writes `data/intelligence/<YYYY-MM-DD>/threats.json` with
   `{refreshed_at, source_count, threats[]}`.
4. Updates the `data/intelligence/latest` symlink to point at the new
   dated directory.

The dashboard route then reads the symlink at request time. If the
symlink is missing or stale, the route falls back to the
lexicographically newest dated subdirectory containing
`threats.json` — so an operator running the refresher manually never
needs to coordinate with the dashboard.

### Diagnosing "no recent snapshot" on the page

1. `ls -lt data/intelligence/ | head -5` — confirm a recent dated dir.
2. `cat data/intelligence/latest/threats.json | jq '.refreshed_at, .source_count'`
   — confirm the JSON parses and the source count is >0.
3. `launchctl print gui/$(id -u)/com.sapphire.threat-refresh` — confirm
   the LaunchAgent is loaded and the last exit status was 0.
4. `tail -50 ~/Library/Logs/sapphire-threat-refresh.log` — the script
   logs to stderr; the LaunchAgent redirects to a logfile.

If `cyber-threat-bot` is missing or out-of-date, the script emits the
error to stderr and exits non-zero. The page will keep showing the
*previous* good snapshot until a fresh one lands.

### Manual refresh

```bash
# From the Sapphire repo root, no environment switching needed.
python3 services/dashboard/refresh_threats.py
```

Or, if the bot binary is unavailable:

```bash
SAPPHIRE_THREATS_BOT_BIN=native python3 services/dashboard/refresh_threats.py
```

### Smoke test for the page

```bash
# The dashboard must be running on :8080 with AUTH_PASSWORD set.
curl -sf -u "${AUTH_USERNAME:-sapphire}:${AUTH_PASSWORD}" \
  http://127.0.0.1:8080/api/threat-intel | jq '.available, .summary'
```

Expected: `available: true` and a non-zero `total_threats`. If the JSON
contains `available: false`, refer to the diagnosis steps above.

### Read-only contract verification

```bash
# All non-GET methods must return 405.
for m in POST PUT DELETE PATCH; do
  echo "$m: $(curl -s -o /dev/null -w '%{http_code}' -X $m -u "${AUTH_USERNAME:-sapphire}:${AUTH_PASSWORD}" http://127.0.0.1:8080/api/threat-intel)"
done
# Expected: every line ends with 405.
```

## /customer-dossier — operations

### Snapshot generation

The product page reads from `data/tho_intel/dossier_*.json`. To produce
a snapshot from the live `tho_intel` plugin tool:

```bash
echo '{"action":"report"}' \
  | python3 plugins/claw-sapphire/tools/tho_intel.py \
  | python3 -c '
import json, sys, datetime, pathlib
data = json.loads(sys.stdin.read())
out = pathlib.Path("data/tho_intel")
out.mkdir(parents=True, exist_ok=True)
fname = out / f"dossier_{datetime.date.today().isoformat()}.json"
fname.write_text(json.dumps({
  "snapshot_at": datetime.datetime.utcnow().isoformat() + "Z",
  "document_template_count": (data.get("market", {}) or {}).get("document_template_count", 0),
  "customers": [],   # pre-redacted summaries only
  "deals": [],       # pre-redacted summaries only
  "metadata": data.get("market", {}),
}))
print(f"wrote {fname}")
'
```

Running the redactor twice is harmless — the dashboard re-walks the
file with `redact_record()` on every read, so even if the operator
saves a partially-redacted file the page is still safe.

### Verifying the redaction contract before release

The mandatory pre-merge checklist:

1. `python3 -m pytest tests/unit/test_pii_redactor.py -x` — all 60+
   redactor cases pass.
2. `python3 -m pytest tests/unit/test_dashboard_customer_dossier.py -x`
   — all dashboard route cases pass, including the literal-token
   forbidden-list assertion (`test_api_customer_dossier_no_unredacted_pii_in_response`).
3. `ruff check .` — no new lint regressions.
4. Hand-verify with a deliberately dirty fixture:

```bash
mkdir -p /tmp/dossier-smoke && cat > /tmp/dossier-smoke/dossier_today.json <<'JSON'
{
  "snapshot_at": "2026-04-28T00:00:00Z",
  "customers": [
    {"customer_name": "Smoke Test", "phone": "555-123-4567",
     "email": "smoke@example.com", "address": "1 Test St, Houston, TX 77001",
     "ssn": "999-99-9999", "status": "ENROLLED"}
  ],
  "deals": []
}
JSON
# Redirect the dashboard's tho_intel dir for this run only.
SAPPHIRE_DOSSIER_DIR=/tmp/dossier-smoke python3 -c 'pass'  # placeholder
```

The unit tests cover the same shape — manual verification is a
secondary check, not the source of truth.

### Diagnosing empty state

If `/customer-dossier` shows the empty banner:

1. `ls data/tho_intel/dossier_*.json | head -3` — confirm at least
   one snapshot file exists.
2. `python3 -c 'import json; print(list(json.load(open("data/tho_intel/dossier_<latest>.json")).keys()))'`
   — confirm the JSON has at least the `customers` and `deals` keys.
3. Inspect `services/dashboard/app.py` log output (`stderr`) for any
   `customer-dossier API error: …` line.

### Auth troubleshooting

Both routes inherit `requires_auth`. The credentials are from the
dashboard's `AUTH_USERNAME` / `AUTH_PASSWORD` environment variables.
If the page returns 401:

```bash
# Confirm the password is set (do NOT echo it — print only its length).
python3 -c 'import os; print(len(os.environ["AUTH_PASSWORD"]))'
```

The dashboard refuses to start if `AUTH_PASSWORD` is empty or in the
weak-password list.

## /diligence — operations

The `/diligence` page is a buyer-facing aggregate. It does not run tests,
start services, read secret files, inspect plist environment variables, or call
external APIs. It composes small local summaries:

- `/api/diligence-summary` reads `docs/diligence/00-09`, extracts the title,
  first packet paragraph, first diligence-readout paragraph, and evidence list,
  then redacts local user paths and secret-shaped text.
- `/api/risk-kernel-summary` imports `lib.core.risk_kernel`, evaluates one safe
  sample and one blocked sample, and returns policy names, version, and headline
  thresholds from the live policy objects.
- `/api/provenance-summary` calls `scripts.ops.provenance_verify.build_report`
  in read-only mode and returns counts plus a capped invalid sample. It never
  writes sidecars.
- `/api/test-suite-health` reads source test files and `.pytest_cache` metadata
  when present. It does not read README counts and does not invoke pytest.
- `/api/launchagent-summary` reads version-controlled plist labels and
  `launchctl list` output only. It returns `label`, `status_label`, `pid`, and
  `last_exit`; it does not read plist secrets or call `launchctl load/unload`.

### Smoke test

```bash
curl -sf -u "${AUTH_USERNAME:-sapphire}:${AUTH_PASSWORD}" \
  http://127.0.0.1:8080/api/diligence-summary | jq '.status, .totals'
curl -sf -u "${AUTH_USERNAME:-sapphire}:${AUTH_PASSWORD}" \
  http://127.0.0.1:8080/api/risk-kernel-summary | jq '.status, .headline'
curl -sf -u "${AUTH_USERNAME:-sapphire}:${AUTH_PASSWORD}" \
  http://127.0.0.1:8080/api/launchagent-summary | jq '.totals'
```

Expected: diligence has 10 documents, risk kernel reports five default
policies, and LaunchAgent rows contain labels plus last-exit values.

### Diagnosing stale or sparse output

1. For missing packet rows, check `ls docs/diligence/0*.md`.
2. For provenance warnings, run
   `python3 scripts/ops/provenance_verify.py --older-than-hours 24 --pretty`.
3. For test health warnings, run the local verification gate, then refresh the
   page so `.pytest_cache` reflects the latest local result.
4. For LaunchAgent unknown status, run `launchctl list | grep sapphire` and
   inspect whether macOS denied the read-only query.

## /sovereign-thesis/story — operations

The story page is the narrative companion to `/sovereign-thesis`. It fetches
the existing `/api/investments/thesis` report and renders five fixed sections:
Thesis, Evidence, Convergence, Bear case, and Acquirer fit.

The page is intentionally research-only. It does not call order-draft routes,
Telegram routes, lease-write routes, or any POST endpoint. The source API
already carries the safety envelope for live trading and Telegram sends.

### Smoke test

```bash
curl -sf -u "${AUTH_USERNAME:-sapphire}:${AUTH_PASSWORD}" \
  http://127.0.0.1:8080/sovereign-thesis/story | grep -E "Thesis|Evidence|Convergence|Bear case|Acquirer fit"
curl -sf -u "${AUTH_USERNAME:-sapphire}:${AUTH_PASSWORD}" \
  http://127.0.0.1:8080/api/investments/thesis | jq '.mode, .totals'
```

Expected: all five story sections render, and the thesis API returns
`research_intel_only` mode with asset/evidence totals.

## Safety contract — what the routes guarantee

The `/threat-intel` and `/customer-dossier` routes ship with a `safety` block in
every response. The block is the load-bearing contract for downstream
consumers:

| Field | Meaning |
|---|---|
| `execution_enabled: false` | No tool execution is triggered by reading this page. |
| `live_trading_enabled: false` | No order placement, kill-switch toggle, or position adjustment. |
| `writes_by_default: false` | The route does not persist any state. |
| `telegram_sends_enabled: false` | No Telegram or notification side-effects. |
| `pii_redaction: "applied_to_every_leaf"` | (dossier only) Every leaf was passed through `redact_record()`. |
| `guards: [...]` | Free-text guards naming the controls actually applied. |

Consumers — including the page's own JavaScript — should treat the
absence of any field above as an error condition.

The `/diligence` and `/sovereign-thesis/story` surfaces rely on route-level
constraints instead: dashboard basic auth, GET-only methods, no write helpers,
sanitized summaries, and downstream APIs that are already read-only. Treat any
future POST, live send, LaunchAgent mutation, or test-running behavior on these
pages as a regression.

## Incident response

If you discover unredacted PII in `/customer-dossier`:

1. **Stop traffic**: `launchctl unload ~/Library/LaunchAgents/com.sapphire.dashboard.plist`
   (or the equivalent on the host running the dashboard).
2. **Capture evidence**: the response that leaked, plus the source
   snapshot file. Move both to `data/incident/$(date +%F)/` and
   restrict permissions.
3. **Add a regression test**: extend
   `tests/unit/test_dashboard_customer_dossier.py` with the leaked
   token in the forbidden list before fixing the redactor.
4. **Fix the redactor** in `lib/security/pii_redactor.py`. Run the
   full unit-test suite locally.
5. **Re-deploy**: reload the LaunchAgent only after CI is green.

## Related docs

* `docs/products/threat-intel-product-0.1.0.md`
* `docs/products/customer-dossier-product-0.1.0.md`
* `lib/security/pii_redactor.py` (module docstring)
* `services/dashboard/refresh_threats.py` (snapshot writer)
