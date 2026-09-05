/* NeuroFence web — thin API client over the local FastAPI adapter. */
"use strict";

const API = (() => {
  async function request(path, opts = {}) {
    const init = {
      method: opts.method || "GET",
      headers: { Accept: "application/json" },
    };
    if (opts.json !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.json);
    } else if (opts.form !== undefined) {
      init.body = opts.form;
    }
    let res;
    try {
      res = await fetch(path, init);
    } catch (err) {
      const e = new Error("Request failed — server not reachable.");
      e.network = true;
      throw e;
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) { /* ignore */ }
      const e = new Error(detail || `HTTP ${res.status}`);
      e.status = res.status;
      throw e;
    }
    return res.json();
  }

  return {
    meta: () => request("/api/meta"),
    health: () => request("/api/health"),
    dashboard: () => request("/api/dashboard"),
    activities: (limit = 20) => request(`/api/activities?limit=${limit}`),
    audit: (limit = 200) => request(`/api/audit?limit=${limit}`),
    settings: () => request("/api/settings"),

    models: () => request("/api/models"),
    model: (id) => request(`/api/models/${id}`),
    importFile: (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return request("/api/models/import", { method: "POST", form: fd });
    },
    importDir: (path) => request("/api/models/import-dir", { method: "POST", json: { path } }),
    deleteModel: (id) => request(`/api/models/${id}`, { method: "DELETE" }),
    setModelStatus: (id, status) => request(`/api/models/${id}/status`, { method: "PUT", json: { status } }),
    loadModel: (id) => request(`/api/models/${id}/load`, { method: "POST" }),
    modelLoadStatus: (id) => request(`/api/models/${id}/load-status`),
    applyDecision: (id) => request(`/api/models/${id}/decision`, { method: "POST" }),

    activation: (model) => request(`/api/activation?model=${encodeURIComponent(model || "")}`),

    scanConfig: () => request("/api/scan/config"),
    createScan: (cfg) => request("/api/scan", { method: "POST", json: cfg }),
    scan: (id) => request(`/api/scan/${id}`),
    cancelScan: (id) => request(`/api/scan/${id}/cancel`, { method: "POST" }),
    scanHistory: (limit = 100) => request(`/api/scan/history?limit=${limit}`),
    scanDetail: (id) => request(`/api/scans/${id}/detail`),

    findings: (params = {}) => {
      const q = new URLSearchParams();
      if (params.run_id) q.set("run_id", params.run_id);
      if (params.severity) q.set("severity", params.severity);
      if (params.layer) q.set("layer", params.layer);
      if (params.min_score) q.set("min_score", params.min_score);
      if (params.limit) q.set("limit", params.limit);
      return request(`/api/findings?${q.toString()}`);
    },
    finding: (id) => request(`/api/findings/${id}`),
    analyzeRun: (run_id) => request("/api/findings/analyze", { method: "POST", json: { run_id } }),

    reports: () => request("/api/reports"),
    reportSources: () => request("/api/reports/sources"),
    openReport: (id) => request(`/api/reports/open?report_id=${id}`),
    generateReport: (scan_id, run_id) => request("/api/reports/generate", { method: "POST", json: { scan_id, run_id } }),
    reportFileUrl: (id) => `/api/report-file/${id}`,
  };
})();