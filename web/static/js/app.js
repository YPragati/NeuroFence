/* NeuroFence web — app shell bootstrap + hash router.
   Single global stepper lives only inside the Investigate flow (views.js). */
"use strict";

(() => {
  const content = document.getElementById("content");
  const navEl = document.getElementById("nav");
  const titleEl = document.getElementById("page-title");
  const analystNameEl = document.getElementById("analyst-name");
  const analystChipEl = document.getElementById("analyst-chip");

  const NAV = [
    { label: "OVERVIEW", items: [["dashboard", "Dashboard"]] },
    { label: "INVESTIGATE", items: [
      ["investigate-new", "New Investigation"],
      ["investigations", "Investigations"],
    ] },
    { label: "FORENSICS", items: [
      ["findings", "Findings"],
      ["activation", "Activation Explorer"],
      ["scan-history", "Scan History"],
    ] },
    { label: "MODELS", items: [
      ["models", "Model Registry"],
      ["scanner", "Model Scanner"],
    ] },
    { label: "REPORTING", items: [["reports", "Security Reports"]] },
    { label: "SYSTEM", items: [
      ["settings", "Settings"],
      ["audit", "Audit Logs"],
    ] },
  ];

  const ROUTES = {
    "/": "dashboard",
    "/dashboard": "dashboard",
    "/investigate/new": "investigate-new",
    "/investigations": "investigations",
    "/forensics/findings": "findings",
    "/forensics/activation": "activation",
    "/forensics/scans": "scan-history",
    "/models": "models",
    "/scanner": "scanner",
    "/reports": "reports",
    "/settings": "settings",
    "/audit": "audit",
  };

  const TITLES = {
    dashboard: "Dashboard",
    "investigate-new": "New Investigation",
    investigations: "Investigations",
    "investigation-detail": "Investigation",
    findings: "Findings",
    activation: "Activation Explorer",
    "scan-history": "Scan History",
    models: "Model Registry",
    scanner: "Model Scanner",
    reports: "Security Reports",
    settings: "Settings",
    audit: "Audit Logs",
  };

  function buildNav() {
    navEl.innerHTML = "";
    NAV.forEach((group) => {
      const g = document.createElement("div");
      g.className = "nav-group";
      const h = document.createElement("div");
      h.className = "nav-group-label";
      h.textContent = group.label;
      g.append(h);
      group.items.forEach(([route, label]) => {
        const a = document.createElement("a");
        a.className = "nav-item";
        a.href = "#" + route;
        a.textContent = label;
        a.dataset.route = route;
        g.append(a);
      });
      navEl.append(g);
    });
  }

  function setActive(route) {
    const base = route === "investigation-detail" ? "investigations" : route;
    navEl.querySelectorAll(".nav-item").forEach((a) => {
      a.classList.toggle("active", a.dataset.route === base);
    });
  }

  function parseHash() {
    let raw = location.hash.replace(/^#/, "") || "/";
    let path = raw;
    const query = {};
    const qIdx = raw.indexOf("?");
    if (qIdx >= 0) {
      path = raw.slice(0, qIdx);
      try { Object.assign(query, Object.fromEntries(new URLSearchParams(raw.slice(qIdx + 1)))); } catch (_) { /* ignore */ }
    }
    if (!path.startsWith("/")) path = "/" + path;
    return { path, query };
  }

  function resolve() {
    const { path, query } = parseHash();
    const m = path.match(/^\/investigations\/(\d+)$/);
    if (m) return { view: "investigation-detail", params: Object.assign({ id: m[1] }, query) };
    const view = ROUTES[path] || "dashboard";
    return { view, params: Object.keys(query).length ? Object.assign({}, query) : {} };
  }

  function render() {
    const { view, params } = resolve();
    setActive(view);
    titleEl.textContent = TITLES[view] || "NeuroFence";
    content.innerHTML = "";
    try {
      Views.routes[view](content, params);
    } catch (err) {
      content.innerHTML = "";
      const box = document.createElement("div");
      box.className = "state-block";
      box.innerHTML = `<div class="state-icon">&#9888;</div><div class="state-title state-error">${ChartLib.esc(err.message || "Render failed")}</div>`;
      content.append(box);
      console.error(err);
    }
  }

  function boot() {
    buildNav();
    window.addEventListener("hashchange", render);
    render();

    const audit = /[?&]audit=1/.test(location.search);
    if (audit) ChartLib.startAudit();

    API.meta().then((m) => {
      const analyst = (m && m.analyst) || "magisha";
      if (analystNameEl) analystNameEl.textContent = analyst;
      if (analystChipEl) analystChipEl.textContent = "Analyst";
    }).catch(() => {});
    API.health().then((h) => {
      const ok = h && h.offline !== false && h.status !== "error";
      const dot = document.querySelector(".sidebar-footer .status-dot");
      const txt = document.querySelector(".sidebar-footer .status-text");
      if (dot) { dot.classList.toggle("ok", !!ok); dot.classList.toggle("danger", !ok); }
      if (txt) txt.textContent = ok ? "All Systems Operational" : "System Degraded";
    }).catch(() => {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();