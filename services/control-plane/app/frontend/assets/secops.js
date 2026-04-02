const secEls = {
  refresh: document.getElementById("refresh-secops"),
  riskBand: document.getElementById("secops-risk-band"),
  riskPoints: document.getElementById("secops-risk-points"),
  policy: document.getElementById("secops-policy"),
  drift: document.getElementById("secops-drift"),
  executor: document.getElementById("secops-executor"),
  executorHost: document.getElementById("secops-executor-host"),
  queue: document.getElementById("secops-queue"),
  blocker: document.getElementById("secops-blocker"),
  timeline: document.getElementById("secops-timeline"),
  generated: document.getElementById("secops-generated"),
  theaterMap: document.getElementById("theater-map"),
  redactionEnvelope: document.getElementById("redaction-envelope"),
  buildCard: document.getElementById("build-card"),
  sectorGrid: document.getElementById("sector-grid"),
  mixLogkind: document.getElementById("mix-logkind"),
  mixSeverity: document.getElementById("mix-severity"),
  mixEventTypes: document.getElementById("mix-event-types"),
  executorToolGrid: document.getElementById("executor-tool-grid"),
  privacyCards: document.getElementById("privacy-cards"),
  predeployGate: document.getElementById("predeploy-gate"),
  hardeningActions: document.getElementById("hardening-actions"),
  timelineToolbar: document.getElementById("timeline-toolbar"),
  timelineSearch: document.getElementById("timeline-search"),
  timelineSeverity: document.getElementById("timeline-severity-filter"),
  timelineList: document.getElementById("timeline-list"),
  ledgerDecision: document.getElementById("ledger-decision"),
  ledgerHandoff: document.getElementById("ledger-handoff"),
  ledgerIncident: document.getElementById("ledger-incident"),
  ledgerVerification: document.getElementById("ledger-verification"),
};

const SECOPS_POLL_MS = 20000;
let secState = {
  payload: null,
  timelineFilter: "all",
  timelineSearch: "",
  severityFilter: "",
};
let secPoll = null;

function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setText(node, value) {
  if (node) node.textContent = value;
}

function isoShort(v) {
  if (!v) return "--";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return `${d.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

function renderSimpleList(node, rows, emptyText = "None.") {
  if (!node) return;
  if (!Array.isArray(rows) || !rows.length) {
    node.innerHTML = `<li>${esc(emptyText)}</li>`;
    return;
  }
  node.innerHTML = rows.join("");
}

function ratioPct(value, total) {
  const v = Number(value || 0);
  const t = Number(total || 0);
  if (!Number.isFinite(v) || !Number.isFinite(t) || t <= 0) return 0;
  return Math.max(0, Math.min((v / t) * 100, 100));
}

function renderBarList(node, source, maxItems = 8) {
  if (!node) return;
  const entries = Object.entries(source || {});
  if (!entries.length) {
    node.innerHTML = '<p class="muted">No recent data.</p>';
    return;
  }
  const rows = entries
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0) || String(a[0]).localeCompare(String(b[0])))
    .slice(0, maxItems);
  const total = rows.reduce((sum, [, count]) => sum + Number(count || 0), 0) || 1;
  node.innerHTML = rows
    .map(([label, count]) => {
      const pct = ratioPct(count, total).toFixed(1);
      return `
        <div class="metric-row">
          <div class="head"><span class="label">${esc(label)}</span><span class="value">${esc(count)}</span></div>
          <div class="metric-track"><div class="metric-fill" style="width:${pct}%"></div></div>
        </div>
      `;
    })
    .join("");
}

function badgeClassForStatus(value) {
  const s = String(value || "").toLowerCase();
  if (["stable", "ok", "healthy", "false"].includes(s)) return "ok";
  if (["guarded", "warning", "warn", "elevated", "true"].includes(s)) return "warn";
  if (["critical", "degraded", "error"].includes(s)) return "error";
  return "";
}

function fetchSecOps({ refresh = false, eventLimit = 60 } = {}) {
  const params = new URLSearchParams();
  if (refresh) params.set("refresh", "true");
  if (Number.isFinite(Number(eventLimit))) params.set("event_limit", String(Math.max(20, Math.min(180, Math.trunc(Number(eventLimit))))));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetch(`/api/frontend/secops${suffix}`, { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error(`secops request failed (${r.status})`);
    return r.json();
  });
}

function renderSummary(payload) {
  const summary = payload.summary || {};
  const posture = payload.posture || {};
  const executor = posture.executor || {};
  const primary = executor.primary_executor || {};
  setText(secEls.riskBand, String(summary.risk_band || "unknown").toUpperCase());
  setText(secEls.riskPoints, `risk points: ${Number(summary.risk_points || 0)}`);
  setText(secEls.policy, `${String(summary.policy_mode || "unknown").toUpperCase()}${summary.policy_lock_applied ? " / LOCK" : ""}`);
  setText(secEls.drift, `drift: ${summary.policy_drift_detected ? "detected" : "clear"}`);
  setText(secEls.executor, `${Number(summary.agents_executor_online || 0)}/${Number(summary.agents_executor_total || 0)} online`);
  setText(secEls.executorHost, `host: ${String((primary.host || {}).host_class || "unknown").toUpperCase()}`);
  setText(secEls.queue, `Q${Number(summary.tasks_queued || 0)} · L${Number(summary.tasks_leased || 0)} · F${Number(summary.tasks_failed || 0)}`);
  setText(secEls.blocker, `blocker: ${summary.queue_top_blocker_reason || "none"}`);
  setText(secEls.timeline, `${Number(summary.timeline_count || 0)} events`);
  setText(secEls.generated, isoShort(payload.generated_at));
}

function renderTheaterMap(payload) {
  if (!secEls.theaterMap) return;
  const topology = ((payload.analysis || {}).topology || {});
  const nodes = Array.isArray(topology.nodes) ? topology.nodes : [];
  const links = Array.isArray(topology.links) ? topology.links : [];
  if (!nodes.length) {
    secEls.theaterMap.innerHTML = '<p class="muted">No topology available.</p>';
    return;
  }
  const linkByFrom = new Map();
  links.forEach((link) => {
    const from = String(link?.from || "");
    if (!from) return;
    if (!linkByFrom.has(from)) linkByFrom.set(from, []);
    linkByFrom.get(from).push(link);
  });
  secEls.theaterMap.innerHTML = nodes
    .map((node) => {
      const id = String(node.id || "");
      const outgoing = linkByFrom.get(id) || [];
      return `
        <div class="theater-node" data-status="${esc(node.status || "stable")}">
          <span class="label">${esc(node.label || id)}</span>
          <span class="sub">${esc(node.subtitle || "")}</span>
        </div>
        ${outgoing
          .map((link) => `<div class="theater-link"><span>${esc(link.label || "flow")}</span></div>`)
          .join("")}
      `;
    })
    .join("");
}

function renderRedactionEnvelope(payload) {
  if (!secEls.redactionEnvelope) return;
  const redaction = payload.redaction || {};
  const aliases = redaction.aliases_applied || {};
  const fieldsRemoved = Array.isArray(redaction.fields_removed) ? redaction.fields_removed : [];
  const rows = [
    ["Mode", redaction.mode || "unknown"],
    ["Surface", (payload.classification || {}).surface || "unknown"],
    ["Command", (payload.classification || {}).command_channel || "telegram"],
    ["Tokens", fieldsRemoved.includes("task_ids") ? "aliased" : "redacted"],
    ["Paths", fieldsRemoved.includes("local_paths") ? "suppressed" : "unknown"],
    ["URLs", fieldsRemoved.includes("raw_repo_urls") ? "suppressed" : "unknown"],
    ["Host aliases", aliases.hosts ? "enabled" : "disabled"],
    ["Agent aliases", aliases.agents ? "enabled" : "disabled"],
    ["Project aliases", aliases.projects ? "enabled" : "disabled"],
  ];
  secEls.redactionEnvelope.innerHTML = rows
    .map(
      ([k, v]) =>
        `<div class="redaction-item"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`,
    )
    .join("");
}

function renderBuildCard(payload) {
  if (!secEls.buildCard) return;
  const summary = payload.summary || {};
  secEls.buildCard.innerHTML = `
    <div class="rev">${esc(payload.service_revision || "local")}</div>
    <div class="build-row"><span class="k">runtime</span><span class="v">${esc(payload.runtime_mode || "local")}</span></div>
    <div class="build-row"><span class="k">generated</span><span class="v">${esc(isoShort(payload.generated_at))}</span></div>
    <div class="build-row"><span class="k">policy</span><span class="v">${esc((summary.policy_mode || "unknown") + (summary.policy_lock_applied ? " / lock" : ""))}</span></div>
    <div class="build-row"><span class="k">drift</span><span class="v">${esc(summary.policy_drift_detected ? "detected" : "clear")}</span></div>
  `;
}

function renderSectors(payload) {
  if (!secEls.sectorGrid) return;
  const sectors = Array.isArray((payload.analysis || {}).sectors) ? payload.analysis.sectors : [];
  if (!sectors.length) {
    secEls.sectorGrid.innerHTML = '<p class="muted">No sector analysis available.</p>';
    return;
  }
  secEls.sectorGrid.innerHTML = sectors
    .map((sector) => {
      const metrics = sector.metrics && typeof sector.metrics === "object" ? sector.metrics : {};
      const rows = Object.entries(metrics)
        .slice(0, 8)
        .map(([k, v]) => `<div class="row"><span class="k">${esc(k)}</span><span class="v">${esc(String(v))}</span></div>`)
        .join("");
      const statusClass = badgeClassForStatus(sector.status || "");
      return `
        <div class="sector-card">
          <div class="head">
            <h4>${esc(sector.label || sector.id || "Sector")}</h4>
            <span class="sector-status ${esc(statusClass)}">${esc(sector.status || "unknown")}</span>
          </div>
          <div class="metrics-table">${rows}</div>
          <div class="sector-note">${esc(sector.analysis || "")}</div>
        </div>
      `;
    })
    .join("");
}

function renderPrivacyPosture(payload) {
  if (!secEls.privacyCards) return;
  const posture = payload.security_posture || {};
  const blocks = [
    {
      label: "Privacy First",
      status: "stable",
      metrics: posture.privacy_first || {},
      analysis: "Public-facing Sec Ops surface suppresses identifiers and keeps control actions off-page.",
    },
    {
      label: "Auth Boundaries",
      status: (posture.auth_boundaries || {}).telegram_webhook_secret_configured ? "stable" : "guarded",
      metrics: posture.auth_boundaries || {},
      analysis: "Token guards and webhook secret controls are reported as booleans only.",
    },
    {
      label: "Hardening Signals",
      status: ((posture.hardening_signals || {}).openclaw_embedded_secret_key_count || 0) > 0 ? "elevated" : "stable",
      metrics: posture.hardening_signals || {},
      analysis: "Baseline hardening readiness across agent stack integrations.",
    },
  ];
  secEls.privacyCards.innerHTML = blocks
    .map((sector) => {
      const metrics = sector.metrics && typeof sector.metrics === "object" ? sector.metrics : {};
      const rows = Object.entries(metrics)
        .slice(0, 8)
        .map(([k, v]) => `<div class="row"><span class="k">${esc(k)}</span><span class="v">${esc(String(v))}</span></div>`)
        .join("");
      const statusClass = badgeClassForStatus(sector.status || "");
      return `
        <div class="sector-card">
          <div class="head">
            <h4>${esc(sector.label)}</h4>
            <span class="sector-status ${esc(statusClass)}">${esc(sector.status)}</span>
          </div>
          <div class="metrics-table">${rows}</div>
          <div class="sector-note">${esc(sector.analysis || "")}</div>
        </div>
      `;
    })
    .join("");
}

function renderPredeployGate(payload) {
  const gates = Array.isArray(payload.predeploy_gate) ? payload.predeploy_gate : [];
  renderSimpleList(
    secEls.predeployGate,
    gates.map((gate) => {
      const status = String(gate.status || "warn");
      const cls = status === "pass" ? "ok" : status === "fail" ? "error" : "warn";
      return `<li><span class="badge ${cls}">${esc(status)}</span> ${esc(gate.label || gate.id || "gate")}<div class="muted">${esc(gate.detail || "")}</div></li>`;
    }),
    "No gate checks available.",
  );
  const actions = (((payload.security_posture || {}).recommended_actions) || []).slice(0, 8);
  renderSimpleList(
    secEls.hardeningActions,
    actions.map((item) => `<li>${esc(item)}</li>`),
    "No immediate hardening actions reported.",
  );
}

function renderToolGrid(payload) {
  if (!secEls.executorToolGrid) return;
  const tools = (((payload.posture || {}).executor || {}).tool_summary) || {};
  const rows = [
    ["gh", "gh"],
    ["gcloud", "cloud bridge"],
    ["docker", "docker"],
    ["node", "node"],
  ].map(([key, label]) => {
    const ok = Boolean(tools[key]);
    return `
      <div class="tool-chip ${ok ? "ok" : "warn"}">
        <span>${esc(label)}</span><span>${ok ? "READY" : "MISSING"}</span>
      </div>
    `;
  });
  secEls.executorToolGrid.innerHTML = rows.join("");
}

function renderMix(payload) {
  const mix = ((payload.analysis || {}).event_mix || {});
  renderBarList(secEls.mixLogkind, mix.by_log_kind || {}, 6);
  renderBarList(secEls.mixSeverity, mix.by_severity || {}, 6);
  const types = Array.isArray(mix.top_event_types) ? mix.top_event_types : [];
  renderSimpleList(
    secEls.mixEventTypes,
    types.slice(0, 8).map((row) => `<li>${esc(row.event_type || "event")}: ${esc(row.count ?? 0)}</li>`),
    "No event types.",
  );
}

function ledgerRows(rows) {
  if (!Array.isArray(rows) || !rows.length) return [];
  return rows.slice(0, 6).map((row) => {
    const sevClass = badgeClassForStatus(row.severity || "");
    return `
      <li>
        <div><span class="badge ${esc(sevClass)}">${esc(row.log_kind || row.severity || "log")}</span> ${esc(row.headline || "entry")}</div>
        <div class="muted">${esc(row.agent || "SYSTEM")} · ${esc(row.project || "UNSCOPED")} · ${esc(isoShort(row.created_at))}</div>
      </li>
    `;
  });
}

function renderLedgers(payload) {
  const ledgers = payload.ledgers || {};
  renderSimpleList(secEls.ledgerDecision, ledgerRows(ledgers.decision || []), "No decision entries.");
  renderSimpleList(secEls.ledgerHandoff, ledgerRows(ledgers.handoff || []), "No handoff entries.");
  renderSimpleList(secEls.ledgerIncident, ledgerRows(ledgers.incident || []), "No incident entries.");
  renderSimpleList(secEls.ledgerVerification, ledgerRows(ledgers.verification || []), "No verification entries.");
}

function passesTimelineFilter(row) {
  const kindFilter = String(secState.timelineFilter || "all");
  const severityFilter = String(secState.severityFilter || "");
  const search = String(secState.timelineSearch || "").trim().toLowerCase();
  if (kindFilter !== "all" && String(row.log_kind || "") !== kindFilter) return false;
  if (severityFilter && String(row.severity || "") !== severityFilter) return false;
  if (search) {
    const hay = [row.headline, row.message, row.agent, row.project, row.event_type].join(" ").toLowerCase();
    if (!hay.includes(search)) return false;
  }
  return true;
}

function renderTimeline(payload) {
  if (!secEls.timelineList) return;
  const rows = Array.isArray(payload.timeline) ? payload.timeline : [];
  const filtered = rows.filter(passesTimelineFilter);
  if (!filtered.length) {
    secEls.timelineList.innerHTML = '<p class="muted">No timeline entries match current filters.</p>';
    return;
  }
  secEls.timelineList.innerHTML = filtered.slice(0, 80).map((row) => {
    const sevClass = badgeClassForStatus(row.severity || "");
    const kindClass = badgeClassForStatus(row.log_kind === "incident" ? "warning" : row.log_kind === "verification" ? "ok" : "");
    return `
      <div class="timeline-row">
        <div class="head">
          <div class="title">${esc(row.headline || row.event_type || "event")}</div>
          <div class="meta">
            <span class="badge ${esc(sevClass)}">${esc(row.severity || "info")}</span>
            <span class="badge ${esc(kindClass)}">${esc(row.log_kind || "progress")}</span>
            <span class="badge">${esc(row.channel || "control")}</span>
          </div>
        </div>
        <div class="message">${esc(row.message || "No redacted detail available.")}</div>
        <div class="tail">
          <span>${esc(row.agent || "SYSTEM")}</span>
          <span>· ${esc(row.project || "UNSCOPED")}</span>
          <span>· ${esc(isoShort(row.created_at))}</span>
          ${row.status ? `<span>· ${esc(row.status)}</span>` : ""}
        </div>
      </div>
    `;
  }).join("");
}

function renderAll(payload) {
  secState.payload = payload;
  renderSummary(payload);
  renderTheaterMap(payload);
  renderRedactionEnvelope(payload);
  renderBuildCard(payload);
  renderSectors(payload);
  renderPrivacyPosture(payload);
  renderPredeployGate(payload);
  renderToolGrid(payload);
  renderMix(payload);
  renderLedgers(payload);
  renderTimeline(payload);
}

async function loadSecOps({ refresh = false } = {}) {
  try {
    if (secEls.refresh) secEls.refresh.disabled = true;
    const payload = await fetchSecOps({ refresh, eventLimit: 80 });
    renderAll(payload);
  } catch (error) {
    console.error(error);
    if (secEls.timelineList) {
      secEls.timelineList.innerHTML = `<p class="muted">Failed to load Sec Ops surface: ${esc(error.message || error)}</p>`;
    }
  } finally {
    if (secEls.refresh) secEls.refresh.disabled = false;
  }
}

function bindUi() {
  secEls.refresh?.addEventListener("click", () => loadSecOps({ refresh: true }));
  secEls.timelineToolbar?.addEventListener("click", (event) => {
    const button = event.target instanceof HTMLElement ? event.target.closest("button[data-filter]") : null;
    if (!button) return;
    secState.timelineFilter = String(button.dataset.filter || "all");
    secEls.timelineToolbar.querySelectorAll("button[data-filter]").forEach((node) => {
      node.classList.toggle("active", node === button);
    });
    if (secState.payload) renderTimeline(secState.payload);
  });
  secEls.timelineSearch?.addEventListener("input", (event) => {
    secState.timelineSearch = String(event.target?.value || "");
    if (secState.payload) renderTimeline(secState.payload);
  });
  secEls.timelineSeverity?.addEventListener("change", (event) => {
    secState.severityFilter = String(event.target?.value || "");
    if (secState.payload) renderTimeline(secState.payload);
  });
}

function startPolling() {
  if (secPoll) window.clearInterval(secPoll);
  secPoll = window.setInterval(() => loadSecOps({ refresh: false }), SECOPS_POLL_MS);
}

bindUi();
loadSecOps({ refresh: true });
startPolling();
