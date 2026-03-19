(function () {
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

  function renderSimpleList(node, rows, empty = "No entries.") {
    if (!node) return;
    if (!Array.isArray(rows) || rows.length === 0) {
      node.innerHTML = `<li>${escapeHtml(empty)}</li>`;
      return;
    }
    node.innerHTML = rows
      .map((row) => `<li>${typeof row === "string" ? escapeHtml(row) : row}</li>`)
      .join("");
  }

  function badgeTone(kind) {
    const text = String(kind || "").toLowerCase();
    if (text === "incident") return "error";
    if (text === "verification") return "ok";
    if (text === "decision") return "warn";
    if (text === "handoff") return "handoff";
    return "info";
  }

  function communicationLedgerRows(rows, empty) {
    if (!Array.isArray(rows) || !rows.length) return [String(empty || "No entries.")];
    return rows.slice(0, 6).map((row) => {
      const headline = String(row?.headline || row?.event_type || "entry");
      const when = formatIso(row?.created_at || "");
      const agent = String(row?.agent_id || row?.channel || "");
      const project = String(row?.project_id || "");
      const metaBits = [agent, project, when].filter(Boolean).join(" · ");
      return `${headline}${metaBits ? ` — ${metaBits}` : ""}`;
    });
  }

  function renderCommunicationCategoryCards(node, communicationViews) {
    if (!node) return;
    const categories = communicationViews && typeof communicationViews === "object" ? (communicationViews.categories || {}) : {};
    const order = ["progress", "decision", "verification", "incident", "handoff"];
    if (!order.some((kind) => categories && categories[kind])) {
      node.innerHTML = '<p class="muted">No communication categories available.</p>';
      return;
    }
    node.innerHTML = order
      .map((kind) => {
        const row = categories[kind] || {};
        const count = Number(row.count || 0);
        const latestHeadline = String(row.latest_headline || "");
        const latestAt = formatIso(row.latest_at || "");
        const latestActor = String(row.latest_agent_id || row.latest_project_id || "--");
        const tone = badgeTone(kind);
        return `
          <article class="lw-card">
            <div class="lw-card-top">
              <h4>${escapeHtml(kind)}</h4>
              <span class="lw-badge ${tone}">${count}</span>
            </div>
            <p class="lw-card-copy">${latestHeadline ? escapeHtml(latestHeadline) : "No recent entries."}</p>
            <div class="lw-card-foot">
              <span class="lw-meta">${escapeHtml(latestAt)}</span>
              <span class="lw-chip">${escapeHtml(latestActor)}</span>
            </div>
          </article>
        `;
      })
      .join("");
  }

  function renderCommunicationLedgers(targets, communicationViews) {
    const views = communicationViews && typeof communicationViews === "object" ? communicationViews : {};
    renderSimpleList(targets?.decision, communicationLedgerRows(views.decision_ledger, "No decisions logged."), "No decisions logged.");
    renderSimpleList(targets?.handoff, communicationLedgerRows(views.handoff_ledger, "No handoffs logged."), "No handoffs logged.");
    renderSimpleList(targets?.incident, communicationLedgerRows(views.incident_ledger, "No incidents logged."), "No incidents logged.");
    renderSimpleList(targets?.verification, communicationLedgerRows(views.verification_ledger, "No verifications logged."), "No verifications logged.");
  }

  function renderMiniTimeline(node, timeline, options) {
    if (!node) return;
    const opts = options && typeof options === "object" ? options : {};
    const limit = Number(opts.limit || 8);
    const rows = Array.isArray(timeline) ? timeline : [];
    if (!rows.length) {
      node.innerHTML = '<p class="muted">No logbook timeline entries available.</p>';
      return;
    }
    node.innerHTML = rows
      .slice(0, limit)
      .map((row) => {
        const kind = String(row?.log_kind || "progress");
        const severity = String(row?.severity || "info");
        const headline = String(row?.headline || row?.event_type || "entry");
        const meta = [row?.agent_id || row?.channel || "", row?.project_id || "", formatIso(row?.created_at || "")].filter(Boolean).join(" · ");
        return `
          <article class="lw-timeline-item">
            <div class="lw-timeline-row">
              <span class="lw-badge ${badgeTone(kind)}">${escapeHtml(kind)}</span>
              <span class="lw-badge ${badgeTone(severity)}">${escapeHtml(severity)}</span>
            </div>
            <p class="lw-timeline-head">${escapeHtml(headline)}</p>
            <p class="lw-meta">${escapeHtml(meta)}</p>
          </article>
        `;
      })
      .join("");
  }

  function renderLogbookSummary(node, payload) {
    if (!node) return;
    const p = payload && typeof payload === "object" ? payload : {};
    const s = p.summary && typeof p.summary === "object" ? p.summary : {};
    const rows = [
      `policy=${String(s.policy_mode || "unknown")}${s.policy_lock_applied ? " (lock)" : ""}`,
      `drift=${Boolean(s.policy_drift_detected)}`,
      `timeline=${Number(s.timeline_count || 0)} (task=${Number(s.task_event_count || 0)} system=${Number(s.system_event_count || 0)})`,
      `queue=Q${Number(s.tasks_queued || 0)} L${Number(s.tasks_leased || 0)} F${Number(s.tasks_failed || 0)}`,
      `roadmap=Now ${Number(s.roadmap_now_count || 0)} · Next ${Number(s.roadmap_next_count || 0)}`,
    ];
    renderSimpleList(node, rows, "No logbook summary available.");
  }

  window.SapphireLogbookWidgets = {
    escapeHtml,
    formatIso,
    renderSimpleList,
    renderCommunicationCategoryCards,
    renderCommunicationLedgers,
    renderMiniTimeline,
    renderLogbookSummary,
  };
})();
