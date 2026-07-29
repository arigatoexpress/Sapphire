const stateEls = {
  servicePill: document.getElementById("service-pill"),
  syncMeta: document.getElementById("sync-meta"),
  controlChannel: document.getElementById("control-channel"),
  storeMode: document.getElementById("store-mode"),
  heartbeatMinutes: document.getElementById("heartbeat-minutes"),
  signalCount: document.getElementById("signal-count"),
  signalList: document.getElementById("signal-list"),
  lastRefresh: document.getElementById("last-refresh"),
  promptLock: document.getElementById("prompt-lock"),
  pulsePath: document.getElementById("pulse-path"),
  pulseArea: document.getElementById("pulse-area"),
  pulsePoints: document.getElementById("pulse-points"),
  pulseMin: document.getElementById("pulse-min"),
  pulseMax: document.getElementById("pulse-max"),
  systemAnalysisControl: document.getElementById("system-analysis-control"),
  systemAnalysisExecutor: document.getElementById("system-analysis-executor"),
  systemAnalysisLogkind: document.getElementById("system-analysis-logkind"),
  systemAnalysisRevision: document.getElementById("system-analysis-revision"),
  overnightUpdated: document.getElementById("overnight-updated"),
  overnightMonitorHealth: document.getElementById("overnight-monitor-health"),
  overnightSoakGate: document.getElementById("overnight-soak-gate"),
  overnightTestsDuration: document.getElementById("overnight-tests-duration"),
  overnightTestsSlowest: document.getElementById("overnight-tests-slowest"),
  overnightCycleList: document.getElementById("overnight-cycle-list"),
  overnightSoakList: document.getElementById("overnight-soak-list"),
  overnightTestsList: document.getElementById("overnight-tests-list"),
  overnightTestSummary: document.getElementById("overnight-test-summary"),
};
const currentAssetVersion =
  document.querySelector('meta[name="asset-version"]')?.getAttribute("content")?.trim() || "unknown";

function setText(el, text) {
  if (el) {
    el.textContent = text;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isoToUtcLabel(iso) {
  if (!iso) return "--";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--";
  return `${date.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

function formatSeconds(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return "--";
  if (n >= 10) return `${n.toFixed(1)}s`;
  if (n >= 1) return `${n.toFixed(2)}s`;
  return `${n.toFixed(3)}s`;
}

function formatRatio(success, total) {
  const s = Number(success);
  const t = Number(total);
  if (!Number.isFinite(s) || !Number.isFinite(t) || t <= 0) return "--";
  return `${s}/${t}`;
}

function formatPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "--";
  return `${(n * 100).toFixed(1)}%`;
}

function classifyScore(score) {
  if (typeof score !== "number") return "";
  if (score >= 75) return "score-high";
  if (score <= 45) return "score-low";
  return "";
}

function renderAnalysisList(el, rows, empty = "No data.") {
  if (!el) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    el.innerHTML = `<li>${escapeHtml(empty)}</li>`;
    return;
  }
  el.innerHTML = rows.map((row) => `<li>${typeof row === "string" ? escapeHtml(row) : row}</li>`).join("");
}

function renderAnalysisBars(el, values) {
  if (!el) return;
  const entries = Object.entries(values || {})
    .map(([k, v]) => [String(k), Number(v || 0)])
    .filter(([, v]) => Number.isFinite(v) && v >= 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!entries.length) {
    el.innerHTML = '<p class="empty-state">No logbook activity categories yet.</p>';
    return;
  }
  const total = entries.reduce((sum, [, v]) => sum + v, 0) || 1;
  el.innerHTML = entries
    .slice(0, 6)
    .map(([label, count]) => {
      const pct = Math.max(6, Math.min(100, (count / total) * 100));
      return `
        <div class="analysis-bar-row">
          <div class="analysis-bar-head"><span>${escapeHtml(label)}</span><strong>${escapeHtml(count)}</strong></div>
          <div class="analysis-bar-track"><div class="analysis-bar-fill" style="width:${pct.toFixed(1)}%"></div></div>
        </div>
      `;
    })
    .join("");
}

function renderSystemAnalysis(opsData, logbookData) {
  const ops = opsData && typeof opsData === "object" ? opsData : {};
  const summary = ops.summary && typeof ops.summary === "object" ? ops.summary : {};
  const policyDrift = ops.policy_drift && typeof ops.policy_drift === "object" ? ops.policy_drift : {};
  const queue = ops.queue_routability && typeof ops.queue_routability === "object" ? ops.queue_routability : {};
  const queueSummary = queue.summary && typeof queue.summary === "object" ? queue.summary : {};
  const readiness = ops.executor_readiness && typeof ops.executor_readiness === "object" ? ops.executor_readiness : {};
  const attestation = readiness.attestation && typeof readiness.attestation === "object" ? readiness.attestation : {};
  const toolSummary = readiness.tool_summary && typeof readiness.tool_summary === "object" ? readiness.tool_summary : {};
  const primary = readiness.primary_executor && typeof readiness.primary_executor === "object" ? readiness.primary_executor : {};
  const primaryHost = primary.host && typeof primary.host === "object" ? primary.host : {};

  const controlRows = [
    `policy=${String(summary.policy_mode || "unknown")}${summary.policy_lock_applied ? " (lock)" : ""}`,
    `drift=${Boolean(policyDrift.drift_detected)}${Array.isArray(policyDrift.mismatches) && policyDrift.mismatches.length ? ` · ${policyDrift.mismatches.map((m) => String(m.field || "mismatch")).join(", ")}` : ""}`,
    `queue=Q${Number(summary.tasks_queued || 0)} L${Number(summary.tasks_leased || 0)} F${Number(summary.tasks_failed || 0)}`,
    `queue_stall=${Boolean(summary.queue_stall_detected)} · blocker=${String(summary.queue_top_blocker_reason || "none")}`,
    `routable=${Number(queueSummary.routable_count || 0)}/${Number(queueSummary.queued_count || 0)}`,
  ];
  renderAnalysisList(stateEls.systemAnalysisControl, controlRows, "No control-plane analysis.");

  const executorRows = [
    `executors_online=${Number(attestation.online_executor_count || 0)}/${Number(attestation.executor_count || 0)}`,
    `primary=${String(primary.agent_id || "--")} · ${String(primaryHost.host_id || "--")} (${String(primaryHost.host_class || "--")})`,
    `attested=${Boolean(attestation.all_online_have_host_attestation)}`,
    `tools: gh=${Boolean(toolSummary.gh)} docker=${Boolean(toolSummary.docker)} node=${Boolean(toolSummary.node)} cloud_bridge=${Boolean(toolSummary.gcloud)}`,
  ];
  renderAnalysisList(stateEls.systemAnalysisExecutor, executorRows, "No executor readiness analysis.");

  const logbook = logbookData && typeof logbookData === "object" ? logbookData : {};
  const eventMix = logbook.event_mix && typeof logbook.event_mix === "object" ? logbook.event_mix : {};
  renderAnalysisBars(stateEls.systemAnalysisLogkind, eventMix.by_log_kind || {});
  setText(stateEls.systemAnalysisRevision, `rev: ${String(logbook.service_revision || ops.service_revision || "--")}`);
}

function renderOvernightReliability(snapshot) {
  const data = snapshot && typeof snapshot === "object" ? snapshot : {};
  const monitor = data.monitor && typeof data.monitor === "object" ? data.monitor : {};
  const cycle = data.latest_cycle && typeof data.latest_cycle === "object" ? data.latest_cycle : {};
  const tests = data.tests && typeof data.tests === "object" ? data.tests : {};
  const soak = data.soak && typeof data.soak === "object" ? data.soak : {};
  const monitorHealthy = typeof monitor.healthy === "boolean" ? monitor.healthy : null;
  const alertCount = Number(monitor.alert_count || 0);

  setText(
    stateEls.overnightUpdated,
    `Monitor refresh: ${isoToUtcLabel(monitor.generated_at || soak.generated_at || null)}`
  );
  setText(
    stateEls.overnightMonitorHealth,
    monitorHealthy === null ? "unknown" : monitorHealthy ? `healthy (${alertCount} alerts)` : `alerting (${alertCount})`
  );
  setText(stateEls.overnightSoakGate, String(soak.gate_status || "missing"));
  setText(stateEls.overnightTestsDuration, formatSeconds(tests.duration_seconds));
  setText(stateEls.overnightTestsSlowest, formatSeconds(tests.slowest_test_seconds));
  setText(stateEls.overnightTestSummary, tests.summary_line || "Nightly test summary unavailable.");

  const cycleRows = [];
  if (cycle.timestamp_utc) {
    cycleRows.push(`cycle=${String(cycle.timestamp_utc)}${Number.isFinite(Number(cycle.age_minutes)) ? ` · age=${Math.round(Number(cycle.age_minutes))}m` : ""}`);
  }
  cycleRows.push(`unified_ops=${String(cycle.unified_ops || "unknown")} · tests=${String(cycle.tests || "unknown")}`);
  cycleRows.push(`pi=${String(cycle.pi_fleet_audit || "unknown")} · canary=${String(cycle.canary_soak || "unknown")}`);
  cycleRows.push(`queue=Q${Number(cycle.queue || 0)} F${Number(cycle.failed || 0)} · slo=${String(cycle.slo_status || "unknown")}`);
  if (monitorHealthy !== null) {
    cycleRows.push(`monitor=${monitorHealthy ? "healthy" : "alerting"} · alerts=${alertCount}`);
  }
  renderAnalysisList(stateEls.overnightCycleList, cycleRows, "Overnight cycle artifacts unavailable.");

  const soakRows = [
    `gate=${String(soak.gate_status || "unknown")} · latest=${String(soak.latest_observation_outcome || "unknown")}`,
    `success_rate=${formatPercent(soak.success_rate)} · samples=${formatRatio(soak.observations_success, soak.observations_total)}`,
    `errors=${Number(soak.observations_error || 0)} · ignored=${Number(soak.ignored_observations_total || 0)}`,
  ];
  if (typeof soak.gate_detail === "string" && soak.gate_detail.trim()) {
    soakRows.push(soak.gate_detail.trim().replace(/\s+/g, " ").slice(0, 180));
  }
  renderAnalysisList(stateEls.overnightSoakList, soakRows, "Canary soak artifacts unavailable.");

  const testsRows = [
    `summary=${String(tests.summary_line || "unavailable")}`,
    `duration=${formatSeconds(tests.duration_seconds)} · slowest=${formatSeconds(tests.slowest_test_seconds)}`,
    `passed=${Number(tests.passed || 0)} · failed=${Number(tests.failed || 0)} · errors=${Number(tests.errors || 0)} · skipped=${Number(tests.skipped || 0)}`,
  ];
  if (tests.slowest_test_name) {
    testsRows.push(`slowest_test=${String(tests.slowest_test_name)}`);
  }
  renderAnalysisList(stateEls.overnightTestsList, testsRows, "Nightly test artifacts unavailable.");
}

function renderSignals(signals) {
  if (!stateEls.signalList) return;

  if (!Array.isArray(signals) || signals.length === 0) {
    stateEls.signalList.innerHTML = '<p class="empty-state">No high-confidence signals in the current window.</p>';
    return;
  }

  stateEls.signalList.innerHTML = signals
    .map((signal) => {
      const title = signal.title || "Untitled signal";
      const source = signal.source || "unknown";
      const score = typeof signal.alpha_score === "number" ? signal.alpha_score : null;
      const scoreLabel = score === null ? "-" : String(score);
      const bias = signal.bias || "Two-sided";
      const confidence = signal.confidence || "low";
      const assets = Array.isArray(signal.assets) && signal.assets.length ? signal.assets.join(", ") : "none";
      const href = signal.url || "#";
      const safeHref = href.startsWith("http") ? href : "#";
      const published = isoToUtcLabel(signal.published_at);
      const scoreClass = classifyScore(score || 0);

      return `
        <article class="signal-card">
          <h4><a href="${safeHref}" target="_blank" rel="noreferrer">${title}</a></h4>
          <div class="signal-meta">
            <span class="badge ${scoreClass}">Alpha ${scoreLabel}</span>
            <span class="badge">${bias}</span>
            <span class="badge">${confidence}</span>
            <span class="badge">${source}</span>
            <span class="badge">assets: ${assets}</span>
            <span class="badge">${published}</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderPulse(signals) {
  if (!stateEls.pulsePath || !stateEls.pulseArea || !stateEls.pulsePoints) return;

  const values = (Array.isArray(signals) ? signals : [])
    .map((s) => (typeof s.alpha_score === "number" ? s.alpha_score : null))
    .filter((s) => s !== null);

  const normalized = values.length > 0 ? values : [50, 50, 50, 50, 50, 50];
  const width = 360;
  const height = 150;
  const padX = 18;
  const padY = 14;
  const baseline = height - padY;
  const min = Math.min(...normalized);
  const max = Math.max(...normalized);
  const spread = Math.max(1, max - min);

  const points = normalized.map((value, index) => {
    const x = padX + (index * (width - padX * 2)) / Math.max(1, normalized.length - 1);
    const y = baseline - ((value - min) / spread) * (height - padY * 2);
    return { x, y, value };
  });

  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${path} L ${points[points.length - 1].x.toFixed(2)} ${baseline.toFixed(2)} L ${points[0].x.toFixed(2)} ${baseline.toFixed(2)} Z`;

  stateEls.pulsePath.setAttribute("d", path);
  stateEls.pulseArea.setAttribute("d", areaPath);
  stateEls.pulsePoints.innerHTML = points
    .map(
      (point) =>
        `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="3.4" fill="#005f86" stroke="#d8f6ff" stroke-width="1.2"></circle>`
    )
    .join("");

  setText(stateEls.pulseMin, String(min));
  setText(stateEls.pulseMax, String(max));
}

async function refreshOverview() {
  try {
    const [overviewResp, opsResp, logbookResp] = await Promise.all([
      fetch("/api/frontend/overview", { cache: "no-store" }),
      fetch("/api/frontend/ops-status?event_limit=20", { cache: "no-store" }).catch(() => null),
      fetch("/api/frontend/logbook?event_limit=30", { cache: "no-store" }).catch(() => null),
    ]);
    if (!overviewResp.ok) {
      throw new Error(`HTTP ${overviewResp.status}`);
    }
    const data = await overviewResp.json();
    const opsData = opsResp && opsResp.ok ? await opsResp.json() : {};
    const logbookData = logbookResp && logbookResp.ok ? await logbookResp.json() : {};
    const healthy = data.status === "ok";
    const latestAssetVersion = (data.frontend_asset_version || "").trim();
    if (latestAssetVersion && currentAssetVersion && latestAssetVersion !== currentAssetVersion) {
      window.location.reload();
      return;
    }

    setText(stateEls.servicePill, `Status: ${healthy ? "operational" : "degraded"}`);
    if (stateEls.servicePill) {
      stateEls.servicePill.classList.toggle("degraded", !healthy);
    }

    setText(stateEls.controlChannel, data.control_channel || "owner_secure_review");
    setText(stateEls.storeMode, data.store || "-");
    setText(
      stateEls.syncMeta,
      `service: ${data.service_name || "local"} | revision: ${data.service_revision || "local"}`
    );
    setText(stateEls.heartbeatMinutes, String(data.heartbeat_interval_minutes ?? "-"));
    const alphaStream = data.alpha_stream && typeof data.alpha_stream === "object" ? data.alpha_stream : {};
    const alphaItems = Array.isArray(alphaStream.items) ? alphaStream.items : [];
    const signalItems = alphaItems.length ? alphaItems : data.signals || [];
    setText(stateEls.signalCount, String(signalItems.length));
    setText(stateEls.lastRefresh, `Last refresh: ${isoToUtcLabel(data.generated_at)}`);

    if (stateEls.promptLock) {
      const publicPrompting = Boolean(data.public_prompting_enabled);
      stateEls.promptLock.textContent = publicPrompting
        ? "Warning: public prompting exposed"
        : "Telegram notification-only";
      stateEls.promptLock.style.borderColor = publicPrompting ? "rgba(196, 103, 57, 0.45)" : "rgba(0, 95, 134, 0.3)";
    }

    renderSignals(signalItems);
    renderPulse(signalItems);
    renderSystemAnalysis(opsData, logbookData);
    renderOvernightReliability(data.overnight_reliability || {});
  } catch (_error) {
    setText(stateEls.servicePill, "Status: degraded");
    if (stateEls.servicePill) {
      stateEls.servicePill.classList.add("degraded");
    }
    if (stateEls.signalList) {
      stateEls.signalList.innerHTML = '<p class="empty-state">Live overview unavailable. Check local control-plane logs.</p>';
    }
    setText(stateEls.lastRefresh, "Last refresh: failed");
    renderPulse([]);
    renderAnalysisList(stateEls.systemAnalysisControl, ["Live ops-status unavailable."]);
    renderAnalysisList(stateEls.systemAnalysisExecutor, ["Executor readiness unavailable."]);
    if (stateEls.systemAnalysisLogkind) {
      stateEls.systemAnalysisLogkind.innerHTML = '<p class="empty-state">Logbook activity mix unavailable.</p>';
    }
    renderOvernightReliability({});
  }
}

refreshOverview();
setInterval(refreshOverview, 60000);
