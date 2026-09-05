"""
NeuroFence -- desktop data access layer.

Reads real values from the SQLite database for the dashboard. This keeps
backend/DB logic out of the UI widgets (which only render). No data is
fabricated or hard-coded here.
"""

from collections import Counter, defaultdict
from datetime import datetime, date
from typing import List, Dict, Optional

from src.db.db_manager import get_session
from src.db.models import (
    Prompt, FuzzResult, BackdoorTest, AnomalyResult, EvaluationMetric,
    EvaluationConfusion, RiskAssessmentRow, ModelMetadata, Report,
    PipelineScan, StatisticalFinding, ActivationMeasurement,
)
from src.reporting.report_builder import _build_prompt_lookup


_SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def dashboard_stats() -> Dict:
    """
    Real, pipeline-era aggregates for the Dashboard page.

    Every value is derived from live database rows (model registry,
    pipeline scan runs, statistical findings, activation measurements,
    reports). No statistics are fabricated: if nothing has been scanned,
    the relevant counters are zero / None.
    """
    session = get_session()
    try:
        model_rows = session.query(ModelMetadata).all()
        scan_rows = session.query(PipelineScan).all()
        stat_rows = session.query(StatisticalFinding).all()
        risk_rows = session.query(RiskAssessmentRow).all()
        measurement_rows = session.query(ActivationMeasurement).all()
        report_count = session.query(Report).count()
    finally:
        session.close()

    total_models = len(model_rows)
    scanned_models = sum(
        1 for m in model_rows
        if (m.status == "scanned") or m.scanned_at is not None
    )

    stat_count = len(stat_rows)
    risk_count = len(risk_rows)

    suspicious_models = {
        f.model for f in stat_rows
        if f.severity in ("HIGH", "CRITICAL") and f.model
    }

    severity_dist = {level: 0 for level in _SEVERITY_ORDER}
    for f in stat_rows:
        severity_dist[f.severity] = severity_dist.get(f.severity, 0) + 1

    scores = [f.anomaly_score for f in stat_rows if f.anomaly_score is not None]
    avg_risk = round(sum(scores) / len(scores), 1) if scores else None

    overall_level = "NO DATA"
    if severity_dist["CRITICAL"] or severity_dist["HIGH"] or \
            severity_dist["MEDIUM"] or severity_dist["LOW"]:
        for level in _SEVERITY_ORDER:
            if severity_dist[level]:
                overall_level = level
                break

    recent_scans = [
        {
            "scan_id": r.scan_id,
            "status": r.status,
            "model": r.model,
            "percentage": r.percentage or 0.0,
            "total_prompts": r.total_prompts or 0,
            "prompts_processed": r.prompts_processed or 0,
            "layers_analyzed": r.layers_analyzed or 0,
            "findings_generated": r.findings_generated or 0,
            "current_anomaly_score": r.current_anomaly_score,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in sorted(scan_rows, key=lambda r: r.scan_id, reverse=True)[:6]
    ]

    recent_findings = [
        {
            "finding_id": f.finding_id,
            "severity": f.severity,
            "layer": f.layer,
            "feature": f.feature,
            "category": f.category,
            "model": f.model,
            "anomaly_score": f.anomaly_score,
            "z_score": f.z_score,
            "prompt_id": f.prompt_id,
            "explanation": f.explanation,
        }
        for f in sorted(stat_rows, key=lambda f: f.finding_id, reverse=True)[:8]
    ]

    # Activation anomaly overview: real per-category aggregates.
    by_cat = {}
    for m in measurement_rows:
        cat = m.category or "unknown"
        acc = by_cat.setdefault(cat, {
            "category": cat,
            "measurements": 0,
            "mean": 0.0,
            "std": 0.0,
            "norm": 0.0,
            "active_fraction": 0.0,
        })
        acc["measurements"] += 1
        acc["mean"] += (m.mean or 0.0)
        acc["std"] += (m.std or 0.0)
        acc["norm"] += (m.norm or 0.0)
        acc["active_fraction"] += (m.active_fraction or 0.0)
    for acc in by_cat.values():
        n = acc["measurements"]
        acc["mean"] = round(acc["mean"] / n, 4) if n else 0.0
        acc["std"] = round(acc["std"] / n, 4) if n else 0.0
        acc["norm"] = round(acc["norm"] / n, 4) if n else 0.0
        acc["active_fraction"] = round(acc["active_fraction"] / n, 4) if n else 0.0
        acc["suspicious"] = sum(
            1 for f in stat_rows
            if f.category == cat and f.severity in ("HIGH", "CRITICAL")
        )
    activation_overview = sorted(
        by_cat.values(), key=lambda x: x["measurements"], reverse=True
    )

    active_scans = sum(1 for r in scan_rows if r.status not in
                       frozenset({"COMPLETED", "FAILED", "CANCELLED"}))

    today = date.today().isoformat()
    scanned_today = sum(
        1 for r in scan_rows
        if r.created_at and r.created_at.isoformat().startswith(today)
    )

    statuses = {m.status or "imported" for m in model_rows}
    quarantined_models = sum(1 for s in statuses if s == "quarantined")
    safe_to_deploy = sum(1 for s in statuses if s in ("approved",))

    return {
        "total_models": total_models,
        "scanned_models": scanned_models,
        "suspicious_models": len(suspicious_models),
        "total_findings": stat_count + risk_count,
        "statistical_findings": stat_count,
        "risk_findings": risk_count,
        "average_risk_score": avg_risk,
        "severity_distribution": severity_dist,
        "overall_level": overall_level,
        "reports": report_count,
        "active_scans": active_scans,
        "scanned_today": scanned_today,
        "quarantined_models": quarantined_models,
        "safe_to_deploy": safe_to_deploy,
        "recent_scans": recent_scans,
        "recent_findings": recent_findings,
        "activation_overview": activation_overview,
    }


def overview_stats() -> Dict:
    """Aggregate the top-level KPI values for the Overview page."""
    session = get_session()
    try:
        prompt_count = session.query(Prompt).count()
        fuzz_count = session.query(FuzzResult).count()
        bd_rows = session.query(BackdoorTest).all()
        anomaly_rows = session.query(AnomalyResult).all()
        risk_rows = session.query(RiskAssessmentRow).all()
        metric_rows = session.query(EvaluationMetric).all()
        confusion_rows = session.query(EvaluationConfusion).all()
        model_row = session.query(ModelMetadata).order_by(
            ModelMetadata.metadata_id.desc()
        ).first()
    finally:
        session.close()

    fired = sum(1 for r in bd_rows if r.triggered_flag)
    flagged = sum(1 for r in anomaly_rows if r.is_anomaly)
    total_bd = len(bd_rows)

    # Risk distribution
    counts = Counter(str(r.risk_level) for r in risk_rows)
    risk_dist = {
        "LOW": counts.get("LOW", 0),
        "MEDIUM": counts.get("MEDIUM", 0),
        "HIGH": counts.get("HIGH", 0),
        "CRITICAL": counts.get("CRITICAL", 0),
    }
    total_risk = sum(risk_dist.values())

    # Security score = share of LOW/MEDIUM
    security_score = None
    if total_risk:
        low_med = risk_dist["LOW"] + risk_dist["MEDIUM"]
        security_score = round(100 * low_med / total_risk, 1)

    # Overall risk level = worst present
    overall_level = "NO DATA"
    if total_risk:
        for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if risk_dist[level]:
                overall_level = level
                break

    # ML metrics averaged across evaluation runs
    f1 = None
    accuracy = None
    if metric_rows:
        f1s = [m.f1_score for m in metric_rows if m.f1_score is not None]
        if f1s:
            f1 = round(sum(f1s) / len(f1s), 3)
    if confusion_rows:
        accs = [c.accuracy for c in confusion_rows if c.accuracy is not None]
        if accs:
            accuracy = round(sum(accs) / len(accs), 3)

    model = None
    if model_row:
        model = {
            "file_name": model_row.file_name,
            "model_type": model_row.model_type,
            "architecture": model_row.architecture,
            "sha256": model_row.sha256_hash,
            "size": model_row.file_size_bytes,
            "params": model_row.num_parameters,
            "layers": model_row.layer_count,
            "supported": model_row.supported,
        }

    return {
        "prompts": prompt_count,
        "fuzz": fuzz_count,
        "backdoor_fired": fired,
        "backdoor_total": total_bd,
        "anomalies": flagged,
        "risk_dist": risk_dist,
        "total_risk": total_risk,
        "security_score": security_score,
        "overall_level": overall_level,
        "f1": f1,
        "accuracy": accuracy,
        "model": model,
    }


def findings(count: int = 20, only_high: bool = False) -> List[Dict]:
    """Top-risk real findings for the Findings / Overview pages."""
    session = get_session()
    try:
        lookup = _build_prompt_lookup(session)
        risk_rows = session.query(RiskAssessmentRow).all()
    finally:
        session.close()

    rows = sorted(risk_rows, key=lambda r: r.risk_score, reverse=True)
    if only_high:
        rows = [r for r in rows if r.risk_level in ("HIGH", "CRITICAL")]
    rows = rows[:count]
    out = []
    for r in rows:
        signals = []
        if float(r.trigger_signal) > 0:
            signals.append("trigger")
        if float(r.injection_signal) > 0:
            signals.append("injection")
        if float(r.response_change) > 0:
            signals.append("response-change")
        if not signals:
            signals.append("activation-anomaly")
        out.append({
            "risk_score": round(r.risk_score, 1),
            "risk_level": r.risk_level,
            "source_ref_id": r.source_ref_id,
            "source_type": r.source_type,
            "prompt": lookup.get((r.source_ref_id, r.source_type), "?"),
            "trigger_signal": r.trigger_signal,
            "injection_signal": r.injection_signal,
            "anomaly_signal": r.activation_anomaly,
            "response_change": r.response_change,
            "signals": signals,
        })
    return out


def risk_summary() -> Dict:
    """Risk distribution + counts used by the Reports page."""
    stats = overview_stats()
    return {
        "risk_dist": stats["risk_dist"],
        "total_risk": stats["total_risk"],
        "security_score": stats["security_score"],
        "overall_level": stats["overall_level"],
        "suspicious": stats["risk_dist"]["HIGH"] + stats["risk_dist"]["CRITICAL"],
    }


# ---------------------------------------------------------------------------
# SOC dashboard aggregates (all real, DB-derived -- never fabricated)
# ---------------------------------------------------------------------------

def investigation_stats() -> Dict:
    """The five SOC summary-card values on the Dashboard."""
    session = get_session()
    try:
        scans = session.query(PipelineScan).all()
        stat_count = session.query(StatisticalFinding).count()
        risk_count = session.query(RiskAssessmentRow).count()
        model_count = session.query(ModelMetadata).count()
        report_count = session.query(Report).count()
    finally:
        session.close()
    terminal = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
    completed = sum(1 for r in scans if r.status == "COMPLETED")
    active = sum(1 for r in scans if r.status not in terminal)
    return {
        "active_investigations": active,
        "models_registered": model_count,
        "scans_completed": completed,
        "threat_findings": stat_count + risk_count,
        "reports_generated": report_count,
    }


_SEVERITY_WEIGHTS = {"CRITICAL": 1.0, "HIGH": 0.72, "MEDIUM": 0.45, "LOW": 0.18}


def risk_overview() -> Dict:
    """
    Overall risk score (0-100) + level, derived directly from the real
    severity distribution of statistical findings. ``score`` is None when
    there is genuinely no data yet.
    """
    from src.anomaly_detection import statistical_engine
    summary = statistical_engine.findings_summary(run_id=None)
    dist = {k: int(v) for k, v in (summary.get("severity_distribution") or {}).items()}
    total = sum(dist.values())
    if not total:
        return {"score": None, "level": "NO DATA", "distribution": dist}
    weighted = sum(
        dist.get(level, 0) * _SEVERITY_WEIGHTS.get(level, 0.0)
        for level in _SEVERITY_ORDER
    )
    score = round(100.0 * weighted / total, 1)
    level = next((lv for lv in _SEVERITY_ORDER if dist.get(lv)), "LOW")
    return {"score": score, "level": level, "distribution": dist}


def risk_trend() -> List[Dict]:
    """
    Risk-score trend across completed pipeline scans (oldest first), using
    each scan's real persisted anomaly score. Empty when none exist.
    """
    session = get_session()
    try:
        rows = session.query(PipelineScan).filter(
            PipelineScan.status == "COMPLETED",
            PipelineScan.current_anomaly_score.isnot(None),
        ).order_by(PipelineScan.scan_id.asc()).all()
    finally:
        session.close()
    points = []
    from src.desktop import theme
    for r in rows:
        value = float(r.current_anomaly_score)
        if value < 25:
            color = theme.SUCCESS
        elif value < 55:
            color = theme.WARNING
        else:
            color = theme.CRITICAL
        label = f"#{r.scan_id}"
        ts = None
        if r.created_at:
            label = f"{label} {r.created_at.strftime('%m-%d')}"
            ts = r.created_at.date().isoformat()
        points.append({
            "label": label, "value": value, "color": color, "ts": ts,
        })
    return points


def threat_distribution() -> Dict:
    """Severity distribution (CRITICAL/HIGH/MEDIUM/LOW) + BENIGN models."""
    stats = dashboard_stats()
    from src.desktop import theme
    dist = dict(stats["severity_distribution"])
    dist["BENIGN"] = stats["safe_to_deploy"]
    items = [
        {"label": level, "count": dist.get(level, 0),
         "color": theme.risk_color(level)}
        for level in _SEVERITY_ORDER
    ]
    items.append({"label": "BENIGN", "count": dist.get("BENIGN", 0),
                  "color": theme.SUCCESS})
    return {"items": items, "total": sum(v for v in dist.values()),
            "severity_distribution": dist}


def system_health() -> List[Dict]:
    """
    Real availability probes for the System Health panel. Each check does an
    actual import / connectivity / writability test; nothing is hardcoded.
    """
    import os

    checks = []

    # Inference engine: pipeline + inference stack
    try:
        from src.scanner import pipeline  # noqa: F401
        from src.model_interface import loader as _loader  # noqa: F401
        checks.append({"name": "INFERENCE ENGINE", "ok": True,
                       "detail": "Scan pipeline + model loader importable"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "INFERENCE ENGINE", "ok": False,
                       "detail": f"Import failed: {exc}"})

    # Activation tracker: PyTorch forward-hook capture service
    try:
        from src.torch_analysis import activation_tracker  # noqa: F401
        checks.append({"name": "ACTIVATION TRACKER", "ok": True,
                       "detail": "Forward-hook activation capture available"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "ACTIVATION TRACKER", "ok": False,
                       "detail": f"Unavailable: {exc}"})

    # Model sandbox / loader
    try:
        from src.model_interface import loader as _loader2  # noqa: F401
        from src.model_interface import sandbox_service  # noqa: F401
        checks.append({"name": "MODEL SANDBOX", "ok": True,
                       "detail": "Local loader + sandbox available (offline)"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "MODEL SANDBOX", "ok": False,
                       "detail": f"Unavailable: {exc}"})

    # Forensic engine: statistical anomaly detection
    try:
        from src.anomaly_detection import statistical_engine  # noqa: F401
        checks.append({"name": "FORENSIC ENGINE", "ok": True,
                       "detail": "Statistical anomaly engine importable"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "FORENSIC ENGINE", "ok": False,
                       "detail": f"Import failed: {exc}"})

    # Storage / reports dir
    try:
        from src.reporting.forensic_report import _reports_dir
        d = _reports_dir()
        os.makedirs(d, exist_ok=True)
        ok = os.access(d, os.W_OK)
        checks.append({"name": "STORAGE", "ok": ok,
                       "detail": ("Reports directory writable" if ok
                                  else "Reports directory not writable")})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "STORAGE", "ok": False,
                       "detail": f"Storage check failed: {exc}"})

    # Report generator: forensic PDF/Markdown exporter
    try:
        from src.reporting import forensic_report  # noqa: F401
        checks.append({"name": "REPORT GENERATOR", "ok": True,
                       "detail": "PDF / Markdown report exporter available"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "REPORT GENERATOR", "ok": False,
                       "detail": f"Import failed: {exc}"})

    return checks


def audit_events(limit: int = 100) -> List[Dict]:
    """
    Merged, chronological operational events from real persisted rows:
    model registry changes, pipeline scans and forensic report generation.
    Returns the newest ``limit`` events.
    """
    import os
    from src.desktop import theme

    session = get_session()
    try:
        scans = session.query(PipelineScan).all()
        reports = session.query(Report).all()
        models = session.query(ModelMetadata).all()
    finally:
        session.close()

    events = []
    _SCAN_STATUS_COLOR = {
        "COMPLETED": theme.SUCCESS, "QUEUED": theme.ACCENT,
        "FAILED": theme.DANGER, "CANCELLED": theme.DANGER,
    }
    for r in scans:
        events.append({
            "ts": r.created_at.isoformat() if r.created_at else "",
            "level": "SCAN",
            "action": f"Scan #{r.scan_id} -> {r.status}",
            "actor": "platform",
            "detail": ("{0} \u00b7 {1} prompts \u00b7 {2} findings".format(
                r.model or "?", r.total_prompts or 0, r.findings_generated or 0)),
            "color": _SCAN_STATUS_COLOR.get(r.status, theme.TEXT_MUTED),
        })
    for rep in reports:
        events.append({
            "ts": rep.created_at.isoformat() if rep.created_at else "",
            "level": "REPORT",
            "action": f"Forensic report #{rep.report_id} generated",
            "actor": "platform",
            "detail": os.path.basename(rep.file_path or ""),
            "color": theme.ACCENT,
        })
    for m in models:
        events.append({
            "ts": m.created_at.isoformat() if m.created_at else "",
            "level": "MODEL",
            "action": f"Model '{m.file_name}' added",
            "actor": "analyst",
            "detail": m.model_type or m.architecture or "local file",
            "color": theme.ACCENT_SECONDARY,
        })

    events.sort(key=lambda e: e["ts"] or "", reverse=True)
    return events[:limit]


def model_metadata() -> Optional[Dict]:
    return overview_stats()["model"]


def model_status_label_local(model: Dict) -> str:
    """Professional lifecycle label for a model record (real status value)."""
    from src.desktop import theme
    return theme.model_status_label((model or {}).get("status") or "imported")


def model_status_color_local(model: Dict) -> str:
    """Colour for the lifecycle label of a model record."""
    from src.desktop import theme
    return theme.model_status_color((model or {}).get("status") or "imported")


def latest_report() -> Optional[Dict]:
    session = get_session()
    try:
        row = session.query(Report).order_by(Report.report_id.desc()).first()
    finally:
        session.close()
    if row is None:
        return None
    return {
        "run_id": row.run_id,
        "file_path": row.file_path,
        "created_at": row.created_at,
    }


# ---------------------------------------------------------------------------
# Real forensic reports (backend-generated PDFs from live scan data)
# ---------------------------------------------------------------------------

def report_records(limit: int = 50) -> List[Dict]:
    """Real forensic report metadata rows, newest first."""
    from src.reporting.forensic_report import list_reports
    return list_reports(limit=limit)


def report_detail(report_id) -> Optional[Dict]:
    """Full metadata for one report row (None if it does not exist)."""
    from src.reporting.forensic_report import report_detail as _detail
    return _detail(report_id)


def report_sources() -> List[Dict]:
    """The scans a report can be generated for (pipeline scans + orphan runs)."""
    from src.reporting.forensic_report import report_sources as _sources
    return _sources()


def generate_forensic_report(scan_id=None, run_id=None) -> str:
    """Generate a real forensic report from backend data + log metadata."""
    from src.reporting.forensic_report import generate_forensic_report as _gen
    return _gen(scan_id=scan_id, run_id=run_id)


def structured_findings(count: int = 50):
    """
    Real, structured security findings generated from the scan results.

    Delegates to src.findings.engine so the UI consumes the same
    explainable finding records (severity/title/reason/evidence, ...)
    that the report generation uses.
    """
    from src.findings.engine import generate_findings
    return [f.as_dict() for f in generate_findings(limit=count)]


def findings_security_score() -> Dict:
    """
    Real security score derived from the generated findings.

    Uses the explainable prototype formula (see src.findings.engine) so
    the displayed number is never hardcoded and always derived from the
    actual scan results present in the database.
    """
    from src.findings.engine import generate_findings, security_score_from_findings
    findings = generate_findings()
    return security_score_from_findings(findings)


# ---------------------------------------------------------------------------
# Statistical anomaly findings (real statistical anomaly detection engine)
# ---------------------------------------------------------------------------

def statistical_findings(run_id=None, severity=None, limit=1000) -> List[Dict]:
    """Real statistical findings from the statistical anomaly engine."""
    from src.anomaly_detection import statistical_engine
    return statistical_engine.list_findings(
        limit=limit, run_id=run_id, severity=severity
    )


def statistical_summary(run_id=None) -> Dict:
    """Severity distribution + aggregates for the statistical Findings page."""
    from src.anomaly_detection import statistical_engine
    return statistical_engine.findings_summary(run_id=run_id)


def statistical_scan_runs(limit: int = 25) -> List[Dict]:
    """Completed adversarial scan runs that can be analyzed."""
    from src.fuzzer.adversarial_scan import list_scan_runs
    runs = list_scan_runs(limit=limit)
    return [
        {
            "run_id": r["run_id"],
            "run_label": r["run_label"],
            "num_prompts": r["num_prompts"],
            "measurement_count": r["measurement_count"],
            "layer_count": r["layer_count"],
            "seed": r["seed"],
            "created_at": r["created_at"],
        }
        for r in runs
        if r["status"] == "completed"
    ]


def detect_statistical_findings(run_id=None, force=True) -> Dict:
    """Run the statistical anomaly engine over a scan run's measurements."""
    from src.anomaly_detection import statistical_engine
    return statistical_engine.generate_statistical_findings(
        run_id=run_id, force=force
    )


# ---------------------------------------------------------------------------
# Scan pipeline (real backend-owned lifecycle state)
# ---------------------------------------------------------------------------

def pipeline_create_scan(config: Dict) -> Dict:
    """Create a QUEUED pipeline scan row and return its initial state."""
    from src.scanner import pipeline
    scan_id = pipeline.create_scan(config or {})
    return pipeline.get_scan_state(scan_id)


def pipeline_scan_state(scan_id) -> Optional[Dict]:
    """Real persisted progress for one pipeline scan (None if absent)."""
    if scan_id is None:
        return None
    from src.scanner import pipeline
    return pipeline.get_scan_state(scan_id)


def pipeline_cancel(scan_id) -> Optional[Dict]:
    """Request graceful cancellation; returns updated state (None if bad id)."""
    from src.scanner import pipeline
    if not pipeline.cancel_scan(scan_id):
        return None
    return pipeline.get_scan_state(scan_id)


def pipeline_runs(limit: int = 25) -> List[Dict]:
    """Recent pipeline scan runs, newest first."""
    from src.scanner import pipeline
    return pipeline.list_pipeline_runs(limit=limit)


# ---------------------------------------------------------------------------
# Model lifecycle / risk decision + Overview activity (real engine output)
# ---------------------------------------------------------------------------

def _scan_model_distribution(stat_rows, model_name: str) -> Dict:
    """Severity distribution of real statistical findings for a model."""
    dist = {level: 0 for level in _SEVERITY_ORDER}
    for f in stat_rows:
        if f.model == model_name and f.severity in dist:
            dist[f.severity] += 1
    return dist


def risk_decision_from_distribution(dist: Dict, scanned: bool) -> str:
    """
    Honest risk-decision gate derived from the real anomaly engine output:
        * CRITICAL finding present      -> quarantined
        * HIGH or MEDIUM finding present -> review required
        * only LOW / no findings (scanned) -> approved
        * not yet scanned               -> pending
    """
    if not scanned:
        return "pending"
    if dist.get("CRITICAL", 0):
        return "quarantined"
    if dist.get("HIGH", 0) or dist.get("MEDIUM", 0):
        return "review"
    return "approved"


def model_decision(metadata_id: int) -> Dict:
    """Real risk decision for one registry model (never fabricated)."""
    from src.model_interface.import_service import get_model
    model = get_model(metadata_id)
    if model is None:
        return {"decision": "pending", "model": None, "severity_distribution": {},
                "scanned": False}
    return _model_decision_for_record(model)


def _model_decision_for_record(model: Dict) -> Dict:
    session = get_session()
    try:
        stat_rows = [f for f in session.query(StatisticalFinding).all()
                     if f.model == model["file_name"]]
    finally:
        session.close()
    dist = _scan_model_distribution(stat_rows, model["file_name"])
    scanned = bool(model.get("scanned_at")) or \
        (model.get("status") or "").lower() in ("scanned", "approved", "review", "quarantined")
    decision = risk_decision_from_distribution(dist, scanned)
    return {
        "decision": decision,
        "severity_distribution": dist,
        "scanned": scanned,
        "total_findings": sum(dist.values()),
    }


def apply_risk_decision(metadata_id: int) -> Dict:
    """
    Persist the real risk decision onto the model's status field
    (approved / review / quarantined). No fabricated values: the decision
    follows directly from the statistical anomaly engine output.
    """
    from src.model_interface.import_service import update_model_status, get_model
    info = _model_decision_for_record(get_model(metadata_id) or {"file_name": None})
    if info["decision"] == "pending":
        return {"decision": "pending", "updated": False}
    model = get_model(metadata_id)
    if model is None:
        return {"decision": "pending", "updated": False}
    updated = update_model_status(metadata_id, info["decision"])
    info["updated"] = True
    info["record"] = updated
    return info


def model_checkpoint(metadata_id: int) -> Dict:
    """
    Real security-checkpoint state for one registry model: the six
    workflow stages, the persisted decision and the severity distribution
    that produced it. All values come from real database rows.
    """
    from src.model_interface.import_service import get_model
    model = get_model(metadata_id)
    if model is None:
        return {"model": None, "steps": [], "decision": "pending",
                "severity_distribution": {}, "scanned": False}

    info = _model_decision_for_record(model)
    name = model["file_name"]

    session = get_session()
    try:
        has_measurements = session.query(ActivationMeasurement).filter(
            ActivationMeasurement.model == name
        ).first() is not None
        has_completed_scan = session.query(PipelineScan).filter(
            PipelineScan.model == name, PipelineScan.status == "COMPLETED"
        ).first() is not None
    finally:
        session.close()

    decision = info["decision"]
    has_decision = (model.get("status") or "").lower() in \
        ("approved", "review", "quarantined")
    steps = [
        {"label": "MODEL", "done": True},
        {"label": "INTEGRITY", "done": bool(model.get("sha256_hash"))},
        {"label": "SCAN", "done": info["scanned"] or has_completed_scan},
        {"label": "ANALYSIS", "done": has_measurements},
        {"label": "RISK", "done": info["total_findings"] > 0},
        {"label": "DECISION", "done": has_decision},
    ]
    return {
        "model": model,
        "steps": steps,
        "decision": decision,
        "severity_distribution": info["severity_distribution"],
        "scanned": info["scanned"],
    }


def model_activity() -> List[Dict]:
    """
    Overview "RECENT MODEL ACTIVITY" rows: one per registry model with
    real status, risk severity, last scan and recommendation.
    """
    from src.model_interface.import_service import list_models
    from src.desktop import theme
    session = get_session()
    try:
        scan_rows = session.query(PipelineScan).order_by(PipelineScan.scan_id.desc()).all()
        stat_rows = session.query(StatisticalFinding).all()
    finally:
        session.close()

    by_model = defaultdict(list)
    for r in scan_rows:
        (r.model or "tiny") and by_model[r.model].append(r)

    rows = []
    for m in list_models():
        name = m["file_name"]
        runs = by_model.get(name, [])
        last = runs[0] if runs else None
        info = _model_decision_for_record(m)
        dist = info["severity_distribution"]
        worst = next((lv for lv in _SEVERITY_ORDER if dist.get(lv)), None)

        status = (m.get("status") or "imported").lower()
        if status in ("approved", "review", "quarantined"):
            label = theme.model_status_label(status)
        else:
            label = theme.model_status_label(status)
        if status in ("approved",):
            rec = "APPROVE MODEL"
        elif status == "review":
            rec = "REVIEW FINDINGS"
        elif status == "quarantined":
            rec = "VIEW EVIDENCE"
        elif info["scanned"]:
            rec = "SCAN COMPLETE \u2014 REVIEW"
        else:
            rec = "RUN SECURITY SCAN"

        rows.append({
            "metadata_id": m["metadata_id"],
            "file_name": name,
            "status": status,
            "status_label": label,
            "status_color": theme.model_status_color(status),
            "risk_severity": worst,
            "risk_color": theme.risk_color(worst) if worst else None,
            "total_findings": info["total_findings"],
            "last_scan_id": last.scan_id if last else None,
            "last_scan_status": (last.status if last else None),
            "last_scanned": last.created_at.isoformat()[:19] if (last and last.created_at) else
                            (m.get("scanned_at") or "")[:19] if m.get("scanned_at") else "Never",
            "recommendation": rec,
        })
    return rows


def model_count_by_status(statuses: tuple) -> int:
    """Number of registry models whose real status is in ``statuses``."""
    from src.model_interface.import_service import list_models
    wanted = {s.lower() for s in statuses}
    return sum(1 for m in list_models() if (m.get("status") or "").lower() in wanted)


# ---------------------------------------------------------------------------
# Real activation heatmap data (per-layer x per-category mean activation)
# ---------------------------------------------------------------------------

def activation_matrix() -> Dict:
    """
    Real mean-activation matrix: layers x input categories, aggregated from
    ActivationMeasurement rows written during actual scans. Never synthetic.
    """
    session = get_session()
    try:
        meas = session.query(ActivationMeasurement).all()
    finally:
        session.close()

    layer_order = []
    cat_order = []
    sums = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(lambda: defaultdict(int))
    for m in meas:
        if m.layer not in layer_order:
            layer_order.append(m.layer)
        if m.category not in cat_order:
            cat_order.append(m.category)
        sums[m.layer][m.category] += (m.mean or 0.0)
        counts[m.layer][m.category] += 1

    matrix = []
    counts_grid = []
    for layer in layer_order:
        matrix.append([
            round(sums[layer][c] / counts[layer][c], 6) if counts[layer][c] else None
            for c in cat_order
        ])
        counts_grid.append([counts[layer][c] for c in cat_order])
    return {
        "layers": layer_order,
        "categories": cat_order,
        "matrix": matrix,
        "counts": counts_grid,
    }


def scans_today() -> int:
    """Real count of pipeline scan runs created today (local date)."""
    from src.scanner import pipeline
    runs = pipeline.list_pipeline_runs(limit=5000)
    today = date.today().isoformat()
    return sum(1 for r in runs if (r.get("created_at") or "").startswith(today))


def workflow_stages() -> List[Dict]:
    """
    Real state of the six-stage security workflow shown in the header:
    MODEL -> INTEGRITY -> SCAN -> ANALYSIS -> RISK -> DECISION.
    Every stage is derived from actual database rows -- nothing fabricated.
    """
    session = get_session()
    try:
        models = session.query(ModelMetadata).all()
        scans = session.query(PipelineScan).all()
        measurements = session.query(ActivationMeasurement).first()
        findings = session.query(StatisticalFinding).first()
    finally:
        session.close()

    has_scan = any(
        (m.status == "scanned" or m.scanned_at is not None) for m in models
    ) or any(r.status == "COMPLETED" for r in scans)

    has_decision = any(
        (m.status or "").lower() in ("approved", "review", "quarantined")
        for m in models
    )

    return [
        {"label": "MODEL", "done": bool(models)},
        {"label": "INTEGRITY", "done": any(m.sha256_hash for m in models)},
        {"label": "SCAN", "done": has_scan},
        {"label": "ANALYSIS", "done": measurements is not None},
        {"label": "RISK", "done": findings is not None},
        {"label": "DECISION", "done": has_decision},
    ]
