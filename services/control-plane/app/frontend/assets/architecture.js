const els = {
  refreshButton: document.getElementById("refresh-architecture"),
  generatedAt: document.getElementById("arch-generated-at"),
  metricAgents: document.getElementById("metric-agents"),
  metricQueue: document.getElementById("metric-queue"),
  metricPi: document.getElementById("metric-pi"),
  metricPolicy: document.getElementById("metric-policy"),
  topologyMeta: document.getElementById("topology-meta"),
  topologyMermaid: document.getElementById("topology-mermaid"),
  agentWorkflowMermaid: document.getElementById("agent-workflow-mermaid"),
  autonomyMermaid: document.getElementById("autonomy-mermaid"),
  gcpPiMermaid: document.getElementById("gcp-pi-mermaid"),
  securityBoundaryMermaid: document.getElementById("security-boundary-mermaid"),
  eventMixGrid: document.getElementById("eventmix-grid"),
  telemetryGrid: document.getElementById("telemetry-grid"),
  sloSummary: document.getElementById("slo-summary"),
  queueDiagnostics: document.getElementById("queue-diagnostics"),
  queueRecommendations: document.getElementById("queue-recommendations"),
  executorToolGrid: document.getElementById("executor-tool-grid"),
  executorAttestationList: document.getElementById("executor-attestation-list"),
  executorPrimaryDetails: document.getElementById("executor-primary-details"),
  executorReadinessRecommendations: document.getElementById("executor-readiness-recommendations"),
  logbookSummary: document.getElementById("architecture-logbook-summary"),
  logbookCommCards: document.getElementById("architecture-comm-cards"),
  logbookDecisionLedger: document.getElementById("architecture-decision-ledger"),
  logbookHandoffLedger: document.getElementById("architecture-handoff-ledger"),
  logbookIncidentLedger: document.getElementById("architecture-incident-ledger"),
  logbookVerificationLedger: document.getElementById("architecture-verification-ledger"),
  logbookTimeline: document.getElementById("architecture-logbook-timeline"),
  policySummary: document.getElementById("policy-summary"),
  policyJson: document.getElementById("policy-json"),
  logs: document.getElementById("architecture-logs"),
  chartsMeta: document.getElementById("charts-meta"),
  projectCharts: document.getElementById("project-charts"),
};

const POLL_MS = 15000;
let pollHandle = null;

function setText(el, value) {
  if (el) {
    el.textContent = value;
  }
}

function formatIso(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return `${date.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

function renderMermaid(container, source) {
  if (!container) return;
  container.innerHTML = "";
  if (!source) {
    container.innerHTML = '<p class="muted">No topology data available.</p>';
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
    // Keep raw chart text visible when rendering fails.
  }
}

function renderPolicy(policy, policyDrift = {}) {
  const drift = policyDrift && typeof policyDrift === "object" ? policyDrift : {};
  const mode = String(policy?.mode || "open");
  const effectiveLockApplied = Boolean(policy?.effective_policy_lock_applied);
  const allowedAgents = Array.isArray(policy?.allowed_executor_agent_ids) ? policy.allowed_executor_agent_ids : [];
  const allowedMemberships = Array.isArray(policy?.allowed_executor_membership_ids)
    ? policy.allowed_executor_membership_ids
    : [];
  const expected = drift.expected && typeof drift.expected === "object" ? drift.expected : {};
  const observed = drift.observed && typeof drift.observed === "object" ? drift.observed : {};
  const observedAgents = Array.isArray(observed?.allowed_executor_agent_ids) ? observed.allowed_executor_agent_ids : [];
  const observedMemberships = Array.isArray(observed?.allowed_executor_membership_ids)
    ? observed.allowed_executor_membership_ids
    : [];
  const mismatchFields = Array.isArray(drift.mismatches)
    ? drift.mismatches.map((row) => String(row?.field || "unknown")).filter(Boolean)
    : [];
  const driftSuffix = Boolean(drift.enabled) ? (Boolean(drift.drift_detected) ? "drift" : "locked") : "unlocked";
  setText(els.metricPolicy, `${mode} (${driftSuffix})`);
  if (els.policySummary) {
    const rows = [
      `<li><strong>Effective mode:</strong> ${mode}${effectiveLockApplied ? " (lock-applied)" : ""}</li>`,
      `<li><strong>Effective allowed agents:</strong> ${allowedAgents.join(", ") || "none"}</li>`,
      `<li><strong>Effective allowed memberships:</strong> ${allowedMemberships.join(", ") || "none"}</li>`,
      `<li><strong>Updated:</strong> ${formatIso(policy?.updated_at || "")}</li>`,
    ];
    if (Boolean(drift.enabled)) {
      rows.push(`<li><strong>Policy lock:</strong> enabled</li>`);
      rows.push(`<li><strong>Drift detected:</strong> ${Boolean(drift.drift_detected)}</li>`);
      if (String(expected.mode || "")) {
        rows.push(`<li><strong>Expected mode:</strong> ${String(expected.mode)}</li>`);
      }
      if (String(observed.mode || "")) {
        rows.push(`<li><strong>Observed stored mode:</strong> ${String(observed.mode)}</li>`);
      }
      if (observedAgents.length) {
        rows.push(`<li><strong>Observed stored agents:</strong> ${observedAgents.join(", ")}</li>`);
      }
      if (observedMemberships.length) {
        rows.push(`<li><strong>Observed stored memberships:</strong> ${observedMemberships.join(", ")}</li>`);
      }
      if (mismatchFields.length) {
        rows.push(`<li><strong>Mismatches:</strong> ${mismatchFields.join(", ")}</li>`);
      }
    }
    els.policySummary.innerHTML = rows.join("");
  }
  if (els.policyJson) {
    const combined = {
      policy: policy || {},
      policy_drift: drift || {},
    };
    els.policyJson.textContent = JSON.stringify(combined, null, 2);
  }
}

function ratioPercent(value, total) {
  const safeValue = Number(value || 0);
  const safeTotal = Number(total || 0);
  if (!Number.isFinite(safeValue) || !Number.isFinite(safeTotal) || safeTotal <= 0) return 0;
  return Math.max(0, Math.min((safeValue / safeTotal) * 100, 100));
}

function buildAutonomyMermaid(stats, policy) {
  const queued = Number(stats?.tasks_queued || 0);
  const leased = Number(stats?.tasks_leased || 0);
  const failed = Number(stats?.tasks_failed || 0);
  const mode = String(policy?.mode || "custom");
  return `flowchart TB
  CRON["30m Scheduler"] --> HUB["PM Hub (Local Control Plane)"]
  TG["Telegram Operator Channel"] --> HUB
  HUB --> ROUTER["Membership Router + Policy\\\\nmode:${mode}"]
  ROUTER --> QUEUE["Control Queue\\\\nQ:${queued} L:${leased} F:${failed}"]
  QUEUE --> A1["rari1 / execution rail"]
  QUEUE --> A2["rari2 / research rail"]
  A1 --> ASTER["Aster Execution Rail"]
  A2 --> LIGHTER["Lighter Execution Rail"]
  A1 --> CODE["GitHub + Local Code Projects"]
  A2 --> CODE
  CODE --> STATE["State + Logs + Architecture Dashboards"]
  HUB --> STATE`;
}

function buildGcpPiMermaid(stats) {
  const agentsOnline = Number(stats?.agents_executor_online ?? stats?.agents_online ?? 0);
  const piReachable = Number(stats?.pi_nodes_reachable || 0);
  const piTotal = Number(stats?.pi_nodes_total || 0);
  return `flowchart TB
  subgraph GCP["Local Operator Surface"]
    RUN["Local Control Plane"]
    SCHED["Local Scheduler / Cron"]
    SECRETS["Local secrets"]
  end
  subgraph EDGE["Raspberry Pi Edge Executors"]
    R1["rari1\\\\nexecution rail"]
    R2["rari2\\\\nresearch rail"]
  end
  TEL["Telegram Bots"] --> RUN
  SCHED --> RUN
  RUN --> R1
  RUN --> R2
  SECRETS --> RUN
  R1 --> VENUE1["Aster Venue"]
  R2 --> VENUE2["Lighter Venue"]
  RUN --> OBS["Organization OS + Architecture Map\\\\nagents:${agentsOnline} pi:${piReachable}/${piTotal}"]`;
}

function buildAgentWorkflowMermaid(payload) {
  const stats = payload?.stats || {};
  const topology = payload?.topology || {};
  const fleet = Array.isArray(topology?.fleet_nodes) ? topology.fleet_nodes : [];
  const serviceName = String(payload?.service_name || "sapphire-control-plane");
  const revision = String(payload?.service_revision || "unknown");
  const runtimeMode = String(payload?.runtime_mode || "local");

  const findNode = (needle) =>
    fleet.find((row) => String(row?.node || "").toLowerCase().includes(String(needle || "").toLowerCase()));

  const rari1 = findNode("rari1");
  const rari2 = findNode("rari2");

  const rari1Label = `${String(rari1?.node || "rari1")}\\\\n${String(rari1?.role || "execution rail")}\\\\n${rari1?.reachable ? "reachable" : "offline"}`;
  const rari2Label = `${String(rari2?.node || "rari2")}\\\\n${String(rari2?.role || "research rail")}\\\\n${rari2?.reachable ? "reachable" : "offline"}`;
  const agentsOnline = Number(stats?.agents_executor_online ?? stats?.agents_online ?? 0);

  return `flowchart TB
  subgraph LAP["MacBook / Local Workbench"]
    DESK["PMCommander app\\\\nCodex workspace"]
  end
  subgraph CLOUD["Control Plane (${runtimeMode})"]
    HUB["${serviceName}\\\\nrev:${revision}"]
    ROUTER["Policy + Membership Router"]
    QUEUE["Control Queue"]
    SECRETS["Local secrets + scheduler"]
  end
  subgraph EDGE["Raspberry Pi Executors"]
    R1["${rari1Label}"]
    R2["${rari2Label}"]
  end
  TG["Telegram bots"] --> HUB
  DESK --> HUB
  SECRETS --> HUB
  HUB --> ROUTER --> QUEUE
  QUEUE --> R1
  QUEUE --> R2
  R1 --> VENUEA["Aster venue"]
  R2 --> VENUEB["Lighter venue"]
  R1 --> HUB
  R2 --> HUB
  HUB --> DESK
  HUB --> TG
  HUB --- META["agents_online:${agentsOnline}"]`;
}

function buildSecurityBoundaryMermaid(payload, opsInventory) {
  const policy = payload?.executor_policy || {};
  const readiness = opsInventory?.executor_readiness || {};
  const primary = readiness?.primary_executor || {};
  const host = primary?.host || {};
  const tools = readiness?.tool_summary || {};
  const lockApplied = Boolean(readiness?.effective_policy_lock_applied || policy?.effective_policy_lock_applied);
  const primaryHostId = String(host.host_id || "rari2");
  const primaryHostClass = String(host.host_class || "pi");
  const workspace = String(host.workspace_root || "/home/rari/.openclaw/runtime/codex-projects");

  return `flowchart TB
  subgraph MAC["Mac (authoritative secrets + ops)"]
    VAULT["Consolidated secrets vault\\n~/.config/sapphire-secrets"]
    MACBK["Encrypted backup\\n~/Documents/Organized/Backups/sapphire-secrets"]
    APP["PMCommander + Codex workspace"]
  end
  subgraph CLOUD["Local Control Plane"]
    HUB["PM Hub"]
    LOCK["Executor policy lock\\n${lockApplied ? "active" : "inactive"}"]
  end
  subgraph PI1["rari1 (backup + trading rail)"]
    SSD["Encrypted backup replica\\n/mnt/ssd/sapphire-secrets-backups"]
    TR1["rari1-trader\\ntrading env only"]
  end
  subgraph PI2["${primaryHostId} (${primaryHostClass}) Kimi executor"]
    PMENV["pm-executor.env\\ncontrol-plane only"]
    DEPLOYENV["deploy.env\\nlocal/GitHub creds"]
    KIMI["kimi-main\\nworkspace=${workspace.replace(/"/g, "'")}"]
    TR2["rari2-trader\\nseparate trading.env"]
  end
  TG["Telegram bots"] --> HUB
  APP --> HUB
  HUB --> LOCK
  LOCK --> KIMI
  VAULT --> MACBK
  MACBK --> SSD
  VAULT -. sync scoped values .-> PMENV
  VAULT -. sync scoped values .-> DEPLOYENV
  PMENV --> KIMI
  DEPLOYENV --> KIMI
  TR2 --> LIGHT["Lighter venue"]
  TR1 --> ASTER["Aster venue"]
  KIMI --> HUB
  KIMI --- TOOLS["tools: gh=${Boolean(tools.gh)} | cloud_bridge=${Boolean(tools.gcloud)} | docker=${Boolean(tools.docker)} | node=${Boolean(tools.node)}"]
  NOTE["No master backup decrypt key on Pi"] --- PI2`;
}

function renderEventMix(logs) {
  if (!els.eventMixGrid) return;
  const rows = Array.isArray(logs) ? logs : [];
  if (!rows.length) {
    els.eventMixGrid.innerHTML = '<p class="muted">No recent control events available.</p>';
    return;
  }

  const typeCounts = new Map();
  const agentCounts = new Map();
  rows.forEach((row) => {
    const eventType = String(row?.event_type || "event");
    const typeBucket = eventType.includes(".") ? eventType.split(".", 1)[0] : eventType;
    typeCounts.set(typeBucket, (typeCounts.get(typeBucket) || 0) + 1);
    const agent = String(row?.agent_id || "").trim();
    if (agent) {
      agentCounts.set(agent, (agentCounts.get(agent) || 0) + 1);
    }
  });

  const topTypes = [...typeCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  const topAgents = [...agentCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  const maxType = Math.max(1, ...topTypes.map(([, count]) => count));
  const maxAgent = Math.max(1, ...topAgents.map(([, count]) => count));

  const renderBars = (title, items, max) => `
    <section class="eventmix-panel">
      <h4>${title}</h4>
      ${
        items.length
          ? items
              .map(([label, count]) => {
                const pct = ratioPercent(count, max);
                return `
                  <div class="eventmix-row">
                    <div class="eventmix-label">${String(label)}</div>
                    <div class="eventmix-bar"><span style="width:${pct.toFixed(1)}%"></span></div>
                    <div class="eventmix-value">${count}</div>
                  </div>
                `;
              })
              .join("")
          : '<p class="muted">No data.</p>'
      }
    </section>
  `;

  els.eventMixGrid.innerHTML = [
    renderBars("Event Types", topTypes, maxType),
    renderBars("Agents", topAgents, maxAgent),
  ].join("");
}

function renderTelemetry(stats) {
  if (!els.telemetryGrid) return;
  const safe = stats && typeof stats === "object" ? stats : {};
  const agentsOnline = Number(safe.agents_executor_online ?? safe.agents_online ?? 0);
  const agentsRegistered = Number(safe.agents_registered || 0);
  const queued = Number(safe.tasks_queued || 0);
  const leased = Number(safe.tasks_leased || 0);
  const failed = Number(safe.tasks_failed || 0);
  const blockedReview = Number(safe.tasks_blocked_review || 0);
  const kpiExcluded = Number(safe.kpi_excluded_low_signal || 0);
  const piReachable = Number(safe.pi_nodes_reachable || 0);
  const piTotal = Number(safe.pi_nodes_total || 0);

  const rows = [
    {
      label: "Agent Availability",
      value: `${agentsOnline}/${agentsRegistered}`,
      percent: ratioPercent(agentsOnline, Math.max(agentsRegistered, 1)),
    },
    {
      label: "Queue Pressure",
      value: `${queued} queued`,
      percent: ratioPercent(queued, Math.max(queued + leased + 2, 3)),
    },
    {
      label: "Active Leases",
      value: `${leased} leased`,
      percent: ratioPercent(leased, Math.max(queued + leased, 1)),
    },
    {
      label: "Pi Reachability",
      value: `${piReachable}/${piTotal}`,
      percent: ratioPercent(piReachable, Math.max(piTotal, 1)),
    },
    {
      label: "Failure Load",
      value: `${failed} failed`,
      percent: ratioPercent(failed, Math.max(queued + leased + failed, 1)),
    },
    {
      label: "Dead-Letter",
      value: `${blockedReview} blocked_review`,
      percent: ratioPercent(blockedReview, Math.max(queued + leased + failed + blockedReview, 1)),
    },
    {
      label: "Low-Signal Excluded",
      value: `${kpiExcluded} excluded`,
      percent: ratioPercent(kpiExcluded, Math.max(kpiExcluded + queued + leased + failed + 1, 1)),
    },
  ];

  els.telemetryGrid.innerHTML = rows
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

function renderSloSummary(slo) {
  if (!els.sloSummary) return;
  const safe = slo && typeof slo === "object" ? slo : {};
  const status = String(safe.status || "unknown");
  const drain = safe.queue_drain_time_seconds;
  const staleLeaseRate = Number(safe.stale_lease_rate || 0);
  const autocancelRate = Number(safe.autocancel_rate || 0);
  const alerts = Array.isArray(safe.alerts) ? safe.alerts : [];
  const rows = [
    `SLO status: ${status}`,
    `Queue drain estimate: ${drain == null ? "unknown" : `${drain}s`}`,
    `Stale lease rate: ${(staleLeaseRate * 100).toFixed(1)}%`,
    `Auto-cancel rate: ${(autocancelRate * 100).toFixed(1)}%`,
  ];
  if (alerts.length > 0) {
    rows.push(...alerts.slice(0, 4).map((item) => `Alert: ${String(item?.id || "unknown")} · ${String(item?.message || "")}`));
  } else {
    rows.push("No active SLO alert thresholds breached.");
  }
  els.sloSummary.innerHTML = rows.map((row) => `<li>${row}</li>`).join("");
}

function renderQueueDiagnostics(opsInventory) {
  const summary = opsInventory?.summary && typeof opsInventory.summary === "object" ? opsInventory.summary : {};
  const policyDrift = opsInventory?.policy_drift && typeof opsInventory.policy_drift === "object" ? opsInventory.policy_drift : {};
  const queueRoutability = opsInventory?.queue_routability && typeof opsInventory.queue_routability === "object"
    ? opsInventory.queue_routability
    : {};
  const qrSummary = queueRoutability?.summary && typeof queueRoutability.summary === "object" ? queueRoutability.summary : {};
  const blockers = Array.isArray(qrSummary.blocker_breakdown) ? qrSummary.blocker_breakdown : [];
  const queuedTasks = Array.isArray(queueRoutability.queued_tasks) ? queueRoutability.queued_tasks : [];
  const recommendations = Array.isArray(queueRoutability.recommendations) ? queueRoutability.recommendations : [];

  if (els.queueDiagnostics) {
    const rows = [
      `queue_stall_detected=${Boolean(summary.queue_stall_detected)}`,
      `queued=${Number(qrSummary.queued_count || 0)} · routable=${Number(qrSummary.routable_count || 0)} · unroutable=${Number(qrSummary.unroutable_count || 0)}`,
      `top_blocker=${String(qrSummary.top_blocker_reason || "none")}`,
    ];
    if (Boolean(policyDrift.enabled)) {
      rows.push(`policy_lock=true · drift=${Boolean(policyDrift.drift_detected)}`);
      const mismatchFields = Array.isArray(policyDrift.mismatches)
        ? policyDrift.mismatches.map((row) => String(row?.field || "unknown")).filter(Boolean)
        : [];
      if (mismatchFields.length) rows.push(`policy_mismatches=${mismatchFields.join(", ")}`);
    }
    blockers.slice(0, 4).forEach((row) => {
      rows.push(`blocker: ${String(row?.reason || "unknown")} (${Number(row?.count || 0)})`);
    });
    queuedTasks.slice(0, 3).forEach((row) => {
      const title = String(row?.title || row?.task_id || "task");
      const blockersList = Array.isArray(row?.blocker_reasons) ? row.blocker_reasons.join(", ") : "unknown";
      rows.push(`task: ${title} -> ${blockersList}`);
    });
    els.queueDiagnostics.innerHTML = rows.map((row) => `<li>${row}</li>`).join("");
  }

  if (els.queueRecommendations) {
    if (!recommendations.length) {
      els.queueRecommendations.innerHTML = "<li>No queue recovery recommendations.</li>";
    } else {
      els.queueRecommendations.innerHTML = recommendations
        .slice(0, 6)
        .map((row) => {
          const priority = String(row?.priority || "info");
          const id = String(row?.id || "recommendation");
          const action = String(row?.action || "");
          return `<li><strong>${priority}</strong> · ${id}<br/>${action}</li>`;
        })
        .join("");
    }
  }
}

function yesNo(value) {
  return value ? "yes" : "no";
}

function renderExecutorReadiness(opsInventory) {
  const readiness = opsInventory?.executor_readiness && typeof opsInventory.executor_readiness === "object"
    ? opsInventory.executor_readiness
    : {};
  const attestation = readiness?.attestation && typeof readiness.attestation === "object" ? readiness.attestation : {};
  const toolSummary = readiness?.tool_summary && typeof readiness.tool_summary === "object" ? readiness.tool_summary : {};
  const primary = readiness?.primary_executor && typeof readiness.primary_executor === "object" ? readiness.primary_executor : {};
  const recs = Array.isArray(readiness?.recommendations) ? readiness.recommendations : [];
  const primaryHost = primary?.host && typeof primary.host === "object" ? primary.host : {};
  const primaryMembership = primary?.membership && typeof primary.membership === "object" ? primary.membership : {};

  if (els.executorToolGrid) {
    const chips = [
      { label: "gh", ok: Boolean(toolSummary.gh) },
      { label: "cloud bridge", ok: Boolean(toolSummary.gcloud) },
      { label: "docker", ok: Boolean(toolSummary.docker) },
      { label: "node", ok: Boolean(toolSummary.node) },
      { label: "lock", ok: Boolean(readiness.effective_policy_lock_applied) },
      { label: "pi-hosted", ok: Boolean(attestation.primary_executor_pi_hosted) },
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
      els.executorPrimaryDetails.innerHTML = "<li>No executor selected by current policy.</li>";
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

function renderLogs(logs) {
  if (!els.logs) return;
  const rows = Array.isArray(logs) ? logs : [];
  if (!rows.length) {
    els.logs.innerHTML = "<li>No control logs available.</li>";
    return;
  }
  els.logs.innerHTML = rows
    .slice(0, 14)
    .map((row) => {
      const eventType = String(row?.event_type || "event");
      const eventTime = formatIso(row?.created_at || "");
      const agentId = String(row?.agent_id || "");
      const taskId = String(row?.task_id || "");
      const summary = String(row?.summary || "").trim();
      const context = [agentId ? `agent:${agentId}` : "", taskId ? `task:${taskId}` : ""].filter(Boolean).join(" | ");
      return `<li><strong>${eventType}</strong> <span class="muted">${eventTime}</span>${context ? `<br/><span class="muted">${context}</span>` : ""}${summary ? `<br/>${summary}` : ""}</li>`;
    })
    .join("");
}

function renderProjectCharts(charts, markdownPath) {
  if (!els.projectCharts) return;
  const rows = Array.isArray(charts) ? charts : [];
  setText(els.chartsMeta, markdownPath ? `Charts artifact: ${markdownPath}` : "Charts generated from tracked repos.");
  if (!rows.length) {
    els.projectCharts.innerHTML = '<p class="muted">No tracked project charts available.</p>';
    return;
  }

  const frag = document.createDocumentFragment();
  rows.forEach((row, idx) => {
    const card = document.createElement("article");
    card.className = "project-card";
    const stacks = Array.isArray(row?.stack_signals) ? row.stack_signals : [];
    const topComponents = Array.isArray(row?.top_components) ? row.top_components : [];
    const fileCount = Number(row?.scanned_files || 0);
    card.innerHTML = `
      <h4>${String(row?.name || row?.id || `Project ${idx + 1}`)}</h4>
      <div class="project-meta">
        <span class="pill">health: ${String(row?.health || "unknown")}</span>
        <span class="pill">files scanned: ${Number.isFinite(fileCount) ? fileCount : 0}</span>
        <span class="pill">stack: ${stacks.join(", ") || "unknown"}</span>
      </div>
      <p class="muted">${String(row?.canonical_local_path || "")}</p>
      <p class="muted">${topComponents.slice(0, 3).map((item) => `${item.name}/(${item.files})`).join(" | ") || "No components detected."}</p>
      <div class="mermaid-shell"></div>
    `;
    const shell = card.querySelector(".mermaid-shell");
    renderMermaid(shell, String(row?.mermaid || ""));
    frag.appendChild(card);
  });
  els.projectCharts.innerHTML = "";
  els.projectCharts.appendChild(frag);
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

function renderSummary(payload) {
  const stats = payload?.stats || {};
  const agentsOnline = Number(stats.agents_executor_online ?? stats.agents_online ?? 0);
  const agentsRegistered = Number(stats.agents_registered || 0);
  const agentsDisabled = Number(stats.agents_disabled || 0);
  const queued = Number(stats.tasks_queued || 0);
  const leased = Number(stats.tasks_leased || 0);
  const failed = Number(stats.tasks_failed || 0);
  const blockedReview = Number(stats.tasks_blocked_review || 0);
  const piReachable = Number(stats.pi_nodes_reachable || 0);
  const piTotal = Number(stats.pi_nodes_total || 0);
  setText(els.generatedAt, formatIso(payload?.generated_at || ""));
  setText(els.metricAgents, `${agentsOnline}/${agentsRegistered} (disabled ${agentsDisabled})`);
  setText(els.metricQueue, `Q${queued} · L${leased} · F${failed} · BR${blockedReview}`);
  setText(els.metricPi, `${piReachable}/${piTotal}`);
}

async function loadArchitecture(refresh = false) {
  const params = refresh ? "?refresh=true" : "";
  const logbookClient = window.SapphireFrontendLogbookClient;
  const [archResponse, opsResponse, logbookResponse] = await Promise.all([
    fetch(`/api/architecture/overview${params}`, { cache: "no-store" }),
    fetch(`/api/frontend/ops-status${params}${params ? "&" : "?"}event_limit=20`, { cache: "no-store" }),
    logbookClient && typeof logbookClient.fetchLogbookMaybe === "function"
      ? logbookClient.fetchLogbookMaybe({ refresh, eventLimit: 24 })
      : fetch(`/api/frontend/logbook${params}${params ? "&" : "?"}event_limit=24`, { cache: "no-store" }),
  ]);
  if (!archResponse.ok) {
    throw new Error(`Request failed with status ${archResponse.status}`);
  }
  const payload = await archResponse.json();
  const opsInventory = opsResponse.ok ? await opsResponse.json() : null;
  const logbookPayload = logbookClient && typeof logbookClient.fetchLogbookMaybe === "function"
    ? logbookResponse
    : (logbookResponse.ok ? await logbookResponse.json() : null);
  renderSummary(payload);
  renderPolicy(payload?.executor_policy || {}, opsInventory?.policy_drift || {});
  renderLogs(payload?.logs || []);
  renderMermaid(els.topologyMermaid, String(payload?.topology?.mermaid || ""));
  renderMermaid(els.agentWorkflowMermaid, buildAgentWorkflowMermaid(payload));
  renderMermaid(els.autonomyMermaid, buildAutonomyMermaid(payload?.stats || {}, payload?.executor_policy || {}));
  renderMermaid(els.gcpPiMermaid, buildGcpPiMermaid(payload?.stats || {}));
  renderMermaid(els.securityBoundaryMermaid, buildSecurityBoundaryMermaid(payload, opsInventory || {}));
  renderEventMix(payload?.logs || []);
  renderTelemetry(payload?.stats || {});
  renderSloSummary(payload?.slo || {});
  renderQueueDiagnostics(opsInventory || {});
  renderExecutorReadiness(opsInventory || {});
  renderSharedLogbook(logbookPayload || {});
  renderProjectCharts(payload?.project_charts || [], String(payload?.project_charts_markdown_path || ""));
  if (els.topologyMeta) {
    if (opsInventory?.summary?.queue_stall_detected) {
      const blocker = String(opsInventory?.summary?.queue_top_blocker_reason || "unknown");
      els.topologyMeta.textContent = `Queue stall detected: ${blocker}. Use queue diagnostics + recovery recommendations below.`;
    } else if (opsInventory?.policy_drift?.enabled && opsInventory?.policy_drift?.drift_detected) {
      els.topologyMeta.textContent = "Executor policy drift detected. Reconcile stored policy to expected lock before autonomous runs.";
    }
  }
  await runMermaidRender();
}

async function refreshNow(force = false) {
  if (els.refreshButton) {
    els.refreshButton.disabled = true;
  }
  try {
    await loadArchitecture(force);
    setText(els.topologyMeta, `Last refresh: ${formatIso(new Date().toISOString())}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    if (els.topologyMermaid) {
      els.topologyMermaid.innerHTML = `<p class="muted">Failed to refresh architecture: ${message}</p>`;
    }
  } finally {
    if (els.refreshButton) {
      els.refreshButton.disabled = false;
    }
  }
}

function startPolling() {
  if (pollHandle) {
    clearInterval(pollHandle);
  }
  pollHandle = window.setInterval(() => {
    refreshNow(false);
  }, POLL_MS);
}

function init() {
  if (window.mermaid && typeof window.mermaid.initialize === "function") {
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: "dark",
      flowchart: { curve: "linear" },
      themeVariables: {
        fontSize: "18px",
      },
    });
  }

  if (els.refreshButton) {
    els.refreshButton.addEventListener("click", () => {
      refreshNow(true);
    });
  }

  refreshNow(true);
  startPolling();
}

document.addEventListener("DOMContentLoaded", init);
