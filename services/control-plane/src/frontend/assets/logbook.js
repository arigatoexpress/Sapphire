const els = {
  refreshButton: document.getElementById("refresh-logbook"),
  summaryGenerated: document.getElementById("summary-generated"),
  summaryTimeline: document.getElementById("summary-timeline"),
  summaryExecutors: document.getElementById("summary-executors"),
  summaryQueue: document.getElementById("summary-queue"),
  summaryPolicy: document.getElementById("summary-policy"),
  statusStrip: document.getElementById("status-strip"),
  trendEvents: document.getElementById("trend-events"),
  trendEventsMeta: document.getElementById("trend-events-meta"),
  trendLeases: document.getElementById("trend-leases"),
  trendLeasesMeta: document.getElementById("trend-leases-meta"),
  trendFailures: document.getElementById("trend-failures"),
  trendFailuresMeta: document.getElementById("trend-failures-meta"),
  trendDrift: document.getElementById("trend-drift"),
  trendDriftMeta: document.getElementById("trend-drift-meta"),
  trendLogKind: document.getElementById("trend-logkind"),
  buildCard: document.getElementById("build-card"),
  viewTimeRange: document.getElementById("view-time-range"),
  viewEventLimit: document.getElementById("view-event-limit"),
  trendBucketCount: document.getElementById("trend-bucket-count"),
  viewControlsStatus: document.getElementById("view-controls-status"),
  timelineToolbar: document.getElementById("timeline-toolbar"),
  timelineSearch: document.getElementById("timeline-search"),
  timelineAgentFilter: document.getElementById("timeline-agent-filter"),
  timelineProjectFilter: document.getElementById("timeline-project-filter"),
  timelineKindFilter: document.getElementById("timeline-kind-filter"),
  timelineList: document.getElementById("timeline-list"),
  eventMixSeverity: document.getElementById("event-mix-severity"),
  eventMixCategory: document.getElementById("event-mix-category"),
  eventMixLogKind: document.getElementById("event-mix-logkind"),
  eventTypeTop: document.getElementById("event-type-top"),
  communicationCategoryCards: document.getElementById("communication-category-cards"),
  decisionLedger: document.getElementById("decision-ledger"),
  handoffLedger: document.getElementById("handoff-ledger"),
  incidentLedger: document.getElementById("incident-ledger"),
  verificationLedger: document.getElementById("verification-ledger"),
  agentLanes: document.getElementById("agent-lanes"),
  workstreams: document.getElementById("workstreams"),
  trackedProjects: document.getElementById("tracked-projects"),
  roadmapNow: document.getElementById("roadmap-now"),
  roadmapNext: document.getElementById("roadmap-next"),
  nextActions: document.getElementById("next-actions"),
  controlTaskList: document.getElementById("control-task-list"),
  protocolGoal: document.getElementById("protocol-goal"),
  protocolTemplate: document.getElementById("protocol-template"),
  protocolRules: document.getElementById("protocol-rules"),
};

const POLL_MS = 15000;
const LOGBOOK_VIEW_PREFS_KEY = "agentic.logbook.view_prefs";
let pollHandle = null;
let logbookState = {
  payload: null,
  filter: "all",
  search: "",
  agentId: "",
  projectId: "",
  logKind: "",
  timeRange: "6h",
  eventLimit: 100,
  trendBucketCount: 10,
};

function setText(node, value) {
  if (node) node.textContent = value;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatIso(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${date.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

function pluralize(count, singular, plural = `${singular}s`) {
  const n = Number(count || 0);
  return `${n} ${n === 1 ? singular : plural}`;
}

function boolBadge(ok, label) {
  return `<span class="inline-chip ${ok ? "ok" : "warn"}">${escapeHtml(label)}: ${ok ? "yes" : "no"}</span>`;
}

function loadViewPrefs() {
  try {
    const raw = window.localStorage.getItem(LOGBOOK_VIEW_PREFS_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return;
    const timeRange = String(parsed.timeRange || "").trim();
    const eventLimit = Number.parseInt(String(parsed.eventLimit || ""), 10);
    const trendBucketCount = Number.parseInt(String(parsed.trendBucketCount || ""), 10);
    if (["1h", "6h", "24h", "7d", "all"].includes(timeRange)) {
      logbookState.timeRange = timeRange;
    }
    if ([50, 100, 200].includes(eventLimit)) {
      logbookState.eventLimit = eventLimit;
    }
    if ([8, 10, 12, 16].includes(trendBucketCount)) {
      logbookState.trendBucketCount = trendBucketCount;
    }
  } catch (_error) {
    // ignore invalid local storage
  }
}

function saveViewPrefs() {
  try {
    window.localStorage.setItem(
      LOGBOOK_VIEW_PREFS_KEY,
      JSON.stringify({
        timeRange: logbookState.timeRange,
        eventLimit: logbookState.eventLimit,
        trendBucketCount: logbookState.trendBucketCount,
      }),
    );
  } catch (_error) {
    // ignore storage failures
  }
}

function applyViewControlsToDom() {
  if (els.viewTimeRange) els.viewTimeRange.value = String(logbookState.timeRange || "6h");
  if (els.viewEventLimit) els.viewEventLimit.value = String(logbookState.eventLimit || 100);
  if (els.trendBucketCount) els.trendBucketCount.value = String(logbookState.trendBucketCount || 10);
}

function renderSimpleList(node, rows, empty = "None.") {
  if (!node) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    node.innerHTML = `<li>${escapeHtml(empty)}</li>`;
    return;
  }
  node.innerHTML = rows.map((row) => `<li>${typeof row === "string" ? escapeHtml(row) : row}</li>`).join("");
}

function ratioPercent(value, total) {
  const v = Number(value || 0);
  const t = Number(total || 0);
  if (!Number.isFinite(v) || !Number.isFinite(t) || t <= 0) return 0;
  return Math.max(0, Math.min((v / t) * 100, 100));
}

function renderBarList(node, obj, { maxItems = 8 } = {}) {
  if (!node) return;
  const entries = Object.entries(obj || {});
  if (!entries.length) {
    node.innerHTML = '<p class="muted">No recent data.</p>';
    return;
  }
  const rows = entries
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0) || String(a[0]).localeCompare(String(b[0])))
    .slice(0, maxItems);
  const total = rows.reduce((sum, [, count]) => sum + Number(count || 0), 0);
  node.innerHTML = rows
    .map(([label, count]) => {
      const pct = ratioPercent(count, total || 1);
      return `
        <div class="metric-row">
          <div class="head"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(count)}</span></div>
          <div class="metric-track"><div class="metric-fill" style="width:${pct.toFixed(1)}%"></div></div>
        </div>
      `;
    })
    .join("");
}

function renderStatusStrip(payload) {
  if (!els.statusStrip) return;
  const summary = payload.summary || {};
  const queue = payload.queue?.summary || {};
  const policyDrift = payload.policy_drift || {};
  const items = [
    ["Queue stall", summary.queue_stall_detected ? "true" : "false"],
    ["Top blocker", summary.queue_top_blocker_reason || "none"],
    ["Policy drift", policyDrift.drift_detected ? "true" : "false"],
    ["Roadmap", `Now ${summary.roadmap_now_count || 0} · Next ${summary.roadmap_next_count || 0}`],
    ["Routable queue", `${queue.routable_count ?? 0}/${(queue.queued_count ?? 0) || 0}`],
    ["Service", `${payload.service_name || "local"} · ${payload.service_revision || "local"}`],
  ];
  els.statusStrip.innerHTML = items
    .map(([label, value]) => `<div class="strip-item"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(value)}</span></div>`)
    .join("");
}

function viewRangeCutoffMs(rangeId) {
  const now = Date.now();
  if (rangeId === "1h") return now - 60 * 60 * 1000;
  if (rangeId === "6h") return now - 6 * 60 * 60 * 1000;
  if (rangeId === "24h") return now - 24 * 60 * 60 * 1000;
  if (rangeId === "7d") return now - 7 * 24 * 60 * 60 * 1000;
  return null;
}

function rowInSelectedTimeRange(row) {
  const rangeId = String(logbookState.timeRange || "all");
  if (rangeId === "all") return true;
  const cutoff = viewRangeCutoffMs(rangeId);
  if (cutoff === null) return true;
  const ts = Date.parse(String(row?.created_at || ""));
  if (Number.isNaN(ts)) return false;
  return ts >= cutoff;
}

function filteredTimelineRows(payload) {
  const rows = Array.isArray(payload?.timeline) ? payload.timeline : [];
  return rows.filter((row) => rowInSelectedTimeRange(row));
}

function renderViewControlsStatus(payload) {
  if (!els.viewControlsStatus) return;
  const totalRows = Array.isArray(payload?.timeline) ? payload.timeline.length : 0;
  const visibleRows = filteredTimelineRows(payload).length;
  const rangeId = String(logbookState.timeRange || "all");
  const eventLimit = Number(logbookState.eventLimit || 0);
  const buckets = Number(logbookState.trendBucketCount || 0);
  els.viewControlsStatus.textContent = `${visibleRows}/${totalRows} events · ${rangeId} · limit ${eventLimit} · ${buckets} buckets`;
}

function renderBuildCard(payload) {
  if (!els.buildCard) return;
  const summary = payload.summary || {};
  const policyDrift = payload.policy_drift || {};
  const queue = payload.queue || {};
  const qSummary = queue.summary || {};
  const lines = [
    ["Service", `${payload.service_name || "local"}`],
    ["Revision", `${payload.service_revision || "local"}`],
    ["Generated", `${formatIso(payload.generated_at)}`],
    ["Policy", `${summary.policy_mode || "unknown"}${summary.policy_lock_applied ? " (lock)" : ""}`],
    ["Drift", `${policyDrift.drift_detected ? "detected" : "clear"}`],
    ["Queue", `Q${summary.tasks_queued || 0} · L${summary.tasks_leased || 0} · F${summary.tasks_failed || 0}`],
    ["Routable", `${qSummary.routable_count ?? 0}/${qSummary.queued_count ?? 0}`],
  ];
  els.buildCard.innerHTML = `
    <div class="build-rev">${escapeHtml(String(payload.service_revision || "local"))}</div>
    <div class="build-grid">
      ${lines
        .map(
          ([k, v]) =>
            `<div class="build-row"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v)}</span></div>`,
        )
        .join("")}
    </div>
  `;
}

function timelineBuckets(rows, bucketCount = 10) {
  const items = Array.isArray(rows) ? rows.slice().reverse() : [];
  const count = Math.max(1, Math.min(24, Number(bucketCount || 10)));
  const buckets = Array.from({ length: count }, (_, idx) => ({
    index: idx,
    total: 0,
    leases: 0,
    failures: 0,
    drift: 0,
  }));
  if (!items.length) return buckets;
  items.forEach((row, idx) => {
    const bucketIdx = Math.min(count - 1, Math.floor((idx * count) / items.length));
    const bucket = buckets[bucketIdx];
    const eventType = String(row?.event_type || "").toLowerCase();
    const severity = String(row?.severity || "").toLowerCase();
    const logKind = String(row?.log_kind || "").toLowerCase();
    const headline = String(row?.headline || "").toLowerCase();
    const message = String(row?.message || row?.payload_preview || "").toLowerCase();
    const status = String(row?.status || "").toLowerCase();
    bucket.total += 1;
    if (
      eventType.includes("lease")
      || status === "leased"
      || headline.includes("leased")
      || message.includes("leased")
    ) {
      bucket.leases += 1;
    }
    if (
      severity === "error"
      || severity === "critical"
      || logKind === "incident"
      || eventType.includes("fail")
      || status === "failed"
      || headline.includes("failed")
    ) {
      bucket.failures += 1;
    }
    if (headline.includes("drift") || message.includes("drift") || eventType.includes("policy")) {
      bucket.drift += 1;
    }
  });
  return buckets;
}

function renderSparkBars(node, values, options = {}) {
  if (!node) return;
  const rows = Array.isArray(values) ? values.map((v) => Number(v || 0)) : [];
  if (!rows.length) {
    node.innerHTML = '<p class="muted">No trend data.</p>';
    return;
  }
  const maxValue = Math.max(...rows, 0, 1);
  const tone = String(options.tone || "info");
  const labels = Array.isArray(options.labels) ? options.labels : [];
  node.innerHTML = `
    <div class="spark-track">
      ${rows
        .map((value, idx) => {
          const pct = Math.max(6, (Math.max(0, value) / maxValue) * 100);
          const title = labels[idx] ? `${labels[idx]}: ${value}` : `${value}`;
          return `<div class="spark-bar ${tone}" style="height:${pct.toFixed(1)}%" title="${escapeHtml(title)}"></div>`;
        })
        .join("")}
    </div>
  `;
}

function renderTrends(payload) {
  const timeline = filteredTimelineRows(payload);
  const buckets = timelineBuckets(timeline, Number(logbookState.trendBucketCount || 10));
  const labels = buckets.map((b) => `slice ${b.index + 1}`);
  const totalEvents = buckets.reduce((sum, b) => sum + b.total, 0);
  const totalLeases = buckets.reduce((sum, b) => sum + b.leases, 0);
  const totalFailures = buckets.reduce((sum, b) => sum + b.failures, 0);
  const totalDrift = buckets.reduce((sum, b) => sum + b.drift, 0);

  renderSparkBars(els.trendEvents, buckets.map((b) => b.total), { tone: "info", labels });
  renderSparkBars(els.trendLeases, buckets.map((b) => b.leases), { tone: "ok", labels });
  renderSparkBars(els.trendFailures, buckets.map((b) => b.failures), { tone: "error", labels });
  renderSparkBars(els.trendDrift, buckets.map((b) => b.drift), { tone: "warn", labels });
  setText(els.trendEventsMeta, `${totalEvents} events / ${buckets.length} slices`);
  setText(els.trendLeasesMeta, `${totalLeases} lease signals`);
  setText(els.trendFailuresMeta, `${totalFailures} fail/incident signals`);
  setText(els.trendDriftMeta, `${totalDrift} drift signals`);

  const logKindMix = timeline.reduce((acc, row) => {
    const key = String(row?.log_kind || "").toLowerCase().trim();
    if (!key) return acc;
    acc[key] = Number(acc[key] || 0) + 1;
    return acc;
  }, {});
  renderBarList(els.trendLogKind, logKindMix, { maxItems: 5 });
}

function renderSummary(payload) {
  const summary = payload.summary || {};
  setText(els.summaryGenerated, formatIso(payload.generated_at));
  setText(els.summaryTimeline, `${summary.timeline_count || 0} (${summary.task_event_count || 0}/${summary.system_event_count || 0})`);
  setText(
    els.summaryExecutors,
    `${summary.agents_executor_online ?? summary.agents_online ?? 0}/${summary.agents_online ?? 0}`,
  );
  setText(els.summaryQueue, `Q${summary.tasks_queued || 0} L${summary.tasks_leased || 0} F${summary.tasks_failed || 0}`);
  setText(
    els.summaryPolicy,
    `${summary.policy_mode || "unknown"}${summary.policy_lock_applied ? " (lock)" : ""}${summary.policy_drift_detected ? " · drift" : ""}`,
  );
}

function passesFilter(row, filter) {
  if (!row || filter === "all") return true;
  if (filter === "control") return row.channel === "control";
  if (filter === "system") return row.channel === "system";
  if (filter === "warning") return ["warning", "error", "critical"].includes(String(row.severity || "").toLowerCase());
  if (filter === "error") return ["error", "critical"].includes(String(row.severity || "").toLowerCase());
  return true;
}

function passesSearchFilters(row) {
  if (!row) return false;
  if (!rowInSelectedTimeRange(row)) return false;
  const agentId = String(logbookState.agentId || "");
  const projectId = String(logbookState.projectId || "");
  const logKind = String(logbookState.logKind || "");
  const search = String(logbookState.search || "").trim().toLowerCase();
  if (agentId && String(row.agent_id || "") !== agentId) return false;
  if (projectId && String(row.project_id || "") !== projectId) return false;
  if (logKind && String(row.log_kind || "") !== logKind) return false;
  if (!search) return true;
  const haystack = [
    row.headline,
    row.message,
    row.event_type,
    row.task_id,
    row.task_title,
    row.agent_id,
    row.project_id,
    row.repo,
    row.status,
    row.log_kind,
  ]
    .map((item) => String(item || "").toLowerCase())
    .join(" ");
  return haystack.includes(search);
}

function timelineMetaChips(row) {
  const chips = [];
  if (row.task_id) chips.push(`<code>${escapeHtml(row.task_id)}</code>`);
  if (row.agent_id) chips.push(`<code>${escapeHtml(row.agent_id)}</code>`);
  if (row.project_id) chips.push(`<code>project:${escapeHtml(row.project_id)}</code>`);
  if (row.repo) chips.push(`<code>repo:${escapeHtml(row.repo)}</code>`);
  if (row.status) chips.push(`<code>status:${escapeHtml(row.status)}</code>`);
  chips.push(`<code>${escapeHtml(formatIso(row.created_at))}</code>`);
  return chips.join("");
}

function renderTimeline(payload) {
  if (!els.timelineList) return;
  const rows = filteredTimelineRows(payload);
  const filtered = rows.filter((row) => passesFilter(row, logbookState.filter) && passesSearchFilters(row));
  if (!filtered.length) {
    els.timelineList.innerHTML = '<p class="muted">No timeline entries match the current filter.</p>';
    return;
  }
  els.timelineList.innerHTML = filtered
    .slice(0, 80)
    .map((row) => {
      const severity = String(row.severity || "info").toLowerCase();
      const channelBadge = `<span class="badge ${row.channel === "control" ? "ok" : "info"}">${escapeHtml(row.channel || "unknown")}</span>`;
      const severityBadge = `<span class="badge ${severity}">${escapeHtml(severity)}</span>`;
      const logKind = String(row.log_kind || "").toLowerCase();
      const kindBadge = logKind ? `<span class="badge ${logKind}">${escapeHtml(logKind)}</span>` : "";
      const type = escapeHtml(String(row.event_type || "event"));
      const headline = escapeHtml(String(row.headline || row.event_type || "event"));
      const message = escapeHtml(String(row.message || row.payload_preview || ""));
      return `
        <article class="timeline-item">
          <div class="timeline-dot ${severity}"></div>
          <div class="timeline-main">
            <div class="timeline-top">
              <span class="timeline-type">${type}</span>
              ${channelBadge}
              ${kindBadge}
              ${severityBadge}
            </div>
            <p class="timeline-headline">${headline}</p>
            ${message ? `<p class="timeline-message">${message}</p>` : ""}
            <div class="timeline-meta">${timelineMetaChips(row)}</div>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderFilterSelects(payload) {
  const timeline = Array.isArray(payload.timeline) ? payload.timeline : [];
  const agentIds = Array.from(
    new Set(
      timeline
        .map((row) => String(row?.agent_id || "").trim())
        .filter(Boolean),
    ),
  ).sort();
  const projectIds = Array.from(
    new Set(
      timeline
        .map((row) => String(row?.project_id || "").trim())
        .filter(Boolean),
    ),
  ).sort();
  const logKinds = Array.from(
    new Set(
      timeline
        .map((row) => String(row?.log_kind || "").trim().toLowerCase())
        .filter(Boolean),
    ),
  ).sort();

  if (els.timelineAgentFilter) {
    const current = String(logbookState.agentId || "");
    els.timelineAgentFilter.innerHTML =
      '<option value=\"\">All agents</option>' +
      agentIds.map((id) => `<option value=\"${escapeHtml(id)}\">${escapeHtml(id)}</option>`).join("");
    els.timelineAgentFilter.value = agentIds.includes(current) ? current : "";
    logbookState.agentId = els.timelineAgentFilter.value;
  }
  if (els.timelineProjectFilter) {
    const current = String(logbookState.projectId || "");
    els.timelineProjectFilter.innerHTML =
      '<option value=\"\">All projects</option>' +
      projectIds.map((id) => `<option value=\"${escapeHtml(id)}\">${escapeHtml(id)}</option>`).join("");
    els.timelineProjectFilter.value = projectIds.includes(current) ? current : "";
    logbookState.projectId = els.timelineProjectFilter.value;
  }
  if (els.timelineKindFilter) {
    const current = String(logbookState.logKind || "");
    els.timelineKindFilter.innerHTML =
      '<option value=\"\">All log categories</option>' +
      logKinds.map((id) => `<option value=\"${escapeHtml(id)}\">${escapeHtml(id)}</option>`).join("");
    els.timelineKindFilter.value = logKinds.includes(current) ? current : "";
    logbookState.logKind = els.timelineKindFilter.value;
  }
}

function toolChipRow(tools = {}) {
  return [
    boolBadge(Boolean(tools.gh), "gh"),
    boolBadge(Boolean(tools.gcloud), "gcloud"),
    boolBadge(Boolean(tools.docker), "docker"),
    boolBadge(Boolean(tools.node), "node"),
  ].join("");
}

function renderAgentLanes(payload) {
  if (!els.agentLanes) return;
  const rows = Array.isArray(payload.agent_lanes) ? payload.agent_lanes : [];
  if (!rows.length) {
    els.agentLanes.innerHTML = '<p class="muted">No agent lanes available.</p>';
    return;
  }
  els.agentLanes.innerHTML = rows
    .slice(0, 12)
    .map((row) => {
      const host = row.host || {};
      const online = Boolean(row.online);
      const memberships = Array.isArray(row.memberships) ? row.memberships : [];
      return `
        <article class="lane-card">
          <div class="lane-top">
            <p class="lane-title">${escapeHtml(row.agent_id || "agent")}</p>
            <span class="badge ${online ? "ok" : "warning"}">${online ? "online" : "offline"}</span>
          </div>
          <p class="lane-meta">${escapeHtml(host.host_id || "--")} · ${escapeHtml(host.host_class || "--")} · ${escapeHtml(host.node_role || "--")}</p>
          <p class="lane-meta">${escapeHtml(host.hostname || "--")} · heartbeat_age=${escapeHtml(row.heartbeat_age_seconds ?? "--")}</p>
          <div class="inline-chips">
            ${(memberships.length ? memberships : [row.labels_membership_id || "membership:unknown"]).map((m) => `<span class="inline-chip">${escapeHtml(m)}</span>`).join("")}
          </div>
          <div class="inline-chips">${toolChipRow(row.tools || {})}</div>
          <p class="lane-meta">Recent events: ${escapeHtml(row.recent_event_count || 0)} · Last: ${escapeHtml(formatIso(row.last_event_at || ""))}</p>
          ${row.last_event_headline ? `<p class="lane-meta">${escapeHtml(row.last_event_headline)}</p>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderWorkstreams(payload) {
  if (!els.workstreams) return;
  const rows = Array.isArray(payload.workstreams) ? payload.workstreams : [];
  if (!rows.length) {
    els.workstreams.innerHTML = '<p class="muted">No workstream card activity available.</p>';
    return;
  }
  els.workstreams.innerHTML = rows
    .slice(0, 10)
    .map((row) => {
      const counts = row.counts || {};
      const priorityCounts = row.priority_counts || {};
      const recentTitles = Array.isArray(row.recent_titles) ? row.recent_titles : [];
      return `
        <article class="workstream-card">
          <div class="card-top">
            <p class="card-title">${escapeHtml(row.workstream || "Workstream")}</p>
            <span class="badge info">${escapeHtml(pluralize(row.card_count || 0, "card"))}</span>
          </div>
          <div class="count-bands">
            <div class="count-band"><span class="n">${escapeHtml(counts.backlog || 0)}</span><span class="k">backlog</span></div>
            <div class="count-band"><span class="n">${escapeHtml(counts.in_progress || 0)}</span><span class="k">in progress</span></div>
            <div class="count-band"><span class="n">${escapeHtml(counts.blocked || 0)}</span><span class="k">blocked</span></div>
            <div class="count-band"><span class="n">${escapeHtml(counts.done || 0)}</span><span class="k">done</span></div>
          </div>
          <div class="inline-chips">
            <span class="inline-chip ${Number(priorityCounts.urgent || 0) > 0 ? "error" : ""}">urgent:${escapeHtml(priorityCounts.urgent || 0)}</span>
            <span class="inline-chip ${Number(priorityCounts.high || 0) > 0 ? "warn" : ""}">high:${escapeHtml(priorityCounts.high || 0)}</span>
            <span class="inline-chip">medium:${escapeHtml(priorityCounts.medium || 0)}</span>
            <span class="inline-chip">low:${escapeHtml(priorityCounts.low || 0)}</span>
          </div>
          ${recentTitles.length ? `<ul class="simple-list compact">${recentTitles.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderTrackedProjects(payload) {
  if (!els.trackedProjects) return;
  const rows = Array.isArray(payload.tracked_projects) ? payload.tracked_projects : [];
  if (!rows.length) {
    els.trackedProjects.innerHTML = '<p class="muted">No tracked project rows available.</p>';
    return;
  }
  els.trackedProjects.innerHTML = rows
    .slice(0, 8)
    .map((row) => {
      const githubUrls = Array.isArray(row.github_urls) ? row.github_urls : [];
      const localPaths = Array.isArray(row.local_paths) ? row.local_paths : [];
      return `
        <article class="project-card">
          <div class="card-top">
            <p class="card-title">${escapeHtml(row.name || row.id || "project")}</p>
            <span class="badge ${String(row.health || "").toLowerCase() === "healthy" ? "ok" : "warning"}">${escapeHtml(row.health || "unknown")}</span>
          </div>
          <p class="card-meta">id=${escapeHtml(row.id || "--")} · events=${escapeHtml(row.event_count || 0)}</p>
          <p class="card-meta">local=${escapeHtml(row.local_path_check || "--")} · github=${escapeHtml(row.github_check || "--")}</p>
          <div class="inline-chips">
            <span class="inline-chip ${row.missing_local ? "warn" : "ok"}">missing_local:${row.missing_local ? "yes" : "no"}</span>
            <span class="inline-chip ${row.missing_github ? "warn" : "ok"}">missing_github:${row.missing_github ? "yes" : "no"}</span>
          </div>
          ${githubUrls.length ? `<p class="card-meta">GitHub: ${githubUrls.map((u) => escapeHtml(String(u).replace(/^https:\/\/github\.com\//, ""))).join(", ")}</p>` : ""}
          ${localPaths.length ? `<p class="card-meta">Local: ${escapeHtml(localPaths[0])}</p>` : ""}
          ${row.last_event_headline ? `<p class="card-meta">Last: ${escapeHtml(row.last_event_headline)} · ${escapeHtml(formatIso(row.last_event_at || ""))}</p>` : ""}
        </article>
      `;
    })
    .join("");
}

function itemTitle(item) {
  const title = String(item?.title || item?.message || item?.id || "item");
  const status = String(item?.status || "");
  const priority = String(item?.priority || "");
  const bits = [];
  if (priority) bits.push(`priority:${priority}`);
  if (status) bits.push(`status:${status}`);
  return `${escapeHtml(title)}${bits.length ? ` <code>${bits.map(escapeHtml).join(" · ")}</code>` : ""}`;
}

function renderProgressDigest(payload) {
  const digest = payload.progress_digest || {};
  const roadmap = digest.roadmap || {};
  renderSimpleList(els.roadmapNow, (roadmap.now || []).map((item) => itemTitle(item)), "No roadmap items in Now.");
  renderSimpleList(els.roadmapNext, (roadmap.next || []).map((item) => itemTitle(item)), "No roadmap items in Next.");
  renderSimpleList(els.nextActions, (digest.next_actions || []).map((item) => itemTitle(item)), "No next actions.");
}

function renderControlTasks(payload) {
  if (!els.controlTaskList) return;
  const rows = payload.control_tasks?.visible;
  if (!Array.isArray(rows) || !rows.length) {
    els.controlTaskList.innerHTML = '<p class="muted">No visible control tasks.</p>';
    return;
  }
  els.controlTaskList.innerHTML = rows
    .slice(0, 16)
    .map((row) => {
      const required = Array.isArray(row.required_capabilities) ? row.required_capabilities : [];
      return `
        <article class="task-card">
          <div class="card-top">
            <p class="card-title">${escapeHtml(row.display_title || row.title || row.task_id || "task")}</p>
            <span class="badge ${String(row.status || "").toLowerCase() === "failed" ? "error" : "info"}">${escapeHtml(row.status || "unknown")}</span>
          </div>
          <p class="card-meta">${escapeHtml(row.task_id || "")} · priority=${escapeHtml(row.priority ?? "--")} · attempts=${escapeHtml(row.attempts ?? 0)}/${escapeHtml(row.max_attempts ?? "--")}</p>
          <p class="card-meta">created_by=${escapeHtml(row.created_by || "--")} · updated=${escapeHtml(formatIso(row.updated_at || row.created_at || ""))}</p>
          <div class="inline-chips">${required.slice(0, 8).map((cap) => `<span class="inline-chip">${escapeHtml(cap)}</span>`).join("") || '<span class="inline-chip">no_caps</span>'}</div>
          ${row.error_text ? `<p class="card-meta">${escapeHtml(String(row.error_text).slice(0, 220))}</p>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderProtocol(payload) {
  const protocol = payload.logging_protocol || {};
  setText(els.protocolGoal, protocol.goal || "No protocol guidance available.");
  const categories = Array.isArray(protocol.categories) ? protocol.categories : [];
  const templateRows = [];
  if (categories.length) {
    templateRows.push(
      `<strong>Categories:</strong> ${categories
        .map((row) => `${escapeHtml(row.label || row.id || "category")} (${escapeHtml(row.id || "")})`)
        .join(", ")}`,
    );
  }
  templateRows.push(...(protocol.entry_template || []));
  renderSimpleList(els.protocolTemplate, templateRows, "No template defined.");
  renderSimpleList(els.protocolRules, protocol.rules || [], "No rules defined.");
}

function renderEventMix(payload) {
  const mix = payload.event_mix || {};
  renderBarList(els.eventMixSeverity, mix.by_severity || {}, { maxItems: 6 });
  renderBarList(els.eventMixCategory, mix.by_category || {}, { maxItems: 6 });
  renderBarList(els.eventMixLogKind, mix.by_log_kind || {}, { maxItems: 6 });
  const eventTypes = Array.isArray(mix.top_event_types) ? mix.top_event_types : [];
  renderSimpleList(
    els.eventTypeTop,
    eventTypes.map((row) => `${escapeHtml(row.event_type || "event")}: <strong>${escapeHtml(row.count || 0)}</strong>`),
    "No event types logged.",
  );
}

function communicationLedgerRows(rows, empty) {
  if (!Array.isArray(rows) || !rows.length) return [String(empty)];
  return rows.slice(0, 6).map((row) => {
    const headline = String(row?.headline || row?.event_type || "entry");
    const when = formatIso(row?.created_at || "");
    const agent = String(row?.agent_id || row?.channel || "");
    const project = String(row?.project_id || "");
    const metaBits = [agent, project, when].filter(Boolean).join(" · ");
    return `${headline}${metaBits ? ` — ${metaBits}` : ""}`;
  });
}

function renderCommunicationViews(payload) {
  const views = payload.communication_views || {};
  const categories = views.categories || {};
  const order = ["progress", "decision", "verification", "incident", "handoff"];
  if (els.communicationCategoryCards) {
    const cards = order.map((kind) => {
      const row = categories[kind] || {};
      const count = Number(row.count || 0);
      const latestHeadline = String(row.latest_headline || "");
      const latestAt = formatIso(row.latest_at || "");
      const tone = kind === "incident" ? "error" : kind === "decision" ? "warn" : kind === "verification" ? "ok" : "";
      return `
        <article class="comm-card">
          <div class="card-top">
            <h4>${escapeHtml(kind)}</h4>
            <span class="badge ${tone || "info"}">${count}</span>
          </div>
          <p>${latestHeadline ? escapeHtml(latestHeadline) : "No recent entries."}</p>
          <div class="comm-count">
            <span class="card-meta">${latestAt !== "--" ? latestAt : "No timestamp"}</span>
            <span class="inline-chip">${escapeHtml(String(row.latest_agent_id || row.latest_project_id || "--"))}</span>
          </div>
        </article>
      `;
    });
    els.communicationCategoryCards.innerHTML = cards.join("");
  }
  renderSimpleList(els.decisionLedger, communicationLedgerRows(views.decision_ledger, "No decisions logged."), "No decisions logged.");
  renderSimpleList(els.handoffLedger, communicationLedgerRows(views.handoff_ledger, "No handoffs logged."), "No handoffs logged.");
  const incidentRows = communicationLedgerRows(views.incident_ledger, "No incidents logged.");
  const verificationRows = communicationLedgerRows(views.verification_ledger, "No verifications logged.");
  renderSimpleList(els.incidentLedger, incidentRows, "No incidents logged.");
  renderSimpleList(els.verificationLedger, verificationRows, "No verifications logged.");
}

function renderToolbarState() {
  if (!els.timelineToolbar) return;
  els.timelineToolbar.querySelectorAll("[data-filter]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-filter") === logbookState.filter);
  });
}

function render(payload) {
  logbookState.payload = payload;
  renderSummary(payload);
  renderStatusStrip(payload);
  renderViewControlsStatus(payload);
  renderBuildCard(payload);
  renderTrends(payload);
  renderEventMix(payload);
  renderCommunicationViews(payload);
  renderAgentLanes(payload);
  renderWorkstreams(payload);
  renderTrackedProjects(payload);
  renderProgressDigest(payload);
  renderControlTasks(payload);
  renderProtocol(payload);
  renderToolbarState();
  renderFilterSelects(payload);
  renderTimeline(payload);
}

async function loadLogbook({ refresh = false } = {}) {
  const client = window.SapphireFrontendLogbookClient;
  let payload;
  const requestedLimit = Number(logbookState.eventLimit || 100);
  if (client && typeof client.fetchLogbook === "function") {
    payload = await client.fetchLogbook({ refresh, eventLimit: requestedLimit });
  } else {
    const url = `/api/frontend/logbook?event_limit=${encodeURIComponent(String(requestedLimit))}${refresh ? "&refresh=true" : ""}`;
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    payload = await response.json();
  }
  render(payload);
}

function setLoadingError(message) {
  if (!els.timelineList) return;
  els.timelineList.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
}

function bindEvents() {
  els.refreshButton?.addEventListener("click", () => {
    loadLogbook({ refresh: true }).catch((error) => setLoadingError(`Refresh failed: ${error.message}`));
  });
  els.timelineToolbar?.addEventListener("click", (event) => {
    const target = event.target instanceof HTMLElement ? event.target.closest("[data-filter]") : null;
    if (!target) return;
    logbookState.filter = String(target.getAttribute("data-filter") || "all");
    renderToolbarState();
    if (logbookState.payload) {
      renderTimeline(logbookState.payload);
    }
  });
  els.timelineSearch?.addEventListener("input", () => {
    logbookState.search = String(els.timelineSearch?.value || "");
    if (logbookState.payload) renderTimeline(logbookState.payload);
  });
  els.timelineAgentFilter?.addEventListener("change", () => {
    logbookState.agentId = String(els.timelineAgentFilter?.value || "");
    if (logbookState.payload) renderTimeline(logbookState.payload);
  });
  els.timelineProjectFilter?.addEventListener("change", () => {
    logbookState.projectId = String(els.timelineProjectFilter?.value || "");
    if (logbookState.payload) renderTimeline(logbookState.payload);
  });
  els.timelineKindFilter?.addEventListener("change", () => {
    logbookState.logKind = String(els.timelineKindFilter?.value || "");
    if (logbookState.payload) renderTimeline(logbookState.payload);
  });
  els.viewTimeRange?.addEventListener("change", () => {
    logbookState.timeRange = String(els.viewTimeRange?.value || "6h");
    saveViewPrefs();
    if (logbookState.payload) {
      renderViewControlsStatus(logbookState.payload);
      renderTrends(logbookState.payload);
      renderTimeline(logbookState.payload);
    }
  });
  els.viewEventLimit?.addEventListener("change", () => {
    const nextValue = Number.parseInt(String(els.viewEventLimit?.value || "100"), 10);
    logbookState.eventLimit = [50, 100, 200].includes(nextValue) ? nextValue : 100;
    saveViewPrefs();
    loadLogbook({ refresh: true }).catch((error) => setLoadingError(`Reload failed: ${error.message}`));
  });
  els.trendBucketCount?.addEventListener("change", () => {
    const nextValue = Number.parseInt(String(els.trendBucketCount?.value || "10"), 10);
    logbookState.trendBucketCount = [8, 10, 12, 16].includes(nextValue) ? nextValue : 10;
    saveViewPrefs();
    if (logbookState.payload) {
      renderViewControlsStatus(logbookState.payload);
      renderTrends(logbookState.payload);
    }
  });
}

async function boot() {
  loadViewPrefs();
  applyViewControlsToDom();
  bindEvents();
  await loadLogbook({ refresh: true });
  if (pollHandle) clearInterval(pollHandle);
  pollHandle = window.setInterval(() => {
    loadLogbook().catch(() => {
      // keep last successful UI state visible
    });
  }, POLL_MS);
}

boot().catch((error) => {
  setLoadingError(`Failed to load logbook: ${error.message}`);
});
