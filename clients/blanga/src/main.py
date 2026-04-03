from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from bis.api import router as bis_router
from bis.auth import require_bis_auth
from bis.settings import get_settings
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="Blanga Intelligence System API",
    version="0.1.0-beta",
    description="Standalone BIS beta for Austin MSA STNL real estate workflows.",
)
app.include_router(bis_router)
settings = get_settings()


def _meta_payload() -> dict:
    return {
        "status": "ok",
        "product": "Blanga Intelligence System",
        "environment": settings.environment,
        "auth_required": settings.require_auth,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "api_prefix": "/api/bis",
    }


def _render_landing_html() -> str:
    auth_note = "Enabled" if settings.require_auth else "Disabled"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Blanga Intelligence System</title>
  <style>
    :root {{
      --bg: #f3f0e8;
      --ink: #1b1c1d;
      --muted: #5e646b;
      --card: #fffdf7;
      --line: #d8d0be;
      --accent: #0a6a66;
      --accent2: #9f3b18;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, ui-serif, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 10%, rgba(10,106,102,.10), transparent 45%),
        radial-gradient(circle at 90% 20%, rgba(159,59,24,.10), transparent 45%),
        var(--bg);
    }}
    .wrap {{ max-width: 1050px; margin: 0 auto; padding: 28px 18px 48px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(255,253,247,.95), rgba(245,239,225,.95));
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 10px 30px rgba(0,0,0,.06);
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; line-height: 1.05; }}
    p {{ margin: 0; color: var(--muted); line-height: 1.45; }}
    .grid {{
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }}
    .label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }}
    .value {{ font-size: 18px; margin-top: 6px; font-weight: 700; }}
    .actions {{ margin-top: 18px; display: flex; flex-wrap: wrap; gap: 10px; }}
    .btn {{
      display: inline-block;
      text-decoration: none;
      border-radius: 999px;
      padding: 10px 14px;
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      font-weight: 600;
    }}
    .btn.primary {{ background: var(--accent); color: white; border-color: var(--accent); }}
    .btn.alt {{ background: var(--accent2); color: white; border-color: var(--accent2); }}
    code {{
      background: #eee8da;
      padding: 2px 6px;
      border-radius: 6px;
      font-size: 12px;
    }}
    .note {{ margin-top: 14px; font-size: 14px; color: var(--muted); }}
    ul {{ margin: 10px 0 0 18px; color: var(--muted); }}
    li {{ margin: 4px 0; }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Blanga Intelligence System</h1>
      <p>Standalone beta for Austin MSA STNL and redevelopment workflows. This is the browser entrypoint; operational data lives under the BIS API and protected dashboard.</p>
      <div class="grid">
        <div class="card"><div class="label">Environment</div><div class="value">{escape(settings.environment)}</div></div>
        <div class="card"><div class="label">Auth</div><div class="value">{auth_note}</div></div>
        <div class="card"><div class="label">API Prefix</div><div class="value"><code>/api/bis</code></div></div>
      </div>
      <div class="actions">
        <a class="btn primary" href="/dashboard">Open Dashboard</a>
        <a class="btn" href="/docs">Open API Docs</a>
        <a class="btn alt" href="/api/bis/compliance/sources">Source Policy</a>
      </div>
      <div class="note">
        If auth is enabled, opening <code>/dashboard</code> or <code>/api/bis/*</code> will prompt for your BIS username/password.
        <ul>
          <li>Use <code>POST /api/bis/intake/drop</code> for new leads/listings</li>
          <li>Use <code>GET /api/bis/sheets/contract</code> and <code>POST /api/bis/sheets/import</code> for Sheets-first workflows</li>
          <li>Use <code>GET /api/bis/sheets/google/status</code>, <code>POST /api/bis/sheets/google/pull</code>, and <code>POST /api/bis/sheets/google/push</code> for live Google Sheets sync (when configured)</li>
          <li>Use <code>GET /api/bis/system/readiness</code> for a deployment checklist and concrete improvement recommendations</li>
          <li>Use <code>GET /api/bis/reviews</code> to approve note-derived field updates</li>
          <li>Use <code>POST /api/bis/reviews/auto-approve</code> to auto-approve high-confidence note/OM field suggestions with thresholds</li>
          <li>Use <code>GET /api/bis/system/backup/status</code> and <code>POST /api/bis/system/backup/save</code> for snapshots</li>
          <li>Use <code>POST /api/bis/automation/run</code> for manual automation test runs</li>
        </ul>
      </div>
    </section>
  </div>
</body>
</html>"""


def _render_dashboard_html() -> str:
    auth_label = "Off (public testing mode)" if not settings.require_auth else "On"
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BIS Operator Console</title>
  <style>
    :root {
      --bg: #f2eee3;
      --panel: #fffdf7;
      --ink: #202327;
      --muted: #66707a;
      --line: #d9d1c2;
      --brand: #0a6b67;
      --brand-2: #8b3a1a;
      --good: #1b7f4a;
      --warn: #b36c00;
      --bad: #b42318;
      --shadow: 0 10px 30px rgba(0,0,0,.06);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 8% 8%, rgba(10,107,103,.10), transparent 40%),
        radial-gradient(circle at 92% 12%, rgba(139,58,26,.10), transparent 40%),
        var(--bg);
      font-family: ui-sans-serif, system-ui, sans-serif;
    }
    .wrap { max-width: 1280px; margin: 0 auto; padding: 18px; }
    .hero {
      background: linear-gradient(135deg, rgba(255,255,255,.95), rgba(247,241,228,.96));
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: var(--shadow);
    }
    .hero-top { display:flex; gap:12px; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; }
    h1 { margin: 0; font-size: 26px; line-height: 1.1; }
    .sub { margin-top: 6px; color: var(--muted); max-width: 780px; }
    .chips { display:flex; flex-wrap:wrap; gap:8px; }
    .chip { background: #fff; border: 1px solid var(--line); border-radius: 999px; padding: 7px 10px; font-size: 12px; }
    .chip strong { color: var(--ink); }
    .hero-grid {
      display:grid;
      grid-template-columns: 1.1fr .9fr;
      gap: 12px;
      margin-top: 12px;
    }
    .hero-card {
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255,255,255,.78);
      padding: 12px;
    }
    .hero-card h2 { margin: 0 0 6px; font-size: 15px; }
    .hero-card p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.45; }
    .mini-steps {
      display:grid;
      gap:8px;
      margin-top:8px;
    }
    .mini-step {
      border:1px solid var(--line);
      border-radius:12px;
      background:#fff;
      padding:8px 10px;
      display:grid;
      grid-template-columns: 28px 1fr;
      gap:8px;
      align-items:start;
    }
    .mini-step .num {
      width: 28px;
      height: 28px;
      border-radius: 999px;
      background: var(--brand);
      color: #fff;
      display:grid;
      place-items:center;
      font-weight:700;
      font-size: 12px;
    }
    .mini-step .txt { font-size: 12px; color: var(--muted); line-height: 1.35; }
    .mini-step .txt strong { color: var(--ink); }
    .beta-note {
      margin-top: 8px;
      border-radius: 12px;
      padding: 10px;
      border: 1px dashed #c8bba0;
      background: #fffdf7;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.45;
    }
    .grid { display:grid; gap:12px; margin-top: 12px; }
    .stats { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
    .cards-2 { grid-template-columns: 1.1fr .9fr; }
    .cards-3 { grid-template-columns: repeat(3, minmax(0,1fr)); }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      box-shadow: var(--shadow);
    }
    .panel h2 { margin: 0 0 8px; font-size: 15px; }
    .panel > .tiny { line-height: 1.4; }
    .panel h3 { margin: 0 0 6px; font-size: 14px; }
    .stat { padding: 12px; border-radius: 12px; border: 1px solid var(--line); background: rgba(255,255,255,.8); }
    .stat .k { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
    .stat .v { font-size: 22px; font-weight: 700; margin-top: 6px; }
    .stat .s { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .actions { display:flex; flex-wrap:wrap; gap:8px; }
    button, .link-btn {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 10px;
      padding: 9px 12px;
      font-weight: 600;
      cursor: pointer;
      font-size: 13px;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    button.primary, .link-btn.primary { background: var(--brand); color: white; border-color: var(--brand); }
    button.alt, .link-btn.alt { background: var(--brand-2); color: white; border-color: var(--brand-2); }
    button:disabled { opacity: .6; cursor: not-allowed; }
    .tiny { font-size: 12px; color: var(--muted); }
    .workflow { margin: 0; padding-left: 18px; color: var(--muted); }
    .workflow li { margin: 6px 0; }
    .status-box {
      border-radius: 12px;
      padding: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.7);
    }
    .good { color: var(--good); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    .banner {
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid #e9d9ad;
      background: #fff8e7;
      color: #6c5315;
      font-size: 13px;
    }
    .notice-stack {
      display:grid;
      gap:8px;
      margin-top: 10px;
    }
    .notice {
      border-radius: 12px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      background: #fff;
      font-size: 13px;
      line-height: 1.4;
      display:flex;
      justify-content:space-between;
      gap:10px;
      align-items:flex-start;
    }
    .notice.info { border-color: #bfe3e1; background: #f3fbfa; }
    .notice.success { border-color: #b7e3c9; background: #eefbf3; }
    .notice.warn { border-color: #f4ddb0; background: #fff7e9; }
    .notice.error { border-color: #f0c4c1; background: #fff1f0; }
    .notice button {
      padding: 4px 8px;
      font-size: 12px;
      border-radius: 8px;
    }
    .tour-box {
      margin-top: 10px;
      border-radius: 14px;
      border: 1px solid #cfe4e2;
      background: linear-gradient(135deg, rgba(10,107,103,.08), rgba(255,255,255,.85));
      padding: 12px;
    }
    .tour-head { display:flex; justify-content:space-between; gap:8px; align-items:center; flex-wrap:wrap; }
    .tour-title { font-weight: 700; font-size: 14px; }
    .tour-body { margin-top: 8px; font-size: 13px; color: var(--muted); line-height: 1.45; }
    .tour-actions { margin-top: 10px; display:flex; flex-wrap:wrap; gap:8px; }
    .tour-chip {
      border-radius: 999px;
      padding: 4px 8px;
      border: 1px solid var(--line);
      background: #fff;
      font-size: 12px;
    }
    .tour-active {
      box-shadow: 0 0 0 3px rgba(10,107,103,.18), var(--shadow);
      border-color: #97d2cd !important;
      scroll-margin-top: 12px;
    }
    .layout {
      display:grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 12px;
      margin-top: 12px;
      align-items: start;
    }
    .stack { display:grid; gap:12px; }
    .form-grid { display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:10px; }
    .form-grid .full { grid-column: 1 / -1; }
    label { display:block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
    input, select, textarea {
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--line);
      padding: 10px;
      font: inherit;
      background: white;
    }
    textarea { min-height: 88px; resize: vertical; }
    table { width:100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align:left; border-bottom: 1px solid var(--line); padding: 8px 6px; vertical-align: top; }
    th { color: var(--muted); font-size: 12px; font-weight: 600; }
    .badge {
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 11px;
      border: 1px solid var(--line);
      background: white;
      display: inline-block;
      white-space: nowrap;
    }
    .badge.good { border-color: #b7e3c9; background: #eefbf3; color: #146c43; }
    .badge.warn { border-color: #f4ddb0; background: #fff7e9; color: #8a5a00; }
    .badge.bad { border-color: #f0c4c1; background: #fff1f0; color: #a1221a; }
    .actions-cell { display:flex; flex-wrap:wrap; gap:6px; }
    .small-btn { padding: 5px 8px; font-size: 12px; border-radius: 8px; }
    .priority-pill { border-radius: 999px; padding: 3px 8px; font-size: 11px; font-weight: 700; background: #fff; border: 1px solid var(--line); }
    .muted { color: var(--muted); }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .log {
      background: #171a1d;
      color: #d2f6ec;
      border-radius: 12px;
      padding: 10px;
      min-height: 130px;
      max-height: 240px;
      overflow: auto;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      line-height: 1.45;
    }
    .footer {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
      display:flex;
      flex-wrap:wrap;
      gap:10px;
    }
    details { border:1px solid var(--line); border-radius:12px; padding: 8px 10px; background: #fff; }
    summary { cursor:pointer; font-weight: 600; }
    .inline-help { margin-top: 8px; padding: 8px 10px; border-radius: 10px; background: #f7f4eb; border: 1px solid var(--line); font-size: 12px; color: var(--muted); }
    .soft { background: rgba(255,255,255,.65); }
    @media (max-width: 980px) {
      .layout, .cards-2, .cards-3 { grid-template-columns: 1fr; }
      .hero-grid { grid-template-columns: 1fr; }
      .form-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-top">
        <div>
          <h1>Blanga Intelligence System: Operator Console</h1>
          <div class="sub">Built for day-to-day brokerage use. Use the forms and buttons below. You do not need to know the API.</div>
        </div>
        <div class="chips">
          <div class="chip"><strong>Environment:</strong> __ENV__</div>
          <div class="chip"><strong>Auth:</strong> __AUTH__</div>
          <div class="chip"><strong>Mode:</strong> Guided Console</div>
        </div>
      </div>
      <div class="banner">
        Start here: add a property note, review suggested updates, run daily refresh, then save a backup. Extra tools like market events, comp search saving, and activity history are available below when needed.
      </div>
      <div class="inline-help">
        Suggested daily use: <strong>1) Intake</strong> -> <strong>2) Review Suggestions</strong> -> <strong>3) Run Daily Refresh</strong> -> <strong>4) Backup</strong>. Everything else is optional support tooling.
      </div>
      <div class="notice-stack" id="noticeStack"></div>
      <div class="tour-box" id="tourBox">
        <div class="tour-head">
          <div>
            <div class="tour-title">Guided Tour (Beginner)</div>
            <div class="tiny">Use this once to learn the beta workflow. You can restart anytime.</div>
          </div>
          <div class="tour-chip" id="tourProgressChip">Not started</div>
        </div>
        <div class="tour-body" id="tourBody">
          Start the tour to get step-by-step guidance on how to use BIS as a first-time beta tester.
        </div>
        <div class="tour-actions">
          <button id="tourStartBtn" class="primary">Start Tour</button>
          <button id="tourNextBtn">Next Step</button>
          <button id="tourSkipBtn">Hide Tour</button>
          <button id="tourResetBtn">Reset Tour</button>
        </div>
      </div>
      <div class="hero-grid">
        <div class="hero-card">
          <h2>What This System Is</h2>
          <p>
            BIS (Blanga Intelligence System) is a brokerage assistant for organizing property/owner information, turning notes into suggested record updates, tracking market events, and helping decide what to work on next.
          </p>
          <div class="beta-note">
            It is a <strong>beta</strong>. That means it is useful for testing real workflows, but you should still review important changes before relying on them.
          </div>
        </div>
        <div class="hero-card">
          <h2>Beginner Guide (How To Use It)</h2>
          <div class="mini-steps">
            <div class="mini-step">
              <div class="num">1</div>
              <div class="txt"><strong>Add a property note</strong><br>Use Step 1 with address + owner + note. BIS will create suggestions from what you type.</div>
            </div>
            <div class="mini-step">
              <div class="num">2</div>
              <div class="txt"><strong>Review suggested updates</strong><br>Approve obvious items (for example vacancy). Reject anything uncertain.</div>
            </div>
            <div class="mini-step">
              <div class="num">3</div>
              <div class="txt"><strong>Use Today’s Tasks</strong><br>Let BIS suggest who/what to follow up on today and why.</div>
            </div>
            <div class="mini-step">
              <div class="num">4</div>
              <div class="txt"><strong>Run Daily Refresh + Backup</strong><br>Generate summaries/alerts, then save a backup snapshot.</div>
            </div>
          </div>
        </div>
      </div>
      <div class="grid stats" id="statsGrid">
        <div class="stat"><div class="k">Loading</div><div class="v">...</div><div class="s">Pulling BIS overview</div></div>
      </div>
    </section>

    <section class="panel" style="margin-top:12px;">
      <h2>Beta Tester Notes (What To Try)</h2>
      <div class="tiny">
        Try these workflows and note what feels confusing or slow:
      </div>
      <ol class="workflow" style="margin-top:8px;">
        <li>Add a note that includes "tenant vacated" and see if BIS creates a vacancy suggestion.</li>
        <li>Approve a suggestion and confirm the property tracker updates.</li>
        <li>Use Today’s Tasks and mark one task done or snoozed.</li>
        <li>Run a comp search, then save it and re-run it from Saved Comp Searches.</li>
        <li>Record a market event (listed/sold/news) and confirm it shows in Recent Documents / Events.</li>
      </ol>
      <div class="inline-help">
        Feedback to share during beta: <strong>What was easy?</strong> <strong>What was confusing?</strong> <strong>What took too many clicks?</strong> <strong>What info did you expect but not see?</strong>
      </div>
    </section>

    <div class="layout">
      <div class="stack">
        <section class="panel" id="tour-step-intake">
          <h2>Step 1: Add Property Note</h2>
          <div class="tiny">Fastest way to use BIS. Add address + owner + note. BIS will read your note and suggest updates (like vacancy or lease timing) for you to review.</div>
          <form id="intakeForm" style="margin-top:10px;">
            <div class="form-grid">
              <div>
                <label>Property Address *</label>
                <input name="address_line1" placeholder="7809 S 1st St" required />
              </div>
              <div>
                <label>Owner Name *</label>
                <input name="owner_name" placeholder="John Smith" required />
              </div>
              <div>
                <label>City</label>
                <input name="city" value="Austin" />
              </div>
              <div>
                <label>County</label>
                <select name="county">
                  <option>Travis</option>
                  <option>Williamson</option>
                  <option>Hays</option>
                  <option>Bastrop</option>
                  <option>Caldwell</option>
                </select>
              </div>
              <div>
                <label>Tenant (optional, if known)</label>
                <input name="tenant_brand" placeholder="Walgreens / Vacant / Local tenant" />
              </div>
              <div>
                <label>Listing Status</label>
                <select name="listing_status">
                  <option value="">No Change</option>
                  <option value="listed">Listed</option>
                  <option value="under_contract">Under Contract</option>
                  <option value="sold">Sold</option>
                  <option value="off_market">Off Market</option>
                </select>
              </div>
              <div>
                <label>Asking Price (optional)</label>
                <input name="asking_price" type="number" step="0.01" placeholder="5000000" />
              </div>
              <div>
                <label>Occupancy (optional)</label>
                <select name="occupancy_status">
                  <option value="">No Change</option>
                  <option value="vacant">Vacant</option>
                  <option value="leased">Leased</option>
                </select>
              </div>
              <div class="full">
                <label>Owner / Property Note (recommended - this is where BIS learns)</label>
                <textarea name="note_text" placeholder="Examples: Tenant vacated. Owner says 8 years left on lease. Wants to revisit numbers in Q2."></textarea>
              </div>
            </div>
            <div class="actions" style="margin-top:10px;">
              <button type="submit" class="primary">Save Note / Property</button>
              <button type="button" id="seedBtn">Load Demo Data</button>
              <button type="button" id="refreshBtn">Refresh Dashboard</button>
            </div>
          </form>
        </section>

        <section class="panel" id="tour-step-review">
          <h2>Step 2: Review Suggested Updates</h2>
          <div class="tiny">BIS does not silently overwrite important fields. Review suggestions here. Approve clear items and reject anything uncertain.</div>
          <div class="actions" style="margin:8px 0 10px;">
            <button id="autoApproveVacancyBtn">Auto-Approve Vacancy Only</button>
            <button id="autoApproveVacancyDryBtn">Preview Auto-Approve</button>
          </div>
          <div style="overflow:auto;">
            <table>
              <thead>
                <tr><th>Field</th><th>Suggested Value</th><th>Confidence</th><th>Source</th><th>Actions</th></tr>
              </thead>
              <tbody id="reviewTableBody">
                <tr><td colspan="5" class="muted">Loading review tasks...</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel" id="tour-step-next-actions">
          <h2>Step 3: Today’s Tasks (Next Best Actions)</h2>
          <div class="tiny">This is your daily call/decision list. BIS ranks items by urgency using pending reviews, vacancy flags, listing age, and recent market events.</div>
          <div class="actions" style="margin:8px 0 10px;">
            <button id="refreshNextActionsBtn">Refresh Tasks</button>
          </div>
          <div style="overflow:auto;">
            <table>
              <thead>
                <tr><th>Priority</th><th>Task</th><th>Why BIS flagged it</th><th>Actions</th></tr>
              </thead>
              <tbody id="nextActionsTableBody">
                <tr><td colspan="4" class="muted">Loading tasks...</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel" id="tour-step-refresh">
          <h2>Step 4: Property Tracker (Recent Records)</h2>
          <div class="tiny">Use this to confirm BIS updates (status, days on market, pricing, occupancy, and outreach state).</div>
          <details class="soft" style="margin-top:8px;">
            <summary>Show property table</summary>
            <div style="overflow:auto; margin-top:8px;">
            <table>
              <thead>
                <tr><th>Address</th><th>Status</th><th>DOM</th><th>Tenant / Occupancy</th><th>Price Metrics</th><th>Outreach</th></tr>
              </thead>
            <tbody id="propertyTableBody">
              <tr><td colspan="6" class="muted">Loading properties...</td></tr>
            </tbody>
            </table>
            </div>
          </div>
          </details>
        </section>

        <section class="panel" id="tour-step-comps">
          <h2>Optional: Record Market Event (Listed / Sold / News)</h2>
          <div class="tiny">Use this when you hear something in the market and want it tracked. This is optional and can be filled out later.</div>
          <details class="soft" style="margin-top:8px;">
            <summary>Open market event form</summary>
            <form id="marketEventForm" style="margin-top:10px;">
            <div class="form-grid">
              <div>
                <label>Event Type *</label>
                <select name="event_type" required>
                  <option value="listed">Listed</option>
                  <option value="sold">Sold</option>
                  <option value="client_news">Client News</option>
                  <option value="industry_news">Industry News</option>
                  <option value="new_company">New Company</option>
                </select>
              </div>
              <div>
                <label>Title *</label>
                <input name="title" placeholder="Example: Tenant vacated former QSR building" required />
              </div>
              <div class="full">
                <label>Property Address (recommended)</label>
                <input name="property_address_hint" placeholder="7809 S 1st St" />
              </div>
              <div>
                <label>Owner Name (optional)</label>
                <input name="owner_name_hint" placeholder="Owner / contact name" />
              </div>
              <div>
                <label>Company Name (optional)</label>
                <input name="company_name" placeholder="Tenant / brand / company" />
              </div>
              <div>
                <label>List Price (if listed)</label>
                <input name="list_price" type="number" step="0.01" placeholder="5000000" />
              </div>
              <div>
                <label>Close Price (if sold)</label>
                <input name="close_price" type="number" step="0.01" placeholder="4850000" />
              </div>
              <div class="full">
                <label>Summary / Notes</label>
                <textarea name="summary" placeholder="Where you heard it, why it matters, tenant vacated / motivation details, etc."></textarea>
              </div>
              <div class="full">
                <label>Source URL (optional)</label>
                <input name="source_url" placeholder="https://..." />
              </div>
            </div>
            <div class="actions" style="margin-top:10px;">
              <button type="submit">Save Market Event</button>
            </div>
            </form>
          </details>
        </section>
      </div>

      <div class="stack">
        <section class="panel">
          <h2>Today’s Workflow</h2>
          <ol class="workflow" id="workflowList">
            <li>Loading checklist...</li>
          </ol>
          <div class="actions">
            <button id="runDailyRefreshBtn" class="primary">Run Daily Refresh (Safe)</button>
            <button id="saveBackupBtn">Save Backup</button>
            <button id="readinessBtn">Refresh Status</button>
          </div>
        </section>

        <section class="panel">
          <h2>System Status (Only check if something seems off)</h2>
          <div class="status-box">
            <div><strong>Readiness Score:</strong> <span id="readinessScore">...</span></div>
            <div class="tiny" id="readinessSummary">Loading readiness...</div>
          </div>
          <details class="soft" style="margin-top:8px;">
            <summary>Open setup checks and recommendations</summary>
            <div style="margin-top:8px;" id="recommendationsBox" class="tiny muted">Loading recommendations...</div>
            <div style="margin-top:10px;" class="grid">
            <div class="status-box">
              <div><strong>Google Sheets</strong></div>
              <div class="tiny" id="sheetsStatusLine">Loading...</div>
              <div class="actions" style="margin-top:8px;">
                <button id="sheetsStatusBtn" class="small-btn">Check Sheets Status</button>
                <button id="sheetsPullBtn" class="small-btn">Pull Sheet Now</button>
                <button id="sheetsPushBtn" class="small-btn">Push Writeback</button>
              </div>
            </div>
            <div class="status-box">
              <div><strong>Backups</strong></div>
              <div class="tiny" id="backupStatusLine">Loading...</div>
              <div class="actions" style="margin-top:8px;">
                <button id="backupStatusBtn" class="small-btn">Refresh Backup Status</button>
                <button id="backupSaveBtn2" class="small-btn">Save Backup Now</button>
              </div>
            </div>
            </div>
          </details>
        </section>

        <section class="panel">
          <h2>Client Source Coverage (Beta)</h2>
          <div class="tiny">These are the sources BIS is configured to use for local news and permit signals based on client feedback. This makes the intake scope visible and reviewable.</div>
          <details class="soft" style="margin-top:8px;">
            <summary>Show local news and permit source coverage</summary>
            <div id="clientSourceCoverageBox" style="margin-top:8px;" class="tiny muted">Loading source coverage...</div>
          </details>
        </section>

        <section class="panel">
          <h2>Recent Documents / Events</h2>
          <div class="tiny">Quick reference. Useful if you want to confirm BIS generated summaries or captured recent events.</div>
          <details class="soft" style="margin-top:8px;">
            <summary>Show recent documents and events</summary>
            <div id="recentDocsBox" style="margin-top:8px;" class="tiny muted">Loading...</div>
            <div id="recentEventsBox" style="margin-top:8px;" class="tiny muted">Loading...</div>
          </details>
        </section>

        <section class="panel">
          <h2>Comps Finder</h2>
          <div class="tiny">Use this during pricing conversations. Start broad first (city/county), then tighten filters (cap rate, occupancy, pricing metrics) if you get too many results.</div>
          <form id="compsForm" style="margin-top:10px;">
            <div class="form-grid">
              <div>
                <label>City</label>
                <input name="city" value="Austin" />
              </div>
              <div>
                <label>County</label>
                <select name="county">
                  <option value="">Any</option>
                  <option>Travis</option>
                  <option>Williamson</option>
                  <option>Hays</option>
                  <option>Bastrop</option>
                  <option>Caldwell</option>
                </select>
              </div>
              <div>
                <label>Tenant Brand (optional)</label>
                <input name="tenant_brand" placeholder="Walgreens / Starbucks / etc." />
              </div>
              <div>
                <label>Submarket / Corridor (optional)</label>
                <input name="submarket" placeholder="South Austin / Round Rock / etc." />
              </div>
              <div>
                <label>Max Land $/SF (optional)</label>
                <input name="max_land_psf" type="number" step="0.01" placeholder="100" />
              </div>
              <div>
                <label>Max Building $/SF (optional)</label>
                <input name="max_building_psf" type="number" step="0.01" placeholder="250" />
              </div>
              <div>
                <label>Max Building SF (optional)</label>
                <input name="max_building_sqft" type="number" step="1" min="1" placeholder="15000" />
              </div>
              <div>
                <label>Occupancy (optional)</label>
                <select name="occupancy_status">
                  <option value="">Any</option>
                  <option value="leased">Leased</option>
                  <option value="vacant">Vacant</option>
                </select>
              </div>
              <div>
                <label>Min Cap Rate (optional)</label>
                <input name="min_cap_rate" type="number" step="0.01" placeholder="5.5" />
              </div>
              <div>
                <label>Max Cap Rate (optional)</label>
                <input name="max_cap_rate" type="number" step="0.01" placeholder="7.5" />
              </div>
              <div>
                <label>Lease Expiring Within (years)</label>
                <input name="lease_expiring_within_years" type="number" step="1" min="1" placeholder="4" />
              </div>
            </div>
            <div class="actions" style="margin-top:10px;">
              <button type="submit" class="alt">Run Comp Search</button>
            </div>
          </form>
          <div id="compsSummaryBox" style="margin-top:10px;" class="tiny muted">No comp search run yet.</div>
          <div class="actions" style="margin-top:8px;">
            <button id="saveCurrentCompSearchBtn" class="small-btn">Save This Search</button>
            <button id="refreshSavedCompSearchesBtn" class="small-btn">Refresh Saved List</button>
          </div>
          <details class="soft" style="margin-top:8px;" open>
            <summary>Show comp results table</summary>
            <div style="overflow:auto; margin-top:8px;">
            <table>
              <thead>
                <tr><th>Address</th><th>Status</th><th>DOM</th><th>Land $/SF</th><th>Bldg $/SF</th><th>Cap</th></tr>
              </thead>
              <tbody id="compsTableBody">
                <tr><td colspan="6" class="muted">Run a comp search to see results.</td></tr>
              </tbody>
            </table>
            </div>
          </details>
        </section>

        <section class="panel">
          <h2>Saved Comp Searches</h2>
          <div class="tiny">Optional convenience tool. Save comp filters you use often so you can rerun them quickly.</div>
          <details class="soft" style="margin-top:8px;">
            <summary>Show saved comp searches</summary>
            <div style="overflow:auto; margin-top:8px;">
            <table>
              <thead>
                <tr><th>Name</th><th>Filters</th><th>Updated</th><th>Actions</th></tr>
              </thead>
              <tbody id="savedCompsTableBody">
                <tr><td colspan="4" class="muted">No saved searches yet.</td></tr>
              </tbody>
            </table>
            </div>
          </details>
        </section>

        <section class="panel">
          <h2>Recent Activity (What BIS Did)</h2>
          <div class="tiny">Use this when you want to understand what changed and why. This is the trust/history view.</div>
          <details class="soft" style="margin-top:8px;">
            <summary>Show activity timeline</summary>
            <div style="overflow:auto; margin-top:8px;">
            <table>
              <thead>
                <tr><th>Time</th><th>Action</th><th>What Happened</th></tr>
              </thead>
              <tbody id="auditTimelineBody">
                <tr><td colspan="3" class="muted">Loading activity...</td></tr>
              </tbody>
            </table>
            </div>
          </details>
        </section>

        <section class="panel">
          <h2>Session Log (Technical)</h2>
          <div class="tiny">Usually safe to ignore. This shows button clicks and errors for this browser session only.</div>
          <details class="soft" style="margin-top:8px;">
            <summary>Show session log</summary>
            <div id="actionLog" class="log" style="margin-top:8px;">BIS console ready. Loading data...\n</div>
          </details>
          <details style="margin-top:8px;">
            <summary>Advanced Links (for technical support)</summary>
            <div class="actions" style="margin-top:8px;">
              <a class="link-btn" href="/docs">API Docs</a>
              <a class="link-btn" href="/api/bis/system/readiness" target="_blank">Readiness JSON</a>
              <a class="link-btn" href="/api/bis/sheets/google/status" target="_blank">Sheets Status JSON</a>
              <a class="link-btn" href="/api/bis/system/backup/status" target="_blank">Backup Status JSON</a>
            </div>
          </details>
        </section>
      </div>
    </div>

    <div class="footer">
      <div>Tip: If the system is open for testing, anyone with the URL can use it.</div>
      <div>When testing is done, turn auth back on.</div>
      <div class="mono">/api/bis/ui/overview</div>
    </div>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    const state = {
      overview: null,
      lastCompsPayload: null,
      lastCompsResult: null,
      notices: [],
      tourHidden: false,
      tourStepIndex: -1
    };
    const TOUR_STEPS = [
      {
        id: "tour-step-intake",
        title: "Step 1: Add a property note",
        body: "Start here. Enter an address, owner, and a note. Try adding language like 'tenant vacated' so BIS can create a suggested update."
      },
      {
        id: "tour-step-review",
        title: "Step 2: Review suggested updates",
        body: "Check what BIS extracted from your notes. Approve obvious items and reject anything unclear."
      },
      {
        id: "tour-step-next-actions",
        title: "Step 3: Use Today’s Tasks",
        body: "This is your daily action list. BIS ranks follow-ups based on urgency (vacancy, stale listing, pending review, recent market intel)."
      },
      {
        id: "tour-step-refresh",
        title: "Step 4: Run Daily Refresh + Backup",
        body: "Run Daily Refresh to generate summaries and alerts, then save a backup snapshot to preserve your session data."
      },
      {
        id: "tour-step-comps",
        title: "Step 5: Run a comp search",
        body: "Use Comps Finder during pricing conversations. Start broad, then refine filters. Save useful searches for later reuse."
      }
    ];

    function logLine(message, tone = "info") {
      const box = el("actionLog");
      const stamp = new Date().toLocaleTimeString();
      const prefix = tone === "error" ? "[ERROR]" : tone === "warn" ? "[WARN]" : "[OK]";
      box.textContent += `${stamp} ${prefix} ${message}\\n`;
      box.scrollTop = box.scrollHeight;
    }

    function pushNotice(message, tone = "info") {
      const item = {
        id: `${Date.now()}-${Math.random().toString(16).slice(2,8)}`,
        tone,
        message
      };
      state.notices.unshift(item);
      state.notices = state.notices.slice(0, 5);
      renderNotices();
      return item.id;
    }

    function dismissNotice(id) {
      state.notices = state.notices.filter(n => n.id !== id);
      renderNotices();
    }
    window.dismissNotice = dismissNotice;

    function renderNotices() {
      const box = el("noticeStack");
      if (!box) return;
      if (!state.notices.length) {
        box.innerHTML = "";
        return;
      }
      box.innerHTML = state.notices.map((n) => `
        <div class="notice ${n.tone}">
          <div>${n.message}</div>
          <button onclick="dismissNotice('${n.id}')">Dismiss</button>
        </div>
      `).join("");
    }

    function clearTourHighlights() {
      for (const step of TOUR_STEPS) {
        const node = el(step.id);
        if (node) node.classList.remove("tour-active");
      }
    }

    function renderTour() {
      const box = el("tourBox");
      const body = el("tourBody");
      const chip = el("tourProgressChip");
      if (!box || !body || !chip) return;
      if (state.tourHidden) {
        box.style.display = "none";
        clearTourHighlights();
        return;
      }
      box.style.display = "block";
      clearTourHighlights();
      if (state.tourStepIndex < 0) {
        chip.textContent = "Not started";
        body.textContent = "Start the tour to get step-by-step guidance on how to use BIS as a first-time beta tester.";
        return;
      }
      const idx = Math.min(state.tourStepIndex, TOUR_STEPS.length - 1);
      const step = TOUR_STEPS[idx];
      chip.textContent = `Step ${idx + 1} of ${TOUR_STEPS.length}`;
      body.innerHTML = `<strong>${step.title}</strong><br>${step.body}`;
      const node = el(step.id);
      if (node) {
        node.classList.add("tour-active");
        node.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }

    function startTour() {
      state.tourHidden = false;
      state.tourStepIndex = 0;
      renderTour();
      pushNotice("Tour started. Follow the highlighted section.", "info");
    }

    function nextTourStep() {
      state.tourHidden = false;
      if (state.tourStepIndex < 0) {
        state.tourStepIndex = 0;
      } else if (state.tourStepIndex < TOUR_STEPS.length - 1) {
        state.tourStepIndex += 1;
      } else {
        pushNotice("Tour complete. You can reset and run it again anytime.", "success");
      }
      renderTour();
    }

    function resetTour() {
      state.tourHidden = false;
      state.tourStepIndex = -1;
      renderTour();
      pushNotice("Tour reset.", "info");
    }

    function hideTour() {
      state.tourHidden = true;
      renderTour();
    }

    function money(v) {
      if (v === null || v === undefined || v === "") return "n/a";
      const n = Number(v);
      if (Number.isNaN(n)) return String(v);
      return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
    }

    function pct(v) {
      if (v === null || v === undefined || v === "") return "n/a";
      const n = Number(v);
      if (Number.isNaN(n)) return String(v);
      return `${n.toFixed(2)}%`;
    }

    function shortIso(v) {
      if (!v) return "n/a";
      try {
        return new Date(v).toLocaleString();
      } catch {
        return String(v);
      }
    }

    async function api(path, options = {}) {
      const res = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
      });
      const text = await res.text();
      let data;
      try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
      if (!res.ok) {
        const detail = data?.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : (data?.raw || res.statusText);
        throw new Error(`${res.status} ${detail}`);
      }
      return data;
    }

    function statusBadge(text) {
      const raw = String(text || "n/a");
      const low = raw.toLowerCase();
      let cls = "";
      if (["sold", "approved", "active", "ready", "ok", "vacant"].includes(low)) cls = "good";
      else if (["listed", "pending", "warning", "under_contract"].includes(low)) cls = "warn";
      else if (["rejected", "paused", "error", "failed"].includes(low)) cls = "bad";
      return `<span class="badge ${cls}">${raw}</span>`;
    }

    function renderStats(overview) {
      const c = overview.counts || {};
      const readiness = overview.readiness || {};
      el("statsGrid").innerHTML = `
        <div class="stat"><div class="k">Properties</div><div class="v">${c.properties ?? 0}</div><div class="s">Tracked assets</div></div>
        <div class="stat"><div class="k">Pending Reviews</div><div class="v">${c.pending_reviews ?? 0}</div><div class="s">Suggested field updates</div></div>
        <div class="stat"><div class="k">Documents</div><div class="v">${c.documents ?? 0}</div><div class="s">Call briefs + summaries</div></div>
        <div class="stat"><div class="k">Events (30d)</div><div class="v">${c.market_events_30d ?? 0}</div><div class="s">Market signals/news</div></div>
        <div class="stat"><div class="k">Readiness</div><div class="v">${readiness.ready_score ?? 0}/${readiness.ready_total ?? 0}</div><div class="s">Setup health</div></div>
        <div class="stat"><div class="k">People</div><div class="v">${c.people ?? 0}</div><div class="s">Owners/contacts</div></div>
      `;
    }

    function renderWorkflow(overview) {
      const items = overview.beginner_workflow || [];
      el("workflowList").innerHTML = items.map((line) => `<li>${line}</li>`).join("") || "<li>No workflow guidance returned.</li>";
    }

    function renderReadiness(overview) {
      const readiness = overview.readiness || {};
      const score = `${readiness.ready_score ?? 0}/${readiness.ready_total ?? 0}`;
      el("readinessScore").textContent = score;
      const checks = readiness.checks || [];
      const ok = checks.filter(c => c.ok).length;
      el("readinessSummary").textContent = `${ok} checks passing. ${checks.length - ok} need attention.`;
      const recs = readiness.recommendations || [];
      el("recommendationsBox").innerHTML = recs.length
        ? `<ul class="workflow">${recs.map((r) => `<li>${r}</li>`).join("")}</ul>`
        : `<span class="good">No urgent setup issues found.</span>`;

      const gSheets = readiness.google_sheets_status || {};
      el("sheetsStatusLine").innerHTML = gSheets.auth_ok
        ? `Connected to Google APIs (${gSheets.project_id || "project unknown"}). ${recs.some(r => r.includes("SPREADSHEET_ID")) ? "Spreadsheet ID still needs to be set." : ""}`
        : `<span class="bad">Not ready:</span> ${gSheets.error || "Google Sheets auth failed."}`;

      const b = readiness.snapshot_status || {};
      const g = b.gcs || {};
      const local = b.snapshot_exists ? "local snapshot present" : "no local snapshot yet";
      const gcsText = g.configured ? (g.exists ? "GCS snapshot present" : "GCS configured; no snapshot file yet") : "GCS snapshot bucket not configured";
      el("backupStatusLine").textContent = `${local}. ${gcsText}.`;
    }

    function renderReviews(overview) {
      const rows = overview.pending_reviews || [];
      const tbody = el("reviewTableBody");
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="muted">No pending review tasks right now.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map((r) => {
        const obs = r.observation || {};
        return `
          <tr>
            <td>${r.field_name || "-"}</td>
            <td><div>${obs.proposed_value || "-"}</div><div class="tiny muted">${r.entity_urn || ""}</div></td>
            <td>${typeof obs.confidence === "number" ? obs.confidence.toFixed(2) : "n/a"}</td>
            <td><div>${obs.source_type || "-"}</div><div class="tiny muted mono">${obs.source_ref || ""}</div></td>
            <td>
              <div class="actions-cell">
                <button class="small-btn" onclick="approveReview('${r.review_urn}')">Approve</button>
                <button class="small-btn" onclick="rejectReview('${r.review_urn}')">Reject</button>
              </div>
            </td>
          </tr>
        `;
      }).join("");
    }

    function renderNextActions(overview) {
      const rows = overview.next_actions || [];
      const tbody = el("nextActionsTableBody");
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="muted">No next actions right now. Add notes/events or run daily refresh.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map((a) => {
        const priority = Number(a.priority_score || 0);
        const priClass = priority >= 90 ? "bad" : priority >= 75 ? "warn" : "good";
        const location = a.property_address || a.entity_urn || "";
        const meta = a.metadata || {};
        const reviewAction = a.review_urn
          ? `<button class="small-btn" onclick="approveReview('${a.review_urn}')">Approve</button>`
          : "";
        return `
          <tr>
            <td><span class="priority-pill ${priClass}">${priority}</span></td>
            <td>
              <div><strong>${a.title || "Task"}</strong></div>
              <div class="tiny muted">${location}</div>
              <div class="tiny muted">${a.recommended_action || ""}</div>
            </td>
            <td>
              <div>${a.reason || ""}</div>
              <div class="tiny muted">${Object.keys(meta).length ? Object.entries(meta).slice(0,3).map(([k,v]) => `${k}: ${v}`).join(" | ") : ""}</div>
            </td>
            <td>
              <div class="actions-cell">
                ${reviewAction}
                <button class="small-btn" onclick="logNextAction('${a.action_urn}','done')">Done</button>
                <button class="small-btn" onclick="logNextAction('${a.action_urn}','snoozed')">Snooze</button>
              </div>
            </td>
          </tr>
        `;
      }).join("");
    }

    function renderProperties(overview) {
      const rows = overview.recent_properties || [];
      const tbody = el("propertyTableBody");
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="muted">No properties yet. Use the intake form above.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map((p) => {
        const tenantOrOcc = p.tenant_brand ? `${p.tenant_brand}` : (p.occupancy_status ? p.occupancy_status : "n/a");
        const priceMetrics = `Bldg: ${p.sale_price_per_building_sf ? money(p.sale_price_per_building_sf).replace('.00','') + '/SF' : 'n/a'}<br>Land: ${p.sale_price_per_land_sf ? money(p.sale_price_per_land_sf).replace('.00','') + '/SF' : 'n/a'}`;
        return `
          <tr>
            <td>
              <div>${p.address_line1 || "-"}</div>
              <div class="tiny muted">${p.city || ""}, ${p.county || ""}</div>
            </td>
            <td>${statusBadge(p.listing_status || "n/a")}</td>
            <td>${p.days_on_market ?? "n/a"}</td>
            <td>
              <div>${tenantOrOcc}</div>
              <div class="tiny muted">Occupancy: ${p.occupancy_status || "unknown"}</div>
            </td>
            <td class="tiny">${priceMetrics}</td>
            <td>
              ${statusBadge(p.outreach_state || "n/a")}
              <div class="tiny muted">Redo: ${p.redo ? "Yes" : "No"} | Potential: ${p.potential_listing ? "Yes" : "No"}</div>
            </td>
          </tr>
        `;
      }).join("");
    }

    function renderRecentBoxes(overview) {
      const docs = overview.recent_documents || [];
      const events = overview.recent_events || [];
      el("recentDocsBox").innerHTML = docs.length
        ? docs.slice(0, 5).map(d => `<div><strong>${d.doc_type}</strong>: ${d.title} <span class="muted">(${shortIso(d.created_at)})</span></div>`).join("")
        : `<span class="muted">No recent documents.</span>`;
      el("recentEventsBox").innerHTML = events.length
        ? events.slice(0, 5).map(e => `<div><strong>${e.event_type}</strong>: ${e.title} <span class="muted">(${shortIso(e.observed_at)})</span></div>`).join("")
        : `<span class="muted">No recent market events.</span>`;
    }

    function renderClientSourceCoverage(overview) {
      const focus = overview.client_source_focus || {};
      const news = focus.news_sources || [];
      const permits = focus.permit_sources || [];
      const counties = focus.counties || [];
      const box = el("clientSourceCoverageBox");
      const newsHtml = news.length ? news.map((s) => `
        <tr>
          <td>${s.display_name || s.source_key}</td>
          <td>${(s.sections || []).join(", ") || "-"}</td>
          <td>${statusBadge(s.access_mode || "unknown")}</td>
          <td>${s.auto_ingest ? "Yes" : "Manual"}</td>
        </tr>
      `).join("") : `<tr><td colspan="4" class="muted">No news sources configured.</td></tr>`;
      const permitHtml = permits.length ? permits.map((s) => `
        <tr>
          <td>${s.county || "-"}</td>
          <td>${s.source_name || s.source_key}</td>
          <td>${statusBadge(s.supports_live_pull ? "live" : "pending")}</td>
          <td>${s.supports_valuation_filter ? "Yes" : "No"}</td>
        </tr>
      `).join("") : `<tr><td colspan="4" class="muted">No permit sources configured.</td></tr>`;
      box.innerHTML = `
        <div><strong>Counties in scope:</strong> ${(counties || []).join(", ") || "n/a"}</div>
        <div style="overflow:auto; margin-top:8px;">
          <table>
            <thead><tr><th colspan="4">Local News Sources</th></tr><tr><th>Source</th><th>Sections</th><th>Access</th><th>Auto</th></tr></thead>
            <tbody>${newsHtml}</tbody>
          </table>
        </div>
        <div style="overflow:auto; margin-top:10px;">
          <table>
            <thead><tr><th colspan="4">Permit Sources</th></tr><tr><th>County</th><th>Source</th><th>Live Pull</th><th>Valuation in List</th></tr></thead>
            <tbody>${permitHtml}</tbody>
          </table>
        </div>
      `;
    }

    function renderCompsResults(result) {
      state.lastCompsResult = result;
      const s = result.summary || {};
      const text = result.summary_text || "";
      el("compsSummaryBox").innerHTML = `
        <div><strong>${text}</strong></div>
        <div class="tiny muted" style="margin-top:4px;">
          Avg Land $/SF: ${s.avg_land_price_per_sf ?? "n/a"} |
          Avg Building $/SF: ${s.avg_building_price_per_sf ?? "n/a"} |
          Avg Cap: ${s.avg_cap_rate ?? "n/a"} |
          Avg DOM: ${s.avg_days_on_market ?? "n/a"}
        </div>
      `;
      const rows = result.properties || [];
      const tbody = el("compsTableBody");
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="muted">No matches. Loosen filters and try again.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map((p) => `
        <tr>
          <td>
            <div>${p.address_line1 || "-"}</div>
            <div class="tiny muted">${p.city || ""}, ${p.county || ""}</div>
          </td>
          <td>${statusBadge(p.listing_status || "n/a")}</td>
          <td>${p.days_on_market ?? "n/a"}</td>
          <td>${p.sale_price_per_land_sf ?? "n/a"}</td>
          <td>${p.sale_price_per_building_sf ?? "n/a"}</td>
          <td>${p.cap_rate ?? "n/a"}</td>
        </tr>
      `).join("");
    }

    function renderSavedCompSearches(overview) {
      const rows = overview.saved_comp_searches || [];
      const tbody = el("savedCompsTableBody");
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="muted">No saved searches yet. Run a comp search, then click "Save Current Comp Search".</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map((s) => {
        const f = s.filters || {};
        const bits = [];
        if (f.city) bits.push(`city=${f.city}`);
        if (f.county) bits.push(`county=${f.county}`);
        if (f.tenant_brand) bits.push(`tenant=${f.tenant_brand}`);
        if (f.submarket) bits.push(`submarket=${f.submarket}`);
        if (f.max_land_psf) bits.push(`max land $/SF=${f.max_land_psf}`);
        if (f.max_building_psf) bits.push(`max bldg $/SF=${f.max_building_psf}`);
        if (f.max_building_sqft) bits.push(`max bldg SF=${f.max_building_sqft}`);
        if (f.occupancy_status) bits.push(`occupancy=${f.occupancy_status}`);
        if (f.min_cap_rate) bits.push(`min cap=${f.min_cap_rate}`);
        if (f.max_cap_rate) bits.push(`max cap=${f.max_cap_rate}`);
        if (f.lease_expiring_within_years) bits.push(`lease<=${f.lease_expiring_within_years}y`);
        return `
          <tr>
            <td><div>${s.name}</div><div class="tiny muted">${s.notes || ""}</div></td>
            <td class="tiny">${bits.join(" | ") || "No filters"}</td>
            <td class="tiny muted">${shortIso(s.updated_at)}</td>
            <td>
              <div class="actions-cell">
                <button class="small-btn" onclick="runSavedCompSearch('${s.saved_search_urn}')">Run</button>
                <button class="small-btn" onclick="deleteSavedCompSearch('${s.saved_search_urn}')">Delete</button>
              </div>
            </td>
          </tr>
        `;
      }).join("");
    }

    function renderAuditTimeline(overview) {
      const rows = overview.recent_audit_events || [];
      const tbody = el("auditTimelineBody");
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="3" class="muted">No audit activity yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map((a) => `
        <tr>
          <td class="tiny muted">${shortIso(a.created_at)}</td>
          <td>${statusBadge(a.action || "event")}</td>
          <td>
            <div>${a.summary || "-"}</div>
            <div class="tiny muted mono">${a.entity_type || ""}${a.entity_urn ? ":"+a.entity_urn : ""}</div>
          </td>
        </tr>
      `).join("");
    }

    async function loadOverview() {
      try {
        const overview = await api("/api/bis/ui/overview");
        state.overview = overview;
        renderStats(overview);
        renderWorkflow(overview);
        renderReadiness(overview);
        renderReviews(overview);
        renderNextActions(overview);
        renderProperties(overview);
        renderClientSourceCoverage(overview);
        renderRecentBoxes(overview);
        renderSavedCompSearches(overview);
        renderAuditTimeline(overview);
        logLine("Dashboard refreshed.");
        renderTour();
      } catch (err) {
        logLine(`Failed to load overview: ${err.message}`, "error");
        pushNotice(`Dashboard refresh failed: ${err.message}`, "error");
      }
    }

    function formToPayload(form) {
      const fd = new FormData(form);
      const payload = {};
      for (const [k, v] of fd.entries()) {
        const s = String(v).trim();
        if (!s) continue;
        payload[k] = s;
      }
      if (payload.asking_price) payload.asking_price = Number(payload.asking_price);
      payload.auto_generate_docs = true;
      return payload;
    }

    async function submitIntake(event) {
      event.preventDefault();
      const form = event.target;
      const payload = formToPayload(form);
      try {
        const result = await api("/api/bis/intake/drop", { method: "POST", body: JSON.stringify(payload) });
        const reviews = result.review_tasks?.length || 0;
        logLine(`Saved ${result.property?.address_line1 || "property"} (${result.property?.property_urn || ""}). Suggested updates created: ${reviews}.`);
        pushNotice(`Saved ${result.property?.address_line1 || "property"}. BIS created ${reviews} suggested update(s).`, "success");
        form.reset();
        form.city.value = "Austin";
        form.county.value = "Travis";
        if (state.tourStepIndex === 0) state.tourStepIndex = 1;
        await loadOverview();
      } catch (err) {
        logLine(`Intake save failed: ${err.message}`, "error");
        pushNotice(`Could not save intake: ${err.message}`, "error");
      }
    }

    function rawFormValues(form) {
      const fd = new FormData(form);
      const payload = {};
      for (const [k, v] of fd.entries()) {
        const s = String(v).trim();
        if (!s) continue;
        payload[k] = s;
      }
      return payload;
    }

    async function seedDemo() {
      try {
        const result = await api("/api/bis/seed", { method: "POST" });
        logLine(result.seeded ? "Demo sample loaded." : `Demo seed skipped (${result.reason || "already exists"}).`, result.seeded ? "info" : "warn");
        pushNotice(result.seeded ? "Demo data loaded." : `Demo data already exists (${result.reason || "already seeded"}).`, result.seeded ? "success" : "warn");
        await loadOverview();
      } catch (err) {
        logLine(`Seed failed: ${err.message}`, "error");
        pushNotice(`Demo seed failed: ${err.message}`, "error");
      }
    }

    async function submitMarketEvent(event) {
      event.preventDefault();
      const form = event.target;
      const payload = rawFormValues(form);
      if (payload.list_price) payload.list_price = Number(payload.list_price);
      if (payload.close_price) payload.close_price = Number(payload.close_price);
      try {
        const result = await api("/api/bis/market-events", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        logLine(`Saved market event: ${result.event?.event_type || ""} - ${result.event?.title || "event"}.`);
        pushNotice(`Market event saved: ${result.event?.title || "event"}.`, "success");
        form.reset();
        await loadOverview();
      } catch (err) {
        logLine(`Market event save failed: ${err.message}`, "error");
        pushNotice(`Could not save market event: ${err.message}`, "error");
      }
    }

    async function runCompsSearch(event) {
      event.preventDefault();
      const form = event.target;
      const payload = rawFormValues(form);
      if (payload.max_land_psf) payload.max_land_psf = Number(payload.max_land_psf);
      if (payload.max_building_psf) payload.max_building_psf = Number(payload.max_building_psf);
      if (payload.max_building_sqft) payload.max_building_sqft = Number(payload.max_building_sqft);
      if (payload.min_cap_rate) payload.min_cap_rate = Number(payload.min_cap_rate);
      if (payload.max_cap_rate) payload.max_cap_rate = Number(payload.max_cap_rate);
      if (payload.lease_expiring_within_years) payload.lease_expiring_within_years = Number(payload.lease_expiring_within_years);
      payload.limit = 15;
      state.lastCompsPayload = { ...payload };
      try {
        const result = await api("/api/bis/ui/comps/search", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        renderCompsResults(result);
        logLine(`Comp search complete. Returned ${result.summary?.returned_count ?? 0} of ${result.summary?.match_count ?? 0} matches.`);
        pushNotice(`Comp search complete: ${result.summary?.returned_count ?? 0} result(s) shown.`, "success");
      } catch (err) {
        logLine(`Comp search failed: ${err.message}`, "error");
        pushNotice(`Comp search failed: ${err.message}`, "error");
      }
    }

    async function saveCurrentCompSearch() {
      if (!state.lastCompsPayload) {
        logLine("Run a comp search first, then save it.", "warn");
        pushNotice("Run a comp search first, then save it.", "warn");
        return;
      }
      const defaultName = `Comp Search ${new Date().toLocaleString()}`;
      const name = window.prompt("Name this comp search:", defaultName);
      if (!name) return;
      const notes = window.prompt("Optional note (what this comp search is for):", "") || "";
      try {
        const result = await api("/api/bis/ui/comps/saved", {
          method: "POST",
          body: JSON.stringify({
            name,
            notes,
            created_by: "dashboard-user",
            filters: state.lastCompsPayload,
          }),
        });
        logLine(`Saved comp search: ${result.saved_search?.name || name}.`);
        pushNotice(`Saved comp search: ${result.saved_search?.name || name}.`, "success");
        await loadOverview();
      } catch (err) {
        logLine(`Save comp search failed: ${err.message}`, "error");
        pushNotice(`Could not save comp search: ${err.message}`, "error");
      }
    }

    async function refreshSavedCompSearches() {
      await loadOverview();
    }

    async function runSavedCompSearch(savedSearchUrn) {
      try {
        const result = await api(`/api/bis/ui/comps/saved/${savedSearchUrn}/run`, { method: "POST" });
        const saved = result.saved_search || {};
        state.lastCompsPayload = { ...(saved.filters || {}) };
        renderCompsResults(result);
        logLine(`Ran saved comp search: ${saved.name || savedSearchUrn}.`);
        pushNotice(`Ran saved comp search: ${saved.name || savedSearchUrn}.`, "success");
        await loadOverview();
      } catch (err) {
        logLine(`Run saved comp search failed: ${err.message}`, "error");
        pushNotice(`Could not run saved comp search: ${err.message}`, "error");
      }
    }
    window.runSavedCompSearch = runSavedCompSearch;

    async function deleteSavedCompSearch(savedSearchUrn) {
      const ok = window.confirm("Delete this saved comp search?");
      if (!ok) return;
      try {
        await api(`/api/bis/ui/comps/saved/${savedSearchUrn}`, { method: "DELETE" });
        logLine(`Deleted saved comp search ${savedSearchUrn}.`, "warn");
        pushNotice("Deleted saved comp search.", "warn");
        await loadOverview();
      } catch (err) {
        logLine(`Delete saved comp search failed: ${err.message}`, "error");
        pushNotice(`Could not delete saved comp search: ${err.message}`, "error");
      }
    }
    window.deleteSavedCompSearch = deleteSavedCompSearch;

    async function refreshNextActions() {
      try {
        const result = await api("/api/bis/ui/next-actions");
        renderNextActions({ next_actions: result.actions || [] });
        logLine(`Refreshed next actions (${result.count || 0} tasks).`);
        pushNotice(`Refreshed Today’s Tasks (${result.count || 0}).`, "info");
      } catch (err) {
        logLine(`Refresh next actions failed: ${err.message}`, "error");
        pushNotice(`Could not refresh tasks: ${err.message}`, "error");
      }
    }

    async function logNextAction(actionUrn, outcome) {
      try {
        const note = outcome === "snoozed" ? (window.prompt("Optional snooze note:", "") || "") : "";
        await api("/api/bis/ui/next-actions/log", {
          method: "POST",
          body: JSON.stringify({
            action_urn: actionUrn,
            outcome,
            note,
            actor: "dashboard-user",
          }),
        });
        logLine(`Marked task ${outcome}: ${actionUrn}.`);
        pushNotice(`Task marked ${outcome}.`, outcome === "done" ? "success" : "warn");
        await loadOverview();
      } catch (err) {
        logLine(`Task update failed: ${err.message}`, "error");
        pushNotice(`Task update failed: ${err.message}`, "error");
      }
    }
    window.logNextAction = logNextAction;

    async function approveReview(reviewUrn) {
      try {
        const result = await api(`/api/bis/reviews/${reviewUrn}/approve`, {
          method: "POST",
          body: JSON.stringify({ reviewed_by: "dashboard-user", review_note: "Approved from guided console" }),
        });
        logLine(`Approved review ${result.review?.field_name || reviewUrn}.`);
        pushNotice(`Approved suggested update: ${result.review?.field_name || "field"}.`, "success");
        if (state.tourStepIndex === 1) state.tourStepIndex = 2;
        await loadOverview();
      } catch (err) {
        logLine(`Approve failed (${reviewUrn}): ${err.message}`, "error");
        pushNotice(`Approve failed: ${err.message}`, "error");
      }
    }
    window.approveReview = approveReview;

    async function rejectReview(reviewUrn) {
      try {
        const result = await api(`/api/bis/reviews/${reviewUrn}/reject`, {
          method: "POST",
          body: JSON.stringify({ reviewed_by: "dashboard-user", review_note: "Rejected from guided console" }),
        });
        logLine(`Rejected review ${result.review?.field_name || reviewUrn}.`, "warn");
        pushNotice("Rejected suggested update.", "warn");
        await loadOverview();
      } catch (err) {
        logLine(`Reject failed (${reviewUrn}): ${err.message}`, "error");
        pushNotice(`Reject failed: ${err.message}`, "error");
      }
    }
    window.rejectReview = rejectReview;

    async function autoApproveVacancy(dryRun) {
      try {
        const result = await api("/api/bis/reviews/auto-approve", {
          method: "POST",
          body: JSON.stringify({
            dry_run: !!dryRun,
            only_fields: ["occupancy_status"],
            min_confidence: 0.85,
            reviewed_by: "dashboard-auto",
            review_note: dryRun ? "Dry run from guided console" : "Auto-approved vacancy from guided console",
          }),
        });
        logLine(
          dryRun
            ? `Auto-approve preview found ${result.candidates} vacancy suggestions.`
            : `Auto-approved ${result.approved_count} vacancy suggestions.`,
          dryRun ? "warn" : "info"
        );
        pushNotice(
          dryRun ? `Preview found ${result.candidates} vacancy suggestion(s).` : `Auto-approved ${result.approved_count} vacancy suggestion(s).`,
          dryRun ? "warn" : "success"
        );
        await loadOverview();
      } catch (err) {
        logLine(`Auto-approve failed: ${err.message}`, "error");
        pushNotice(`Auto-approve failed: ${err.message}`, "error");
      }
    }

    async function runDailyRefresh() {
      try {
        const result = await api("/api/bis/automation/run", {
          method: "POST",
          body: JSON.stringify({
            auto_approve_reviews: true,
            review_auto_only_fields: ["occupancy_status"],
            review_auto_min_confidence: 0.85,
            sync_google_sheets_pull: false,
            sync_google_sheets_push: false
          }),
        });
        const ra = result.review_auto_approve || {};
        logLine(`Daily refresh done. Docs: ${result.generated_documents || 0}, alerts: ${result.listing_age_alerts || 0}, auto-approved reviews: ${ra.approved_count || 0}.`);
        pushNotice(`Daily refresh complete. Docs: ${result.generated_documents || 0}, alerts: ${result.listing_age_alerts || 0}.`, "success");
        if (state.tourStepIndex === 2) state.tourStepIndex = 3;
        await loadOverview();
      } catch (err) {
        logLine(`Daily refresh failed: ${err.message}`, "error");
        pushNotice(`Daily refresh failed: ${err.message}`, "error");
      }
    }

    async function saveBackup() {
      try {
        const result = await api("/api/bis/system/backup/save", { method: "POST" });
        const g = result.gcs_save || {};
        const gText = g.saved ? `GCS saved (${g.bucket})` : `GCS not saved (${g.reason || g.error || "not configured"})`;
        logLine(`Backup saved. Local snapshot updated. ${gText}.`);
        pushNotice(`Backup saved. ${g.saved ? "Cloud backup updated." : "Local backup updated."}`, "success");
        if (state.tourStepIndex === 3) state.tourStepIndex = 4;
        await loadOverview();
      } catch (err) {
        logLine(`Backup save failed: ${err.message}`, "error");
        pushNotice(`Backup save failed: ${err.message}`, "error");
      }
    }

    async function runSheetsStatus() {
      try {
        const result = await api("/api/bis/sheets/google/status");
        const s = result.google_sheets_client || {};
        logLine(`Sheets status: auth=${s.auth_ok ? "ok" : "not ready"} project=${s.project_id || "n/a"} spreadsheetConfigured=${result.default_spreadsheet_id_configured}`);
        pushNotice(`Sheets status checked. ${result.default_spreadsheet_id_configured ? "Spreadsheet configured." : "Spreadsheet ID still missing."}`, "info");
        await loadOverview();
      } catch (err) {
        logLine(`Sheets status failed: ${err.message}`, "error");
        pushNotice(`Sheets status failed: ${err.message}`, "error");
      }
    }

    async function pullSheetNow() {
      try {
        const result = await api("/api/bis/sheets/google/pull", {
          method: "POST",
          body: JSON.stringify({ dry_run: false, auto_generate_docs: false }),
        });
        logLine(`Sheet pull complete. Fetched ${result.google_sheets?.rows_fetched ?? 0} rows, imported ${result.rows_imported ?? 0}, errors ${result.errors?.length ?? 0}.`);
        pushNotice(`Sheet pull complete. Imported ${result.rows_imported ?? 0} row(s).`, "success");
        await loadOverview();
      } catch (err) {
        logLine(`Sheet pull failed: ${err.message}`, "error");
        pushNotice(`Sheet pull failed: ${err.message}`, "error");
      }
    }

    async function pushSheetNow() {
      try {
        const p1 = await api("/api/bis/sheets/google/push", {
          method: "POST",
          body: JSON.stringify({ target: "properties_computed" }),
        });
        const p2 = await api("/api/bis/sheets/google/push", {
          method: "POST",
          body: JSON.stringify({ target: "reviews_pending" }),
        });
        logLine(`Sheet push complete. Properties rows: ${p1.rows_prepared}, Reviews rows: ${p2.rows_prepared}.`);
        pushNotice("Sheet writeback pushed successfully.", "success");
        await loadOverview();
      } catch (err) {
        logLine(`Sheet push failed: ${err.message}`, "error");
        pushNotice(`Sheet writeback failed: ${err.message}`, "error");
      }
    }

    function bindEvents() {
      el("intakeForm").addEventListener("submit", submitIntake);
      el("marketEventForm").addEventListener("submit", submitMarketEvent);
      el("compsForm").addEventListener("submit", runCompsSearch);
      el("seedBtn").addEventListener("click", seedDemo);
      el("refreshBtn").addEventListener("click", loadOverview);
      el("autoApproveVacancyBtn").addEventListener("click", () => autoApproveVacancy(false));
      el("autoApproveVacancyDryBtn").addEventListener("click", () => autoApproveVacancy(true));
      el("runDailyRefreshBtn").addEventListener("click", runDailyRefresh);
      el("saveBackupBtn").addEventListener("click", saveBackup);
      el("backupSaveBtn2").addEventListener("click", saveBackup);
      el("readinessBtn").addEventListener("click", loadOverview);
      el("sheetsStatusBtn").addEventListener("click", runSheetsStatus);
      el("sheetsPullBtn").addEventListener("click", pullSheetNow);
      el("sheetsPushBtn").addEventListener("click", pushSheetNow);
      el("backupStatusBtn").addEventListener("click", loadOverview);
      el("saveCurrentCompSearchBtn").addEventListener("click", saveCurrentCompSearch);
      el("refreshSavedCompSearchesBtn").addEventListener("click", refreshSavedCompSearches);
      el("refreshNextActionsBtn").addEventListener("click", refreshNextActions);
      el("tourStartBtn").addEventListener("click", startTour);
      el("tourNextBtn").addEventListener("click", nextTourStep);
      el("tourSkipBtn").addEventListener("click", hideTour);
      el("tourResetBtn").addEventListener("click", resetTour);
    }

    bindEvents();
    loadOverview();
  </script>
</body>
</html>"""
    return html.replace("__ENV__", escape(settings.environment)).replace("__AUTH__", escape(auth_label))


@app.get("/")
async def root(request: Request):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return HTMLResponse(_render_landing_html())
    return _meta_payload()


@app.get("/dashboard")
async def dashboard(_: None = Depends(require_bis_auth)):
    return HTMLResponse(_render_dashboard_html())
