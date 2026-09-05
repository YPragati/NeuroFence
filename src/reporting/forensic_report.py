"""
NeuroFence -- real forensic report generation.

Builds a forensic PDF directly from the ACTUAL backend data stored in
SQLite: adversarial scan runs, per-layer activation measurements,
statistical anomaly findings and model metadata. Nothing here is
fabricated -- every value either comes from a database row or from real
file forensics (SHA-256 / file size computed on the model file at report
time for the local test model).

The report explicitly states that NeuroFence detects anomalous activation
behavior and does NOT mathematically prove the existence of a backdoor.

PDF rendering uses PyQt5's QPrinter + QTextDocument (offline, no internet).
If the PDF backend is unavailable the HTML is written instead and the
metadata row stays consistent with the real file on disk.
"""

import hashlib
import json
import os
import uuid
from collections import Counter
from datetime import datetime, timezone

from src.config_loader import get_config
from src.db.db_manager import get_session
from src.db.models import (
    Report,
    ModelMetadata,
    AdversarialScanRun,
    ActivationMeasurement,
    PipelineScan,
    StatisticalFinding,
)

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
# Severity weights used ONLY to aggregate the real per-finding severities
# into the transparent overall risk index (0-100).
_SEV_WEIGHT = {"CRITICAL": 1.0, "HIGH": 0.75, "MEDIUM": 0.5, "LOW": 0.25}

DISCLAIMER = (
    "NeuroFence detects anomalous activation behavior relative to a computed "
    "baseline. It does not mathematically prove the existence of a backdoor: "
    "statistical anomalies are evidence of potentially suspicious activation "
    "behavior, not proof. A definitive backdoor conclusion requires full, "
    "reproducible, white-box inspection of weights, training provenance and "
    "input behavior beyond the scope of activation statistics."
)


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _reports_dir() -> str:
    override = os.environ.get("NEUROFENCE_REPORTS_DIR")
    if override:
        return override
    cfg = get_config()
    return os.path.join(_project_root(), cfg["paths"]["outputs_reports"])


def _iso(dt) -> str:
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_size(size_bytes) -> str:
    if size_bytes is None:
        return "Not recorded"
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.2f} {unit}"
        value /= 1024.0
    return f"{size_bytes} bytes"


def _fmt_params(params) -> str:
    if params is None:
        return "Not recorded"
    return f"{params:,}"


# ---------------------------------------------------------------------------
# Real data collection
# ---------------------------------------------------------------------------

def _resolve_scan(session, scan_id=None, run_id=None):
    """
    Resolve (pipeline_scan | None, adversarial_run | None) from real rows.

    Precedence: explicit scan_id -> explicit run_id -> latest terminal
    pipeline scan -> latest completed adversarial run. Raises ValueError
    if an explicitly requested id does not exist.
    """
    pscan = None
    run = None

    if scan_id is not None:
        pscan = session.query(PipelineScan).filter(
            PipelineScan.scan_id == int(scan_id)).first()
        if pscan is None:
            raise ValueError(f"Unknown scan id: {scan_id}")
    elif run_id is None:
        pscan = (session.query(PipelineScan)
                 .filter(PipelineScan.status.in_(["COMPLETED", "FAILED", "CANCELLED"]))
                 .order_by(PipelineScan.scan_id.desc()).first())

    if run_id is not None:
        run = session.query(AdversarialScanRun).filter(
            AdversarialScanRun.run_id == int(run_id)).first()
        if run is None:
            raise ValueError(f"Unknown run id: {run_id}")
    elif pscan is not None and pscan.run_id is not None:
        run = session.query(AdversarialScanRun).filter(
            AdversarialScanRun.run_id == pscan.run_id).first()

    if run is None:
        run = (session.query(AdversarialScanRun)
               .filter(AdversarialScanRun.status == "completed")
               .order_by(AdversarialScanRun.run_id.desc()).first())

    if pscan is None and scan_id is None:
        pscan = (session.query(PipelineScan)
                 .order_by(PipelineScan.scan_id.desc()).first())
    return pscan, run


def _tiny_forensics() -> dict:
    """
    Real file forensics for the local tiny test model.

    Computes SHA-256 + size from the actual safetensors file and reads the
    real `config.json` (architecture, parameter count, format). No torch
    import, so this is safe inside the Qt desktop process.
    """
    from src.model_interface.tiny_test_model import (  # noqa: PLC0415
        config_path, safetensors_path,
    )
    out = {"name": "TinyTransformerLM", "architecture": None, "params": None,
           "size_bytes": None, "sha256": None, "format": None}

    cfg_path = config_path()
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            out["architecture"] = cfg.get("architecture")
            out["params"] = cfg.get("num_parameters")
            if cfg.get("model_type") == "tiny_transformer":
                out["format"] = "PyTorch safetensors"
        except Exception:  # noqa: BLE001 -- best-effort file forensics
            pass

    sf_path = safetensors_path()
    if os.path.exists(sf_path):
        try:
            out["size_bytes"] = os.path.getsize(sf_path)
            digest = hashlib.sha256()
            with open(sf_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    digest.update(chunk)
            out["sha256"] = digest.hexdigest()
        except Exception:  # noqa: BLE001 -- best-effort file forensics
            pass
    return out


def _model_forensics(session, model_name) -> dict:
    """Real model details: perses metadata if present, else live file forensics."""
    meta = session.query(ModelMetadata).order_by(
        ModelMetadata.metadata_id.desc()).first()
    if meta is not None and meta.file_name:
        base = {
            "name": meta.file_name,
            "architecture": meta.architecture,
            "params": meta.num_parameters,
            "size_bytes": meta.file_size_bytes,
            "sha256": meta.sha256_hash,
            "format": meta.model_type,
        }
        if meta.file_path and os.path.exists(meta.file_path):
            return base

    known = ("tinytestmodel", "tiny_test_model", "tinytransformerlm", "tiny")
    if model_name and str(model_name).lower().replace("_", "") in known:
        tiny = _tiny_forensics()
        tiny["name"] = str(model_name)
        return tiny

    if meta is not None and meta.file_name:
        return base
    return {"name": model_name, "architecture": None, "params": None,
            "size_bytes": None, "sha256": None, "format": None}


def _activation_summary(session, run_id):
    """Real per-layer activation statistics aggregated from measurements."""
    rows = (session.query(ActivationMeasurement)
            .filter(ActivationMeasurement.run_id == run_id).all())
    if not rows:
        return {
            "measurement_count": 0,
            "distinct_prompts": 0,
            "distinct_layers": 0,
            "layers": [],
            "averages": None,
        }
    by_layer: dict = {}
    prompts = set()
    for r in rows:
        prompts.add(r.prompt_id)
        agg = by_layer.setdefault(r.layer, {
            "count": 0, "mean": 0.0, "std": 0.0, "norm": 0.0, "active": 0.0,
        })
        agg["count"] += 1
        agg["mean"] += float(r.mean)
        agg["std"] += float(r.std)
        agg["norm"] += float(r.norm)
        agg["active"] += float(r.active_fraction)
    layers = []
    for name, agg in sorted(by_layer.items()):
        n = agg["count"]
        layers.append({
            "name": name,
            "count": n,
            "mean": agg["mean"] / n,
            "std": agg["std"] / n,
            "norm": agg["norm"] / n,
            "active_fraction": agg["active"] / n,
        })
    total = len(rows)
    averages = {
        "mean": round(sum(l["mean"] for l in layers) / len(layers), 4),
        "std": round(sum(l["std"] for l in layers) / len(layers), 4),
        "norm": round(sum(l["norm"] for l in layers) / len(layers), 4),
        "active_fraction": round(
            sum(l["active_fraction"] for l in layers) / len(layers), 4),
    } if layers else None
    return {
        "measurement_count": total,
        "distinct_prompts": len(prompts),
        "distinct_layers": len(layers),
        "layers": layers,
        "averages": averages,
    }


def _findings(session, run_id, limit=15):
    """Real statistical findings (top by anomaly score) + severity tally."""
    rows = (session.query(StatisticalFinding)
            .filter(StatisticalFinding.run_id == run_id)
            .order_by(StatisticalFinding.anomaly_score.desc())
            .all())
    all_rows = rows
    top = all_rows[:limit]
    sev = Counter(r.severity for r in all_rows)
    dist = {level: int(sev.get(level, 0)) for level in SEVERITY_ORDER}
    out = []
    for r in top:
        out.append({
            "finding_id": r.finding_id,
            "prompt_id": r.prompt_id or "",
            "category": r.category,
            "layer": r.layer,
            "feature": r.feature,
            "anomaly_score": round(float(r.anomaly_score), 1),
            "severity": r.severity,
            "z_score": round(float(r.z_score), 2) if r.z_score is not None else None,
            "confidence": round(float(r.confidence), 2) if r.confidence is not None else None,
            "explanation": r.explanation or "",
            "baseline_mean": round(float(r.baseline_mean), 4) if r.baseline_mean is not None else None,
            "observed_statistic": round(float(r.observed_statistic), 4) if r.observed_statistic is not None else None,
        })
    return {"findings": out, "total": len(all_rows), "severity_dist": dist}


def _overall_risk(dist) -> "float | None":
    """Weighted severity index over the real distribution; None if no findings."""
    total = sum(dist.values())
    if not total:
        return None
    weighted = sum(_SEV_WEIGHT[level] * dist[level] for level in SEVERITY_ORDER)
    return round(100.0 * weighted / total, 1)


def _analyst_summary(data: dict) -> str:
    """A summary paragraph written from the real numbers in `data`."""
    run = data.get("run") or {}
    scan = data.get("scan") or {}
    if not run and not scan:
        return ("No completed scan exists in the database yet. Generate a "
                "forensic report after running a NeuroFence scan pipeline run.")
    lines = []
    configured = run.get("num_prompts") or 0
    layers = data.get("layers_analyzed") or 0
    model_name = (data.get("model") or {}).get("name") or "the selected model"
    lines.append(
        f"Scan of {model_name} tested {data.get('inputs_tested') or 0} adversarial "
        f"inputs across {configured} configured inputs and {layers} layers "
        f"({data['activation']['measurement_count']} activation measurement records)."
    )
    total_f = data["findings_total"]
    if total_f:
        dist = data["severity_dist"]
        hi = dist.get("HIGH", 0) + dist.get("CRITICAL", 0)
        peak = data["peak_anomaly_score"]
        risk = data["overall_risk_score"]
        lines.append(
            f"{total_f} statistical findings were flagged, of which {hi} were "
            f"HIGH or CRITICAL; the peak anomaly score was "
            f"{peak if peak is not None else 'N/A'}/100 and the weighted overall "
            f"risk index is {risk if risk is not None else 'not computed'}/100. "
            "The highest-scoring (prompt, layer, feature) triples are listed in "
            "Section 14. Findings indicate potentially suspicious activation "
            "behavior; they are not proof of a backdoor."
        )
    elif data["activation"]["measurement_count"]:
        lines.append(
            "No feature exceeded the configured statistical thresholds, so no "
            "findings were recorded and no overall risk index is computed."
        )
    else:
        lines.append(
            "The run produced no activation measurements, so no statistical "
            "comparison against the baseline was possible."
        )
    return " ".join(lines)


def build_report_data(scan_id=None, run_id=None) -> dict:
    """
    Collect the real data behind a forensic report from SQLite.

    Args:
        scan_id: pipeline scan id (or None for the latest scan in the DB).
        run_id: adversarial run id (used when no pipeline scan is relevant).

    Returns a plain dict containing every value the 18 report sections need.
    """
    session = get_session()
    try:
        pscan, run = _resolve_scan(session, scan_id=scan_id, run_id=run_id)
        run_row = None
        if run is not None:
            run_row = {
                "run_id": run.run_id,
                "run_label": run.run_label,
                "status": run.status,
                "num_prompts": run.num_prompts,
                "max_seq_len": run.max_seq_len,
                "seed": run.seed,
                "layers_target": run.layer_count,
                "prompt_count": run.prompt_count,
                "measurement_count": run.measurement_count,
                "layer_count": run.layer_count,
                "created_at": _iso(run.created_at),
                "categories": json.loads(run.categories) if run.categories else [],
                "error": run.error,
            }
        scan_row = None
        if pscan is not None:
            scan_row = {
                "scan_id": pscan.scan_id,
                "status": pscan.status,
                "percentage": pscan.percentage,
                "model_key": pscan.model,
                "current_anomaly_score": pscan.current_anomaly_score,
                "findings_generated": pscan.findings_generated,
                "error": pscan.error,
                "created_at": _iso(pscan.created_at),
            }

        model_name = (run.model if run is not None else
                      (scan_row["model_key"] if scan_row else None))
        model = _model_forensics(session, model_name)

        activation = {"measurement_count": 0, "distinct_prompts": 0,
                      "distinct_layers": 0, "layers": [], "averages": None}
        findings = {"findings": [], "total": 0,
                    "severity_dist": {k: 0 for k in SEVERITY_ORDER}}
        if run is not None:
            activation = _activation_summary(session, run.run_id)
            findings = _findings(session, run.run_id)

        # Real scan configuration: the run's own settings + the current
        # statistical engine thresholds from config.
        from src.anomaly_detection.statistical_engine import (  # noqa: PLC0415
            StatisticalConfig,
        )
        stat_cfg = StatisticalConfig.from_settings().as_dict()
        scan_config = {
            "model": model.get("name") or model_name,
            "num_prompts": run_row["num_prompts"] if run_row else None,
            "max_seq_len": run_row["max_seq_len"] if run_row else None,
            "seed": run_row["seed"] if run_row else None,
            "categories": (run_row["categories"] if run_row else []),
            "layers_target": run_row["layers_target"] if run_row else None,
            "severity_cutoffs": stat_cfg["severity_cutoffs"],
            "z_score_min": stat_cfg["z_score_min"],
            "baseline_min_n": stat_cfg["baseline_min_n"],
            "correlation_min": stat_cfg["correlation_min"],
        }

        layers = [l["name"] for l in activation["layers"]]
        if not layers and run_row and run_row["layers_target"]:
            layers = [f"layer#{i + 1}" for i in range(run_row["layers_target"])]

        dist = findings["severity_dist"]
        return {
            "title": "NeuroFence",
            "generated_at": _iso(datetime.now(timezone.utc)),
            "has_data": run is not None or scan_row is not None,
            "scan": scan_row,
            "run": run_row,
            "generated_scan_id": scan_row["scan_id"] if scan_row else None,
            "model": model,
            "scan_config": scan_config,
            "inputs_tested": (run_row["prompt_count"] if run_row else None)
                             or (run_row["num_prompts"] if run_row else None)
                             or None,
            "inputs_configured": run_row["num_prompts"] if run_row else None,
            "layers_analyzed": (len(activation["layers"])
                                if activation["layers"] else
                                (run_row["layer_count"] if run_row else None)) or None,
            "layers": layers,
            "activation": activation,
            "findings": findings["findings"],
            "findings_total": findings["total"],
            "severity_dist": dist,
            "peak_anomaly_score": max((f["anomaly_score"] for f in findings["findings"]),
                                     default=None),
            "overall_risk_score": _overall_risk(dist),
            "analyst_summary": None,
            "limitations": DISCLAIMER,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# HTML rendering (the 18 required report sections)
# ---------------------------------------------------------------------------

def _css() -> str:
    return """
    body { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #1a1a1a; margin: 20px; }
    h1 { color: #1a237e; font-size: 22px; border-bottom: 3px solid #1a237e; padding-bottom: 4px; }
    h2 { color: #283593; font-size: 15px; border-bottom: 1px solid #ccc; padding-bottom: 3px; margin-top: 16px; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 10px; }
    th { background-color: #e8eaf6; border: 1px solid #aaa; padding: 4px 6px; text-align: left; font-weight: bold; }
    td { border: 1px solid #aaa; padding: 4px 6px; }
    .kv td:first-child { width: 38%; font-weight: bold; background-color: #f5f6fa; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-weight: bold; font-size: 10px; color: white; }
    .badge-low { background: #388e3c; }
    .badge-medium { background: #f9a825; color: #1a1a1a; }
    .badge-high { background: #e65100; }
    .badge-critical { background: #c62828; }
    .badge-none { background: #9e9e9e; }
    .hash { font-family: monospace; font-size: 9px; word-break: break-all; color: #555; }
    .risk-box { border: 2px solid #1a237e; padding: 8px 12px; margin: 10px 0; font-size: 14px; font-weight: bold; }
    .note { background: #fff3e0; border-left: 3px solid #e65100; padding: 6px 10px; margin: 8px 0; font-size: 10px; }
    .disclaimer { background: #fdecea; border-left: 3px solid #c62828; padding: 8px 10px; margin: 8px 0; font-size: 10px; }
    .footer { font-size: 9px; color: #777; border-top: 1px solid #ccc; margin-top: 16px; padding-top: 6px; }
    .bar-row td { border: none; padding: 1px 6px; }
    .bar { background: #3949ab; height: 8px; display: inline-block; }
    """


def _badge(level: str) -> str:
    key = str(level).lower() if level else "none"
    if key not in ("low", "medium", "high", "critical"):
        key = "none"
    return f'<span class="badge badge-{key}">{level if level else "N/A"}</span>'


def _kv_table(pairs) -> str:
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in pairs)
    return f'<table class="kv">{rows}</table>'


def _severity_dist_html(dist) -> str:
    total = sum(dist.values())
    lines = ["<table><tr><th>Severity</th><th>Count</th><th>Share</th></tr>"]
    if total == 0:
        lines.append("<tr><td>—</td><td>0</td><td>0%</td></tr>")
    for level in SEVERITY_ORDER:
        count = int(dist.get(level, 0))
        share = round(100 * count / total, 1) if total else 0.0
        lines.append(
            f"<tr><td>{_badge(level)}</td><td>{count}</td><td>{share}%</td></tr>"
        )
    lines.append("</table>")
    return "\n".join(lines)


def render_report_html(data: dict) -> str:
    """Render the 18-section forensic report as HTML from real `data`."""
    scan = data.get("scan") or {}
    run = data.get("run") or {}
    model = data.get("model") or {}
    cfg = data.get("scan_config") or {}
    act = data.get("activation") or {"layers": []}
    has_data = bool(data.get("has_data"))

    generated_info = _kv_table([
        ("Scan ID", f"#{scan.get('scan_id')}" if scan.get("scan_id") else "No pipeline scan"),
        ("Run ID", run.get("run_id") or "N/A"),
        ("Run label", run.get("run_label") or "N/A"),
        ("Pipeline status", scan.get("status") or "N/A"),
    ])

    timestamp = data["generated_at"]

    model_rows = []
    for label, value in [
        ("Model name", model.get("name") or (cfg.get("model") or "N/A")),
        ("Architecture", model.get("architecture") or "Not recorded"),
        ("Parameters", _fmt_params(model.get("params"))),
        ("File size", _fmt_size(model.get("size_bytes"))),
        ("Model format", model.get("format") or "Not recorded"),
    ]:
        model_rows.append((label, value))
    sha = model.get("sha256") or "Not recorded"
    model_html = _kv_table(model_rows) + (
        f'<p><b>SHA-256:</b> <span class="hash">{sha}</span></p>'
    )

    cats = cfg.get("categories") or []
    config_html = _kv_table([
        ("Model target", cfg.get("model") or "N/A"),
        ("Inputs configured", cfg.get("num_prompts") or 0),
        ("Max sequence length", cfg.get("max_seq_len") or "N/A"),
        ("Seed", cfg.get("seed") or "N/A"),
        ("Categories", ", ".join(cats) if cats else "N/A"),
        ("Layers target", cfg.get("layers_target") or "N/A"),
        ("Severity cutoffs (CRIT/HIGH/MED)", " / ".join(
            str(x) for x in (cfg.get("severity_cutoffs") or [])) or "N/A"),
        ("Min z-score", cfg.get("z_score_min")),
        ("Baseline min N", cfg.get("baseline_min_n")),
        ("Min correlation", cfg.get("correlation_min")),
    ])

    inputs_tested = data.get("inputs_tested")
    inputs_html = (
        f"<p><b>Inputs tested:</b> {inputs_tested if inputs_tested is not None else 'N/A'}"
        f" &mdash; from <b>{data.get('inputs_configured') or 0}</b> configured inputs."
        f"<br/>Measurement records: <b>{act.get('measurement_count', 0)}</b> across "
        f"<b>{act.get('distinct_prompts', 0)}</b> prompts.</p>"
    )

    layers_list = data.get("layers") or []
    if layers_list:
        layers_html = _kv_table(
            [("Layers analyzed", str(len(layers_list)))] +
            [(f"Layer {i + 1}", name) for i, name in enumerate(layers_list[:20])]
        )
    else:
        layers_html = "<p>No layer names were recorded for this scan.</p>"

    if act.get("averages"):
        avg = act["averages"]
        act_html_rows = [
            "<table><tr><th>Layer</th><th>N</th><th>Mean</th><th>Std</th>"
            "<th>Norm</th><th>Active frac</th></tr>",
        ]
        for l in act.get("layers", []):
            act_html_rows.append(
                f"<tr><td>{l['name']}</td><td>{l['count']}</td><td>{l['mean']:.4f}</td>"
                f"<td>{l['std']:.4f}</td><td>{l['norm']:.4f}</td>"
                f"<td>{l['active_fraction']:.4f}</td></tr>"
            )
        act_html_rows.append("</table>")
        act_html = (
            "".join(act_html_rows) +
            "<p><b>Averages across layers:</b> "
            f"mean {avg['mean']}, std {avg['std']}, norm {avg['norm']}, "
            f"active fraction {avg['active_fraction']}.</p>"
        )
    else:
        act_html = "<p>No activation measurements were recorded for this scan.</p>"

    findings = data.get("findings") or []
    if findings:
        f_rows = [
            "<table><tr><th>#</th><th>Severity</th><th>Score</th><th>Layer</th>"
            "<th>Feature</th><th>Prompt</th><th>z</th><th>Explanation</th></tr>",
        ]
        for i, f in enumerate(findings, start=1):
            prompt = f.get("prompt_id") or ""
            if len(prompt) > 24:
                prompt = prompt[:24] + "…"
            expl = f.get("explanation") or ""
            if len(expl) > 90:
                expl = expl[:90] + "…"
            f_rows.append(
                f"<tr><td>{i}</td><td>{_badge(f.get('severity'))}</td>"
                f"<td>{f.get('anomaly_score')}</td><td>{f.get('layer')}</td>"
                f"<td>{f.get('feature')}</td><td>{prompt}</td>"
                f"<td>{f.get('z_score') if f.get('z_score') is not None else '—'}</td>"
                f"<td>{expl}</td></tr>"
            )
        f_rows.append("</table>")
        findings_html = "".join(f_rows)
    else:
        findings_html = (
            "<p>No statistical findings were recorded."
            + ("" if has_data else " Generate a scan before producing a report.")
            + "</p>"
        )

    dist_html = _severity_dist_html(data.get("severity_dist") or {})

    risk = data.get("overall_risk_score")
    if risk is not None:
        color = "#c62828" if risk >= 75 else "#e65100" if risk >= 50 else "#388e3c"
        risk_txt = f"OVERALL RISK INDEX: {risk}/100"
        risk_html = (f'<div class="risk-box" style="color:{color};">{risk_txt}</div>'
                     + (f"<p>Peak anomaly score: <b>{data['peak_anomaly_score']}/100</b>. "
                        f"The index is the severity-weighted mean of the "
                        f"{data['findings_total']} recorded findings.</p>"
                        if data.get("peak_anomaly_score") is not None else
                        "<p>The index is the severity-weighted mean of all recorded findings.</p>"))
    else:
        risk_html = ('<div class="risk-box" style="color:#616161;">'
                     "OVERALL RISK INDEX: not computed (no findings)</div>")

    summary = data.get("analyst_summary") or _analyst_summary(data)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{data['title']} Forensic Report</title>
<style>{_css()}</style></head><body>
<h1>{data['title']} — AI Security Forensic Report</h1>

<h2>2. Scan Identification</h2>
{generated_info}

<h2>3. Timestamp</h2>
{_kv_table([
    ("Report generated at (UTC)", timestamp),
    ("Scan started at (UTC)", run.get("created_at") or scan.get("created_at") or "N/A"),
])}

<h2>4. Model Name</h2>
<p><b>{model.get('name') or cfg.get('model') or 'N/A'}</b></p>

<h2>5. Model Architecture</h2>
<p>{model.get('architecture') or 'Not recorded'}</p>

<h2>6. Parameter Information</h2>
<p>{_fmt_params(model.get('params'))}</p>

<h2>7. File Size</h2>
<p>{_fmt_size(model.get('size_bytes'))}</p>

<h2>8. SHA-256 Hash</h2>
<p class="hash">{sha}</p>

<h2>9. Model Format</h2>
<p>{model.get('format') or 'Not recorded'}</p>

<h2>10. Scan Configuration</h2>
{config_html}

<h2>11. Number of Inputs Tested</h2>
{inputs_html}

<h2>12. Layers Analyzed</h2>
{layers_html}

<h2>13. Activation Statistics Summary</h2>
{act_html}

<h2>14. Findings</h2>
{findings_html}

<h2>15. Severity Distribution</h2>
{dist_html}

<h2>16. Overall Risk Score</h2>
{risk_html}

<h2>17. Analyst Summary</h2>
<p>{summary}</p>

<h2>18. Scientific Limitations</h2>
<div class="disclaimer">{data['limitations']}</div>
<div class="note">All values in this report were read from the real NeuroFence
backend database (adversarial scan runs, activation measurements and statistical
findings) or computed live from the model file at generation time. No values
are simulated or fabricated.</div>

<div class="footer">
NeuroFence AI Security Forensic Report -- generated offline by NeuroFence.
NeuroFence detects anomalous activation behavior; it does not mathematically
prove the presence of a neural backdoor.
</div>
</body></html>"""


# ---------------------------------------------------------------------------
# PDF rendering + persistence
# ---------------------------------------------------------------------------

def _write_pdf(html: str, out_path: str) -> str:
    """Render HTML to PDF via QPrinter. Returns the real path on disk."""
    try:
        from PyQt5.QtWidgets import QApplication  # noqa: PLC0415
        from PyQt5.QtGui import QTextDocument  # noqa: PLC0415
        from PyQt5.QtPrintSupport import QPrinter  # noqa: PLC0415

        app = QApplication.instance() or QApplication([])
        doc = QTextDocument()
        doc.setHtml(html)
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(out_path)
        doc.print_(printer)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
        raise RuntimeError("PDF backend produced an empty file")
    except Exception as exc:  # noqa: BLE001 -- documented HTML fallback
        print(f"PDF render failed ({exc}); writing HTML fallback.")
        fallback = out_path
        if fallback.endswith(".pdf"):
            fallback = fallback[:-4] + ".html"
        with open(fallback, "w", encoding="utf-8") as f:
            f.write(html)
        return fallback


def generate_forensic_report(scan_id=None, run_id=None, output_path=None) -> str:
    """
    Build a real forensic report from backend data and write it to disk.

    Collects real data, renders the 18-section report as PDF (HTML fallback),
    and logs a `Report` metadata row in SQLite.
    """
    data = build_report_data(scan_id=scan_id, run_id=run_id)

    reports_dir = _reports_dir()
    os.makedirs(reports_dir, exist_ok=True)
    if output_path is None:
        tag = f"scan{scan_id}" if scan_id is not None else f"run{run_id}" if run_id else "latest"
        filename = f"neurofence_report_{tag}_{uuid.uuid4().hex[:6]}.pdf"
        output_path = os.path.join(reports_dir, filename)

    html = render_report_html(data)
    final_path = _write_pdf(html, output_path)

    summary_json = json.dumps({
        "scan_id": data.get("generated_scan_id"),
        "run_id": (data.get("run") or {}).get("run_id"),
        "model": (data.get("model") or {}).get("name"),
        "findings_total": data.get("findings_total", 0),
        "severity_dist": data.get("severity_dist", {}),
        "overall_risk_score": data.get("overall_risk_score"),
        "peak_anomaly_score": data.get("peak_anomaly_score"),
    })
    session = get_session()
    try:
        session.add(Report(
            run_id=str((data.get("run") or {}).get("run_id") or "") or uuid.uuid4().hex[:8],
            scan_id=data.get("generated_scan_id"),
            format="pdf" if final_path.endswith(".pdf") else "html",
            summary=summary_json,
            file_path=final_path,
        ))
        session.commit()
    finally:
        session.close()
    print(f"Forensic report generated: {final_path}")
    return final_path


# ---------------------------------------------------------------------------
# Listing / details for the desktop UI
# ---------------------------------------------------------------------------

def _summary_dict(row) -> dict:
    try:
        return json.loads(row.summary) if row.summary else {}
    except Exception:  # noqa: BLE001 -- legacy rows may hold arbitrary text
        return {}


def list_reports(limit: int = 50) -> list:
    """Real report metadata rows, newest first, with parsed summaries."""
    session = get_session()
    try:
        rows = session.query(Report).order_by(
            Report.report_id.desc()).limit(limit).all()
        out = []
        for r in rows:
            summ = _summary_dict(r)
            out.append({
                "report_id": r.report_id,
                "scan_id": r.scan_id,
                "run_id": summ.get("run_id") or r.run_id,
                "format": r.format,
                "model": summ.get("model"),
                "findings_total": summ.get("findings_total"),
                "overall_risk_score": summ.get("overall_risk_score"),
                "severity_dist": summ.get("severity_dist", {}),
                "file_path": r.file_path,
                "exists": bool(r.file_path and os.path.exists(r.file_path)),
                "created_at": _iso(r.created_at),
            })
        return out
    finally:
        session.close()


def report_detail(report_id: int) -> dict:
    """Real metadata for one report row (None if it does not exist)."""
    session = get_session()
    try:
        row = session.query(Report).filter(
            Report.report_id == int(report_id)).first()
        if row is None:
            return None
        summ = _summary_dict(row)
        return {
            "report_id": row.report_id,
            "scan_id": row.scan_id,
            "run_id": summ.get("run_id") or row.run_id,
            "format": row.format,
            "model": summ.get("model"),
            "findings_total": summ.get("findings_total"),
            "overall_risk_score": summ.get("overall_risk_score"),
            "severity_dist": summ.get("severity_dist", {}),
            "file_path": row.file_path,
            "exists": bool(row.file_path and os.path.exists(row.file_path)),
            "created_at": _iso(row.created_at),
        }
    finally:
        session.close()


def report_sources() -> list:
    """
    The scans a user can generate a report for, newest first.

    Combines pipeline scans (scan_id + real status) with completed
    adversarial runs (run_id) that have no pipeline scan of their own.
    """
    session = get_session()
    try:
        pscans = session.query(PipelineScan).order_by(
            PipelineScan.scan_id.desc()).all()
        used_run_ids = {p.run_id for p in pscans if p.run_id is not None}
        runs = (session.query(AdversarialScanRun)
                .order_by(AdversarialScanRun.run_id.desc()).all())
        extra_runs = [r for r in runs if r.status == "completed"
                      and r.run_id not in used_run_ids]
    finally:
        session.close()

    sources = []
    for p in pscans:
        sources.append({
            "kind": "scan",
            "id": p.scan_id,
            "label": f"{p.model or 'tiny'} / {p.status}",
            "created_at": _iso(p.created_at),
            "findings": p.findings_generated,
        })
    for r in extra_runs:
        sources.append({
            "kind": "run",
            "id": r.run_id,
            "label": f"{r.model or 'model'} / COMPLETED",
            "created_at": _iso(r.created_at),
            "findings": None,
        })
    return sources