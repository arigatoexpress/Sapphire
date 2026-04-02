const els = {
  generated: document.getElementById("org-generated"),
  metricWorkspaces: document.getElementById("metric-workspaces"),
  metricProjects: document.getElementById("metric-projects"),
  metricAgents: document.getElementById("metric-agents"),
  metricModel: document.getElementById("metric-model"),
  modelSubtitle: document.getElementById("model-subtitle"),
  modelList: document.getElementById("org-model"),
  blockers: document.getElementById("org-blockers"),
  operatingUnitsGrid: document.getElementById("operating-units-grid"),
  workspaceGrid: document.getElementById("workspace-grid"),
  railsTable: document.getElementById("rails-table"),
  orgArchitectureMermaid: document.getElementById("org-architecture-mermaid"),
  orgTelemetryBars: document.getElementById("org-telemetry-bars"),
  executorToolGrid: document.getElementById("executor-tool-grid"),
  executorAttestationList: document.getElementById("executor-attestation-list"),
  executorPrimaryDetails: document.getElementById("executor-primary-details"),
  executorReadinessRecommendations: document.getElementById("executor-readiness-recommendations"),
  logbookSummary: document.getElementById("org-logbook-summary"),
  logbookCommCards: document.getElementById("org-comm-cards"),
  logbookDecisionLedger: document.getElementById("org-decision-ledger"),
  logbookHandoffLedger: document.getElementById("org-handoff-ledger"),
  logbookIncidentLedger: document.getElementById("org-incident-ledger"),
  logbookVerificationLedger: document.getElementById("org-verification-ledger"),
  logbookTimeline: document.getElementById("org-logbook-timeline"),
  policyList: document.getElementById("policy-list"),
  recommendations: document.getElementById("org-recommendations"),
  refreshButton: document.getElementById("refresh-org"),
};

function setText(node, value) {
  if (!node) return;
  node.textContent = value;
}

function formatIso(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function renderList(node, rows) {
  if (!node) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    node.innerHTML = "<li>None.</li>";
    return;
  }
  node.innerHTML = rows.map((row) => `<li>${row}</li>`).join("");
}

function renderMermaid(container, source) {
  if (!container) return;
  container.innerHTML = "";
  if (!source) {
    container.innerHTML = '<p class="muted">No diagram available.</p>';
    return;
  }
  const pre = document.createElement("pre");
  pre.className = "mermaid";
  pre.textContent = source;
  container.appendChild(pre);
}

async function runMermaidRender() {
  if (!window.mermaid || typeof window.mermaid.run !== "function") {
    return;
  }
  const nodes = Array.from(document.querySelectorAll("pre.mermaid"));
  nodes.forEach((node) => node.removeAttribute("data-processed"));
  try {
    await window.mermaid.run({ nodes });
  } catch (_error) {
    // Keep raw chart content visible if mermaid rendering fails.
  }
}

function ratioPercent(value, total) {
  const safeValue = Number(value || 0);
  const safeTotal = Number(total || 0);
  if (!Number.isFinite(safeValue) || !Number.isFinite(safeTotal) || safeTotal <= 0) return 0;
  return Math.max(0, Math.min((safeValue / safeTotal) * 100, 100));
}

function renderTelemetry(payload) {
  if (!els.orgTelemetryBars) return;
  const controlOverview = payload.control_plane && payload.control_plane.overview && typeof payload.control_plane.overview === "object"
    ? payload.control_plane.overview
    : {};
  const tasks = controlOverview.tasks && typeof controlOverview.tasks === "object" ? controlOverview.tasks : {};
  const rails = Array.isArray(payload?.trading_operations?.rails) ? payload.trading_operations.rails : [];
  const railsReady = rails.filter((row) => String(row.readiness || "") === "ready").length;
  const railsBlocked = rails.filter((row) => String(row.readiness || "") === "blocked").length;

  const agentsOnline = Number(controlOverview.agents_executor_online ?? controlOverview.agents_online ?? 0);
  const agentsTotal = Number(controlOverview.agents_executor_total ?? controlOverview.agents_total ?? controlOverview.agents_registered ?? 0);
  const queued = Number(tasks.queued || 0);
  const leased = Number(tasks.leased || 0);
  const failed = Number(tasks.failed || 0);

  const rows = [
    { label: "Agent Coverage", value: `${agentsOnline}/${agentsTotal}`, percent: ratioPercent(agentsOnline, Math.max(agentsTotal, 1)) },
    { label: "Queue Pressure", value: `${queued} queued`, percent: ratioPercent(queued, Math.max(queued + leased + 2, 3)) },
    { label: "Lease Throughput", value: `${leased} leased`, percent: ratioPercent(leased, Math.max(queued + leased, 1)) },
    { label: "Rail Readiness", value: `${railsReady}/${rails.length || 0} ready`, percent: ratioPercent(railsReady, Math.max(rails.length, 1)) },
    { label: "Blocked Rails", value: `${railsBlocked}`, percent: ratioPercent(railsBlocked, Math.max(rails.length, 1)) },
    { label: "Failure Load", value: `${failed}`, percent: ratioPercent(failed, Math.max(queued + leased + failed, 1)) },
  ];

  els.orgTelemetryBars.innerHTML = rows
    .map(
      (row) => `
      <article class="telemetry-item">
        <div class="telemetry-head">
          <span class="telemetry-label">${row.label}</span>
          <strong class="telemetry-value">${row.value}</strong>
        </div>
        <div class="telemetry-track">
          <div class="telemetry-fill" style="width:${row.percent.toFixed(1)}%"></div>
        </div>
      </article>
    `
    )
    .join("");
}

function yesNo(value) {
  return value ? "yes" : "no";
}

function renderExecutorTrust(opsInventory) {
  const readiness = opsInventory?.executor_readiness && typeof opsInventory.executor_readiness === "object"
    ? opsInventory.executor_readiness
    : {};
  const attestation = readiness?.attestation && typeof readiness.attestation === "object" ? readiness.attestation : {};
  const tools = readiness?.tool_summary && typeof readiness.tool_summary === "object" ? readiness.tool_summary : {};
  const primary = readiness?.primary_executor && typeof readiness.primary_executor === "object" ? readiness.primary_executor : {};
  const primaryHost = primary?.host && typeof primary.host === "object" ? primary.host : {};
  const primaryMembership = primary?.membership && typeof primary.membership === "object" ? primary.membership : {};
  const recs = Array.isArray(readiness?.recommendations) ? readiness.recommendations : [];

  if (els.executorToolGrid) {
    const chips = [
      { label: "gh", ok: Boolean(tools.gh) },
      { label: "cloud bridge", ok: Boolean(tools.gcloud) },
      { label: "docker", ok: Boolean(tools.docker) },
      { label: "node", ok: Boolean(tools.node) },
      { label: "policy lock", ok: Boolean(readiness.effective_policy_lock_applied) },
      { label: "pi hosted", ok: Boolean(attestation.primary_executor_pi_hosted) },
    ];
    els.executorToolGrid.innerHTML = chips
      .map(
        (chip) =>
          `<span class="status-chip ${chip.ok ? "ok" : "warn"}"><strong>${chip.label}</strong><em>${chip.ok ? "ready" : "missing"}</em></span>`,
      )
      .join("");
  }

  if (els.executorAttestationList) {
    const rows = [
      `policy_mode=${String(readiness.policy_mode || "unknown")}`,
      `executors_online=${Number(attestation.online_executor_count || 0)}/${Number(attestation.executor_count || 0)}`,
      `host_attestation_complete=${yesNo(Boolean(attestation.all_online_have_host_attestation))}`,
      `primary_executor_pi_hosted=${yesNo(Boolean(attestation.primary_executor_pi_hosted))}`,
    ];
    els.executorAttestationList.innerHTML = rows.map((row) => `<li>${row}</li>`).join("");
  }

  if (els.executorPrimaryDetails) {
    if (!primary || !Object.keys(primary).length) {
      els.executorPrimaryDetails.innerHTML = "<li>No active executor matched current policy.</li>";
    } else {
      const memberships = Array.isArray(primaryMembership.memberships) ? primaryMembership.memberships : [];
      const rows = [
        `agent_id=${String(primary.agent_id || "--")} · online=${yesNo(Boolean(primary.online))}`,
        `host=${String(primaryHost.host_id || "--")} · class=${String(primaryHost.host_class || "--")} · role=${String(primaryHost.node_role || "--")}`,
        `hostname=${String(primaryHost.hostname || "--")}`,
        `membership_label=${String(primaryMembership.labels_membership_id || "--")}`,
        `memberships=${memberships.join(", ") || "none"}`,
        `workspace=${String(primaryHost.workspace_root || "--")}`,
      ];
      els.executorPrimaryDetails.innerHTML = rows.map((row) => `<li>${row}</li>`).join("");
    }
  }

  if (els.executorReadinessRecommendations) {
    if (!recs.length) {
      els.executorReadinessRecommendations.innerHTML = "<li>No executor readiness actions pending.</li>";
    } else {
      els.executorReadinessRecommendations.innerHTML = recs.map((row) => `<li>${String(row)}</li>`).join("");
    }
  }
}

function buildOrgArchitectureMermaid(payload) {
  const shellName = String(payload?.shell_app?.name || "Sapphire Command Deck");
  const serviceName = String(payload?.shell_app?.service_name || "sapphire-control-plane");
  const rails = Array.isArray(payload?.trading_operations?.rails) ? payload.trading_operations.rails : [];
  const asterRail = rails.find((row) => String(row?.name || "").toLowerCase() === "aster") || {};
  const lighterRail = rails.find((row) => String(row?.name || "").toLowerCase() === "lighter") || {};
  const asterAgent = String(asterRail.preferred_agent_id || "rari1-executor");
  const lighterAgent = String(lighterRail.preferred_agent_id || "kimi-main");
  const asterNode = String(asterRail.preferred_node || "rari1");
  const lighterNode = String(lighterRail.preferred_node || "rari2");
  return `flowchart TB\n  TG[\"Telegram Control Plane\"] --> HUB[\"Local Control Plane\\\\n${serviceName}\"]\n  HUB --> SHELL[\"${shellName}\"]\n  HUB --> Q[\"Lease Queue + Router\"]\n  Q --> A1[\"${asterNode}\\\\n${asterAgent}\"]\n  Q --> A2[\"${lighterNode}\\\\n${lighterAgent}\"]\n  A1 --> V1[\"Aster Rail\"]\n  A2 --> V2[\"Lighter Rail\"]\n  HUB --> PRJ[\"Projects: PM | THO | Cointracker | Workspace\"]\n  HUB --> OBS[\"Architecture + Organization Dashboards\"]`;
}

function renderWorkspaces(rows) {
  if (!els.workspaceGrid) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    els.workspaceGrid.innerHTML = '<p class="muted">No workspaces configured.</p>';
    return;
  }

  els.workspaceGrid.innerHTML = rows
    .map((row) => {
      const metrics = row.metrics && typeof row.metrics === "object" ? row.metrics : {};
      const projects = Array.isArray(row.projects) ? row.projects : [];
      const chips = projects
        .map((project) => {
          const name = String(project.name || project.id || "project");
          const health = String(project.health || "unknown");
          return `<span class="workspace-chip">${name} · ${health}</span>`;
        })
        .join("");
      return `
        <article class="workspace-card">
          <h4>${String(row.name || "Workspace")}</h4>
          <p class="workspace-meta">${String(row.purpose || "")}</p>
          <p class="workspace-meta">status=${String(row.status || "unknown")} · projects=${Number(metrics.project_count || 0)} · healthy=${Number(metrics.healthy_count || 0)}</p>
          <div>${chips || '<span class="workspace-chip">No linked projects</span>'}</div>
        </article>
      `;
    })
    .join("");
}

function renderOperatingUnits(rows) {
  if (!els.operatingUnitsGrid) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    els.operatingUnitsGrid.innerHTML = '<p class="muted">No operating units configured.</p>';
    return;
  }

  els.operatingUnitsGrid.innerHTML = rows
    .map((row) => {
      const surfaces = Array.isArray(row.surfaces) ? row.surfaces : [];
      const roots = Array.isArray(row.roots) ? row.roots : [];
      return `
        <article class="workspace-card">
          <h4>${String(row.name || "Unit")}</h4>
          <p class="workspace-meta">${String(row.purpose || "")}</p>
          <p class="workspace-meta">surfaces=${surfaces.join(", ") || "none"}</p>
          <div>${roots.map((root) => `<span class="workspace-chip">${String(root)}</span>`).join("") || '<span class="workspace-chip">No roots declared</span>'}</div>
        </article>
      `;
    })
    .join("");
}

function railBadge(status) {
  const safe = String(status || "blocked").toLowerCase();
  if (safe === "ready") return '<span class="badge ready">ready</span>';
  if (safe === "degraded") return '<span class="badge degraded">degraded</span>';
  return '<span class="badge blocked">blocked</span>';
}

function renderRails(rows) {
  if (!els.railsTable) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    els.railsTable.innerHTML = '<tr><td colspan="5">No trading rails configured.</td></tr>';
    return;
  }
  els.railsTable.innerHTML = rows
    .map(
      (row) => `
      <tr>
        <td>${String(row.name || row.id || "rail")}</td>
        <td>${String(row.preferred_node || "--")}</td>
        <td>${String(row.preferred_agent_id || "--")}</td>
        <td>${String(row.required_membership_id || "--")}</td>
        <td>${railBadge(row.readiness)}</td>
      </tr>
    `
    )
    .join("");
}

function renderPolicy(policy, policyDrift = {}) {
  const safe = policy && typeof policy === "object" ? policy : {};
  const drift = policyDrift && typeof policyDrift === "object" ? policyDrift : {};
  const mode = String(safe.mode || "open");
  const effectiveLockApplied = Boolean(safe.effective_policy_lock_applied);
  const agents = Array.isArray(safe.allowed_executor_agent_ids) ? safe.allowed_executor_agent_ids : [];
  const memberships = Array.isArray(safe.allowed_executor_membership_ids)
    ? safe.allowed_executor_membership_ids
    : [];
  const expected = drift.expected && typeof drift.expected === "object" ? drift.expected : {};
  const observed = drift.observed && typeof drift.observed === "object" ? drift.observed : {};
  const mismatches = Array.isArray(drift.mismatches) ? drift.mismatches : [];

  const rows = [
    `effective_mode=${mode}${effectiveLockApplied ? " (lock-applied)" : ""}`,
    `effective_allowed_agents=${agents.length ? agents.join(", ") : "none"}`,
    `effective_allowed_memberships=${memberships.length ? memberships.join(", ") : "none"}`,
    `updated_by=${String(safe.updated_by || "system")}`,
  ];
  if (Boolean(drift.enabled)) {
    rows.unshift(`policy_lock=${Boolean(drift.enabled)} drift=${Boolean(drift.drift_detected)}`);
    if (String(expected.mode || "")) rows.push(`expected_mode=${String(expected.mode)}`);
    if (String(observed.mode || "")) rows.push(`observed_mode=${String(observed.mode)}`);
    const observedAgents = Array.isArray(observed.allowed_executor_agent_ids) ? observed.allowed_executor_agent_ids : [];
    const observedMemberships = Array.isArray(observed.allowed_executor_membership_ids)
      ? observed.allowed_executor_membership_ids
      : [];
    if (observedAgents.length) rows.push(`observed_allowed_agents=${observedAgents.join(", ")}`);
    if (observedMemberships.length) rows.push(`observed_allowed_memberships=${observedMemberships.join(", ")}`);
    if (mismatches.length) {
      rows.push(
        `mismatches=${mismatches
          .map((row) => String(row?.field || "unknown"))
          .filter(Boolean)
          .join(", ")}`,
      );
    }
  }
  renderList(els.policyList, rows);
}

function renderSharedLogbook(logbookPayload) {
  const client = window.SapphireFrontendLogbookClient;
  if (client && typeof client.renderSharedWidgets === "function") {
    client.renderSharedWidgets(
      {
        summary: els.logbookSummary,
        commCards: els.logbookCommCards,
        decision: els.logbookDecisionLedger,
        handoff: els.logbookHandoffLedger,
        incident: els.logbookIncidentLedger,
        verification: els.logbookVerificationLedger,
        timeline: els.logbookTimeline,
      },
      logbookPayload,
      { timelineLimit: 8 },
    );
    return;
  }
  const widgets = window.SapphireLogbookWidgets;
  if (!widgets || !logbookPayload || typeof logbookPayload !== "object") return;
  widgets.renderLogbookSummary(els.logbookSummary, logbookPayload);
  widgets.renderCommunicationCategoryCards(els.logbookCommCards, logbookPayload.communication_views);
  widgets.renderCommunicationLedgers(
    {
      decision: els.logbookDecisionLedger,
      handoff: els.logbookHandoffLedger,
      incident: els.logbookIncidentLedger,
      verification: els.logbookVerificationLedger,
    },
    logbookPayload.communication_views,
  );
  widgets.renderMiniTimeline(els.logbookTimeline, logbookPayload.timeline, { limit: 8 });
}

async function loadOrganization(refresh = false) {
  const params = refresh ? "?refresh=true" : "";
  const logbookClient = window.SapphireFrontendLogbookClient;
  const [response, opsResponse, logbookResponse] = await Promise.all([
    fetch(`/api/org/overview${params}`, { cache: "no-store" }),
    fetch(`/api/frontend/ops-status${params}${params ? "&" : "?"}event_limit=20`, { cache: "no-store" }),
    logbookClient && typeof logbookClient.fetchLogbookMaybe === "function"
      ? logbookClient.fetchLogbookMaybe({ refresh, eventLimit: 24 })
      : fetch(`/api/frontend/logbook${params}${params ? "&" : "?"}event_limit=24`, { cache: "no-store" }),
  ]);
  if (!response.ok) {
    throw new Error(`Organization overview failed (${response.status})`);
  }
  const payload = await response.json();
  const opsInventory = opsResponse.ok ? await opsResponse.json() : {};
  const logbookPayload = logbookClient && typeof logbookClient.fetchLogbookMaybe === "function"
    ? (logbookResponse || {})
    : (logbookResponse.ok ? await logbookResponse.json() : {});

  const generatedAt = formatIso(payload.generated_at);
  const workspaces = Array.isArray(payload.workspaces) ? payload.workspaces : [];
  const projectsSummary = payload.projects_summary && typeof payload.projects_summary === "object" ? payload.projects_summary : {};
  const controlOverview = payload.control_plane && payload.control_plane.overview && typeof payload.control_plane.overview === "object"
    ? payload.control_plane.overview
    : {};
  const tasks = controlOverview.tasks && typeof controlOverview.tasks === "object" ? controlOverview.tasks : {};
  const trading = payload.trading_operations && typeof payload.trading_operations === "object" ? payload.trading_operations : {};
  const rails = Array.isArray(trading.rails) ? trading.rails : [];
  const railsReadyCount = rails.filter((row) => String(row.readiness || "") === "ready").length;

  setText(els.generated, generatedAt);
  setText(els.metricWorkspaces, String(workspaces.length));
  setText(els.metricProjects, String(Number(projectsSummary.tracked_project_count || 0)));
  setText(
    els.metricAgents,
    `${Number(controlOverview.agents_executor_online ?? controlOverview.agents_online ?? 0)}/${
      Number(controlOverview.agents_executor_total ?? controlOverview.agents_total ?? controlOverview.agents_registered ?? 0)
    }`,
  );
  setText(els.metricModel, `${String(trading.recommended_model || "hybrid")} (${railsReadyCount}/${rails.length || 0})`);
  setText(els.modelSubtitle, String(trading.description || "Local-first control + edge execution"));

  const organization = payload.organization && typeof payload.organization === "object" ? payload.organization : {};
  const environment = organization.environment && typeof organization.environment === "object" ? organization.environment : {};
  const principles = Array.isArray(organization.principles) ? organization.principles : [];
  renderList(els.modelList, [
    `Organization: ${String(organization.name || "Sapphire Inc")}`,
    `Mission: ${String(organization.mission || "Autonomous organization coordinating projects, research, trading, and local agent infrastructure.")}`,
    `Shell app: ${String(payload.shell_app?.name || "Sapphire Control Plane")}`,
    `Runtime: ${String(environment.primary_runtime || payload.shell_app?.runtime_mode || "unknown")} | Cloud posture: ${String(environment.cloud_posture || "unknown")}`,
    `Source of truth: ${String(environment.source_of_truth_repo || "/Users/aribs/Code/Sapphire")}`,
    `Queue: queued=${Number(tasks.queued || 0)} leased=${Number(tasks.leased || 0)} failed=${Number(tasks.failed || 0)} blocked_review=${Number(tasks.blocked_review || 0)}`,
    ...principles.map((row) => `Principle: ${String(row)}`),
  ]);

  const opsSummary = opsInventory && typeof opsInventory.summary === "object" ? opsInventory.summary : {};
  const queueRoutability = opsInventory && typeof opsInventory.queue_routability === "object" ? opsInventory.queue_routability : {};
  const qrSummary = queueRoutability && typeof queueRoutability.summary === "object" ? queueRoutability.summary : {};
  const policyDrift = opsInventory && typeof opsInventory.policy_drift === "object" ? opsInventory.policy_drift : {};
  const blockerBreakdown = Array.isArray(qrSummary.blocker_breakdown) ? qrSummary.blocker_breakdown : [];
  const orgBlockers = Array.isArray(payload.blockers) && payload.blockers.length
    ? payload.blockers.map((row) => String(row))
    : ["No blockers."];
  if (Boolean(policyDrift.enabled) && Boolean(policyDrift.drift_detected)) {
    const mismatchFields = Array.isArray(policyDrift.mismatches)
      ? policyDrift.mismatches.map((row) => String(row?.field || "unknown")).filter(Boolean)
      : [];
    orgBlockers.unshift(`Executor policy drift detected: ${mismatchFields.join(", ") || "mismatch"}`);
  }
  if (Boolean(opsSummary.queue_stall_detected)) {
    orgBlockers.unshift(`Queue stall detected: ${String(opsSummary.queue_top_blocker_reason || "unknown blocker")}`);
    blockerBreakdown.slice(0, 4).forEach((row) => {
      orgBlockers.push(`Queue blocker ${String(row?.reason || "unknown")}: ${Number(row?.count || 0)}`);
    });
  }
  renderList(els.blockers, orgBlockers);

  renderOperatingUnits(Array.isArray(organization.operating_units) ? organization.operating_units : []);
  renderWorkspaces(workspaces);
  renderRails(rails);
  renderPolicy(payload.executor_policy, policyDrift);
  renderExecutorTrust(opsInventory);
  renderSharedLogbook(logbookPayload);
  renderMermaid(els.orgArchitectureMermaid, buildOrgArchitectureMermaid(payload));
  renderTelemetry(payload);
  const queueRecommendations = Array.isArray(queueRoutability.recommendations) ? queueRoutability.recommendations : [];
  const combinedRecommendations = [];
  if (Array.isArray(payload.recommendations)) {
    combinedRecommendations.push(...payload.recommendations.map((row) => String(row)));
  }
  if (Boolean(policyDrift.enabled) && Boolean(policyDrift.drift_detected)) {
    combinedRecommendations.unshift("[Policy Lock] Stored executor policy drift detected. Reconcile policy to expected lock via set_executor_policy.");
  }
  queueRecommendations.slice(0, 4).forEach((row) => {
    combinedRecommendations.unshift(`[Queue Recovery · ${String(row?.priority || "info")}] ${String(row?.action || row?.id || "recommendation")}`);
  });
  renderList(els.recommendations, combinedRecommendations.length ? combinedRecommendations : ["No recommendations."]);
  await runMermaidRender();
}

if (els.refreshButton) {
  els.refreshButton.addEventListener("click", () => {
    loadOrganization(true).catch((error) => {
      console.error(error);
      renderList(els.blockers, [`Could not refresh org overview: ${error.message}`]);
    });
  });
}

if (window.mermaid && typeof window.mermaid.initialize === "function") {
  window.mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose",
    theme: "dark",
    flowchart: { curve: "basis" },
    themeVariables: {
      fontSize: "18px",
    },
  });
}

loadOrganization().catch((error) => {
  console.error(error);
  renderList(els.blockers, [`Could not load org overview: ${error.message}`]);
});

setInterval(() => {
  loadOrganization(false).catch(() => {});
}, 45_000);
