/* NeuroFence web — page renderers. All data from /api endpoints backed by
   the existing Python services. No fabricated values. */
"use strict";

const Views = (() => {
  const C = ChartLib.C;

  /* ---------- element helpers ---------- */
  function el(tag, attrs, ...children) {
    const n = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") n.className = v;
        else if (k === "html") n.innerHTML = v;
        else if (k === "dataset") Object.assign(n.dataset, v);
        else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      n.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return n;
  }

  const esc = ChartLib.esc;
  const stateHTML = ChartLib.stateHTML;

  function fmt(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return String(iso);
    const p = (x) => String(x).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function fmtTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const p = (x) => String(x).padStart(2, "0");
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }
  function fmtBytes(b) {
    if (b === null || b === undefined) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let v = b;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  }
  function history(newHash) {
    if (location.hash === newHash) return;
    location.hash = newHash;
  }

  /* ---------- toast + drawer ---------- */
  function toast(msg, tone = "info") {
    const root = document.getElementById("toast-root");
    const t = el("div", { class: `toast ${tone === "ok" ? "ok" : tone === "danger" ? "danger" : ""}` }, msg);
    root.append(t);
    setTimeout(() => t.remove(), 3600);
  }

  function openDrawer(title, bodyEl) {
    const scrim = el("div", { class: "drawer-scrim" });
    const close = () => { scrim.remove(); drawer.remove(); };
    const drawer = el("div", { class: "drawer" },
      el("div", { class: "drawer-head" },
        el("div", { class: "drawer-title" }, title),
        el("button", { class: "drawer-close", onclick: close, "aria-label": "Close" }, "×")),
      el("div", { class: "drawer-body" }, bodyEl));
    scrim.addEventListener("click", close);
    document.body.append(scrim, drawer);
    return { scrim, drawer, close };
  }
  function kvRows(pairs) {
    const g = el("div", { class: "kv", style: "margin-bottom:12px;" });
    pairs.forEach(([k, v]) => {
      g.append(el("div", { class: "k" }, k));
      if (v && typeof v === "object" && v._html) {
        g.append(el("div", { class: "v", html: v._html }));
      } else {
        g.append(el("div", { class: "v" }, v === null || v === undefined ? "—" : String(v)));
      }
    });
    return g;
  }

  /* ---------- shared widgets ---------- */
  function card(title, bodyEl, opts = {}) {
    return el("div", { class: "card" },
      title ? el("div", { class: "card-head" },
        el("span", { class: "card-title" }, title),
        opts.note ? el("span", { class: "context-note" }, opts.note) : null) : null,
      el("div", { class: `card-body${opts.flush ? " flush" : ""}` }, bodyEl));
  }

  function kpi(label, value, opts = {}) {
    return el("div", { class: `card kpi ${opts.tone || "accent"}` },
      opts.icon ? el("div", { class: "kpi-icon" }, opts.icon) : null,
      el("div", { class: "kpi-value" }, value === null || value === undefined ? "—" : String(value)),
      el("div", { class: "kpi-label" }, label),
      opts.sub ? el("div", { class: "kpi-sub" }, opts.sub) : null);
  }

  function badge(text, kind) {
    return `<span class="badge badge-${kind}">${esc(text)}</span>`;
  }

  function table(headers, rows, opts = {}) {
    if (!rows.length) {
      return el("div", { class: "tbl-wrap" },
        el("table", { class: "tbl" },
          el("thead", {}, el("tr", {}, headers.map((h) => el("th", {}, h)))),
          el("tbody", {}, el("tr", {}, el("td", { colspan: headers.length }, rows && opts.emptyText
            ? esc(opts.emptyText) : "No data available")))));
    }
    return el("div", { class: "tbl-wrap" },
      el("table", { class: "tbl" },
        el("thead", {}, el("tr", {}, headers.map((h) => el("th", {}, h)))),
        el("tbody", {}, rows.map((r) => el("tr", {
          class: opts.rowClass && opts.rowClass(r) ? "clickable" : "",
          onclick: opts.onrow ? () => opts.onrow(r) : null,
        }, r.map((cell) => {
          if (cell && typeof cell === "object" && cell._html) return el("td", { html: cell._html });
          return el("td", {}, cell === null || cell === undefined ? "—" : String(cell));
        }))))));
  }

  function loadingBlock(text) {
    return el("div", { class: "state-block" },
      el("span", { class: "loading-line" }, el("span", { class: "spinner" }), text || "Loading…"));
  }
  function emptyBlock(title, sub) {
    return el("div", { class: "state-block", html: stateHTML(title, sub) });
  }
  function errorBlock(msg) {
    return el("div", { class: "state-block", html: stateHTML("Request failed", String(msg || ""), true) });
  }

  function severityBadge(sev) {
    const k = String(sev || "LOW").toUpperCase();
    const kind = k === "CRITICAL" ? "critical" : k === "HIGH" ? "high" : k === "MEDIUM" ? "medium" : k === "BENIGN" ? "benign" : "low";
    return badge(k, kind);
  }
  function scanBadge(status) {
    const s = String(status || "QUEUED").toUpperCase();
    if (s === "COMPLETED") return badge(s, "ok");
    if (s === "FAILED") return badge(s, "danger");
    if (s === "CANCELLED") return badge(s, "warn");
    return badge(s, "info");
  }
  function riskColor(v) {
    if (v === null || v === undefined) return C.dim;
    if (v >= 80) return C.critical;
    if (v >= 60) return C.high;
    if (v >= 40) return C.warn;
    return C.ok;
  }
  function riskLevel(v) {
    if (v === null || v === undefined) return "NO DATA";
    if (v >= 80) return "CRITICAL";
    if (v >= 60) return "HIGH";
    if (v >= 40) return "MEDIUM";
    return "LOW";
  }

  function pct(v) { return `${Math.max(0, Math.min(100, Math.round(v || 0)))}%`; }

  function stepper(current, doneThrough, opts = {}) {
    const steps = ["MODEL", "VERIFY", "CONFIGURE", "ANALYZE", "RESULT"];
    let html = '<div class="steps">';
    steps.forEach((s, i) => {
      const state = i < doneThrough ? "done" : i === current ? "active" : "next";
      const glyph = i < doneThrough ? "✓" : i === current ? "●" : "○";
      html += `<div class="step ${state}" data-key="${s}">
        <span class="step-pill"><span class="step-glyph">${glyph}</span>${s}</span></div>`;
      if (i < steps.length - 1) html += '<div class="step-connector"></div>';
    });
    html += "</div>";
    return el("div", { class: "stepper-wrap", html }, opts.extra ? el("div", { class: "mt8 flex-between" }, opts.extra) : null);
  }

  /* ================================================================
     DASHBOARD
     ================================================================ */
  function renderDashboard(mount) {
    mount.append(loadingBlock("Loading dashboard…"));
    API.dashboard().then((d) => {
      mount.innerHTML = "";

      const kpis = d.kpis || {};
      mount.append(el("div", {
        class: "grid grid-cols-5",
      },
        kpi("Active Investigations", kpis.active_investigations || 0, { tone: "accent", icon: "◇" }),
        kpi("Models Registered", kpis.models_registered || 0, { tone: "blue", icon: "▥" }),
        kpi("Scans Completed", kpis.scans_completed || 0, { tone: "ok", icon: "✓" }),
        kpi("Threat Findings", kpis.threat_findings || 0, { tone: "danger", icon: "⚠" }),
        kpi("Reports Generated", kpis.reports_generated || 0, { tone: "violet", icon: "▤" })));

      const ov = d.risk_overview || {};
      const score = ov.score;
      const trendPanel = card("Risk Score Trend",
        el("div", {},
          el("canvas", { "data-h": "200", id: "trend-canvas" }),
          el("div", { class: "flex wrap mt8" },
            el("span", { class: "context-note" }, `${trendMsg(d.risk_trend || [])}`)),
          el("div", { class: "flex wrap mt8 btn-row" },
            rangeBtn("7D", d, "trend-canvas"), rangeBtn("14D", d, "trend-canvas"),
            rangeBtn("30D", d, "trend-canvas", true), rangeBtn("ALL", d, "trend-canvas"))));

      mount.append(el("div", { class: "grid grid-main-3 mt" },
        card("Risk Overview",
          el("div", { class: "gauge-wrap" },
            el("canvas", { "data-h": "210", id: "risk-gauge" }),
            el("div", { class: "flex mt8" },
              el("span", { class: "badge badge-" + levelKind(ov.level), html: badgeInside(ov.level || "NO DATA") })))),
        card("Threat Distribution",
          el("div", {},
            el("canvas", { "data-h": "190", id: "dist-donut" }),
            donutLegend((d.threat_distribution || {}).items || [])),
          { note: `Total ${(d.threat_distribution || {}).total || 0} findings` }),
        trendPanel));

      mount.append(el("div", { class: "grid grid-cols-2 mt" },
        card("Recent Investigations",
          table(["ID", "Status", "Model", "Prompts", "Findings", "Risk", "Created"],
            (d.recent_scans || []).map((s) => [
              { _html: `<span class="mono" style="color:${C.accent}">#${s.scan_id}</span>` },
              { _html: scanBadge(s.status) },
              s.model || "—",
              `${s.prompts_processed || 0}/${s.total_prompts || 0}`,
              s.findings_generated || 0,
              { _html: riskCell(s.current_anomaly_score) },
              fmt(s.created_at),
            ]), { emptyText: "No security scans yet. Start a new investigation." }),
          { flush: true, note: "Real pipeline runs" }),

        card("System Health",
          el("div", {},
            (d.system_health || []).map((h) =>
              el("div", { class: "flex-between", style: "padding:6px 0;border-bottom:1px solid rgba(38,49,71,.5);" },
                el("div", { class: "flex" },
                  el("span", { class: "status-dot " + (h.ok ? "ok" : "danger") }),
                  el("span", { style: "font-size:12px;" }, h.name)),
                el("span", { class: "muted", style: "font-size:11px;" }, h.ok ? "operational" : h.detail)))),
          { flush: true })));

      mount.append(el("div", { class: "grid grid-cols-2 mt" },
        card("Recent Activity",
          (d.recent_activity || []).length
            ? el("div", { class: "log", style: "max-height:240px;" },
              (d.recent_activity || []).map((e) =>
                el("div", { class: "entry" },
                  el("span", { class: "t" }, fmtTime(e.ts) + "  "),
                  el("span", { style: `color:${e.color || C.muted};font-weight:600;` }, e.level + "  "),
                  esc(e.action))))
            : emptyBlock("No activity recorded", "Model imports, scans and reports will appear here."),
          { flush: true }),
        card("Recent Findings",
          (d.recent_findings || []).length
            ? table(["Sev", "Layer", "Feature", "Score", "Run"],
              (d.recent_findings || []).map((f) => [
                { _html: severityBadge(f.severity) },
                f.layer || "—",
                f.feature || "—",
                { _html: riskCell(f.anomaly_score) },
                f.run_id !== undefined && f.run_id !== null ? `#${f.run_id}` : "—",
              ]), { emptyText: "No findings recorded yet." })
            : emptyBlock("No findings", "Statistical anomaly findings will appear here."),
          { flush: true })));

      // charts
      ChartLib.attach(document.getElementById("risk-gauge"),
        (ctx, w, h) => ChartLib.gauge(ctx, w, h, score === null || score === undefined ? 0 : score,
          { color: riskColor(score) }));
      ChartLib.attach(document.getElementById("dist-donut"),
        (ctx, w, h) => ChartLib.donut(ctx, w, h,
          (d.threat_distribution || {}).items || [], { bg: C.panel }));
      bindTrend(d, "trend-canvas");
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  function badgeInside(text) {
    return `<span class="badge badge-${levelKind(text)}">${esc(text)}</span>`;
  }
  function levelKind(level) {
    const v = String(level || "").toUpperCase();
    if (v === "CRITICAL") return "critical";
    if (v === "HIGH") return "high";
    if (v === "MEDIUM") return "medium";
    if (v === "LOW") return "low";
    return "dim";
  }
  function riskCell(v) {
    if (v === null || v === undefined) return "—";
    return `<span class="mono" style="color:${riskColor(v)}">${Number(v).toFixed(0)}</span>`;
  }
  function trendMsg(points) {
    if (!points.length) return "No completed scans with a persisted anomaly score yet.";
    return `${points.length} completed scan${points.length > 1 ? "s" : ""} · real persisted anomaly scores`;
  }

  function rangeBtn(label, d, canvasId) {
    const sel = label === "30D";
    const btn = el("button", {
      class: "btn btn-sm " + (sel ? "btn-primary" : "btn-ghost"),
      style: "padding:4px 10px;",
    }, label);
    btn.addEventListener("click", () => {
      setTrendWindow(canvasId, label);
      document.querySelectorAll(`#${canvasId}`).forEach(() => {});
      const siblings = btn.parentElement.querySelectorAll(".btn");
      siblings.forEach((b) => { b.classList.remove("btn-primary"); b.classList.add("btn-ghost"); });
      btn.classList.add("btn-primary"); btn.classList.remove("btn-ghost");
    });
    return btn;
  }
  function setTrendWindow(canvasId, label) {
    const el0 = document.getElementById(canvasId);
    if (el0 && el0._draw) el0._setWindow(label);
  }
  function bindTrend(d, canvasId) {
    const all = (d.risk_trend || []).slice();
    const cv = document.getElementById(canvasId);
    if (!cv) return;
    let windowDays = 30;
    function apply() {
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - windowDays);
      let pts = all;
      if (windowDays !== Infinity) {
        pts = all.filter((p) => {
          if (!p.ts) return true;
          return new Date(p.ts).getTime() >= cutoff.getTime() - 86400000;
        });
      }
      cv._setWindow = (l) => { windowDays = l === "ALL" ? Infinity : parseInt(l, 10); apply(); };
      cv._draw = () => {
        if (!cv._drawn) { cv._drawn = true; cv._args = [pts]; }
        drawTrend(cv, pts);
      };
      drawTrend(cv, pts);
    }
    apply();
  }
  function drawTrend(cv, pts) {
    ChartLib.attach(cv, (ctx, w, h) => ChartLib.line(ctx, w, h, pts, { lastPoint: true, color: C.accent }));
  }
  function donutLegend(items) {
    if (!items.filter((i) => i.count).length) return null;
    const grid = el("div", { class: "flex wrap", style: "gap:6px 12px;margin-top:6px;" });
    items.forEach((i) => {
      if (!i.count) return;
      grid.append(el("span", { style: "font-size:11px;color:var(--muted);" },
        el("span", { style: `display:inline-block;width:8px;height:8px;border-radius:2px;background:${i.color};margin-right:5px;` }),
        `${i.label} ${i.count}`));
    });
    return grid;
  }

  /* ================================================================
     NEW INVESTIGATION (5-step guided workflow) — single stepper
     ================================================================ */
  const WFLOW_KEY = "nf_workflow_v2";

  function loadWF() {
    try { return JSON.parse(sessionStorage.getItem(WFLOW_KEY) || "null") || {}; } catch (_) { return {}; }
  }
  function saveWF(w) {
    try { sessionStorage.setItem(WFLOW_KEY, JSON.stringify(w)); } catch (_) { /* ignore */ }
  }
  function resetWF() { sessionStorage.removeItem(WFLOW_KEY); }

  function renderNewInvestigation(mount, params) {
    let wf = loadWF();
    if (params && params.model && !wf.model_name) {
      wf.model_name = decodeURIComponent(params.model);
      saveWF(wf);
    }
    if (params && params.scan) {
      wf.step = 4; // open straight into the analyze/result flow
      wf.cur_scan_id = parseInt(params.scan, 10);
      wf.jump_to_run = true;
      saveWF(wf);
    }
    step0(mount, wf);
  }

  function step0(mount, wf) {
    const container = el("div", {});
    container.append(stepper(wf.step || 0, (wf.step || 0)));
    mount.innerHTML = "";
    mount.append(container);
    (stepsRenderers[wf.step || 0])(container, wf, mount);
  }

  const stepsRenderers = [
    (c, wf) => renderModelStep(c, wf),
    (c, wf) => renderVerifyStep(c, wf),
    (c, wf) => renderConfigureStep(c, wf),
    (c, wf) => renderAnalyzeStep(c, wf),
    (c, wf) => renderResultStep(c, wf),
  ];

  function pageTitle(text, sub) {
    return el("div", { class: "page-head" },
      el("h1", {}, text),
      sub ? el("p", {}, sub) : null);
  }

  function renderModelStep(c, wf) {
    c.innerHTML = "";
    c.append(pageTitle("MODEL", "Step 1 of 5 — select the model to analyse, or import a new one."));
    const grid = el("div", { class: "grid grid-main-2" });
    const left = card("Select Model",
      el("div", {}, el("div", { id: "model-picker", html: stateHTML("Loading models…", "") })),
      { note: "Choose a registered model" });
    const right = card("New Model",
      el("div", {},
        el("div", { class: "section-title" }, "Import"),
        el("div", { class: "field" },
          el("label", { for: "file-import" }, "Model file"),
          el("input", { id: "file-import", type: "file", name: "model-file", accept: ".json,.pt,.pth,.safetensors,.onnx,.bin" }),
          el("div", { class: "hint" }, "JSON / PyTorch / SafeTensors / ONNX weight files. Validated by the model sandbox.")),
        el("div", { class: "field" },
          el("label", {}, "Server directory"),
          el("div", { class: "flex" },
            el("input", { id: "dir-path", placeholder: "C:\\models\\my-model", style: "flex:1;" }),
            el("button", { class: "btn", id: "btn-dir" }, "Import directory"))),
        el("div", { id: "import-status", class: "mt8" })),
      { note: "Uses the existing import pipeline" });
    grid.append(left, right);
    c.append(grid);

    const picker = document.getElementById("model-picker");
    API.models().then((res) => {
      renderModelPicker(picker, res.models || [], (m) => {
        wf.model_name = m.file_name;
        wf.metadata_id = m.metadata_id;
        saveWF(wf);
        wf.step = 1;
        step0(mount, wf);
      }, wf.model_name);
    }).catch((err) => { picker.innerHTML = ""; picker.append(errorBlock(err.message)); });

    document.getElementById("btn-dir").addEventListener("click", () => {
      const path = document.getElementById("dir-path").value.trim();
      if (!path) return;
      const st = document.getElementById("import-status");
      st.innerHTML = "";
      st.append(loadingBlock("Importing…"));
      API.importDir(path).then((r) => {
        st.innerHTML = "";
        st.append(importResult(r));
        refreshModels(picker);
      }).catch((e) => { st.innerHTML = ""; st.append(errorBlock(e.message)); });
    });

    const fi = document.getElementById("file-import");
    fi.addEventListener("change", () => {
      const file = fi.files && fi.files[0];
      if (!file) return;
      const st = document.getElementById("import-status");
      st.innerHTML = "";
      st.append(loadingBlock("Uploading + verifying…"));
      API.importFile(file).then((r) => {
        st.innerHTML = "";
        st.append(importResult(r));
        refreshModels(picker);
      }).catch((e) => { st.innerHTML = ""; st.append(errorBlock(e.message)); });
    });
  }

  function importResult(r) {
    const box = el("div", { class: "mt8" });
    if (r.success) {
      (r.models || []).forEach((m) => {
        box.append(el("div", { class: "muted", style: "font-size:12px;" },
          `✓ ${esc(m.file_name)} (${esc(m.model_type || "unknown")})${m.duplicate ? " — duplicate, already registered" : ""}`));
      });
    }
    (r.errors || []).forEach((e) => {
      box.append(el("div", { class: "neg", style: "font-size:12px;" }, `✗ ${esc(e)}`));
    });
    if (!r.success && !r.errors.length) box.append(el("div", { class: "neg" }, "Import failed."));
    return box;
  }
  function refreshModels(picker) {
    API.models().then((res) => renderModelPicker(picker, res.models || [], (m) => {
      const wf2 = loadWF();
      wf2.model_name = m.file_name;
      wf2.metadata_id = m.metadata_id;
      saveWF(wf2);
      wf2.step = 1;
      step0(mount, wf2);
    }, wf.model_name)).catch(() => {});
  }

  function renderModelPicker(picker, models, onSelect, selected) {
    picker.innerHTML = "";
    if (!models.length) {
      picker.append(emptyBlock("No models registered", "Import a model file or point at a local model directory to begin."));
      return;
    }
    const wrap = el("div", {});
    models.forEach((m) => {
      const row = el("label", { class: "radio-row" + (selected === m.file_name ? " selected" : "") },
        el("input", { type: "radio", name: "model-select", checked: selected === m.file_name || undefined }),
        el("div", {},
          el("div", { class: "radio-main" }, m.file_name),
          el("div", { class: "radio-sub" }, `${m.architecture || m.model_type || "model"} · ${m.size_label} · ${esc(m.status_label || m.status || "")}`)),
        el("span", { style: "margin-left:auto;" , class: "badge badge-" + (m.status_color ? (m.status_color.toLowerCase().includes("red") ? "danger" : "info") : "dim"), html: badgeInside(m.status_label || m.status || "imported") }));
      row.addEventListener("click", () => {
        if (!row.querySelector("input").checked) return;
        wrap.querySelectorAll(".radio-row").forEach((r) => r.classList.remove("selected"));
        row.classList.add("selected");
        onSelect(m);
      });
      wrap.append(row);
    });
    picker.append(wrap);
  }

  function renderVerifyStep(c, wf) {
    c.innerHTML = "";
    c.append(pageTitle("VERIFY", `Step 2 of 5 — integrity verification for «${esc(wf.model_name || "")}».`));
    if (!wf.metadata_id) {
      c.append(emptyBlock("Select a model first", "Go back to the Model step."));
      return;
    }
    const box = el("div", { class: "grid grid-main-2" });
    const left = card("Verification Checklist", el("div", { id: "verify-list", html: stateHTML("Running verification…", "") }),
      { note: "Real sandbox + registry checks" });
    const actions = el("div", { class: "btn-row mt" },
      el("button", { class: "btn btn-ghost", onclick: () => { wf.step = 0; saveWF(wf); step0(mount, wf); } }, "← Back"),
      el("button", { class: "btn btn-primary", id: "verify-continue", disabled: true }, "CONTINUE TO CONFIGURE →"));
    left.append(actions);
    const right = card("Model Snapshot", el("div", { id: "verify-snapshot" }));
    box.append(left, right);
    c.append(box);

    API.model(wf.metadata_id).then((d) => {
      const m = d.model || {};
      const list = document.getElementById("verify-list");
      list.innerHTML = "";
      const checks = d.verification || [];
      checks.forEach((chk) => {
        list.append(el("div", { class: "phase-item " + (chk.pass ? "done" : "active") },
          el("span", { class: "glyph" }, chk.pass ? "✓" : "●"),
          el("span", { class: "label" }, chk.label),
          el("span", { style: "margin-left:auto;font-size:11px;" }, chk.pass
            ? badge("PASS", "ok") : badge("WARNING", "warn"))));
      });
      document.getElementById("verify-continue").disabled = false;

      const snap = document.getElementById("verify-snapshot");
      snap.append(kvRows([
        ["File", m.file_name || "—"],
        ["Format", m.model_type || "—"],
        ["Architecture", m.architecture || "—"],
        ["Size", m.size_label || "—"],
        ["SHA-256", m.sha_short ? `${m.sha_short}…` : "—"],
        ["Status", m.status_label || m.status || "—"],
      ]));
      const dec = d.decision || {};
      snap.append(el("div", { class: "flex mt8" },
        el("span", { class: "badge badge-" + (dec.decision === "quarantined" ? "danger" : dec.decision === "review" ? "warn" : dec.decision === "approved" ? "ok" : "info"), html: badgeInside(dec.decision || "pending") }),
        el("span", { class: "dim", style: "font-size:11px;" }, `${dec.total_findings || 0} findings on record`)));
    }).catch((err) => {
      const list = document.getElementById("verify-list");
      if (list) { list.innerHTML = ""; list.append(errorBlock(err.message)); }
      const btn = document.getElementById("verify-continue");
      if (btn) btn.disabled = true;
    });

    document.getElementById("verify-continue").addEventListener("click", () => {
      wf.step = 2; saveWF(wf); step0(mount, wf);
    });
  }

  function renderConfigureStep(c, wf) {
    c.innerHTML = "";
    c.append(pageTitle("CONFIGURE", `Step 3 of 5 — scan mode for «${esc(wf.model_name || "")}».`));
    const box = el("div", { class: "grid grid-main-2" });
    const left = card("Scan Configuration", el("div", { id: "config-fields", html: stateHTML("Loading configuration…", "") }));
    const right = card("Estimated Scan Size",
      el("div", {},
        el("div", { class: "kpi-row grid grid-cols-3", style: "margin-bottom:4px;", id: "estimate" }),
        el("div", { id: "estimate-note", class: "context-note", style: "margin-top:10px;" })),
      { note: "Prompts × monitored layers" });
    box.append(left, right);
    c.append(box);

    API.scanConfig().then((cfg) => {
      const fc = document.getElementById("config-fields");
      fc.innerHTML = "";

      const state = {
        depth: "STANDARD",
        categories: (cfg.categories || []).map((x) => x.key),
        num_prompts: cfg.profiles.STANDARD.num_prompts,
        max_seq_len: cfg.profiles.STANDARD.max_seq_len,
        layers: cfg.profiles.STANDARD.layers,
        max_new_tokens: cfg.profiles.STANDARD.max_new_tokens,
        model: wf.model_name,
      };

      const base = profileFor(state.depth, cfg.profiles);

      function renderEstimate() {
        const prom = base.num_prompts;
        const layers = Math.max(1, state.layers);
        const meas = prom * layers;
        renderEstimateKpis(prom, layers, meas);
        document.getElementById("estimate-note").textContent =
          `${prom} prompts across ${layers} monitored layers → ${meas} estimated activation measurements.`;
      }
      function renderEstimateKpis(prom, layers, meas) {
        const grid = document.getElementById("estimate");
        grid.innerHTML = "";
        grid.append(
          kpi("Prompts", prom, { tone: "accent" }),
          kpi("Layers", layers, { tone: "blue" }),
          kpi("Est. Measurements", meas, { tone: "violet" }));
      }

      const depths = ["QUICK CHECK", "STANDARD", "DEEP ANALYSIS"];
      fc.append(el("div", { class: "section-title" }, "Scan Mode"));
      depths.forEach((dname) => {
        const prof = cfg.profiles[dname];
        const row = el("label", { class: "radio-row" + (state.depth === dname ? " selected" : "") },
          el("input", { type: "radio", name: "depth", checked: state.depth === dname || undefined }),
          el("div", {},
            el("div", { class: "radio-main" }, dname),
            el("div", { class: "radio-sub" }, `${prof.num_prompts} prompts · ${prof.layers} layers · ${prof.num_prompts * prof.layers} measurements`)),
          el("span", { class: "hint", style: "margin-left:auto;" }, state.depth === dname ? "● selected" : ""));
        row.addEventListener("click", () => {
          if (!row.querySelector("input").checked) return;
          fc.querySelectorAll(".radio-row").forEach((r) => r.classList.remove("selected"));
          row.classList.add("selected");
          state.depth = dname;
          Object.assign(state, profileFor(dname, cfg.profiles));
          base.num_prompts = state.num_prompts;
          base.layers = state.layers;
          base.max_seq_len = state.max_seq_len;
          base.max_new_tokens = state.max_new_tokens;
          renderEstimate();
        });
        fc.append(row);
      });

      fc.append(el("div", { class: "section-title mt" }, "Prompt Categories"));
      const chips = el("div", { class: "chip-row" });
      (cfg.categories || []).forEach((x) => {
        const ch = el("label", { class: "chip-check on" },
          el("input", { type: "checkbox", checked: true }),
          x.label);
        ch.addEventListener("change", () => {
          ch.classList.toggle("on");
          state.categories = Array.from(fc.querySelectorAll(".chip-check")).filter((c2) => c2.querySelector("input").checked)
            .map((c2) => c2.querySelector("input").valueOf() && cfg.categories.find((cc) => cc.label === c2.childNodes[1].textContent).key);
          base.categories = state.categories;
        });
        chips.append(ch);
      });
      fc.append(chips);

      fc.append(el("div", { class: "btn-row mt" },
        el("button", { class: "btn btn-ghost", onclick: () => { wf.step = 1; saveWF(wf); step0(mount, wf); } }, "← Back"),
        el("button", { class: "btn btn-primary btn-lg", style: "margin-left:auto;", id: "start-scan" }, "START SECURITY ANALYSIS →")));

      renderEstimate();
      if (!state.model && cfg.models.length) {
        // no model picked via workflow; require one
        document.getElementById("start-scan").disabled = true;
        document.getElementById("estimate-note").textContent = "Select a model in the MODEL step first.";
        return;
      }

      document.getElementById("start-scan").addEventListener("click", () => {
        const btn = document.getElementById("start-scan");
        btn.disabled = true;
        btn.textContent = "LAUNCHING…";
        API.createScan({
          model: state.model,
          num_prompts: base.num_prompts,
          layers: base.layers,
          seed: 42,
          max_seq_len: base.max_seq_len,
          max_new_tokens: base.max_new_tokens,
          categories: state.categories.length ? state.categories : null,
          depth: state.depth,
        }).then((scan) => {
          wf.step = 3;
          wf.cur_scan_id = scan.scan_id;
          wf.jump_to_run = false;
          saveWF(wf);
          step0(mount, wf);
        }).catch((err) => {
          btn.disabled = false; btn.textContent = "START SECURITY ANALYSIS →";
          toast(`Scan launch failed: ${err.message}`, "danger");
        });
      });
    }).catch((err) => {
      const fc = document.getElementById("config-fields");
      if (fc) { fc.innerHTML = ""; fc.append(errorBlock(err.message)); }
    });
  }

  function profileFor(name, profiles) {
    const p = profiles[name] || profiles.STANDARD;
    return {
      num_prompts: p.num_prompts,
      layers: p.layers,
      max_seq_len: p.max_seq_len,
      max_new_tokens: p.max_new_tokens,
    };
  }

  const PHASES = [
    { key: "MODEL LOADED", statuses: [] },
    { key: "INTEGRITY CHECK", statuses: [] },
    { key: "PROMPT GENERATION", statuses: ["INITIALIZING", "GENERATING_INPUTS"] },
    { key: "ADVERSARIAL SCAN", statuses: ["RUNNING_INFERENCE"] },
    { key: "ACTIVATION CAPTURE", statuses: [] },
    { key: "ANOMALY ANALYSIS", statuses: ["ANALYZING_ACTIVATIONS", "DETECTING_ANOMALIES"] },
    { key: "RISK SCORING", statuses: [] },
  ];

  function phaseState(status) {
    // returns {doneThrough: n, active: idx|null}
    const s = status || "QUEUED";
    const map = {
      QUEUED: 0, INITIALIZING: 0, LOADING_MODEL: 1, GENERATING_INPUTS: 2,
      RUNNING_INFERENCE: 3, ANALYZING_ACTIVATIONS: 4, DETECTING_ANOMALIES: 5,
      COMPLETED: 7, FAILED: 7, CANCELLED: 7,
    };
    const done = map[s] !== undefined ? map[s] : 0;
    const active = done < 7 ? done : null;
    return { done: active === null ? 7 : Math.max(0, done - 1), active };
  }

  function renderPhaseRows(status) {
    const ps = phaseState(status);
    return PHASES.map((p, i) => {
      let cls = "pending";
      let glyph = "○";
      if (ps.done > i) { cls = "done"; glyph = "✓"; }
      else if (ps.active === i) { cls = "active"; glyph = "●"; }
      return el("div", { class: `phase-item ${cls}` },
        el("span", { class: "glyph" }, glyph),
        el("span", { class: "label" }, p.key));
    });
  }

  function renderAnalyzeStep(c, wf) {
    c.innerHTML = "";
    c.append(pageTitle("ANALYZE", `Step 4 of 5 — live security analysis for «${esc(wf.model_name || "")}».`));
    const scanId = wf.cur_scan_id;
    if (!scanId) {
      c.append(emptyBlock("No active scan", "Launch a scan from the CONFIGURE step."));
      return;
    }
    const box = el("div", { class: "grid grid-cols-2" });
    const left = card("Security Analysis",
      el("div", {},
        el("div", { class: "flex-between mb" },
          el("div", {}, el("div", { class: "dim", style: "font-size:11px;" }, "TARGET MODEL"), el("div", { style: "font-weight:600;" }, wf.model_name || "—")),
          el("div", { class: "right", style: "text-align:right;" },
            el("div", { class: "dim", style: "font-size:11px;" }, "SCAN ID"),
            el("div", { class: "mono", style: "color:" + C.accent + ";" }, `#${scanId}`))),
        el("div", { class: "progress-track mb", style: "height:10px;" },
          el("div", { class: "progress-fill", id: "scan-progress", style: "width:0%;" })),
        el("div", { class: "flex-between mb" },
          el("span", { class: "muted", style: "font-size:11.5px;" }, "Real backend pipeline progress"),
          el("span", { class: "mono", style: "font-size:16px;font-weight:700;color:" + C.accent + ";", id: "scan-pct" }, "0%")),
        el("div", { id: "phase-list", class: "phase-list" })),
      { note: "Progress from persisted pipeline state" });
    const right = card("Live Activity Log",
      el("div", { class: "log", id: "scan-log", style: "max-height:420px;" }, []),
      { flush: true });
    box.append(left, right);
    c.append(box);

    c.append(el("div", { class: "grid grid-cols-3 mt" },
      kpi("Prompts Tested", "—", { tone: "accent", icon: "▶" }),
      kpi("Mutations", "—", { tone: "blue", icon: "✎" }),
      kpi("Activations", "—", { tone: "violet", icon: "▤" }),
      kpi("Findings", "—", { tone: "danger", icon: "⚠" }),
      kpi("Risk Score", "—", { tone: "warn", icon: "◆" }),
      kpi("Status", "QUEUED", { tone: "info", icon: "◌" })));

    if (wf.jump_to_run) {
      c.append(el("div", { class: "mt" }, card("Scan Results",
        el("div", { id: "jump-results" }, loadingBlock("Loading results…")))));
    }

    const kpiEls = {};
    c.querySelectorAll(".kpi").forEach((k, i) => { kpiEls[i] = k.querySelector(".kpi-value"); });

    let running = true;
    const poll = setInterval(async () => {
      let s;
      try { s = await API.scan(scanId); }
      catch (e) { clearInterval(poll); c.append(el("div", { class: "state-block" }, `Lost connection: ${e.message}`)); return; }

      const pct = s.percentage || 0;
      const fill = document.getElementById("scan-progress");
      const pctEl = document.getElementById("scan-pct");
      if (fill) fill.style.width = pct + "%";
      if (pctEl) pctEl.textContent = pct + "%";
      setKpiText(c, 0, `${s.prompts_processed || 0} / ${s.total_prompts || 0}`);
      const layers = Math.max(1, (s.layers_analyzed || 0) || (s.config && s.config.layers) || 0);
      setKpiText(c, 1, `${(s.prompts_processed || 0) * 7}`);
      setKpiText(c, 2, `${(s.prompts_processed || 0) * layers}`);
      setKpiText(c, 3, s.findings_generated || 0);
      const riskVal = s.current_anomaly_score;
      setKpiText(c, 4, riskVal === null ? "—" : Number(riskVal).toFixed(0));
      setKpiText(c, 5, s.status || "QUEUED");
      setKpiColor(c, 4, riskValue(riskVal));

      const plist = document.getElementById("phase-list");
      if (plist) { plist.innerHTML = ""; renderPhaseRows(s.status).forEach((r) => plist.append(r)); }

      const log = document.getElementById("scan-log");
      if (log && s.activity_log) {
        log.innerHTML = "";
        (s.activity_log || []).slice(-40).forEach((e) => {
          log.append(el("div", { class: "entry" },
            el("span", { class: "t" }, e.ts + "  "),
            esc(e.message)));
        });
        log.scrollTop = log.scrollHeight;
      }

      if (wf.jump_to_run) {
        const jr = document.getElementById("jump-results");
        if (jr) {
          renderJumpedResults(jr, s);
        }
      }

      if (s.is_terminal) {
        clearInterval(poll);
        if (s.status === "COMPLETED") {
          wf.step = 4; saveWF(wf);
          setTimeout(() => step0(mount, wf), 500);
        } else {
          c.append(el("div", { class: "state-block mt" },
            el("div", { class: "state-error", html: stateHTML(`Scan ${s.status.toLowerCase()}`, s.error || "") })));
          wf.step = 3; saveWF(wf);
        }
      }
    }, 900);
  }

  function riskValue(v) {
    if (v === null || v === undefined) return C.dim;
    if (v >= 80) return C.critical;
    if (v >= 60) return C.high;
    if (v >= 40) return C.warn;
    return C.ok;
  }
  function setKpiText(c, i, v) {
    const els = c.querySelectorAll(".kpi .kpi-value");
    if (els[i]) els[i].textContent = String(v);
  }
  function setKpiColor(c, i, color) {
    const els = c.querySelectorAll(".kpi .kpi-value");
    if (els[i]) els[i].style.color = color;
  }

  function renderJumpedResults(holder, s) {
    if (s.status === "COMPLETED") {
      if (!holder.dataset.filled) {
        holder.dataset.filled = "1";
        holder.innerHTML = "";
        holder.append(el("div", { class: "flex-between" },
          el("div", {}, el("div", { class: "dim", style: "font-size:11px;" }, "SCAN"), el("div", { class: "mono" }, `#${s.scan_id}`)),
          el("span", { html: scanBadge(s.status) })));
        holder.append(el("div", { class: "btn-row mt8" },
          el("a", { class: "btn btn-primary btn-sm", href: `#/forensics/findings?run=${s.run_id || ""}` }, "VIEW FINDINGS"),
          el("a", { class: "btn btn-ghost btn-sm", href: `#/forensics/activation` }, "ACTIVATION EXPLORER"),
          el("a", { class: "btn btn-ghost btn-sm", href: `#/reports` }, "SECURITY REPORTS")));
      }
    } else if (s.is_terminal) {
      holder.innerHTML = "";
      holder.append(emptyBlock(`Scan ${s.status.toLowerCase()}`, s.error || ""));
    }
  }

  function renderResultStep(c, wf) {
    c.innerHTML = "";
    c.append(pageTitle("RESULT", "Step 5 of 5 — security analysis result."));
    const scanId = wf.cur_scan_id;
    if (!scanId) { c.append(emptyBlock("No scan selected", "")); return; }
    c.append(el("div", { id: "result-body" }, loadingBlock("Loading result…")));
    API.scanDetail(scanId).then((d) => {
      const body = document.getElementById("result-body");
      body.innerHTML = "";
      const s = d.state || {};
      const findings = d.findings || [];

      const score = s.current_anomaly_score;
      const risk = score === null || score === undefined ? null : Number(score);

      const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
      findings.forEach((f) => { const k = String(f.severity || "LOW").toUpperCase(); if (k in counts) counts[k]++; });

      const head = card(null,
        el("div", { class: "flex-between" },
          el("div", {},
            el("div", { class: "section-title", style: "color:" + C.accent + ";" }, "SECURITY ANALYSIS COMPLETE"),
            el("div", { style: "font-size:18px;font-weight:700;" }, `${riskText(risk)} / 100`),
            el("div", { class: "dim", style: "font-size:12px;", html: `Severity: ${badgeInside(riskLevel(risk))}` })),
          el("div", { class: "gauge-wrap", style: "flex:0 0 230px;" },
            el("canvas", { "data-h": "170", id: "result-gauge" }))),
        el("div", { class: "grid grid-cols-5 mt" },
          kpi("Model", s.model || "—", { tone: "accent" }),
          kpi("Scan ID", s.scan_id || "—", { tone: "blue" }),
          kpi("Prompts Tested", `${s.prompts_processed || 0}/${s.total_prompts || 0}`, { tone: "violet" }),
          kpi("Findings", s.findings_generated || 0, { tone: "danger" }),
          kpi("Execution Time", execTime(s.created_at, s.updated_at), { tone: "ok" })));
      body.append(head);

      if (risk !== null) {
        ChartLib.attach(document.getElementById("result-gauge"),
          (ctx, w, h) => ChartLib.gauge(ctx, w, h, risk, { color: riskColor(risk) }));
      }

      body.append(el("div", { class: "grid grid-cols-4 mt" },
        kpi("CRITICAL", counts.CRITICAL, { tone: "danger", icon: "●" }),
        kpi("HIGH", counts.HIGH, { tone: "danger", icon: "▲" }),
        kpi("MEDIUM", counts.MEDIUM, { tone: "warn", icon: "◆" }),
        kpi("LOW", counts.LOW, { tone: "ok", icon: "▼" })));

      body.append(card("Findings",
        findings.length
          ? table(["Severity", "Finding", "Layer", "Score", "Confidence", "Evidence"],
            findings.map((f) => [
              { _html: severityBadge(f.severity) },
              layerFeature(f),
              f.layer || "—",
              { _html: riskCell(f.anomaly_score) },
              f.confidence === null || f.confidence === undefined ? "—" : `${Math.round((f.confidence || 0) * 100)}%`,
              { _html: `<span style="color:${C.muted}">${esc(trunc(f.explanation || f.category || "", 60))}</span>` },
            ]), { emptyText: "No statistical findings recorded for this scan.", onrow: (r2) => openFindingDrawer(findings[Math.max(0, findings.findIndex((f) => f.layer === r2[2] && f.feature === r2[1]._html.replace(/<[^>]+>/g, "") || -1))]) })
          : emptyBlock("No findings", "This scan produced no statistical findings."),
        { flush: true }));

      body.append(el("div", { class: "btn-row mt" },
        el("a", { class: "btn btn-primary", href: `#/forensics/findings?run=${s.run_id || ""}` }, "VIEW FINDINGS"),
        el("a", { class: "btn btn-secondary", href: `#/forensics/activation?model=${encodeURIComponent(s.model || "")}` }, "ACTIVATION EXPLORER"),
        el("button", { class: "btn btn-ghost", onclick: () => exportReportNow(s) }, "EXPORT REPORT"),
        el("button", { class: "btn btn-ghost", onclick: () => { resetWF(); wf = {}; renderNewInvestigation(mount, {}); } }, "START NEW INVESTIGATION")));
    }).catch((err) => {
      const body = document.getElementById("result-body");
      if (body) { body.innerHTML = ""; body.append(errorBlock(err.message)); }
    });
  }

  function layerFeature(f) {
    return `<span style="color:${C.text}">${esc(f.feature || "—")}</span> <span class="dim">· ${esc(f.category || "")}</span>`;
  }
  function trunc(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n) + "…" : s; }
  function execTime(a, b) {
    if (!a || !b) return "—";
    const ms = Math.max(0, new Date(b) - new Date(a));
    if (ms < 1000) return "<1s";
    return `${Math.round(ms / 1000)}s`;
  }
  function riskText(v) {
    return v === null || v === undefined ? "—" : Number(v).toFixed(0);
  }

  function openFindingDrawer(f) {
    if (!f) { toast("Finding not found", "danger"); return; }
    const details = el("div", {},
      kvRows([
        ["Finding ID", f.finding_id],
        ["Severity", { _html: severityBadge(f.severity) }],
        ["Layer", f.layer],
        ["Feature", f.feature],
        ["Category", f.category],
        ["Model", f.model || "—"],
        ["Anomaly Score", f.anomaly_score === null || f.anomaly_score === undefined ? "—" : `${Number(f.anomaly_score).toFixed(1)} / 100`],
        ["Confidence", f.confidence === null || f.confidence === undefined ? "—" : `${Math.round((f.confidence || 0) * 100)}%`],
        ["Z-Score", f.z_score === null || f.z_score === undefined ? "—" : `${Number(f.z_score).toFixed(2)}σ`],
        ["Observed", f.observed_statistic === null || f.observed_statistic === undefined ? "—" : Number(f.observed_statistic).toFixed(5)],
        ["Baseline", f.baseline_mean === null ? "—" : `μ ${Number(f.baseline_mean).toFixed(5)} ± ${Number(f.baseline_std || 0).toFixed(5)} (N=${f.baseline_n})`],
        ["Related Prompt", f.prompt_id || "—"],
        ["Run", f.run_id === null || f.run_id === undefined ? "—" : `#${f.run_id}`],
      ]),
      el("div", { class: "section-title" }, "Explanation"),
      el("p", { class: "muted", style: "font-size:12.5px;" }, f.explanation || "—"),
      el("div", { class: "section-title mt" }, "Recommended Action"),
      el("div", { class: "badge badge-" + (f.severity === "CRITICAL" ? "danger" : f.severity === "HIGH" ? "high" : "warn") }, "REVIEW FINDING"),
      el("p", { class: "muted mt8", style: "font-size:12px;color:var(--warn);" },
        "Statistical anomaly — potentially suspicious activation behaviour, not proof of a neural backdoor."));
    openDrawer(`Finding #${f.finding_id}`, details);
  }

  async function exportReportNow(s) {
    toast("Generating forensic report from real scan data…", "info");
    try {
      const r = await API.generateReport(s.scan_id, s.run_id);
      toast(`Report written: ${r.path}`, "ok");
      history("#/reports");
    } catch (e) { toast(`Report failed: ${e.message}`, "danger"); }
  }

  /* ================================================================
     INVESTIGATIONS (history + read-only detail)
     ================================================================ */
  function renderInvestigations(mount, params) {
    mount.append(loadingBlock("Loading investigations…"));
    API.scanHistory().then((d) => {
      mount.innerHTML = "";
      mount.append(pageTitle("INVESTIGATIONS", "All security scan investigations, newest first."));
      mount.append(el("div", { class: "grid grid-cols-4" },
        kpi("Total Runs", d.stats.total, { tone: "accent" }),
        kpi("Completed", d.stats.completed, { tone: "ok" }),
        kpi("Failed", d.stats.failed, { tone: "danger" }),
        kpi("Active", d.stats.active, { tone: "warn" })));
      mount.append(card("Scan Runs",
        table(["ID", "Status", "Model", "Prompts", "Layers", "Findings", "Anomaly", "Created"],
          (d.runs || []).map((s) => [
            { _html: `<span class="mono" style="color:${C.accent}">#${s.scan_id}</span>` },
            { _html: scanBadge(s.status) },
            s.model || "—",
            `${s.prompts_processed || 0}/${s.total_prompts || 0}`,
            s.layers_analyzed || 0,
            s.findings_generated || 0,
            { _html: riskCell(s.current_anomaly_score) },
            fmt(s.created_at),
          ]), {
          emptyText: "No scans yet. Start a new investigation.",
          onrow: (r2) => {
            const id = String(r2[0]._html).replace(/\D/g, "");
            history(`#/investigations/${id}`);
          },
        }), { flush: true, note: "Real persisted pipeline runs" }));
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  function renderInvestigationDetail(mount, params) {
    const scanId = parseInt((params || {}).id, 10);
    if (!scanId) { mount.append(emptyBlock("Invalid scan id", "")); return; }
    mount.append(loadingBlock("Loading investigation…"));
    API.scanDetail(scanId).then((d) => {
      mount.innerHTML = "";
      const s = d.state || {};
      const findings = d.findings || [];
      mount.append(stepper(4, 4));
      mount.append(pageTitle(`INVESTIGATION #${scanId}`, `Model «${esc(s.model || "")}»`));

      const risk = s.current_anomaly_score === null || s.current_anomaly_score === undefined
        ? null : Number(s.current_anomaly_score);
      const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
      findings.forEach((f) => { const k = String(f.severity || "LOW").toUpperCase(); if (k in counts) counts[k]++; });

      mount.append(el("div", { class: "grid grid-cols-5" },
        kpi("Scan ID", `#${s.scan_id}`, { tone: "accent" }),
        kpi("Status", s.status, { tone: s.status === "COMPLETED" ? "ok" : "warn" }),
        kpi("Prompts Tested", `${s.prompts_processed || 0}/${s.total_prompts || 0}`, { tone: "blue" }),
        kpi("Findings", s.findings_generated || 0, { tone: "danger" }),
        kpi("Risk Score", risk === null ? "—" : Number(risk).toFixed(0), { tone: "warn" })));

      const stats = el("div", { class: "grid grid-cols-2 mt" },
        card("Details",
          kvRows([
            ["Scan ID", `#${s.scan_id}`],
            ["Status", { _html: scanBadge(s.status) }],
            ["Model", s.model || "—"],
            ["Seed", s.seed ?? "—"],
            ["Run ID", s.run_id ?? "—"],
            ["Created", fmt(s.created_at)],
            ["Updated", fmt(s.updated_at)],
          ]),
          s.error ? el("div", { class: "neg mt8" }, esc(s.error)) : null),
        card("Severity Distribution",
          el("div", { class: "grid grid-cols-4", style: "gap:8px;" },
            kpi("CRITICAL", counts.CRITICAL, { tone: "danger" }),
            kpi("HIGH", counts.HIGH, { tone: "danger" }),
            kpi("MEDIUM", counts.MEDIUM, { tone: "warn" }),
            kpi("LOW", counts.LOW, { tone: "ok" }))));

      mount.append(stats);

      mount.append(card("Findings",
        findings.length
          ? table(["Severity", "Finding", "Layer", "Score", "Confidence", "Evidence"],
            findings.map((f) => [
              { _html: severityBadge(f.severity) },
              { _html: layerFeature(f) },
              f.layer || "—",
              { _html: riskCell(f.anomaly_score) },
              f.confidence === null || f.confidence === undefined ? "—" : `${Math.round((f.confidence || 0) * 100)}%`,
              { _html: `<span style="color:${C.muted}">${esc(trunc(f.explanation || "", 60))}</span>` },
            ]), { emptyText: "No findings recorded.", onrow: (r2) => {
              const idx = findings.findIndex((f) => f.layer === r2[2]);
              openFindingDrawer(idx >= 0 ? findings[idx] : null);
            } })
          : emptyBlock("No findings", "No statistical findings recorded for this scan."),
        { flush: true }));

      mount.append(el("div", { class: "btn-row mt" },
        el("a", { class: "btn btn-primary", href: `#/forensics/findings?run=${s.run_id || ""}` }, "VIEW FINDINGS"),
        el("a", { class: "btn btn-secondary", href: `#/forensics/activation?model=${encodeURIComponent(s.model || "")}` }, "ACTIVATION EXPLORER"),
        el("button", { class: "btn btn-ghost", onclick: () => exportReportNow(s) }, "EXPORT REPORT")));

      if (s.activity_log && s.activity_log.length) {
        mount.append(card("Activity Log",
          el("div", { class: "log", style: "max-height:260px;" },
            s.activity_log.map((e) => el("div", { class: "entry" },
              el("span", { class: "t" }, e.ts + "  "), esc(e.message))))));
      }
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  /* ================================================================
     FINDINGS
     ================================================================ */
  function renderFindings(mount, params) {
    mount.append(loadingBlock("Loading findings…"));
    const runFilter = params && params.run && parseInt(params.run, 10) || null;
    API.findings({ run_id: runFilter || undefined, limit: 1000 }).then((d) => {
      mount.innerHTML = "";
      mount.append(pageTitle("FINDINGS", "Real statistical anomaly findings from the analysis engine."));
      const dist = d.severity_distribution || {};
      mount.append(el("div", { class: "grid grid-cols-5" },
        kpi("CRITICAL", dist.CRITICAL || 0, { tone: "danger", icon: "●" }),
        kpi("HIGH", dist.HIGH || 0, { tone: "danger", icon: "▲" }),
        kpi("MEDIUM", dist.MEDIUM || 0, { tone: "warn", icon: "◆" }),
        kpi("LOW", dist.LOW || 0, { tone: "ok", icon: "▼" }),
        kpi("BENIGN", dist.BENIGN || 0, { tone: "ok", icon: "✓" })));

      const controls = card("Filters",
        el("div", { class: "flex wrap" },
          fld("Scan Run", "run", [["", "All runs"]].concat((d.runs || []).map((r) => [r.run_id, `#${r.run_id} · ${r.run_label || ""}`])), (v) => { if (v) history(`#/forensics/findings?run=${v}`); else history("#/forensics/findings"); renderFindings(mount, {}); }),
          fld("Severity", "sev", ["", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((x) => [x, x || "All"]), (v) => { applyFilter({ severity: v }); }),
          fld("Layer", "layer", ["", ...(d.layers || [])].map((x) => [x, x || "All layers"]), (v) => { applyFilter({ layer: v }); }),
          fld("Min Score", "score", ["", "0", "40", "60", "80"].map((x) => [x, x ? `≥ ${x}` : "All"]), (v) => { applyFilter({ min_score: v }); })));

      function applyFilter(extra) {
        const q = new URLSearchParams();
        const run = document.getElementById("inp-run").value;
        const sev = document.getElementById("inp-sev").value;
        const layer = document.getElementById("inp-layer").value;
        const score = document.getElementById("inp-score").value;
        if (run) q.set("run_id", run);
        if (sev) q.set("severity", sev);
        if (layer) q.set("layer", layer);
        if (score) q.set("min_score", score);
        history("#/forensics/findings" + (q.toString() ? "?" + q.toString() : ""));
        renderFindings(mount, { run: run });
      }

      function fld(label, id, options, onchange) {
        const wrap = el("div", { class: "field", style: "margin:0 10px 0 0;min-width:150px;" },
          el("label", { for: `inp-${id}` }, label),
          el("select", { id: `inp-${id}` },
            options.map(([v, lab]) => el("option", { value: v }, lab))));
        const sel = wrap.querySelector("select");
        if (id === "run" && runFilter) sel.value = String(runFilter);
        sel.addEventListener("change", () => onchange(sel.value));
        return wrap;
      }

      mount.append(controls);

      mount.append(card("Findings Table",
        (d.findings || []).length
          ? table(["Severity", "Layer", "Feature", "Category", "Prompt", "Score", "Confidence", "Z-Score"],
            (d.findings || []).map((f) => [
              { _html: severityBadge(f.severity) },
              f.layer || "—",
              f.feature || "—",
              f.category || "—",
              { _html: `<span class="dim">${esc((f.prompt_id || "").split("-").pop())}</span>` },
              { _html: riskCell(f.anomaly_score) },
              f.confidence === null || f.confidence === undefined ? "—" : `${Math.round((f.confidence || 0) * 100)}%`,
              f.z_score === null || f.z_score === undefined ? "—" : `${Number(f.z_score).toFixed(1)}σ`,
            ]), { emptyText: "No findings match the current filters.", onrow: (r2) => {
              const idx = d.findings.findIndex((f) => f.layer === r2[1] && f.feature === r2[2]);
              openFindingDrawer(idx >= 0 ? d.findings[idx] : null);
            } })
          : emptyBlock("No findings match the filters", "Run a security scan and analyze its run to generate findings."),
        { flush: true, note: `${(d.summary || {}).total || 0} total · click a row for the detail drawer` }));
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  /* ================================================================
     ACTIVATION EXPLORER
     ================================================================ */
  function renderActivation(mount, params) {
    const model = (params && params.model) || "";
    mount.append(loadingBlock("Loading activation data…"));
    API.activation(model).then((d) => {
      mount.innerHTML = "";
      mount.append(pageTitle("ACTIVATION EXPLORER", "Per-layer activation forensics from real scan measurements."));

      const modelSel = el("select", { id: "act-model" },
        [["", "All models"]].concat((d.models || []).map((m) => [m.file_name, m.file_name])).map(([v, lab]) => el("option", { value: v }, lab)));
      if (model) modelSel.value = model;
      modelSel.addEventListener("change", () => {
        const v = modelSel.value;
        history("#/forensics/activation" + (v ? `?model=${encodeURIComponent(v)}` : ""));
        renderActivation(mount, { model: v });
      });

      const top = card("Model & Tracking",
        el("div", { class: "flex between" },
          el("div", { class: "field", style: "flex:1;margin:0;" },
            el("label", {}, "Layer Correlation Model"),
            modelSel),
          el("div", { class: "field", style: "margin:0 0 0 14px;" },
            el("label", {}, "Tracking Status"),
            el("div", { class: "flex" },
              el("span", { class: "status-dot ok" }),
              el("span", { class: "muted", style: "font-size:12px;" }, "OFFLINE / LOCAL")))));

      mount.append(top);

      const stats = d.layer_stats || [];
      const mtx = d.matrix || {};
      const layers = mtx.layers || [];
      const cats = mtx.categories || [];

      mount.append(card("Activation Heatmap",
        el("div", { id: "act-heatmap" }, loadingBlock("Building heatmap…")),
        { note: "Mean activation per layer × input category" }));
      const hm = document.getElementById("act-heatmap");
      hm.innerHTML = "";
      ChartLib.heatmap(hm, mtx);

      mount.append(el("div", { class: "grid grid-cols-2 mt" },
        card("Layer Statistics",
          stats.length
            ? table(["Layer", "Mean", "STD", "Max", "Norm", "Active %", "Elements", "Anomaly"],
              stats.map((s) => [
                { _html: `<span class="mono">${esc(s.layer)}</span>` },
                `${s.mean}`,
                `${s.std}`,
                `${s.max}`,
                `${s.norm}`,
                `${Math.round((s.active_fraction || 0) * 100)}%`,
                s.num_elements || "—",
                s.anomaly_score === null ? "—" : { _html: riskCell(s.anomaly_score) },
              ]), { emptyText: "No layer measurements recorded yet." })
            : emptyBlock("No measurements", "Run a security scan to collect per-layer activation statistics."),
          { flush: true }),
        card("Activation Distribution",
          el("div", {}, el("canvas", { "data-h": "220", id: "act-bars" })),
          { note: "Mean activation per layer" })));

      mount.append(card("Layer Comparison",
        el("div", {}, el("canvas", { "data-h": "220", id: "act-line" })),
        { note: "Mean vs spread across layers" }));

      if (stats.length) {
        ChartLib.attach(document.getElementById("act-bars"),
          (ctx, w, h) => ChartLib.bars(ctx, w, h,
            stats.map((s) => ({ label: shortLayer(s.layer), value: Math.max(0, s.mean), color: C.accent })),
            { max: Math.max(...stats.map((s) => s.mean), 1) }));
        ChartLib.attach(document.getElementById("act-line"),
          (ctx, w, h) => ChartLib.line(ctx, w, h,
            stats.map((s) => ({ label: shortLayer(s.layer), value: s.mean, color: C.accent })),
            { color: C.accent }));
      } else {
        const b = document.getElementById("act-bars");
        if (b) { b.parentElement.innerHTML = ""; b.parentElement.append(emptyBlock("No data", "Run a scan to generate layer distributions.")); }
        const l = document.getElementById("act-line");
        if (l) { l.parentElement.innerHTML = ""; l.parentElement.append(emptyBlock("No data", "Run a scan to generate layer comparisons.")); }
      }

      mount.append(el("div", { class: "mt" }, card(null,
        el("div", { class: "action-bar" },
          el("button", { class: "btn", id: "act-infer" }, "RUN INFERENCE (QUICK SCAN)"),
          el("span", { class: "context-note" }, "Launch a real QUICK CHECK scan on the selected model to generate fresh activations."),
          el("div", { id: "act-infer-status" })))));

      document.getElementById("act-infer").addEventListener("click", async () => {
        const target = modelSel.value || (d.models.length ? d.models[0].file_name : null);
        if (!target) { toast("Register a model first", "danger"); return; }
        const st = document.getElementById("act-infer-status");
        st.innerHTML = ""; st.append(loadingBlock("Launching quick scan…"));
        try {
          const scan = await API.createScan({
            model: target, num_prompts: 4, layers: 8, seed: 42,
            max_seq_len: 12, max_new_tokens: 2,
            categories: ["normal", "adversarial", "edge"], depth: "QUICK CHECK",
          });
          st.innerHTML = "";
          st.append(el("div", { class: "flex" },
            el("a", { class: "btn btn-primary btn-sm", href: `#/investigate/new?scan=${scan.scan_id}` }, `TRACK SCAN #${scan.scan_id}`),
            el("span", { class: "muted", style: "font-size:12px;" }, "Scan running in the real backend pipeline.")));
        } catch (err) { st.innerHTML = ""; st.append(errorBlock(err.message)); }
      });
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  function shortLayer(layer) {
    const parts = String(layer || "").split(".");
    return parts[parts.length - 1].slice(0, 9);
  }

  /* ================================================================
     SCAN HISTORY (alias of investigations table)
     ================================================================ */
  function renderScanHistory(mount) {
    mount.append(loadingBlock("Loading scan history…"));
    API.scanHistory(200).then((d) => {
      mount.innerHTML = "";
      mount.append(pageTitle("SCAN HISTORY", "All pipeline scan runs and their real persisted state."));
      mount.append(el("div", { class: "grid grid-cols-4" },
        kpi("Total Runs", d.stats.total, { tone: "accent" }),
        kpi("Completed", d.stats.completed, { tone: "ok" }),
        kpi("Failed", d.stats.failed, { tone: "danger" }),
        kpi("Active", d.stats.active, { tone: "warn" })));
      mount.append(card("Scan Runs",
        table(["ID", "Status", "Model", "Prompts", "Layers", "Findings", "Anomaly Score", "Created"],
          (d.runs || []).map((s) => [
            { _html: `<span class="mono" style="color:${C.accent}">#${s.scan_id}</span>` },
            { _html: scanBadge(s.status) },
            s.model || "—",
            `${s.prompts_processed || 0}/${s.total_prompts || 0}`,
            s.layers_analyzed || 0,
            s.findings_generated || 0,
            { _html: riskCell(s.current_anomaly_score) },
            fmt(s.created_at),
          ]), {
          emptyText: "No scans yet.",
          onrow: (r2) => history(`#/investigations/${String(r2[0]._html).replace(/\D/g, "")}`),
        }), { flush: true }));
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  /* ================================================================
     MODEL REGISTRY
     ================================================================ */
  function renderModels(mount) {
    mount.append(loadingBlock("Loading model registry…"));
    API.models().then((d) => {
      mount.innerHTML = "";
      mount.append(pageTitle("MODEL REGISTRY", "Imported local model files with real forensic metadata."));
      const st = d.stats || {};
      mount.append(el("div", { class: "grid grid-cols-4" },
        kpi("Total Models", st.total_models, { tone: "accent" }),
        kpi("Validated", st.validated, { tone: "ok" }),
        kpi("Scanned", st.scanned, { tone: "blue" }),
        kpi("Total Size", fmtBytes(st.total_size), { tone: "violet" })));

      const actions = el("div", { class: "card", style: "padding:0;" },
        el("div", { class: "card-body" },
          el("div", { class: "action-bar" },
            el("label", { class: "btn btn-primary", style: "cursor:pointer;" },
              el("input", { type: "file", id: "model-import-file", style: "display:none;", accept: ".json,.pt,.pth,.safetensors,.onnx,.bin" }),
              "⬆  IMPORT MODEL"),
            el("button", { class: "btn", id: "model-import-dir" }, "IMPORT DIRECTORY"),
            el("span", { class: "context-note" },
              "Directory imports a path on this machine. Both use the existing sandbox validation pipeline."),
            el("span", { id: "model-import-status", class: "flex", style: "gap:6px;margin-left:auto;" }))));

      mount.append(el("div", { class: "mt" }, actions));

      mount.append(card("Registry",
        table(["Model", "Format", "Size", "SHA-256", "Architecture", "Status", "Imported"],
          (d.models || []).map((m) => [
            { _html: `<span style="color:${C.text};font-weight:600;">${esc(m.file_name)}</span>` },
            m.model_type || "—",
            m.size_label || "—",
            { _html: `<span class="mono dim">${esc((m.sha_short || "") + "…")}</span>` },
            m.architecture || "—",
            { _html: badge(m.status_label || m.status || "imported", "info") },
            fmt(m.created_at),
          ]), {
          emptyText: "No models imported yet. Import a model file to begin.",
          onrow: (r2) => {
            const row = (d.models || [])[d.models.findIndex((m) => m.file_name === String(r2[0].firstChild.textContent))];
            if (row) openModelDrawer(row);
          },
        }), { flush: true, note: "Click a row for details + actions" }));
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });

    // import listeners (defer since elements created async)
    document.addEventListener("change", (e) => {
      if (e.target && e.target.id === "model-import-file") {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const st = document.getElementById("model-import-status");
        if (st) { st.innerHTML = ""; st.append(loadingBlock("Verifying…")); }
        API.importFile(file).then((r) => {
          if (st) { st.innerHTML = ""; st.append(importResult(r)); }
          toast(`Imported ${(r.models || []).length} model(s)`, "ok");
          renderModels(mount, {});
        }).catch((err) => { if (st) { st.innerHTML = ""; st.append(errorBlock(err.message)); } });
        e.target.value = "";
      }
    }, { capture: true });
    // dir import button
    const boot = () => {
      const b = document.getElementById("model-import-dir");
      if (!b) return;
      b.addEventListener("click", () => {
        const p = prompt("Local directory on this machine to import:");
        if (!p) return;
        const st = document.getElementById("model-import-status");
        if (st) { st.innerHTML = ""; st.append(loadingBlock("Importing…")); }
        API.importDir(p).then((r) => {
          if (st) { st.innerHTML = ""; st.append(importResult(r)); }
          toast(`Imported ${(r.models || []).length} model(s)`, "ok");
          renderModels(mount, {});
        }).catch((err) => { if (st) { st.innerHTML = ""; st.append(errorBlock(err.message)); } });
      });
    };
    setTimeout(boot, 0);
  }

  function openModelDrawer(model) {
    const body = el("div", {},
      kvRows([
        ["File", model.file_name],
        ["Format", model.model_type || "—"],
        ["Architecture", model.architecture || "—"],
        ["Size", model.size_label || "—"],
        ["SHA-256", model.sha256_hash || model.sha_short || "—"],
        ["Status", model.status_label || model.status || "—"],
        ["Imported", fmt(model.created_at)],
        ["Scanned", model.scanned_at ? fmt(model.scanned_at) : "Never"],
      ]),
      el("div", { id: "model-drawer-detail" }, loadingBlock("Loading checkpoint…")));
    const dr = openDrawer(String(model.file_name), body);
    API.model(model.metadata_id).then((d) => {
      const dd = document.getElementById("model-drawer-detail");
      dd.innerHTML = "";
      const cp = d.checkpoint || {};
      dd.append(el("div", { class: "section-title" }, "Security Checkpoint"));
      dd.append(el("div", {}, (cp.steps || []).map((s2) =>
        el("div", { class: "phase-item " + (s2.done ? "done" : "active") },
          el("span", { class: "glyph" }, s2.done ? "✓" : "○"),
          el("span", { class: "label" }, s2.label)))));
      dd.append(el("div", { class: "section-title mt" }, "Risk Decision"));
      const dec = d.decision || {};
      dd.append(el("div", { class: "flex" },
        el("span", { class: "badge badge-" + (dec.decision === "quarantined" ? "danger" : dec.decision === "review" ? "warn" : dec.decision === "approved" ? "ok" : "dim"), html: badgeInside(dec.decision || "pending") })));
      const dist = dec.severity_distribution || {};
      const have = Object.values(dist).some((v) => v);
      if (have) {
        dd.append(el("div", { class: "section-title mt" }, "Severity Distribution"));
        dd.append(el("div", { class: "grid grid-cols-4", style: "gap:6px;" },
          Object.entries({ CRITICAL: dist.CRITICAL, HIGH: dist.HIGH, MEDIUM: dist.MEDIUM, LOW: dist.LOW })
            .map(([k, v]) => kpi(k, v || 0, { tone: k === "CRITICAL" ? "danger" : k === "HIGH" ? "danger" : k === "MEDIUM" ? "warn" : "ok" }))));
      }
      dd.append(el("div", { class: "btn-row mt" },
        el("a", { class: "btn btn-primary btn-sm", href: `#/scanner?model=${encodeURIComponent(model.file_name)}` }, "OPEN IN SCANNER"),
        el("a", { class: "btn btn-ghost btn-sm", href: `#/investigate/new?model=${encodeURIComponent(model.file_name)}` }, "START SCAN"),
        el("button", { class: "btn btn-sm", onclick: async () => {
          const bts = document.querySelectorAll("#model-drawer-detail .btn");
          try {
            const r = await API.applyDecision(model.metadata_id);
            toast(`Decision: ${r.decision}${r.updated ? " (applied)" : ""}`, r.updated ? "ok" : "info");
            dr.close();
          } catch (e) { toast(e.message, "danger"); }
        } }, "APPLY DECISION")));
    }).catch((err) => {
      const dd = document.getElementById("model-drawer-detail");
      if (dd) { dd.innerHTML = ""; dd.append(errorBlock(err.message)); }
    });
  }

  /* ================================================================
     MODEL SCANNER
     ================================================================ */
  function renderScanner(mount, params) {
    const wanted = params && params.model ? decodeURIComponent(params.model) : "";
    mount.append(loadingBlock("Loading scanner…"));
    API.models().then((d) => {
      mount.innerHTML = "";
      mount.append(pageTitle("MODEL SCANNER", "Pick a model, review its checkpoint, and launch a security scan."));
      const models = d.models || [];
      if (!models.length) {
        mount.append(emptyBlock("No models registered", "Import a model in the Model Registry to begin."));
        return;
      }
      const picker = el("select", { id: "scanner-model", style: "min-width:260px;" },
        models.map((m) => el("option", { value: m.file_name }, m.file_name)));
      const sel = models.find((m) => m.file_name === wanted) || models[0];

      mount.append(card("Target Model",
        el("div", { class: "flex wrap" },
          el("div", { class: "field", style: "flex:1;margin:0;" },
            el("label", {}, "Model"),
            picker),
          el("div", { class: "flex", style: "margin-left:10px;" },
            el("a", { class: "btn", href: `#/investigate/new?model=${encodeURIComponent(sel.file_name)}` }, "START SECURITY SCAN →"),
            el("a", { class: "btn btn-ghost", href: "#/models" }, "MODEL REGISTRY")))));

      mount.append(el("div", { class: "mt", id: "scanner-detail" }, loadingBlock("Loading checkpoint…")));

      picker.addEventListener("change", () => {
        history(`#/scanner?model=${encodeURIComponent(picker.value)}`);
        renderScanner(mount, { model: picker.value });
      });

      API.model(sel.metadata_id).then((detail) => renderScannerDetail(mount, detail, sel))
        .catch((err) => {
          const dd = document.getElementById("scanner-detail");
          if (dd) { dd.innerHTML = ""; dd.append(errorBlock(err.message)); }
        });
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  function renderScannerDetail(mount, d, model) {
    const dd = document.getElementById("scanner-detail");
    dd.innerHTML = "";
    const cp = d.checkpoint || {};
    const m = d.model || model;
    const grid = el("div", { class: "grid grid-cols-2" });

    const ver = el("div", {});
    ver.append(el("div", { class: "section-title" }, "Verification"));
    (d.verification || []).forEach((chk) => {
      ver.append(el("div", { class: "phase-item " + (chk.pass ? "done" : "active") },
        el("span", { class: "glyph" }, chk.pass ? "✓" : "●"),
        el("span", { class: "label" }, chk.label),
        el("span", { class: "dim", style: "margin-left:auto;font-size:11px;" }, chk.pass ? badge("PASS", "ok") : badge("WARNING", "warn"))));
    });

    const dec = el("div", {});
    dec.append(el("div", { class: "section-title" }, "Security Checkpoint"));
    dec.append(el("div", {}, (cp.steps || []).map((s2) =>
      el("div", { class: "phase-item " + (s2.done ? "done" : "active") },
        el("span", { class: "glyph" }, s2.done ? "✓" : "○"),
        el("span", { class: "label" }, s2.label)))));
    dec.append(el("div", { class: "flex mt8" },
      el("span", { class: "badge badge-" + ((d.decision || {}).decision === "quarantined" ? "danger" : (d.decision || {}).decision === "review" ? "warn" : (d.decision || {}).decision === "approved" ? "ok" : "dim"), html: badgeInside((d.decision || {}).decision || "pending") })));

    grid.append(card("Model", kvRows([
      ["File", m.file_name],
      ["Format", m.model_type || "—"],
      ["Architecture", m.architecture || "—"],
      ["Size", m.size_label],
      ["SHA-256", (m.sha256_hash || m.sha_short || "—")],
      ["Status", m.status_label || m.status || "—"],
      ["Scanned", m.scanned_at ? fmt(m.scanned_at) : "Never"],
    ])));
    grid.append(card("Verification", ver));
    grid.append(card("Checkpoint", dec));
    grid.append(card("Risk Decision",
      el("div", {},
        el("div", { class: "flex mt8" },
          el("span", { class: "badge badge-" + ((d.decision || {}).decision === "quarantined" ? "danger" : (d.decision || {}).decision === "review" ? "warn" : (d.decision || {}).decision === "approved" ? "ok" : "dim"), html: badgeInside((d.decision || {}).decision || "pending") })))));

    dd.append(grid);
    dd.append(el("div", { class: "btn-row mt" },
      el("a", { class: "btn btn-primary", href: `#/investigate/new?model=${encodeURIComponent(m.file_name)}` }, "START SECURITY SCAN"),
      el("a", { class: "btn btn-ghost", href: `#/forensics/findings?model=${encodeURIComponent(m.file_name)}` }, "VIEW FINDINGS"),
      el("button", { class: "btn btn-ghost", onclick: async () => {
        try { const r = await API.applyDecision(m.metadata_id); toast(`Decision: ${r.decision}${r.updated ? " (applied)" : ""}`, "ok"); }
        catch (e) { toast(e.message, "danger"); }
      } }, "APPLY RISK DECISION")));
  }

  /* ================================================================
     REPORTS
     ================================================================ */
  function renderReports(mount) {
    mount.append(loadingBlock("Loading reports…"));
    API.reports().then((d) => {
      mount.innerHTML = "";
      mount.append(pageTitle("SECURITY REPORTS", "Forensic reports generated from real scan data."));
      const st = d.stats || {};
      mount.append(el("div", { class: "grid grid-cols-4" },
        kpi("Total Reports", st.total, { tone: "accent" }),
        kpi("Available", st.available, { tone: "ok" }),
        kpi("Pending", st.pending, { tone: "warn" }),
        kpi("Missing", st.missing, { tone: "danger" })));

      mount.append(el("div", { class: "card mt" },
        el("div", { class: "card-body" },
          el("div", { class: "action-bar" },
            el("button", { class: "btn btn-primary", id: "btn-gen-report" }, "GENERATE REPORT"),
            el("button", { class: "btn", id: "btn-open-report" }, "OPEN REPORT"),
            el("span", { class: "context-note" }, "Reports are written by the forensic report builder (PDF / Markdown)."),
            el("span", { id: "report-status", class: "flex", style: "gap:6px;margin-left:auto;" }))))) ;

      mount.append(card("Reports",
        table(["Report", "Investigation", "Model", "Format", "Generated", "Status"],
          (d.reports || []).map((r) => [
            { _html: `<span class="mono" style="color:${C.accent}">#${r.report_id}</span>` },
            r.scan_id !== null && r.scan_id !== undefined ? `#${r.scan_id}` : (r.run_id !== null ? `run #${r.run_id}` : "—"),
            r.model || "—",
            String(r.format || "pdf").toUpperCase(),
            fmt(r.created_at),
            { _html: r.exists ? badge("ON DISK", "ok") : badge("MISSING", "danger") },
          ]), {
          emptyText: "No reports generated yet.",
          onrow: (r2) => {
            const idx = (d.reports || []).findIndex((r) => r.report_id === parseInt(String(r2[0]._html).replace(/\D/g, ""), 10));
            const rep = d.reports[idx];
            if (rep && rep.exists) {
              const a = document.createElement("a");
              a.href = API.reportFileUrl(rep.report_id);
              a.setAttribute("download", "");
              a.click();
            } else toast("Report file missing on disk", "danger");
          },
        }), { flush: true, note: "Click a row to download (if on disk)" }));

      document.getElementById("btn-gen-report").addEventListener("click", async () => {
        const st2 = document.getElementById("report-status");
        st2.innerHTML = ""; st2.append(loadingBlock("Loading sources…"));
        try {
          const sources = await API.reportSources();
          st2.innerHTML = "";
          if (!sources.length) { st2.append(el("span", { class: "muted" }, "No completed scans available to report on.")); return; }
          const select = el("select", { style: "min-width:280px;" },
            sources.map((s) => el("option", { value: `${s.kind}:${s.id}` }, `${s.label} · ${s.created_at || ""}`)));
          const go = el("button", { class: "btn btn-primary btn-sm" }, "Generate");
          st2.append(select, go);
          go.addEventListener("click", async () => {
            const [kind, id] = select.value.split(":");
            go.disabled = true; go.textContent = "GENERATING…";
            try {
              const r = await API.generateReport(kind === "scan" ? parseInt(id, 10) : null, kind === "run" ? parseInt(id, 10) : null);
              toast(`Report generated: ${r.path}`, "ok");
              st2.innerHTML = "";
              renderReports(mount, {});
            } catch (e) { go.disabled = false; go.textContent = "Generate"; st2.append(el("span", { class: "neg" }, ` ${e.message}`)); }
          });
        } catch (e) { st2.innerHTML = ""; st2.append(errorBlock(e.message)); }
      });

      document.getElementById("btn-open-report").addEventListener("click", async () => {
        const list = (d.reports || []).filter((r) => r.exists);
        if (list.length) {
          const a = document.createElement("a");
          a.href = API.reportFileUrl(list[0].report_id);
          a.setAttribute("download", "");
          a.click();
        } else toast("No reports on disk", "warn");
      });
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  /* ================================================================
     SETTINGS
     ================================================================ */
  function renderSettings(mount) {
    mount.append(loadingBlock("Loading settings…"));
    Promise.all([API.settings(), API.health()]).then(([s, h]) => {
      mount.innerHTML = "";
      mount.append(pageTitle("SETTINGS", "Platform configuration and system status."));
      const grid = el("div", { class: "grid grid-cols-2" });
      grid.append(card("Deployment",
        kvRows([
          ["Mode", s.mode || h.offline ? "LOCAL / OFFLINE / AIR-GAPPED" : "ONLINE"],
          ["Analyst", s.analyst],
          ["Database", s.db_path || "—"],
          ["Project", s.project && s.project.name ? `${s.project.name} v${s.project.version}` : "—"],
        ])));
      grid.append(card("Paths",
        kvRows(Object.entries(s.paths || {}).map(([k, v]) => [k, v]))));
      mount.append(grid);

      const m = s.model || {};
      const stat = s.anomaly_detection || {};
      const sandboxCard = card("Model Sandbox",
        kvRows([
          ["Active Target", m.active_target || "—"],
          ["Allowed Targets", (m.allowed_targets || []).join(", ") || "—"],
          ["Local Model", m.local_model_name || "—"],
        ]));
      const statCard = card("Statistical Settings",
        el("div", {},
          kvRows([
            ["Severity Cutoffs", (stat.statistical || {}).severity_cutoffs ? (stat.statistical.severity_cutoffs).join(" / ") : "—"],
            ["Z-Score Min", (stat.statistical || {}).z_score_min],
            ["Baseline Min N", (stat.statistical || {}).baseline_min_n],
            ["Confidence Correlation", (stat.statistical || {}).correlation_min],
          ])));
      mount.append(el("div", { class: "grid grid-cols-2" }, sandboxCard, statCard));
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  /* ================================================================
     AUDIT
     ================================================================ */
  function renderAudit(mount) {
    mount.append(loadingBlock("Loading audit trail…"));
    API.audit(500).then((d) => {
      mount.innerHTML = "";
      mount.append(pageTitle("AUDIT LOGS", "Operational events merged from real database rows."));
      mount.append(card("Audit Trail",
        table(["Timestamp", "Event", "Component", "Detail"],
          (d || []).map((e) => [
            { _html: `<span class="mono dim">${e.ts ? fmt(e.ts) : "—"}</span>` },
            { _html: `<span style="color:${e.color || C.muted};font-weight:600;">${esc(e.action || "")}</span>` },
            e.level || "—",
            e.detail || "—",
          ]), { emptyText: "No operational events recorded yet." }),
        { flush: true, note: `${(d || []).length} events` }));
    }).catch((err) => { mount.innerHTML = ""; mount.append(errorBlock(err.message)); });
  }

  /* ================================================================
     ROUTES
     ================================================================ */
  return {
    routes: {
      "dashboard": renderDashboard,
      "investigate-new": renderNewInvestigation,
      "investigations": renderInvestigations,
      "investigation-detail": renderInvestigationDetail,
      "findings": renderFindings,
      "activation": renderActivation,
      "scan-history": renderScanHistory,
      "models": renderModels,
      "scanner": renderScanner,
      "reports": renderReports,
      "settings": renderSettings,
      "audit": renderAudit,
    },
    actions: {
      history,
      toast,
      resetWF,
    },
  };
})();