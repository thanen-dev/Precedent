/**
 * Precedent Embed Widget — Phase 4
 * Fetches the latest HIGH-risk conflict from GitHub Pages and renders
 * a compact intelligence card that can be embedded on any site.
 *
 * Usage:
 *   <div data-precedent-widget></div>
 *   <script src="https://thanen-dev.github.io/precedent/widget.js" async></script>
 *
 * Optional attributes on the container div:
 *   data-precedent-theme="light|dark"   (default: auto)
 *   data-precedent-compact="true"       (minimal one-line display)
 */
(function () {
  "use strict";

  var BASE_URL = "https://thanen-dev.github.io/precedent";
  var DATA_URL = BASE_URL + "/conflicts-data.json";
  var SITE_URL = BASE_URL + "/conflicts.html";
  var ANALYZE_URL = BASE_URL + "/analyze.html";

  /* ── styles injected once ─────────────────────────────────────────── */
  var CSS = [
    ".prec-widget{font-family:system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.5;border:1px solid rgba(15,31,61,.15);border-left:3px solid #b02020;background:#fff;color:#0f1f3d;max-width:480px;box-sizing:border-box}",
    ".prec-widget *{box-sizing:border-box}",
    ".prec-widget[data-theme=dark]{background:#0d1628;color:#c8d7f0;border-color:rgba(200,215,240,.12)}",
    ".prec-widget-head{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:rgba(15,31,61,.04);border-bottom:1px solid rgba(15,31,61,.10)}",
    ".prec-widget[data-theme=dark] .prec-widget-head{background:rgba(200,215,240,.04);border-bottom-color:rgba(200,215,240,.10)}",
    ".prec-widget-badge{font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;color:#b02020;font-family:monospace}",
    ".prec-widget-powered{font-size:10px;color:rgba(15,31,61,.40);font-family:monospace;letter-spacing:.04em;text-decoration:none}",
    ".prec-widget[data-theme=dark] .prec-widget-powered{color:rgba(200,215,240,.35)}",
    ".prec-widget-powered:hover{color:#0f1f3d}",
    ".prec-widget[data-theme=dark] .prec-widget-powered:hover{color:#c8d7f0}",
    ".prec-widget-body{padding:12px}",
    ".prec-widget-dim{font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-family:monospace;color:#1a3a6b;margin-bottom:6px;font-weight:500}",
    ".prec-widget[data-theme=dark] .prec-widget-dim{color:#6a82a8}",
    ".prec-widget-text{font-size:13px;line-height:1.65;color:inherit;margin-bottom:10px}",
    ".prec-widget-breaking{font-size:11px;font-family:monospace;color:rgba(15,31,61,.50);border-left:2px solid rgba(15,31,61,.15);padding-left:8px;letter-spacing:.02em}",
    ".prec-widget[data-theme=dark] .prec-widget-breaking{color:rgba(200,215,240,.40);border-left-color:rgba(200,215,240,.15)}",
    ".prec-widget-foot{display:flex;gap:8px;padding:8px 12px;border-top:1px solid rgba(15,31,61,.08);background:rgba(15,31,61,.02)}",
    ".prec-widget[data-theme=dark] .prec-widget-foot{border-top-color:rgba(200,215,240,.08);background:rgba(200,215,240,.02)}",
    ".prec-widget-link{font-size:10px;letter-spacing:.10em;text-transform:uppercase;font-family:monospace;color:#1a3a6b;text-decoration:none;padding:4px 10px;border:1px solid rgba(15,31,61,.18);transition:background .1s,color .1s}",
    ".prec-widget-link:hover{background:#0f1f3d;color:#f4f6f9;border-color:#0f1f3d}",
    ".prec-widget-link.primary{background:#0f1f3d;color:#f4f6f9;border-color:#0f1f3d}",
    ".prec-widget-link.primary:hover{background:#1a3a6b;border-color:#1a3a6b}",
    ".prec-widget[data-theme=dark] .prec-widget-link{color:#c8d7f0;border-color:rgba(200,215,240,.20)}",
    ".prec-widget[data-theme=dark] .prec-widget-link:hover{background:#c8d7f0;color:#0f1f3d}",
    ".prec-widget-error{padding:12px;font-size:12px;color:rgba(15,31,61,.50);font-family:monospace}",
  ].join("");

  function injectStyles() {
    if (document.getElementById("prec-widget-css")) return;
    var s = document.createElement("style");
    s.id = "prec-widget-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  /* ── HTML builder ─────────────────────────────────────────────────── */
  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function buildCard(conflict, theme, compact) {
    var dim      = (conflict.dimension || "").replace(/_/g, " ").toUpperCase();
    var expl     = conflict.conflict_explanation || conflict.explanation || "";
    var breaking = conflict.prediction || conflict.breaking_point || "";
    var encExpl  = encodeURIComponent(expl.slice(0, 300));

    if (compact) {
      return (
        '<div class="prec-widget-head">' +
          '<span class="prec-widget-badge">⚠ CONFLICT ALERT</span>' +
          '<a class="prec-widget-powered" href="' + SITE_URL + '" target="_blank" rel="noopener">PRECEDENT</a>' +
        "</div>" +
        '<div class="prec-widget-body">' +
          '<div class="prec-widget-dim">' + esc(dim) + "</div>" +
          '<div class="prec-widget-text">' + esc(expl.slice(0, 120)) + (expl.length > 120 ? "…" : "") + "</div>" +
        "</div>"
      );
    }

    return (
      '<div class="prec-widget-head">' +
        '<span class="prec-widget-badge">⚠ CONFLICT ALERT</span>' +
        '<a class="prec-widget-powered" href="' + BASE_URL + '" target="_blank" rel="noopener">PRECEDENT ↗</a>' +
      "</div>" +
      '<div class="prec-widget-body">' +
        '<div class="prec-widget-dim">' + esc(dim) + "</div>" +
        '<div class="prec-widget-text">' + esc(expl) + "</div>" +
        (breaking ? '<div class="prec-widget-breaking">Breaking point: ' + esc(breaking) + "</div>" : "") +
      "</div>" +
      '<div class="prec-widget-foot">' +
        '<a class="prec-widget-link primary" href="' + ANALYZE_URL + "?s=" + encExpl + '" target="_blank" rel="noopener">Analyze signal →</a>' +
        '<a class="prec-widget-link" href="' + SITE_URL + '" target="_blank" rel="noopener">Full analysis →</a>' +
      "</div>"
    );
  }

  /* ── fetch + render ───────────────────────────────────────────────── */
  function render(container, conflict) {
    var theme   = container.getAttribute("data-precedent-theme") || "light";
    var compact = container.getAttribute("data-precedent-compact") === "true";

    if (theme === "auto") {
      theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }

    container.className = "prec-widget";
    container.setAttribute("data-theme", theme);
    container.innerHTML = buildCard(conflict, theme, compact);
  }

  function fetchAndRender(container) {
    fetch(DATA_URL)
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        var conflicts = Array.isArray(data) ? data : (data.conflicts || []);
        var high = conflicts.filter(function (c) {
          return (c.implementation_risk || "").toUpperCase() === "HIGH";
        });
        var conflict = high[0] || conflicts[0];
        if (!conflict) throw new Error("no conflicts in data");
        render(container, conflict);
      })
      .catch(function (err) {
        container.className = "prec-widget";
        container.innerHTML =
          '<div class="prec-widget-head"><span class="prec-widget-badge">PRECEDENT</span></div>' +
          '<div class="prec-widget-error">Intelligence data temporarily unavailable. ' +
          '<a href="' + SITE_URL + '" target="_blank">View full analysis →</a></div>';
      });
  }

  /* ── init ─────────────────────────────────────────────────────────── */
  function init() {
    injectStyles();
    var containers = document.querySelectorAll("[data-precedent-widget]");
    for (var i = 0; i < containers.length; i++) {
      fetchAndRender(containers[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
