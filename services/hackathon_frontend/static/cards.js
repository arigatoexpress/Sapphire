// Sapphire OS hackathon-frontend — tab nav + live RPC probe widget.
// No frameworks. ~3KB unminified. Defensive: every selector is null-checked.

(function () {
  "use strict";

  // ------------------------------------------------------------ tab switcher
  document.querySelectorAll(".tabs").forEach(function (nav) {
    var slug = nav.dataset.slug;
    if (!slug) return;
    var card = document.getElementById("card-" + slug);
    if (!card) return;
    nav.addEventListener("click", function (e) {
      var btn = e.target.closest(".tab-btn");
      if (!btn) return;
      var tab = btn.dataset.tab;
      if (!tab) return;
      // Toggle button active state.
      nav.querySelectorAll(".tab-btn").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      // Toggle pane visibility.
      card.querySelectorAll(".tab-pane").forEach(function (p) {
        p.classList.toggle("active", p.dataset.pane === tab);
      });
    });
  });

  // ------------------------------------------------------------ probe runner
  document.querySelectorAll(".probe-btn").forEach(function (btn) {
    if (btn.classList.contains("og-proof-refresh")) return;
    btn.addEventListener("click", function () {
      var slug = btn.dataset.slug;
      if (!slug) return;
      var container = document.getElementById("probe-" + slug);
      if (!container) return;

      btn.disabled = true;
      btn.textContent = "Probing…";

      fetch("/api/probe/" + slug)
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (data) {
          renderProbeResults(container, data);
          btn.textContent = "Re-run probe →";
          btn.disabled = false;
        })
        .catch(function (err) {
          renderProbeError(container, err.message);
          btn.textContent = "Retry probe →";
          btn.disabled = false;
        });
    });
  });

  // ------------------------------------------------------------ 0G proof feed
  var ogPanel = document.getElementById("og-proof-panel");
  if (ogPanel) {
    loadOgProof();
    document.querySelectorAll(".og-proof-refresh").forEach(function (btn) {
      btn.addEventListener("click", loadOgProof);
    });
  }

  function loadOgProof() {
    if (!ogPanel) return;
    ogPanel.innerHTML = '<div class="og-proof-status muted">Loading /api/0g/readiness...</div>';
    Promise.all([
      fetch("/api/0g/readiness").then(function (r) {
        if (!r.ok) throw new Error("readiness HTTP " + r.status);
        return r.json();
      }),
      fetch("/api/0g/feed").then(function (r) {
        if (!r.ok) throw new Error("feed HTTP " + r.status);
        return r.json();
      }),
    ])
      .then(function (pair) {
        renderOgProof(pair[0], pair[1]);
      })
      .catch(function (err) {
        ogPanel.innerHTML =
          '<div class="og-proof-status err">0G proof load failed: <code>' +
          escapeHtml(err.message || "network error") +
          "</code></div>";
      });
  }

  function renderOgProof(readiness, feed) {
    if (!ogPanel) return;
    var artifacts = readiness.public_artifacts || {};
    var rows = (readiness.readiness || [])
      .map(function (row) {
        var cls = row.ok ? "ok" : "pending";
        return (
          '<div class="og-ready-row">' +
          '<span class="og-ready-label">' +
          escapeHtml(row.label) +
          "</span>" +
          '<span class="og-ready-status ' +
          cls +
          '">' +
          escapeHtml(row.status) +
          "</span>" +
          '<span class="og-ready-evidence">' +
          escapeHtml(row.evidence || "") +
          "</span>" +
          "</div>"
        );
      })
      .join("");
    var feedItems = (feed.items || [])
      .map(function (item) {
        var proof = escapeHtml(item.proof || "");
        var body = item.href
          ? '<a href="' + escapeHtml(item.href) + '" target="_blank" rel="noopener">' + proof + "</a>"
          : proof;
        return (
          '<div class="og-feed-item">' +
          '<div class="og-feed-stage">' +
          escapeHtml(item.stage) +
          "</div>" +
          '<div class="og-feed-proof">' +
          body +
          "</div>" +
          "</div>"
        );
      })
      .join("");
    ogPanel.innerHTML =
      '<div class="og-proof-status ' +
      (readiness.status === "live-proof-ready" ? "ok" : "pending") +
      '">' +
      escapeHtml(readiness.status_label || readiness.status || "unknown") +
      "</div>" +
      '<div class="og-artifacts">' +
      artifactCell("Chain", "0G mainnet " + ((readiness.networks || {}).mainnet || {}).chain_id) +
      artifactCell("Contract", artifacts.contract_address || "pending mainnet address") +
      artifactCell("Storage root", artifacts.storage_root_hash || "pending rootHash") +
      artifactCell("Sample tx", artifacts.sample_signal_tx || "pending SignalPublished tx") +
      "</div>" +
      '<div class="section-label">Proof feed</div>' +
      '<div class="og-feed">' +
      feedItems +
      "</div>" +
      '<div class="section-label">Readiness</div>' +
      '<div class="og-ready">' +
      rows +
      "</div>" +
      '<div class="placeholder"><strong>Verify:</strong> <code>' +
      escapeHtml(readiness.verify_command || "") +
      "</code></div>";
  }

  function artifactCell(label, value) {
    return (
      '<div class="og-artifact">' +
      '<div class="og-artifact-label">' +
      escapeHtml(label) +
      "</div>" +
      '<div class="og-artifact-value">' +
      escapeHtml(value || "") +
      "</div>" +
      "</div>"
    );
  }

  function renderProbeResults(container, data) {
    var contracts = (data && data.contracts) || [];
    contracts.forEach(function (c) {
      var statusEl = container.querySelector(
        '.probe-status[data-contract="' + cssEscape(c.name) + '"]'
      );
      if (!statusEl) return;

      if (c.ok && c.bytecode_size > 0) {
        statusEl.classList.remove("muted", "err");
        statusEl.classList.add("ok");
        statusEl.innerHTML =
          '<span class="probe-tick">✓</span> Live on chain · ' +
          c.bytecode_size +
          " bytes of bytecode · preview: <code>" +
          escapeHtml(c.bytecode_preview || "") +
          "…</code>";
      } else if (c.status === "deployment_address_pending") {
        statusEl.classList.add("muted");
        statusEl.innerHTML =
          '<span class="probe-tick muted">○</span> Address pending — see PR for current state.';
      } else if (c.status === "rpc_error") {
        statusEl.classList.remove("muted", "ok");
        statusEl.classList.add("err");
        statusEl.innerHTML =
          '<span class="probe-tick err">✗</span> RPC error: <code>' +
          escapeHtml(c.error || "unknown") +
          "</code> — sponsor RPC may rate-limit; retry in a moment.";
      } else {
        statusEl.classList.remove("muted", "ok");
        statusEl.classList.add("err");
        statusEl.innerHTML =
          '<span class="probe-tick err">✗</span> No bytecode at this address.';
      }
    });
  }

  function renderProbeError(container, msg) {
    var first = container.querySelector(".probe-status");
    if (!first) return;
    first.classList.add("err");
    first.innerHTML =
      '<span class="probe-tick err">✗</span> Probe failed: <code>' +
      escapeHtml(msg || "network error") +
      "</code>";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Polyfill-ish CSS.escape for attribute selectors.
  function cssEscape(s) {
    if (window.CSS && window.CSS.escape) return window.CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }
})();
