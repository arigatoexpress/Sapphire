const els = {
  refreshButton: document.getElementById("refresh-board"),
  syncButton: document.getElementById("sync-board"),
  generatedAt: document.getElementById("board-generated-at"),
  summaryLocalRepos: document.getElementById("summary-local-repos"),
  summaryDirtyRepos: document.getElementById("summary-dirty-repos"),
  summaryBoardCards: document.getElementById("summary-board-cards"),
  summaryTrackedProjects: document.getElementById("summary-tracked-projects"),
  summaryPrunedSize: document.getElementById("summary-pruned-size"),
  routerGeneratedAt: document.getElementById("router-generated-at"),
  routerReadyCount: document.getElementById("router-ready-count"),
  routerUnavailableCount: document.getElementById("router-unavailable-count"),
  routerQuotaUnknownCount: document.getElementById("router-quota-unknown-count"),
  routerFilesystemStatus: document.getElementById("router-filesystem-status"),
  membershipTableBody: document.getElementById("membership-table-body"),
  routerSampleRecs: document.getElementById("router-sample-recs"),
  accessHubBody: document.getElementById("access-hub-body"),
  controlGeneratedAt: document.getElementById("control-generated-at"),
  controlAgentsOnline: document.getElementById("control-agents-online"),
  controlAgentsTotal: document.getElementById("control-agents-total"),
  controlQueued: document.getElementById("control-queued"),
  controlLeased: document.getElementById("control-leased"),
  controlFailed: document.getElementById("control-failed"),
  controlAgentsBody: document.getElementById("control-agents-body"),
  controlTasks: document.getElementById("control-tasks"),
  controlEvents: document.getElementById("control-events"),
  controlActionStatus: document.getElementById("control-action-status"),
  controlTokenForm: document.getElementById("control-token-form"),
  controlTokenInput: document.getElementById("control-token"),
  clearControlTokenButton: document.getElementById("clear-control-token"),
  zkpassProofForm: document.getElementById("zkpass-proof-form"),
  zkpassProofInput: document.getElementById("zkpass-proof"),
  verifyZkpassProofButton: document.getElementById("verify-zkpass-proof"),
  clearZkpassProofButton: document.getElementById("clear-zkpass-proof"),
  controlCreateTaskForm: document.getElementById("control-create-task-form"),
  controlTaskTitle: document.getElementById("control-task-title"),
  controlTaskType: document.getElementById("control-task-type"),
  controlTaskPriority: document.getElementById("control-task-priority"),
  controlTaskCapabilities: document.getElementById("control-task-capabilities"),
  controlTaskEnforce: document.getElementById("control-task-enforce"),
  controlTaskNote: document.getElementById("control-task-note"),
  controlUpdateTaskForm: document.getElementById("control-update-task-form"),
  controlUpdateTaskId: document.getElementById("control-update-task-id"),
  controlUpdateProgress: document.getElementById("control-update-progress"),
  controlUpdateNote: document.getElementById("control-update-note"),
  controlLeaseTaskForm: document.getElementById("control-lease-task-form"),
  controlLeaseAgent: document.getElementById("control-lease-agent"),
  controlLeaseCapabilities: document.getElementById("control-lease-capabilities"),
  controlLeaseLimit: document.getElementById("control-lease-limit"),
  controlResolveTaskForm: document.getElementById("control-resolve-task-form"),
  controlResolveTaskId: document.getElementById("control-resolve-task-id"),
  controlResolveAgent: document.getElementById("control-resolve-agent"),
  controlResolveAction: document.getElementById("control-resolve-action"),
  controlResolveMessage: document.getElementById("control-resolve-message"),
  controlResolveMembership: document.getElementById("control-resolve-membership"),
  controlResolveErrorCode: document.getElementById("control-resolve-error-code"),
  trackedProjectsBody: document.getElementById("tracked-projects-body"),
  repoTableBody: document.getElementById("repo-table-body"),
  cleanupManifestPath: document.getElementById("cleanup-manifest-path"),
  cleanupReasons: document.getElementById("cleanup-reasons"),
  recentMoves: document.getElementById("recent-moves"),
  workspaceSizes: document.getElementById("workspace-sizes"),
  nextActions: document.getElementById("next-actions"),
  nextActionsMeta: document.getElementById("next-actions-meta"),
  logbookSummary: document.getElementById("projects-logbook-summary"),
  logbookCommCards: document.getElementById("projects-comm-cards"),
  logbookDecisionLedger: document.getElementById("projects-decision-ledger"),
  logbookHandoffLedger: document.getElementById("projects-handoff-ledger"),
  logbookIncidentLedger: document.getElementById("projects-incident-ledger"),
  logbookVerificationLedger: document.getElementById("projects-verification-ledger"),
  logbookTimeline: document.getElementById("projects-logbook-timeline"),
  newCardForm: document.getElementById("new-card-form"),
  newTitle: document.getElementById("new-title"),
  newProject: document.getElementById("new-project"),
  newPriority: document.getElementById("new-priority"),
  newStatus: document.getElementById("new-status"),
};

const columns = {
  backlog: document.getElementById("column-backlog"),
  in_progress: document.getElementById("column-in_progress"),
  blocked: document.getElementById("column-blocked"),
  done: document.getElementById("column-done"),
};

const statusOrder = ["backlog", "in_progress", "blocked", "done"];
const CONTROL_TOKEN_STORAGE_KEY = "agentic.projects.control_token";
const ZKPASS_PROOF_STORAGE_KEY = "agentic.projects.zkpass_proof";
const CONTROL_LEASE_SECONDS = 300;
const latestControlTasks = new Map();

function setText(el, value) {
  if (el) {
    el.textContent = value;
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatIso(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return `${date.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

function formatRemaining(value, unit) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "unknown";
  }
  const numeric = Number(value);
  const rounded = Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
  return `${rounded} ${unit || ""}`.trim();
}

function statusLabel(value) {
  if (value === "in_progress") return "in progress";
  return value.replaceAll("_", " ");
}

function setControlStatus(message, isError = false) {
  if (!els.controlActionStatus) return;
  els.controlActionStatus.textContent = message;
  if (isError) {
    els.controlActionStatus.classList.add("error");
  } else {
    els.controlActionStatus.classList.remove("error");
  }
}

function loadStoredControlToken() {
  try {
    return (window.localStorage.getItem(CONTROL_TOKEN_STORAGE_KEY) || "").trim();
  } catch (_error) {
    return "";
  }
}

function saveStoredControlToken(token) {
  const value = String(token || "").trim();
  try {
    if (value) {
      window.localStorage.setItem(CONTROL_TOKEN_STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(CONTROL_TOKEN_STORAGE_KEY);
    }
  } catch (_error) {
    // Ignore storage errors and continue with in-memory usage.
  }
}

function getControlToken() {
  const typed = String(els.controlTokenInput?.value || "").trim();
  if (typed) return typed;
  return loadStoredControlToken();
}

function loadStoredZkPassProof() {
  try {
    return (window.localStorage.getItem(ZKPASS_PROOF_STORAGE_KEY) || "").trim();
  } catch (_error) {
    return "";
  }
}

function saveStoredZkPassProof(rawProof) {
  const value = String(rawProof || "").trim();
  try {
    if (value) {
      window.localStorage.setItem(ZKPASS_PROOF_STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(ZKPASS_PROOF_STORAGE_KEY);
    }
  } catch (_error) {
    // Ignore storage errors and continue with in-memory usage.
  }
}

function getZkPassProof() {
  const typed = String(els.zkpassProofInput?.value || "").trim();
  if (typed) return typed;
  return loadStoredZkPassProof();
}

function parseZkPassProof(rawProof) {
  const text = String(rawProof || "").trim();
  if (!text) return null;
  if (text.startsWith("{")) {
    try {
      return JSON.parse(text);
    } catch (_error) {
      return text;
    }
  }
  return text;
}

function csvCapabilities(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter((item) => item.length > 0);
}

function mapPriorityToValue(level) {
  const normalized = String(level || "medium").trim().toLowerCase();
  if (normalized === "urgent") return 0;
  if (normalized === "high") return 20;
  if (normalized === "low") return 250;
  return 100;
}

function clampInt(value, minValue, maxValue, fallbackValue) {
  const numeric = Number.parseInt(String(value), 10);
  if (Number.isNaN(numeric)) return fallbackValue;
  return Math.max(minValue, Math.min(maxValue, numeric));
}

function renderAgentSelectOptions(agents) {
  const rows = Array.isArray(agents) ? agents : [];
  const options = rows
    .slice()
    .sort((left, right) => {
      const leftOnline = left?.online ? 0 : 1;
      const rightOnline = right?.online ? 0 : 1;
      if (leftOnline !== rightOnline) return leftOnline - rightOnline;
      return String(left?.name || left?.agent_id || "").localeCompare(String(right?.name || right?.agent_id || ""));
    })
    .map((agent) => {
      const agentId = String(agent?.agent_id || "").trim();
      if (!agentId) return "";
      const badge = agent?.online ? "online" : "offline";
      const membership = _agentMembership(agent);
      const suffix = membership ? ` (${membership})` : "";
      return `<option value="${escapeHtml(agentId)}">${escapeHtml(`${agentId} [${badge}]${suffix}`)}</option>`;
    })
    .filter(Boolean)
    .join("");

  [els.controlLeaseAgent, els.controlResolveAgent].forEach((selectEl) => {
    if (!selectEl) return;
    const previous = String(selectEl.value || "").trim();
    const label = selectEl === els.controlLeaseAgent ? "Lease: select agent" : "Resolve: select agent";
    selectEl.innerHTML = `<option value="">${label}</option>${options}`;
    const hasPrevious = previous
      && Array.from(selectEl.options).some((option) => String(option.value || "").trim() === previous);
    if (hasPrevious) {
      selectEl.value = previous;
      return;
    }
    const firstOnline = rows.find((item) => Boolean(item?.online) && String(item?.agent_id || "").trim());
    if (firstOnline) {
      selectEl.value = String(firstOnline.agent_id).trim();
    }
  });
}

function clearColumns() {
  statusOrder.forEach((status) => {
    if (columns[status]) {
      columns[status].innerHTML = "";
    }
  });
}

function renderCard(card) {
  const wrapper = document.createElement("article");
  wrapper.className = "card";
  wrapper.draggable = true;
  wrapper.dataset.cardId = card.id;
  wrapper.innerHTML = `
    <h4>${escapeHtml(card.title)}</h4>
    <div class="card-meta">
      <span class="badge ${escapeHtml(card.priority)}">${escapeHtml(card.priority)}</span>
      <span class="badge">${escapeHtml(card.project || "General")}</span>
      <span class="badge">${escapeHtml(statusLabel(card.status || "backlog"))}</span>
    </div>
    ${card.notes ? `<p class="card-note">${escapeHtml(card.notes)}</p>` : ""}
  `;
  wrapper.addEventListener("dragstart", (event) => {
    event.dataTransfer?.setData("text/plain", card.id);
    event.dataTransfer?.setData("application/x-card-status", card.status || "backlog");
  });
  return wrapper;
}

function renderBoard(cards) {
  clearColumns();
  const grouped = {
    backlog: [],
    in_progress: [],
    blocked: [],
    done: [],
  };

  (cards || []).forEach((card) => {
    const status = statusOrder.includes(card.status) ? card.status : "backlog";
    grouped[status].push(card);
  });

  statusOrder.forEach((status) => {
    const zone = columns[status];
    if (!zone) return;
    const items = grouped[status];
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "card-note";
      empty.textContent = "No cards";
      zone.appendChild(empty);
      return;
    }
    items.forEach((card) => zone.appendChild(renderCard(card)));
  });
}

function renderSummary(summary) {
  setText(els.summaryLocalRepos, String(summary.local_repo_count ?? 0));
  setText(els.summaryDirtyRepos, String(summary.local_dirty_repo_count ?? 0));
  setText(els.summaryBoardCards, String(summary.board_card_count ?? 0));
  setText(els.summaryTrackedProjects, String(summary.tracked_project_count ?? 0));
  setText(els.summaryPrunedSize, String(summary.cleanup_total_size ?? "0B"));
}

function renderTrackedProjects(projects) {
  if (!els.trackedProjectsBody) return;
  if (!Array.isArray(projects) || projects.length === 0) {
    els.trackedProjectsBody.innerHTML = '<tr><td colspan="5">No tracked projects configured.</td></tr>';
    return;
  }

  const rows = projects
    .map((project) => {
      const name = escapeHtml(project.name || project.id || "unknown");
      const health = escapeHtml(project.health || "unknown");
      const canonical = project.canonical_local_path || "";
      const canonicalExists = Boolean(project.canonical_exists);
      const localPathCheck = String(project.local_path_check || "active");
      const githubCheck = String(project.github_check || "active");
      const canonicalHtml = canonical
        ? (localPathCheck === "not_applicable"
          ? `N/A (cloud runtime) <code>${escapeHtml(canonical)}</code>`
          : `${canonicalExists ? "OK" : "MISSING"} <code>${escapeHtml(canonical)}</code>`)
        : '<span class="muted">not set</span>';

      const localRefs = Array.isArray(project.local_refs) ? project.local_refs : [];
      const localHtml = localPathCheck === "not_applicable"
        ? '<span class="muted">host paths not checked in cloud runtime</span>'
        : (localRefs.length
        ? localRefs
            .map((ref) => {
              const path = escapeHtml(ref.path || "");
              const exists = ref.exists ? "ok" : "missing";
              const dirty = Number(ref.dirty_files || 0);
              const dirtyLabel = dirty > 0 ? `, dirty:${dirty}` : "";
              return `<div><span class="inline-pill ${exists === "ok" ? "clean" : "dirty"}">${exists}</span> <code>${path}</code>${dirtyLabel}</div>`;
            })
            .join("")
        : '<span class="muted">none</span>');

      const githubRefs = Array.isArray(project.github_refs) ? project.github_refs : [];
      let githubHtml = '<span class="muted">none</span>';
      if (githubCheck === "not_required") {
        githubHtml = githubRefs.length
          ? githubRefs
              .map((ref) => {
                const href = ref.url || "";
                const label = escapeHtml(ref.owner && ref.name ? `${ref.owner}/${ref.name}` : href || "unknown");
                if (href.startsWith("http")) {
                  return `<div><span class="inline-pill clean">local-only</span> <a class="repo-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${label}</a></div>`;
                }
                return `<div><span class="inline-pill clean">local-only</span> ${label}</div>`;
              })
              .join("")
          : '<span class="muted">local-only tracking (GitHub optional)</span>';
      } else if (githubCheck === "not_applicable") {
        githubHtml = githubRefs.length
          ? githubRefs
              .map((ref) => {
                const href = ref.url || "";
                const label = escapeHtml(ref.owner && ref.name ? `${ref.owner}/${ref.name}` : href || "unknown");
                if (href.startsWith("http")) {
                  return `<div><span class="inline-pill clean">configured</span> <a class="repo-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${label}</a></div>`;
                }
                return `<div><span class="inline-pill clean">configured</span> ${label}</div>`;
              })
              .join("")
          : '<span class="muted">verification unavailable in this runtime</span>';
      } else if (githubRefs.length) {
        githubHtml = githubRefs
          .map((ref) => {
            const exists = ref.exists ? "linked" : "missing";
            const href = ref.url || "";
            const label = escapeHtml(ref.owner && ref.name ? `${ref.owner}/${ref.name}` : href || "unknown");
            if (href.startsWith("http")) {
              return `<div><span class="inline-pill ${ref.exists ? "clean" : "dirty"}">${exists}</span> <a class="repo-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${label}</a></div>`;
            }
            return `<div><span class="inline-pill ${ref.exists ? "clean" : "dirty"}">${exists}</span> ${label}</div>`;
          })
          .join("");
      }

      return `
        <tr>
          <td>${name}</td>
          <td><span class="inline-pill ${health === "healthy" ? "clean" : "dirty"}">${health}</span></td>
          <td>${canonicalHtml}</td>
          <td>${localHtml}</td>
          <td>${githubHtml}</td>
        </tr>
      `;
    })
    .join("");

  els.trackedProjectsBody.innerHTML = rows;
}

function renderRouterSummary(summary, generatedAt) {
  setText(els.routerReadyCount, String(summary.membership_ready_count ?? 0));
  setText(els.routerUnavailableCount, String(summary.membership_unavailable_count ?? 0));
  setText(els.routerQuotaUnknownCount, String(summary.membership_quota_unknown_count ?? 0));
  setText(els.routerFilesystemStatus, String(summary.filesystem_status ?? "unknown"));
  if (generatedAt) {
    setText(els.routerGeneratedAt, `Updated: ${formatIso(generatedAt)}`);
  }
}

function renderMemberships(memberships) {
  if (!els.membershipTableBody) return;
  if (!Array.isArray(memberships) || memberships.length === 0) {
    els.membershipTableBody.innerHTML = '<tr><td colspan="6">No memberships configured.</td></tr>';
    return;
  }

  const rows = memberships
    .map((membership) => {
      const health = String(membership.health || "unknown");
      const healthClass = health === "ready" ? "clean" : "dirty";
      const versionOrPath = membership.kind === "cli"
        ? escapeHtml(membership.version || membership.resolved_command || "--")
        : `<code>${escapeHtml(membership.path || "--")}</code>`;
      const quota = membership.quota || {};
      const remaining = formatRemaining(quota.remaining, quota.unit);
      const nextReset = formatIso(quota.next_reset_at || "");
      const nextUpdate = formatIso(membership.next_update_at || "");
      return `
        <tr>
          <td>${escapeHtml(membership.name || membership.id || "unknown")}</td>
          <td><span class="inline-pill ${healthClass}">${escapeHtml(health)}</span></td>
          <td>${versionOrPath}</td>
          <td>${escapeHtml(remaining)}</td>
          <td>${escapeHtml(nextReset)}</td>
          <td>${escapeHtml(nextUpdate)}</td>
        </tr>
      `;
    })
    .join("");

  els.membershipTableBody.innerHTML = rows;
}

function renderRouterSamples(rows) {
  if (!els.routerSampleRecs) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    els.routerSampleRecs.innerHTML = "<li>No routing recommendations available.</li>";
    return;
  }

  els.routerSampleRecs.innerHTML = rows
    .map((row) => {
      const taskName = escapeHtml(row.task_name || row.task_type || "Task");
      const recommendation = row.recommendation || {};
      const modelName = escapeHtml(recommendation.name || "no eligible provider");
      const score = recommendation.score === undefined ? "--" : escapeHtml(String(recommendation.score));
      const reasons = Array.isArray(recommendation.reasons) ? recommendation.reasons.join(", ") : "";
      return `<li><strong>${taskName}</strong>: ${modelName} (score ${score})${reasons ? `<br>${escapeHtml(reasons)}` : ""}</li>`;
    })
    .join("");
}

function renderAccessHub(accounts) {
  if (!els.accessHubBody) return;
  if (!Array.isArray(accounts) || accounts.length === 0) {
    els.accessHubBody.innerHTML = '<tr><td colspan="5">No membership accounts detected.</td></tr>';
    return;
  }

  const rows = accounts
    .map((account) => {
      const authStatus = String(account.auth_status || "unknown");
      const authClass = authStatus === "connected" ? "clean" : (authStatus === "signed_out" ? "dirty" : "");
      const name = escapeHtml(account.name || account.membership_id || "unknown");
      const provider = escapeHtml(account.provider || "unknown");
      const authDetail = escapeHtml(account.auth_detail || "");
      const googleUrl = String(account.google_signin_url || "");
      const portalUrl = String(account.portal_url || "");
      const cliLogin = escapeHtml(account.cli_login_command || "--");

      const googleLink = googleUrl.startsWith("http")
        ? `<a class="repo-link" href="${escapeHtml(googleUrl)}" target="_blank" rel="noreferrer">Sign in</a>`
        : "--";
      const portalLink = portalUrl.startsWith("http")
        ? `<a class="repo-link" href="${escapeHtml(portalUrl)}" target="_blank" rel="noreferrer">Open</a>`
        : "--";

      return `
        <tr>
          <td><strong>${name}</strong><br><span class="muted">${provider}</span></td>
          <td><span class="inline-pill ${authClass}">${escapeHtml(authStatus)}</span>${authDetail ? `<br><span class="muted">${authDetail}</span>` : ""}</td>
          <td>${googleLink}</td>
          <td>${portalLink}</td>
          <td><code>${cliLogin}</code></td>
        </tr>
      `;
    })
    .join("");

  els.accessHubBody.innerHTML = rows;
}

function _agentMembership(agent) {
  const labels = agent && typeof agent.labels === "object" ? agent.labels : {};
  const byLabel = String(labels.membership_id || labels.model_membership || labels.router_membership || "").trim();
  if (byLabel) return byLabel;
  const capabilities = Array.isArray(agent?.capabilities) ? agent.capabilities : [];
  for (const capability of capabilities) {
    const value = String(capability || "").trim();
    if (value.startsWith("membership:")) {
      return value.split(":", 2)[1] || "";
    }
  }
  return "";
}

function renderControlPlane(controlPlane) {
  const payload = controlPlane && typeof controlPlane === "object" ? controlPlane : {};
  const overview = payload.overview && typeof payload.overview === "object" ? payload.overview : {};
  const tasksSummary = overview.kpi_tasks && typeof overview.kpi_tasks === "object"
    ? overview.kpi_tasks
    : (overview.tasks && typeof overview.tasks === "object" ? overview.tasks : {});
  const agents = Array.isArray(payload.agents) ? payload.agents : [];
  const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];

  setText(els.controlAgentsOnline, String(overview.agents_executor_online ?? overview.agents_online ?? 0));
  setText(els.controlAgentsTotal, String(overview.agents_executor_total ?? overview.agents_total ?? 0));
  setText(els.controlQueued, String(tasksSummary.queued ?? 0));
  setText(els.controlLeased, String(tasksSummary.leased ?? 0));
  setText(els.controlFailed, String(tasksSummary.failed ?? 0));
  setText(els.controlGeneratedAt, `Updated: ${formatIso(payload.generated_at || overview.generated_at || "")}`);
  renderAgentSelectOptions(agents);

  latestControlTasks.clear();
  tasks.forEach((task) => {
    const taskId = String(task?.task_id || "").trim();
    if (taskId) {
      latestControlTasks.set(taskId, task);
    }
  });

  if (els.controlAgentsBody) {
    if (!agents.length) {
      els.controlAgentsBody.innerHTML = '<tr><td colspan="5">No control-plane agents registered.</td></tr>';
    } else {
      els.controlAgentsBody.innerHTML = agents
        .map((agent) => {
          const isOnline = Boolean(agent.online);
          const statusLabel = isOnline ? "online" : "offline";
          const capabilities = Array.isArray(agent.capabilities) ? agent.capabilities.slice(0, 6) : [];
          const membership = _agentMembership(agent);
          const heartbeat = formatIso(agent.last_heartbeat_at || "");
          return `
            <tr>
              <td><strong>${escapeHtml(agent.name || agent.agent_id || "unknown")}</strong><br><span class="muted">${escapeHtml(agent.agent_id || "")}</span></td>
              <td><span class="inline-pill ${isOnline ? "clean" : "dirty"}">${statusLabel}</span></td>
              <td>${capabilities.length ? `<code>${escapeHtml(capabilities.join(", "))}</code>` : "--"}</td>
              <td>${membership ? `<code>${escapeHtml(membership)}</code>` : "--"}</td>
              <td>${escapeHtml(heartbeat)}</td>
            </tr>
          `;
        })
        .join("");
    }
  }

  if (els.controlTasks) {
    if (!tasks.length) {
      els.controlTasks.innerHTML = "<li>No tasks in control queue.</li>";
    } else {
      els.controlTasks.innerHTML = tasks
        .slice(0, 12)
        .map((task) => {
          const routing = task && typeof task.routing === "object" ? task.routing : {};
          const routedTo = routing.required_membership_id || routing.recommended_membership_id || "";
          const owner = task.lease_owner ? ` lease: ${task.lease_owner}` : "";
          const attempts = `${task.attempts ?? 0}/${task.max_attempts ?? 0}`;
          const progress = task.progress ? ` progress: ${task.progress}` : "";
          const routeLine = routedTo ? `<br>route: <code>${escapeHtml(routedTo)}</code>` : "";
          const displayTitle = String(task.display_title || task.title || task.task_id || "task");
          const pickButton = task.task_id
            ? ` <button type="button" class="btn ghost tiny pick-control-task" data-task-id="${escapeHtml(task.task_id)}">Use</button>`
            : "";
          const leaseButton = task.task_id && String(task.status || "").toLowerCase() === "queued"
            ? ` <button type="button" class="btn ghost tiny lease-control-task" data-task-id="${escapeHtml(task.task_id)}">Lease</button>`
            : "";
          const completeButton = task.task_id && String(task.status || "").toLowerCase() === "leased"
            ? ` <button type="button" class="btn ghost tiny complete-control-task" data-task-id="${escapeHtml(task.task_id)}">Complete</button>`
            : "";
          return `<li><strong>[${escapeHtml(task.status || "queued")}]</strong> ${escapeHtml(displayTitle)}${routeLine}<br>attempts: ${escapeHtml(attempts)}${escapeHtml(owner)}${escapeHtml(progress)}${pickButton}${leaseButton}${completeButton}</li>`;
        })
        .join("");
    }
  }

  if (els.controlEvents) {
    const events = Array.isArray(payload.events) ? payload.events : [];
    if (!events.length) {
      els.controlEvents.innerHTML = "<li>No control events yet.</li>";
    } else {
      els.controlEvents.innerHTML = events
        .slice(0, 12)
        .map((event) => {
          const taskRef = event.task_id ? ` task=${event.task_id}` : "";
          const agentRef = event.agent_id ? ` agent=${event.agent_id}` : "";
          return `<li><strong>${escapeHtml(event.event_type || "event")}</strong><br>${escapeHtml(formatIso(event.created_at || ""))}${escapeHtml(taskRef)}${escapeHtml(agentRef)}</li>`;
        })
        .join("");
    }
  }
}

async function controlFetch(url, options = {}) {
  const token = getControlToken();
  if (!token) {
    throw new Error("control token missing");
  }
  const zkpassProof = getZkPassProof();

  const headers = {
    ...(options.headers || {}),
    "X-Control-Token": token,
  };
  if (zkpassProof) {
    headers["X-ZKPass-Proof"] = zkpassProof;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail = `request failed (${response.status})`;
    try {
      const payload = await response.json();
      if (payload && payload.detail) {
        detail = String(payload.detail);
      }
    } catch (_error) {
      // keep fallback detail
    }
    throw new Error(detail);
  }
  return response.json();
}

async function saveControlTokenFromForm(event) {
  event.preventDefault();
  const token = String(els.controlTokenInput?.value || "").trim();
  if (!token) {
    setControlStatus("Enter a control token before saving.", true);
    return;
  }
  saveStoredControlToken(token);
  setControlStatus("Control token saved in this browser.");
}

function clearControlToken() {
  if (els.controlTokenInput) {
    els.controlTokenInput.value = "";
  }
  saveStoredControlToken("");
  setControlStatus("Control token cleared.", false);
}

async function saveZkPassProofFromForm(event) {
  event.preventDefault();
  const rawProof = String(els.zkpassProofInput?.value || "").trim();
  if (!rawProof) {
    setControlStatus("Enter a zkPass proof before saving.", true);
    return;
  }
  saveStoredZkPassProof(rawProof);
  setControlStatus("zkPass proof saved in this browser.");
}

function clearZkPassProof() {
  if (els.zkpassProofInput) {
    els.zkpassProofInput.value = "";
  }
  saveStoredZkPassProof("");
  setControlStatus("zkPass proof cleared.", false);
}

async function verifyZkPassProof() {
  const rawProof = getZkPassProof();
  if (!rawProof) {
    setControlStatus("No zkPass proof found. Paste one and save first.", true);
    return;
  }
  try {
    const response = await controlFetch("/api/security/zkpass/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "projects.dashboard.verify",
        proof: parseZkPassProof(rawProof),
      }),
    });
    const verification = response.verification || {};
    if (verification.valid) {
      const schemaId = String((verification.claims || {}).schema_id || "unknown-schema");
      setControlStatus(`zkPass proof verified (schema=${schemaId}).`);
    } else {
      const errors = Array.isArray(verification.errors) ? verification.errors.join("; ") : "proof invalid";
      setControlStatus(`zkPass verify failed: ${errors}`, true);
    }
  } catch (error) {
    setControlStatus(`zkPass verify request failed: ${String(error.message || error)}`, true);
  }
}

async function createControlTask(event) {
  event.preventDefault();
  const title = String(els.controlTaskTitle?.value || "").trim();
  if (!title) {
    setControlStatus("Task title is required.", true);
    return;
  }

  const taskType = String(els.controlTaskType?.value || "coding").trim() || "coding";
  const priorityLevel = String(els.controlTaskPriority?.value || "medium").trim() || "medium";
  const capabilities = csvCapabilities(els.controlTaskCapabilities?.value || "");
  const description = String(els.controlTaskNote?.value || "").trim();
  const payload = {};
  if (description) {
    payload.description = description;
  }

  const requestPayload = {
    title,
    payload,
    required_capabilities: capabilities,
    priority: mapPriorityToValue(priorityLevel),
    max_attempts: 3,
    created_by: "projects-dashboard",
    task_type: taskType,
    enforce_routing: Boolean(els.controlTaskEnforce?.checked),
  };
  if (taskType === "browser_automation") {
    requestPayload.requires_browser = true;
  }

  try {
    const response = await controlFetch("/api/control/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    const created = response.task || {};
    const routing = response.routing || {};
    const routed = routing.required_membership_id || routing.recommended_membership_id || "none";
    setControlStatus(`Created ${created.task_id || "task"} routed to ${routed}.`);
    if (els.controlTaskTitle) els.controlTaskTitle.value = "";
    if (els.controlTaskCapabilities) els.controlTaskCapabilities.value = "";
    if (els.controlTaskNote) els.controlTaskNote.value = "";
    if (els.controlUpdateTaskId && created.task_id) {
      els.controlUpdateTaskId.value = String(created.task_id);
    }
    await loadOverview(true);
  } catch (error) {
    setControlStatus(`Task create failed: ${String(error.message || error)}`, true);
  }
}

async function updateControlTask(event) {
  event.preventDefault();
  const taskId = String(els.controlUpdateTaskId?.value || "").trim();
  if (!taskId) {
    setControlStatus("Task id is required for updates.", true);
    return;
  }

  const progress = String(els.controlUpdateProgress?.value || "").trim();
  const note = String(els.controlUpdateNote?.value || "").trim();
  const payloadMerge = {};
  if (progress) {
    payloadMerge.progress = progress;
  }
  if (!note && Object.keys(payloadMerge).length === 0) {
    setControlStatus("Add progress or a note to update the task.", true);
    return;
  }

  try {
    await controlFetch(`/api/control/tasks/${encodeURIComponent(taskId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        updated_by: "projects-dashboard",
        payload_merge: payloadMerge,
        note,
      }),
    });
    setControlStatus(`Updated ${taskId}.`);
    if (els.controlUpdateProgress) els.controlUpdateProgress.value = "";
    if (els.controlUpdateNote) els.controlUpdateNote.value = "";
    await loadOverview(true);
  } catch (error) {
    setControlStatus(`Task update failed: ${String(error.message || error)}`, true);
  }
}

function selectTaskForControlForms(taskId) {
  const id = String(taskId || "").trim();
  if (!id) return;
  if (els.controlUpdateTaskId) {
    els.controlUpdateTaskId.value = id;
  }
  if (els.controlResolveTaskId) {
    els.controlResolveTaskId.value = id;
  }

  const task = latestControlTasks.get(id);
  if (!task || typeof task !== "object") return;
  const leaseOwner = String(task.lease_owner || "").trim();
  if (leaseOwner && els.controlResolveAgent) {
    const has = Array.from(els.controlResolveAgent.options).some((option) => String(option.value || "").trim() === leaseOwner);
    if (has) {
      els.controlResolveAgent.value = leaseOwner;
    }
  }
}

async function leaseControlTask(event, forcedTaskId = "") {
  if (event) {
    event.preventDefault();
  }
  const agentId = String(els.controlLeaseAgent?.value || "").trim();
  if (!agentId) {
    setControlStatus("Choose an agent to lease queued tasks.", true);
    return;
  }

  const requestedTaskId = String(forcedTaskId || "").trim();
  const caps = csvCapabilities(els.controlLeaseCapabilities?.value || "");
  const limit = clampInt(els.controlLeaseLimit?.value || "1", 1, 5, 1);
  const payload = {
    agent_id: agentId,
    lease_seconds: CONTROL_LEASE_SECONDS,
    limit,
  };
  if (caps.length) {
    payload.capabilities = caps;
  }

  try {
    const response = await controlFetch("/api/control/tasks/lease", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const leased = Array.isArray(response.leased_tasks) ? response.leased_tasks : [];
    if (!leased.length) {
      setControlStatus(`No eligible queued tasks for ${agentId}.`);
      await loadOverview(true);
      return;
    }

    let selected = leased[0];
    if (requestedTaskId) {
      const exact = leased.find((task) => String(task?.task_id || "").trim() === requestedTaskId);
      if (exact) {
        selected = exact;
      }
    }
    const selectedId = String(selected?.task_id || "").trim();
    if (selectedId) {
      selectTaskForControlForms(selectedId);
      if (els.controlResolveAgent) {
        const has = Array.from(els.controlResolveAgent.options).some((option) => String(option.value || "").trim() === agentId);
        if (has) {
          els.controlResolveAgent.value = agentId;
        }
      }
    }

    setControlStatus(`Leased ${leased.length} task(s) to ${agentId}${selectedId ? ` (selected ${selectedId})` : ""}.`);
    await loadOverview(true);
  } catch (error) {
    setControlStatus(`Task lease failed: ${String(error.message || error)}`, true);
  }
}

async function resolveControlTask(event, forcedAction = "", forcedTaskId = "") {
  if (event) {
    event.preventDefault();
  }
  const taskId = String(forcedTaskId || els.controlResolveTaskId?.value || "").trim();
  if (!taskId) {
    setControlStatus("Task id is required to complete/fail.", true);
    return;
  }

  const agentId = String(els.controlResolveAgent?.value || "").trim();
  if (!agentId) {
    setControlStatus("Choose an agent to complete/fail the task.", true);
    return;
  }

  const action = String(forcedAction || els.controlResolveAction?.value || "complete").trim();
  const message = String(els.controlResolveMessage?.value || "").trim();
  const membershipId = String(els.controlResolveMembership?.value || "").trim();
  const errorCode = String(els.controlResolveErrorCode?.value || "").trim();

  try {
    if (action === "complete") {
      const result = {};
      if (message) {
        result.summary = message;
      }
      result.updated_by = "projects-dashboard";
      await controlFetch(`/api/control/tasks/${encodeURIComponent(taskId)}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_id: agentId,
          result,
        }),
      });
      setControlStatus(`Completed ${taskId} by ${agentId}.`);
    } else {
      const retryable = action === "fail_retry";
      const errorText = message || `task failed from dashboard (${action})`;
      const payload = {
        agent_id: agentId,
        error: errorText,
        retryable,
      };
      if (errorCode) {
        payload.error_code = errorCode;
      }
      if (membershipId) {
        payload.membership_id = membershipId;
      }
      await controlFetch(`/api/control/tasks/${encodeURIComponent(taskId)}/fail`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setControlStatus(`${retryable ? "Failed+retried" : "Failed"} ${taskId} by ${agentId}.`);
    }

    if (els.controlResolveMessage) els.controlResolveMessage.value = "";
    if (els.controlResolveMembership) els.controlResolveMembership.value = "";
    if (els.controlResolveErrorCode) els.controlResolveErrorCode.value = "";
    await loadOverview(true);
  } catch (error) {
    setControlStatus(`Task resolve failed: ${String(error.message || error)}`, true);
  }
}

function handleControlTaskListClick(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const leaseButton = target.closest(".lease-control-task");
  if (leaseButton) {
    const taskId = String(leaseButton.getAttribute("data-task-id") || "").trim();
    if (taskId) {
      selectTaskForControlForms(taskId);
      setControlStatus(`Selected ${taskId} for leasing. Confirm agent, then submit Lease Task.`);
    }
    return;
  }
  const completeButton = target.closest(".complete-control-task");
  if (completeButton) {
    const taskId = String(completeButton.getAttribute("data-task-id") || "").trim();
    if (taskId) {
      selectTaskForControlForms(taskId);
      if (els.controlResolveAction) {
        els.controlResolveAction.value = "complete";
      }
      setControlStatus(`Selected ${taskId} for completion. Review and submit Complete / Fail Task.`);
    }
    return;
  }
  const button = target.closest(".pick-control-task");
  if (!button) return;
  const taskId = String(button.getAttribute("data-task-id") || "").trim();
  if (!taskId) return;
  selectTaskForControlForms(taskId);
  setControlStatus(`Selected ${taskId} for update.`);
}

function initializeControlToken() {
  const token = loadStoredControlToken();
  if (token && els.controlTokenInput) {
    els.controlTokenInput.value = token;
    setControlStatus("Control token loaded from browser storage.");
  }
}

function initializeZkPassProof() {
  const proof = loadStoredZkPassProof();
  if (proof && els.zkpassProofInput) {
    els.zkpassProofInput.value = proof;
    setControlStatus("zkPass proof loaded from browser storage.");
  }
}

async function refreshRouterQuotas(forceRefresh = false) {
  const response = await fetch("/api/router/quotas/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force: forceRefresh }),
  });
  if (!response.ok) {
    throw new Error(`Failed quota refresh (${response.status})`);
  }
  return response.json();
}

async function loadRouterOverview(forceRefresh = false) {
  if (forceRefresh) {
    await refreshRouterQuotas(false).catch(() => {});
  }
  const url = forceRefresh ? "/api/router/overview?refresh=true" : "/api/router/overview";
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed router overview (${response.status})`);
  }
  const payload = await response.json();
  renderRouterSummary(payload.summary || {}, payload.generated_at);
  renderMemberships(payload.memberships || []);
  renderAccessHub((payload.access_hub || {}).accounts || []);
  renderRouterSamples(payload.sample_recommendations || []);
}

function renderRepos(repos) {
  if (!els.repoTableBody) return;

  if (!Array.isArray(repos) || repos.length === 0) {
    els.repoTableBody.innerHTML = `<tr><td colspan="5">No repos detected in canonical workspace.</td></tr>`;
    return;
  }

  const rows = repos
    .map((repo) => {
      const repoUrl = repo.github_url || repo.remote || "";
      const repoName = escapeHtml(repo.name || "unknown");
      const link = repoUrl.startsWith("http")
        ? `<a class="repo-link" href="${escapeHtml(repoUrl)}" target="_blank" rel="noreferrer">${repoName}</a>`
        : repoName;
      const dirty = Number(repo.dirty_files || 0);
      const dirtyPill = dirty > 0
        ? `<span class="inline-pill dirty">dirty: ${dirty}</span>`
        : '<span class="inline-pill clean">clean</span>';
      const githubState = repo.github_archived ? "archived" : "active";

      return `
        <tr>
          <td>${link}</td>
          <td>${escapeHtml(repo.branch || "-")}</td>
          <td>${dirtyPill}</td>
          <td>${escapeHtml(repo.size || "-")}</td>
          <td>${escapeHtml(githubState)}</td>
        </tr>
      `;
    })
    .join("");

  els.repoTableBody.innerHTML = rows;
}

function renderCleanup(cleanup) {
  setText(els.cleanupManifestPath, `Manifest: ${cleanup.manifest_path || "not found"}`);

  if (els.cleanupReasons) {
    const rows = Array.isArray(cleanup.by_reason) ? cleanup.by_reason : [];
    if (!rows.length) {
      els.cleanupReasons.innerHTML = "<li>No cleanup manifest data yet.</li>";
    } else {
      els.cleanupReasons.innerHTML = rows
        .map((row) => `<li><strong>${escapeHtml(String(row.count || 0))}</strong> - ${escapeHtml(row.reason || "")}</li>`)
        .join("");
    }
  }

  if (els.recentMoves) {
    const rows = Array.isArray(cleanup.recent_moves) ? cleanup.recent_moves : [];
    if (!rows.length) {
      els.recentMoves.innerHTML = "<li>No move history found.</li>";
    } else {
      els.recentMoves.innerHTML = rows
        .map((row) => {
          const source = escapeHtml(row.source || "");
          const size = escapeHtml(row.size_before || "");
          return `<li><strong>${size}</strong> - ${source}</li>`;
        })
        .join("");
    }
  }
}

function renderWorkspaceSizes(rows) {
  if (!els.workspaceSizes) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    els.workspaceSizes.innerHTML = "<li>No workspace sizing data available.</li>";
    return;
  }
  els.workspaceSizes.innerHTML = rows
    .map((row) => `<li><strong>${escapeHtml(row.size || "0B")}</strong> - ${escapeHtml(row.label || row.path || "")}</li>`)
    .join("");
}

function renderNextActions(actions) {
  if (!els.nextActions) return;
  if (!Array.isArray(actions) || actions.length === 0) {
    els.nextActions.innerHTML = "<li>No prioritized actions right now.</li>";
    return;
  }
  els.nextActions.innerHTML = actions
    .map((action) => {
      const priority = escapeHtml(action.priority || "medium");
      const title = escapeHtml(action.title || "Untitled action");
      const detail = escapeHtml(action.detail || "");
      const target = escapeHtml(action.target || "");
      return `<li><strong>[${priority}]</strong> ${title}${detail ? `<br>${detail}` : ""}${target ? `<br>Target: <code>${target}</code>` : ""}</li>`;
    })
    .join("");
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
      { timelineLimit: 10 },
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
  widgets.renderMiniTimeline(els.logbookTimeline, logbookPayload.timeline, { limit: 10 });
}

async function patchCardStatus(cardId, newStatus) {
  const response = await fetch(`/api/projects/cards/${encodeURIComponent(cardId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus }),
  });
  if (!response.ok) {
    throw new Error(`Failed to update card (${response.status})`);
  }
}

function wireDropzones() {
  document.querySelectorAll(".kanban-column").forEach((column) => {
    const status = column.getAttribute("data-status") || "backlog";
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      column.classList.add("dragover");
    });
    column.addEventListener("dragleave", () => {
      column.classList.remove("dragover");
    });
    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("dragover");
      const cardId = event.dataTransfer?.getData("text/plain") || "";
      if (!cardId) return;
      try {
        await patchCardStatus(cardId, status);
        await loadOverview(true);
      } catch (_error) {
        // No-op: keep UI stable and refresh on next poll.
      }
    });
  });
}

async function createCardFromForm(event) {
  event.preventDefault();
  const title = (els.newTitle?.value || "").trim();
  if (!title) return;

  const payload = {
    title,
    project: (els.newProject?.value || "General").trim() || "General",
    priority: els.newPriority?.value || "medium",
    status: els.newStatus?.value || "backlog",
  };

  const response = await fetch("/api/projects/cards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    return;
  }

  if (els.newTitle) els.newTitle.value = "";
  if (els.newProject) els.newProject.value = "";
  await loadOverview(true);
}

async function runSync() {
  const response = await fetch("/api/projects/sync", { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed sync request (${response.status})`);
  }
  const payload = await response.json();
  const syncedAt = formatIso(payload.synced_at);
  setText(els.nextActionsMeta, `Last sync: ${syncedAt}`);
  await loadOverview(true);
}

async function loadOverview(forceRefresh = false) {
  const url = forceRefresh ? "/api/projects/overview?refresh=true" : "/api/projects/overview";
  const logbookClient = window.SapphireFrontendLogbookClient;

  const [response, logbookResponse] = await Promise.all([
    fetch(url, { cache: "no-store" }),
    logbookClient && typeof logbookClient.fetchLogbookMaybe === "function"
      ? logbookClient.fetchLogbookMaybe({ refresh: forceRefresh, eventLimit: 24 })
      : fetch(`/api/frontend/logbook?${new URLSearchParams({ ...(forceRefresh ? { refresh: "true" } : {}), event_limit: "24" }).toString()}`, { cache: "no-store" }).catch(() => null),
  ]);
  if (!response.ok) {
    throw new Error(`Failed overview request (${response.status})`);
  }

  const payload = await response.json();
  let logbookPayload = {};
  if (logbookClient && typeof logbookClient.fetchLogbookMaybe === "function") {
    logbookPayload = logbookResponse || {};
  } else if (logbookResponse && logbookResponse.ok) {
    try {
      logbookPayload = await logbookResponse.json();
    } catch (_error) {
      logbookPayload = {};
    }
  }
  renderSummary(payload.summary || {});
  renderBoard(payload.board?.cards || []);
  renderTrackedProjects(payload.tracked_projects || []);
  renderRepos(payload.repos || []);
  renderCleanup(payload.cleanup || {});
  renderWorkspaceSizes(payload.workspace_sizes || []);
  renderNextActions(payload.next_actions || []);
  renderSharedLogbook(logbookPayload);
  renderControlPlane(payload.control_plane || {});
  if (els.nextActionsMeta && payload.generated_at) {
    setText(els.nextActionsMeta, `Generated: ${formatIso(payload.generated_at)}`);
  }
  setText(els.generatedAt, `Updated: ${formatIso(payload.generated_at)}`);
  await loadRouterOverview(forceRefresh).catch(() => {});
}

wireDropzones();
els.refreshButton?.addEventListener("click", () => {
  loadOverview(true).catch(() => {});
});
els.syncButton?.addEventListener("click", () => {
  runSync().catch(() => {});
});
els.newCardForm?.addEventListener("submit", (event) => {
  createCardFromForm(event).catch(() => {});
});
els.controlTokenForm?.addEventListener("submit", (event) => {
  saveControlTokenFromForm(event).catch(() => {});
});
els.clearControlTokenButton?.addEventListener("click", () => {
  clearControlToken();
});
els.zkpassProofForm?.addEventListener("submit", (event) => {
  saveZkPassProofFromForm(event).catch(() => {});
});
els.clearZkpassProofButton?.addEventListener("click", () => {
  clearZkPassProof();
});
els.verifyZkpassProofButton?.addEventListener("click", () => {
  verifyZkPassProof().catch(() => {});
});
els.controlCreateTaskForm?.addEventListener("submit", (event) => {
  createControlTask(event).catch(() => {});
});
els.controlUpdateTaskForm?.addEventListener("submit", (event) => {
  updateControlTask(event).catch(() => {});
});
els.controlLeaseTaskForm?.addEventListener("submit", (event) => {
  leaseControlTask(event).catch(() => {});
});
els.controlResolveTaskForm?.addEventListener("submit", (event) => {
  resolveControlTask(event).catch(() => {});
});
els.controlTasks?.addEventListener("click", (event) => {
  handleControlTaskListClick(event);
});

initializeControlToken();
initializeZkPassProof();
loadOverview().catch(() => {
  setText(els.generatedAt, "Updated: failed");
});
setInterval(() => {
  loadOverview().catch(() => {});
}, 60000);
