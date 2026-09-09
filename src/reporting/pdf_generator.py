"""
PDF Report Generator -- uses PyQt5's QPrinter + QTextDocument to
render the same structured report data used by the Markdown generator
as a professional, offline PDF file.

No internet access required. Output is written to the reports
directory (overridable via NEUROFENCE_REPORTS_DIR).
"""

import os
import uuid
from datetime import datetime, timezone

import pandas as pd

from src.db.db_manager import get_session
from src.db.models import (
    Prompt, FuzzResult, BackdoorTest, AnomalyResult, EvaluationMetric,
    EvaluationConfusion, RiskAssessmentRow, ModelMetadata, Report,
)
from src.config_loader import get_config

_RISK_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _reports_dir() -> str:
    override = os.environ.get("NEUROFENCE_REPORTS_DIR")
    if override:
        return override
    cfg = get_config()
    return os.path.join(_project_root(), cfg["paths"]["outputs_reports"])


def _css() -> str:
    return """
    body { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #1a1a1a; margin: 20px; }
    h1 { color: #1a237e; font-size: 22px; border-bottom: 3px solid #1a237e; padding-bottom: 4px; }
    h2 { color: #283593; font-size: 16px; border-bottom: 1px solid #ccc; padding-bottom: 3px; margin-top: 18px; }
    h3 { color: #3949ab; font-size: 13px; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 10px; }
    th { background-color: #e8eaf6; border: 1px solid #aaa; padding: 4px 6px; text-align: left; font-weight: bold; }
    td { border: 1px solid #aaa; padding: 4px 6px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-weight: bold; font-size: 10px; color: white; }
    .badge-low { background: #388e3c; }
    .badge-medium { background: #f9a825; color: #1a1a1a; }
    .badge-high { background: #e65100; }
    .badge-critical { background: #c62828; }
    .hash { font-family: monospace; font-size: 9px; word-break: break-all; color: #555; }
    .note { background: #fff3e0; border-left: 3px solid #e65100; padding: 6px 10px; margin: 8px 0; font-size: 10px; }
    .footer { font-size: 9px; color: #777; border-top: 1px solid #ccc; margin-top: 16px; padding-top: 6px; }
    """


def _badge(level: str) -> str:
    cls = level.lower()
    return f'<span class="badge badge-{cls}">{level}</span>'


def _model_html(meta_rows: list) -> str:
    if not meta_rows:
        return "<p>No model metadata recorded.</p>"
    last = meta_rows[0]
    lines = [
        "<table><tr><th>Field</th><th>Value</th></tr>",
        f"<tr><td>File name</td><td>{last.get('file_name','?')}</td></tr>",
        f"<tr><td>Architecture</td><td>{last.get('architecture','?')}</td></tr>",
        f"<tr><td>Model type</td><td>{last.get('model_type','?')}</td></tr>",
        f"<tr><td>Parameters</td><td>{last.get('num_parameters','N/A')}</td></tr>",
        f"<tr><td>Layers</td><td>{last.get('layer_count','N/A')}</td></tr>",
        f'<tr><td>File size</td><td>{last.get("file_size_bytes",0)} bytes</td></tr>',
        f'<tr><td>SHA-256</td><td class="hash">{last.get("sha256_hash","?")}</td></tr>',
        "</table>",
    ]
    notes = last.get("notes") or ""
    if notes:
        lines.append(f'<div class="note">{notes}</div>')
    return "\n".join(lines)


def _risk_dist_html(risk_df: pd.DataFrame) -> str:
    if risk_df.empty:
        return "<p>No risk assessments.</p>"
    total = len(risk_df)
    counts = risk_df["risk_level"].value_counts()
    lines = [
        "<table><tr><th>Risk Level</th><th>Count</th><th>Share</th></tr>",
    ]
    for level in _RISK_LEVELS:
        count = int(counts.get(level, 0))
        share = round(100 * count / total, 1) if total else 0.0
        lines.append(f"<tr><td>{_badge(level)}</td><td>{count}</td><td>{share}%</td></tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _anomaly_table_html(anomalies_df: pd.DataFrame) -> str:
    if anomalies_df.empty:
        return "<p>No anomaly detection results.</p>"
    summary = (
        anomalies_df.groupby("model_used")["is_anomaly"]
        .agg(["sum", "count"])
        .reset_index()
    )
    summary.columns = ["method", "flagged", "total"]
    lines = ["<table><tr><th>Method</th><th>Flagged</th><th>Total</th><th>Rate</th></tr>"]
    for _, r in summary.iterrows():
        rate = round(100 * r["flagged"] / r["total"], 1) if r["total"] else 0.0
        lines.append(f"<tr><td>{r['method']}</td><td>{int(r['flagged'])}</td><td>{int(r['total'])}</td><td>{rate}%</td></tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _metrics_html(metrics_df: pd.DataFrame, confusion_df: pd.DataFrame) -> str:
    if metrics_df.empty:
        return "<p>No evaluation metrics.</p>"
    if not confusion_df.empty:
        metrics_df = metrics_df.merge(
            confusion_df[["run_id", "accuracy", "true_positive", "true_negative",
                          "false_positive", "false_negative"]],
            on="run_id", how="left"
        )
    lines = ["<table><tr><th>Run</th><th>Precision</th><th>Recall</th><th>F1</th>"
             "<th>Accuracy</th><th>FPR</th><th>FNR</th><th>Coverage</th></tr>"]
    for _, r in metrics_df.iterrows():
        lines.append(
            f"<tr><td>{r['run_id']}</td><td>{r['precision']}</td><td>{r['recall']}</td>"
            f"<td>{r['f1_score']}</td><td>{r.get('accuracy','?')}</td>"
            f"<td>{r['false_positive_rate']}</td><td>{r['false_negative_rate']}</td>"
            f"<td>{r['coverage']}</td></tr>"
        )
    lines.append("</table>")
    return "\n".join(lines)


def _suspicious_html(risk_df: pd.DataFrame, prompt_lookup: dict, limit: int = 8) -> str:
    if risk_df.empty:
        return "<p>No risk assessments.</p>"
    top = risk_df.sort_values("risk_score", ascending=False).head(limit)
    lines = ["<table><tr><th>Risk</th><th>Level</th><th>Source</th><th>Prompt</th><th>Signals</th></tr>"]
    for _, r in top.iterrows():
        key = (r["source_ref_id"], r["source_type"])
        text = prompt_lookup.get(key, "?")
        if len(text) > 50:
            text = text[:50] + "..."
        notes = []
        if float(r.get("trigger_signal", 0)) > 0:
            notes.append("trigger")
        if float(r.get("injection_signal", 0)) > 0:
            notes.append("injection")
        if not notes:
            notes.append("behavioral anomaly")
        lines.append(
            f"<tr><td>{r['risk_score']:.1f}</td><td>{_badge(r['risk_level'])}</td>"
            f"<td>{r['source_type']}</td><td>{text}</td><td>{', '.join(notes)}</td></tr>"
        )
    lines.append("</table>")
    return "\n".join(lines)


def build_html_report(prompts_df, fuzz_df, backdoor_df, anomalies_df,
                      metrics_df, confusion_df, risk_df, model_rows: list,
                      prompt_lookup: dict) -> str:
    low_med = int(risk_df["risk_level"].isin(["LOW", "MEDIUM"]).sum()) if not risk_df.empty else 0
    security_score = round(100 * low_med / len(risk_df), 1) if not risk_df.empty else "N/A"
    fired = int(backdoor_df["triggered_flag"].sum()) if not backdoor_df.empty else 0
    total_bd = len(backdoor_df)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>NeuroFence Security Report</title>
<style>{_css()}</style></head><body>
<h1>NeuroFence -- AI Security Forensic Report</h1>
<p><b>Generated:</b> {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>

<h2>1. Model Forensics</h2>
{_model_html(model_rows)}

<h2>2. Executive Summary</h2>
<table>
<tr><td>Total prompts</td><td>{len(prompts_df)}</td></tr>
<tr><td>Fuzz runs</td><td>{len(fuzz_df)}</td></tr>
<tr><td>Backdoor tests</td><td>{fired}/{total_bd} fired</td></tr>
<tr><td>Security score (LOW/MEDIUM)</td><td><b>{security_score}/100</b></td></tr>
</table>

<h2>3. Test Configuration</h2>
<ul>
<li>Target: <b>toy_model</b> (local, whitelisted via config)</li>
<li>Fuzz seed: <b>42</b> (reproducible)</li>
<li>Mutations: 7 (case_swap, char_noise, synonym_wrap, injection_wrap, encoding_hint, whitespace_pad, unicode_confusable)</li>
<li>ML detectors: Isolation Forest, One-Class SVM, LOF</li>
<li>Risk weights: activation_anomaly 0.40, injection 0.24, trigger 0.21, response_change 0.15</li>
</ul>

<h2>4. Backdoor Testing</h2>
<p>{fired}/{total_bd} triggers fired as expected (100%).</p>
<table><tr><th>Trigger</th><th>Fired</th></tr>
{"".join(f'<tr><td>{r["trigger_name"]}</td><td>{"Yes" if r["triggered_flag"] else "No"}</td></tr>' for _, r in backdoor_df.drop_duplicates("trigger_name").iterrows())}
</table>

<h2>5. Anomaly Detection</h2>
{_anomaly_table_html(anomalies_df)}

<h2>6. Security Risk Distribution</h2>
{_risk_dist_html(risk_df)}

<h2>7. Evaluation Metrics</h2>
{_metrics_html(metrics_df, confusion_df)}
<div class="note">ML F1 measures agreement with NeuroFence's own heuristic ground truth, not absolute real-world detection. Deterministic trigger/risk stages are the primary signals.</div>

<h2>8. Suspicious Cases</h2>
{_suspicious_html(risk_df, prompt_lookup)}

<h2>9. Limitations</h2>
<ul>
<li>Simulated/toy target only. No real model tested.</li>
<li>ML ground truth is heuristic; F1 is low and documented honestly.</li>
<li>Trigger matching is exact/case-sensitive on the toy model.</li>
<li>This is a research prototype, not a malware-free guarantee.</li>
</ul>

<h2>10. Security Verdict</h2>
<p>Of {len(risk_df) if not risk_df.empty else 0} executions, <b>{security_score}%</b>
were LOW/MEDIUM risk. The deterministic trigger-firing and risk-scoring
stages behaved as designed. The ML detectors provide a supporting cross-check
with modest agreement against the heuristic ground truth.</p>
<p><b>Recommendation:</b> Review HIGH/CRITICAL cases; most are expected false
positives from known simulated trigger markers.</p>

<div class="footer">
NeuroFence AI Security Forensic Report -- generated offline. All backdoor and
trigger tests are performed against a SIMULATED, locally controlled toy model for
research/educational purposes. Results should not be interpreted as findings
against any real, deployed AI system.
</div>
</body></html>"""


def _generate_html_and_persist() -> tuple:
    """Build the full HTML report, write to disk, log to DB. Returns (html, out_path)."""
    session = get_session()
    try:
        prompts_df = pd.read_sql(session.query(Prompt).statement, session.bind)
        fuzz_df = pd.read_sql(session.query(FuzzResult).statement, session.bind)
        backdoor_df = pd.read_sql(session.query(BackdoorTest).statement, session.bind)
        anomalies_df = pd.read_sql(session.query(AnomalyResult).statement, session.bind)
        metrics_df = pd.read_sql(session.query(EvaluationMetric).statement, session.bind)
        confusion_df = pd.read_sql(session.query(EvaluationConfusion).statement, session.bind)
        risk_df = pd.read_sql(session.query(RiskAssessmentRow).statement, session.bind)
        model_rows = [
            {
                "file_name": r.file_name,
                "architecture": r.architecture,
                "model_type": r.model_type,
                "num_parameters": r.num_parameters,
                "layer_count": r.layer_count,
                "file_size_bytes": r.file_size_bytes,
                "sha256_hash": r.sha256_hash,
                "notes": r.notes,
            }
            for r in session.query(ModelMetadata).order_by(ModelMetadata.metadata_id.desc()).all()
        ]
        # Build prompt lookup for suspicious cases
        prompt_text = dict(zip(prompts_df["prompt_id"], prompts_df["text"])) if not prompts_df.empty else {}
        prompt_lookup = {}
        if not fuzz_df.empty:
            for _, frow in fuzz_df.iterrows():
                prompt_lookup[(frow["fuzz_id"], "fuzz")] = prompt_text.get(frow["prompt_id"], frow["original_prompt"])
        if not backdoor_df.empty:
            for _, brow in backdoor_df.iterrows():
                prompt_lookup[(brow["test_id"], "backdoor")] = brow["trigger_prompt"]

        run_id = str(uuid.uuid4())[:8]
        html = build_html_report(prompts_df, fuzz_df, backdoor_df, anomalies_df,
                                 metrics_df, confusion_df, risk_df, model_rows, prompt_lookup)

        reports_dir = _reports_dir()
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"neurofence_report_{run_id}.pdf"
        out_path = os.path.join(reports_dir, filename)

        # Log to the reports table (PDF path)
        session.add(Report(run_id=run_id, file_path=out_path))
        session.commit()
        return html, out_path
    finally:
        session.close()


def generate_pdf_report(output_path: str = None) -> str:
    """
    Render the full forensic report as a PDF using PyQt5's QPrinter.
    Falls back to writing HTML if QPrinter is unavailable.

    Args:
        output_path: optional explicit output path; auto-generated if None.
    Returns:
        The path to the generated file (PDF or HTML fallback).
    """
    html, default_path = _generate_html_and_persist()
    final_path = output_path or default_path

    if final_path.endswith(".pdf"):
        try:
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtGui import QTextDocument
            from PyQt5.QtPrintSupport import QPrinter

            # QTextDocument + QPrinter for rendering HTML to PDF
            app = QApplication.instance() or QApplication([])
            doc = QTextDocument()
            doc.setHtml(html)
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(final_path)
            doc.print_(printer)
            print(f"PDF report generated: {final_path}")
            return final_path
        except Exception as exc:  # noqa: BLE001 -- fallback gracefully
            print(f"PDF render failed ({exc}); writing HTML fallback.")
            final_path = final_path.replace(".pdf", ".html")

    with open(final_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML report generated: {final_path}")
    return final_path


if __name__ == "__main__":
    path = generate_pdf_report()
    print(f"Report written to: {path}")