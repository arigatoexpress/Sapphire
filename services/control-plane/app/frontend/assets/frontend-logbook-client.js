(function () {
  function buildLogbookQuery(options) {
    const opts = options && typeof options === "object" ? options : {};
    const params = new URLSearchParams();
    if (opts.refresh) {
      params.set("refresh", "true");
    }
    const eventLimit = Number(opts.eventLimit || opts.event_limit || 0);
    if (Number.isFinite(eventLimit) && eventLimit > 0) {
      params.set("event_limit", String(Math.max(1, Math.min(200, Math.trunc(eventLimit)))));
    }
    return params.toString();
  }

  async function fetchLogbook(options) {
    const query = buildLogbookQuery(options);
    const suffix = query ? `?${query}` : "";
    const response = await fetch(`/api/frontend/logbook${suffix}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`frontend logbook request failed (${response.status})`);
    }
    return response.json();
  }

  async function fetchLogbookMaybe(options) {
    try {
      return await fetchLogbook(options);
    } catch (_error) {
      return null;
    }
  }

  function renderSharedWidgets(targets, logbookPayload, options) {
    const widgets = window.SapphireLogbookWidgets;
    if (!widgets || !targets || !logbookPayload || typeof logbookPayload !== "object") return;
    const opts = options && typeof options === "object" ? options : {};
    widgets.renderLogbookSummary(targets.summary, logbookPayload);
    widgets.renderCommunicationCategoryCards(targets.commCards, logbookPayload.communication_views);
    widgets.renderCommunicationLedgers(
      {
        decision: targets.decision,
        handoff: targets.handoff,
        incident: targets.incident,
        verification: targets.verification,
      },
      logbookPayload.communication_views,
    );
    widgets.renderMiniTimeline(targets.timeline, logbookPayload.timeline, { limit: Number(opts.timelineLimit || 8) });
  }

  window.SapphireFrontendLogbookClient = {
    buildLogbookQuery,
    fetchLogbook,
    fetchLogbookMaybe,
    renderSharedWidgets,
  };
})();
