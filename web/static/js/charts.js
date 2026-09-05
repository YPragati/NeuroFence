/* NeuroFence web — offline charting (canvas/SVG, no external libs).
   All charts are container-width aware and redraw on resize. */
"use strict";

const ChartLib = (() => {
  const C = {
    accent: "#22D3EE",
    ok: "#22C55E",
    warn: "#F59E0B",
    danger: "#F43F5E",
    high: "#EF4444",
    low: "#22C55E",
    medium: "#F59E0B",
    text: "#F8FAFC",
    muted: "#94A3B8",
    dim: "#64748B",
    grid: "#1B2740",
    border: "#263147",
    panel: "#0B1020",
    input: "#151C2E",
    benign: "#22C55E",
    violet: "#A78BFA",
    blue: "#3B82F6",
    critical: "#F43F5E",
  };

  function sizeCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement
      ? canvas.parentElement.getBoundingClientRect()
      : { width: 0, height: 0 };
    const w = Math.max(0, rect.width);
    const h = Math.max(0, canvas.getAttribute("data-h") || 180);
    const cssW = w;
    const cssH = h;
    if (cssW === 0) return { w: 0, h: 0, cssW: 0, cssH: 0, dpr };
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { w: cssW, h: cssH, cssW, cssH, dpr, ctx };
  }

  function attach(canvas, draw, opts = {}) {
    const run = () => {
      const s = sizeCanvas(canvas);
      if (s.w > 0) draw(s.ctx, s.w, s.h);
    };
    run();
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(() => run());
      ro.observe(canvas.parentElement || canvas);
    }
    return run;
  }

  function line(ctx, w, h, points, o = {}) {
    const pad = { l: 34, r: 10, t: 8, b: 22 };
    const color = o.color || C.accent;
    const xs = new Set(points.map((p) => p.label));
    const step = Math.ceil(points.length / Math.max(2, Math.floor((w - pad.l - pad.r) / 58)));
    const labelEvery = (i) => i % step === 0 || i === points.length - 1;

    ctx.clearRect(0, 0, w, h);
    ctx.font = "10px system-ui, sans-serif";
    ctx.textBaseline = "middle";
    ctx.fillStyle = C.dim;

    const vals = points.map((p) => p.value);
    const lo = Math.min(0, ...vals);
    const hi = Math.max(100, ...vals);
    const span = Math.max(1, hi - lo);
    const X = (i) => pad.l + ((w - pad.l - pad.r) * i) / Math.max(1, points.length - 1);
    const Y = (v) => pad.t + (h - pad.t - pad.b) * (1 - (v - lo) / span);

    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    for (let k = 0; k <= 4; k++) {
      const v = lo + (span * k) / 4;
      const y = Y(v);
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(w - pad.r, y);
      ctx.stroke();
      ctx.fillStyle = C.dim;
      ctx.textAlign = "right";
      ctx.fillText(String(Math.round(v)), pad.l - 6, y);
    }

    if (points.length) {
      const grad = ctx.createLinearGradient(0, pad.t, 0, h - pad.b);
      grad.addColorStop(0, color + "3D");
      grad.addColorStop(1, color + "00");
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = X(i);
        const y = Y(p.value);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.lineTo(X(points.length - 1), h - pad.b);
      ctx.lineTo(X(0), h - pad.b);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();
      points.forEach((p, i) => {
        ctx.beginPath();
        ctx.arc(X(i), Y(p.value), 2.4, 0, Math.PI * 2);
        ctx.fillStyle = p.color || color;
        ctx.fill();
        if (o.lastPoint && i === points.length - 1) {
          ctx.beginPath();
          ctx.arc(X(i), Y(p.value), 5, 0, Math.PI * 2);
          ctx.fillStyle = (p.color || color) + "55";
          ctx.fill();
        }
      });
    }

    ctx.textAlign = "center";
    ctx.fillStyle = C.dim;
    points.forEach((p, i) => {
      if (labelEvery(i)) ctx.fillText(p.label, X(i), h - 6);
    });
    if (!points.length) {
      ctx.fillStyle = C.dim;
      ctx.textAlign = "center";
      ctx.fillText("No scan data available", w / 2, h / 2);
    }
  }

  function bars(ctx, w, h, items, o = {}) {
    const pad = { l: 30, r: 8, t: 10, b: 22 };
    ctx.clearRect(0, 0, w, h);
    ctx.font = "10px system-ui, sans-serif";
    ctx.textBaseline = "middle";
    const max = Math.max(1, ...items.map((i) => i.value || 0));
    const n = items.length;
    const slot = (w - pad.l - pad.r) / Math.max(1, n);
    const barW = Math.min(34, slot * 0.62);
    const X = (i) => pad.l + slot * i + (slot - barW) / 2;
    const Y = (v) => pad.t + (h - pad.t - pad.b) * (1 - v / max);

    ctx.strokeStyle = C.grid;
    ctx.beginPath();
    ctx.moveTo(pad.l, pad.t + (h - pad.t - pad.b));
    ctx.lineTo(w - pad.r, pad.t + (h - pad.t - pad.b));
    ctx.stroke();

    items.forEach((it, i) => {
      const x = X(i);
      const y = Y(it.value || 0);
      const bh = Math.max(0, (h - pad.t - pad.b) - y + pad.t);
      const grad = ctx.createLinearGradient(0, y, 0, y + bh);
      grad.addColorStop(0, it.color);
      grad.addColorStop(1, it.color + "AA");
      ctx.fillStyle = grad;
      roundRect(ctx, x, y, barW, Math.max(1, bh), 2);
      ctx.fill();
      ctx.fillStyle = it.color;
      ctx.font = "700 10px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(String(it.value || 0), x + barW / 2, y - 6);
      ctx.font = "10px system-ui, sans-serif";
      ctx.fillStyle = C.dim;
      const label = it.label.length > 8 ? it.label.slice(0, 7) + "…" : it.label;
      ctx.fillText(label, x + barW / 2, h - 6);
    });
    if (!items.length) {
      ctx.fillStyle = C.dim;
      ctx.textAlign = "center";
      ctx.fillText("No data available", w / 2, h / 2);
    }
  }

  function roundRect(ctx, x, y, w, h, r) {
    if (w <= 0 || h <= 0) return;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function donut(ctx, w, h, items, o = {}) {
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;
    const cy = h / 2;
    const R = Math.min(w, h) / 2 - 14;
    const r0 = R * 0.62;
    const total = items.reduce((s, i) => s + i.value, 0);
    if (!total) {
      ctx.fillStyle = C.dim;
      ctx.font = "12px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("No findings yet", cx, cy - 6);
      ctx.fillText("Run a security scan", cx, cy + 10);
      ctx.fillStyle = C.dim;
      ctx.font = "10px system-ui, sans-serif";
      return;
    }
    let a0 = -Math.PI / 2;
    items.forEach((it) => {
      if (!it.value) return;
      const a1 = a0 + (it.value / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.fillStyle = it.color;
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, R, a0, a1);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.arc(cx, cy, r0, a0, a1);
      ctx.lineTo(cx + r0 * Math.cos(a1), cy + r0 * Math.sin(a1));
      ctx.closePath();
      ctx.fillStyle = o.bg || C.panel;
      ctx.fill();
      a0 = a1;
    });
    ctx.fillStyle = C.text;
    ctx.font = "700 20px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(total), cx, cy - 4);
    ctx.fillStyle = C.dim;
    ctx.font = "10px system-ui, sans-serif";
    ctx.fillText("FINDINGS", cx, cy + 14);
    ctx.textBaseline = "alphabetic";
  }

  function gauge(ctx, w, h, value, o = {}) {
    ctx.clearRect(0, 0, w, h);
    if (value === null || value === undefined) value = 0;
    const cx = w / 2;
    const cy = h - 18;
    const R = Math.min(w / 2 - 8, cy - 6);
    const start = Math.PI;
    const end = Math.PI * 2;
    const color = o.color || C.accent;
    const barW = 10;

    ctx.lineWidth = barW;
    ctx.lineCap = "round";
    ctx.strokeStyle = C.input;
    ctx.beginPath();
    ctx.arc(cx, cy, R, start, end);
    ctx.stroke();

    const clamp = Math.max(0, Math.min(100, value));
    const ang = start + (end - start) * (clamp / 100);
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.arc(cx, cy, R, start, ang);
    ctx.stroke();

    ["0", "25", "50", "75", "100"].forEach((lab, i) => {
      const a = start + (end - start) * (i / 4);
      const x = cx + R * Math.cos(a);
      const y = cy + R * Math.sin(a);
      ctx.fillStyle = C.dim;
      ctx.font = "10px system-ui, sans-serif";
      ctx.textAlign = i === 0 ? "left" : i === 4 ? "right" : "center";
      ctx.fillText(lab, x, y + barW + 10);
    });

    ctx.fillStyle = C.text;
    ctx.font = "700 30px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(Math.round(clamp) + " / 100", cx, cy - R - 12);
    ctx.textBaseline = "alphabetic";
  }

  function heatmap(container, data) {
    const layers = data.layers || [];
    const cats = data.categories || [];
    const matrix = data.matrix || [];
    const counts = data.counts || [];
    if (!layers.length || !cats.length) {
      container.innerHTML = stateHTML("No measurements available", "Run a security scan to collect activation measurements.");
      return;
    }
    const all = matrix.flat().filter((v) => v !== null && v !== undefined);
    const max = all.length ? Math.max(...all) : 1;
    const min = all.length ? Math.min(...all) : 0;

    function colorFor(v) {
      if (v === null || v === undefined) return "#0A0F1E";
      const t = max > min ? (v - min) / (max - min) : 0.5;
      // hot scale: dark -> cyan -> red
      const r = Math.round(34 + t * (244 - 34));
      const g = Math.round(48 + t * (63 - 48) * (t < 0.7 ? 1 : -0.5));
      const b = Math.round(120 + t * (94 - 120));
      const bg = t < 0.5
        ? `rgb(${Math.round(10 + t * 60)},${Math.round(24 + t * 40)},${Math.round(46 + t * 70)})`
        : `rgb(${Math.round(60 + (t - 0.5) * 380)},${Math.round(30 + (t - 0.5) * 60)},${Math.round(40 + (t - 0.5) * 90)})`;
      return bg;
    }

    let html = '<div class="heatmap"><table><thead><tr><th></th>';
    cats.forEach((c) => { html += `<th>${esc(c)}</th>`; });
    html += "</tr></thead><tbody>";
    layers.forEach((layer, r) => {
      html += `<tr><th>${esc(layer)}</th>`;
      cats.forEach((_, c) => {
        const v = matrix[r] ? matrix[r][c] : null;
        const n = counts[r] ? counts[r][c] : 0;
        if (v === null || v === undefined) {
          html += '<td style="background:#0A0F1E;color:#3A4660;">—</td>';
        } else {
          html += `<td class="cell" style="background:${colorFor(v)};" title="mean ${v.toFixed(4)} · ${n} measurements">${v.toFixed(2)}<span class="tiny">${n}m</span></td>`;
        }
      });
      html += "</tr>";
    });
    html += "</tbody></table></div>";
    container.innerHTML = html;
  }

  /* ---------- shared helpers ---------- */

  function stateHTML(title, sub, error) {
    return `<div class="state-block">
      <div class="state-icon">${error ? "&#9888;" : "&#9679;"}</div>
      <div class="state-title ${error ? "state-error" : ""}">${esc(title)}</div>
      <div class="state-sub">${esc(sub)}</div>
    </div>`;
  }

  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* runtime layout audit: surfacing horizontal overflow (dev aid) */
  let auditTimer = null;
  function startAudit() {
    if (auditTimer) return;
    auditTimer = setInterval(() => {
      const scrolled = document.documentElement.scrollWidth - window.innerWidth;
      if (scrolled > 1) {
        // find the widest offender
        let worst = null;
        document.querySelectorAll("body *").forEach((el) => {
          const r = el.getBoundingClientRect();
          if (r.right > window.innerWidth + 2) {
            if (!worst || r.right > worst.right) {
              worst = { el, right: r.right, cls: el.className || el.tagName };
            }
          }
        });
        console.warn(`[layout] horizontal overflow ${scrolled}px`, worst ? worst.cls : "?");
      }
    }, 500);
  }
  function stopAudit() {
    if (auditTimer) { clearInterval(auditTimer); auditTimer = null; }
  }

  return {
    attach,
    line,
    bars,
    donut,
    gauge,
    heatmap,
    stateHTML,
    esc,
    C,
    startAudit,
    stopAudit,
  };
})();