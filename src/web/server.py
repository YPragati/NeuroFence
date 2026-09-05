"""
NeuroFence web backend -- thin localhost adapter over the existing
Python services.

This FastAPI application does NOT re-implement any security/backend
logic. It exposes the exact same functions the PyQt desktop uses
(src.desktop.data_service + the model/scanner/engine modules) as small
JSON endpoints, and serves the offline browser UI from web/.

Everything runs on localhost, fully offline. No cloud, no auth, no
internet dependency.

    python run_web.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.db.models import ActivationMeasurement, StatisticalFinding
from src.db.db_manager import get_session

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "data", "web_uploads")

_DESKTOP = "src.desktop.data_service  (thin adapter over existing services)"

_SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def _ds():
    """Lazy import: keeps server startup light; never imports PyQt anyway."""
    from src.desktop import data_service
    return data_service


def _theme():
    from src.desktop import theme
    return theme


def _import_service():
    from src.model_interface import import_service
    return import_service


def _statistical_engine():
    from src.anomaly_detection import statistical_engine
    return statistical_engine


def _forensic_report():
    from src.reporting import forensic_report
    return forensic_report


# ---------------------------------------------------------------------------
# Scan supervision -- launch the real pipeline in a subprocess (same as the
# desktop worker) and let the browser poll the persisted DB state.
# ---------------------------------------------------------------------------

_LOCKS = {}


def _launch_scan_subprocess(scan_id: int) -> None:
    lock = _LOCKS.setdefault(scan_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return
    try:
        env = dict(os.environ)
        subprocess.Popen(
            [sys.executable, "-m", "src.scanner.pipeline_cli", str(scan_id)],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001 -- surfaced via scan state FAILED
        _ds().pipeline_scan_state(scan_id)
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Thin aggregations that combine existing real service outputs. No values are
# fabricated; every row read comes from the SQLite database.
# ---------------------------------------------------------------------------

def _scan_history_stats() -> Dict[str, int]:
    runs = _ds().pipeline_runs(limit=5000)
    terminal = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
    out = {"total": len(runs), "completed": 0, "failed": 0, "active": 0}
    for r in runs:
        if r["status"] == "COMPLETED":
            out["completed"] += 1
        elif r["status"] == "FAILED":
            out["failed"] += 1
        elif r["status"] not in terminal:
            out["active"] += 1
    return out


def _model_registry_stats(models: List[Dict]) -> Dict[str, Any]:
    total = len(models)
    validated = sum(1 for m in models if (m.get("status") or "").lower() == "validated")
    scanned = sum(1 for m in models if m.get("scanned_at") or
                  (m.get("status") or "").lower() in ("scanned", "approved", "review", "quarantined"))
    total_bytes = sum(m.get("file_size_bytes") or 0 for m in models)
    return {
        "total_models": total,
        "validated": validated,
        "scanned": scanned,
        "total_size": total_bytes,
    }


def _layer_activation_stats(model_name: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    Per-layer activation statistics from real ActivationMeasurement rows.
    ``anomaly_score`` is the max statistical-engine score ever recorded for
    that model+layer (real persisted values, not fabricated).
    """
    session = get_session()
    try:
        q = session.query(ActivationMeasurement)
        if model_name:
            q = q.filter(ActivationMeasurement.model == model_name)
        meas = [m for m in q.all()]
        stats_by_layer = {}
        for m in meas:
            acc = stats_by_layer.setdefault(m.layer, {
                "layer": m.layer,
                "layer_index": m.layer_index,
                "mean": 0.0, "std": 0.0, "max": 0.0,
                "norm": 0.0, "active_fraction": 0.0,
                "num_elements": 0, "measurements": 0, "models": set(),
            })
            acc["mean"] += m.mean or 0.0
            acc["std"] += m.std or 0.0
            acc["max"] = max(acc["max"], m.max_val or 0.0)
            acc["norm"] += m.norm or 0.0
            acc["active_fraction"] += m.active_fraction or 0.0
            acc["num_elements"] = m.num_elements or acc["num_elements"]
            acc["measurements"] += 1
            acc["shape"] = m.shape
            acc["models"].add(m.model or "?")
        findings = session.query(StatisticalFinding).all()
    finally:
        session.close()

    anomaly_by = {}
    for f in findings:
        key = (f.model, f.layer)
        if anomaly_by.get(key, 0) < (f.anomaly_score or 0):
            anomaly_by[key] = f.anomaly_score or 0

    rows = []
    for layer, acc in sorted(stats_by_layer.items(), key=lambda kv: (kv[1]["layer_index"] or 0)):
        n = acc["measurements"] or 1
        score = None
        found = None
        for m in acc["models"]:
            s = anomaly_by.get((m, layer))
            if s is not None and (found is None or s > found):
                found = s
        rows.append({
            "layer": layer,
            "layer_index": acc["layer_index"],
            "mean": round(acc["mean"] / n, 4),
            "std": round(acc["std"] / n, 4),
            "max": round(acc["max"], 4),
            "norm": round(acc["norm"] / n, 4),
            "active_fraction": round(acc["active_fraction"] / n, 4),
            "num_elements": acc["num_elements"],
            "measurements": acc["measurements"],
            "anomaly_score": round(found, 2) if found is not None else None,
            "shape": acc.get("shape"),
        })
    return rows


def _verification_for_model(model: Dict) -> List[Dict]:
    """Real verification checklist rows for one registry model."""
    checks = [
        {"label": "Model file detected",
         "pass": os.path.isfile(model.get("file_path") or "")},
        {"label": "SHA-256 calculated",
         "pass": bool(model.get("sha256_hash"))},
        {"label": "Format verified",
         "pass": bool(model.get("model_type"))},
        {"label": "Architecture identified",
         "pass": bool(model.get("architecture"))},
    ]
    sandbox = [_c for _c in _ds().system_health()
               if _c["name"] == "MODEL SANDBOX"]
    engine = [_c for _c in _ds().system_health()
              if _c["name"] == "INFERENCE ENGINE"]
    checks.append({"label": "Local sandbox available",
                   "pass": bool(sandbox and sandbox[0]["ok"]),
                   "detail": (sandbox[0]["detail"] if sandbox else None)})
    checks.append({"label": "Local execution available",
                   "pass": bool(engine and engine[0]["ok"]),
                   "detail": (engine[0]["detail"] if engine else None)})
    return checks


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ScanConfig(BaseModel):
    model: str = "tiny"
    num_prompts: int = 8
    layers: int = 12
    seed: int = 42
    max_seq_len: int = 16
    max_new_tokens: int = 3
    categories: Optional[List[str]] = None
    depth: Optional[str] = None


class ReportRequest(BaseModel):
    scan_id: Optional[int] = None
    run_id: Optional[int] = None


class AnalyzeRequest(BaseModel):
    run_id: Optional[int] = None


class DirectoryImport(BaseModel):
    path: str


class StatusUpdate(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NeuroFence Web",
    description="Offline browser UI for AI model security forensics",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "neurofence-web",
        "offline": True,
        "database": os.environ.get("NEUROFENCE_DB_PATH") or "default",
    }


def _serve_failed(exc: BaseException) -> HTTPException:
    return HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Dashboard + system
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard():
    try:
        ds = _ds()
        kpis = ds.investigation_stats()
        overview = ds.risk_overview()
        trend = ds.risk_trend()
        dist = ds.threat_distribution()
        health = ds.system_health()
        stats = ds.dashboard_stats()
        activities = ds.audit_events(limit=8)
        history = _scan_history_stats()
        recent_scans = ds.pipeline_runs(limit=6)
        return {
            "kpis": kpis,
            "risk_overview": overview,
            "risk_trend": trend,
            "threat_distribution": dist,
            "system_health": health,
            "recent_scans": recent_scans,
            "recent_findings": stats["recent_findings"],
            "recent_activity": activities,
            "scan_history_stats": history,
        }
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/activities")
def activities(limit: int = Query(20, ge=1, le=200)):
    try:
        return _ds().audit_events(limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/audit")
def audit_logs(limit: int = Query(200, ge=1, le=1000)):
    try:
        return _ds().audit_events(limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@app.get("/api/models")
def models():
    try:
        rows = _import_service().list_models()
        stats = _model_registry_stats(rows)

        fmt_size = _import_service().format_size
        for m in rows:
            m["size_label"] = fmt_size(m.get("file_size_bytes") or 0)
            status = (m.get("status") or "imported").lower()
            m["status_label"] = _theme().model_status_label(status)
            m["status_color"] = _theme().model_status_color(status)
            m["sha_short"] = (m.get("sha256_hash") or "")[:16]
        return {"models": rows, "stats": stats}
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.post("/api/models/import")
async def import_uploaded(file: UploadFile = File(...)):
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe = os.path.basename(file.filename or "model")
        dest = os.path.join(UPLOAD_DIR, safe)
        with open(dest, "wb") as fh:
            shutil.copyfileobj(file.file, fh)
        result = _import_service().import_model(dest)
        return result
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.post("/api/models/import-dir")
def import_directory(payload: DirectoryImport):
    try:
        path = os.path.abspath(payload.path)
        if not os.path.isdir(path):
            return JSONResponse(
                status_code=400,
                content={"success": False, "models": [], "errors": [f"Not a directory: {payload.path}"]},
            )
        return _import_service().import_model(path)
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/models/{metadata_id}")
def model_detail(metadata_id: int):
    try:
        svc = _import_service()
        model = svc.get_model(metadata_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")
        checkpoint = _ds().model_checkpoint(metadata_id)
        decision = _ds().model_decision(metadata_id)
        verification = _verification_for_model(model)
        model["size_label"] = svc.format_size(model.get("file_size_bytes") or 0)
        model["status_label"] = _theme().model_status_label((model.get("status") or "imported").lower())
        model["status_color"] = _theme().model_status_color((model.get("status") or "imported").lower())
        return {
            "model": model,
            "checkpoint": checkpoint,
            "decision": decision,
            "verification": verification,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.post("/api/models/{metadata_id}/load")
def load_model(metadata_id: int):
    try:
        return _import_service().load_model_file(metadata_id)
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/models/{metadata_id}/load-status")
def load_status(metadata_id: int):
    try:
        return _import_service().model_load_status(metadata_id)
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.delete("/api/models/{metadata_id}")
def delete_model(metadata_id: int):
    try:
        ok = _import_service().delete_model(metadata_id)
        return {"deleted": ok}
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.put("/api/models/{metadata_id}/status")
def set_model_status(metadata_id: int, payload: StatusUpdate):
    try:
        updated = _import_service().update_model_status(metadata_id, payload.status)
        if updated is None:
            raise HTTPException(status_code=404, detail="Model not found")
        return updated
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.post("/api/models/{metadata_id}/decision")
def apply_model_decision(metadata_id: int):
    try:
        return _ds().apply_risk_decision(metadata_id)
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


# ---------------------------------------------------------------------------
# Activation explorer
# ---------------------------------------------------------------------------

@app.get("/api/activation")
def activation(model: Optional[str] = None):
    try:
        models = _import_service().list_models()
        matrix = _ds().activation_matrix()
        stats = _layer_activation_stats(model or None)
        return {
            "models": [{"file_name": m["file_name"], "metadata_id": m["metadata_id"],
                        "architecture": m.get("architecture"),
                        "layer_count": m.get("layer_count")} for m in models],
            "active_model": model,
            "matrix": matrix,
            "layer_stats": stats,
        }
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


# ---------------------------------------------------------------------------
# Scan configuration + pipeline
# ---------------------------------------------------------------------------

SCAN_PROFILES = {
    "STANDARD": {"num_prompts": 8, "max_seq_len": 16, "layers": 12, "max_new_tokens": 3},
    "DEEP ANALYSIS": {"num_prompts": 24, "max_seq_len": 32, "layers": 16, "max_new_tokens": 6},
    "QUICK CHECK": {"num_prompts": 4, "max_seq_len": 12, "layers": 8, "max_new_tokens": 2},
}


@app.get("/api/scan/config")
def scan_config():
    try:
        from src.fuzzer.adversarial_generator import CATEGORY_KEYS, CATEGORY_LABELS
        models = _import_service().list_models()
        return {
            "profiles": SCAN_PROFILES,
            "categories": [{"key": k, "label": CATEGORY_LABELS.get(k, k)} for k in CATEGORY_KEYS],
            "models": [{"file_name": m["file_name"], "metadata_id": m["metadata_id"],
                        "architecture": m.get("architecture"),
                        "layer_count": m.get("layer_count")} for m in models],
        }
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.post("/api/scan", status_code=201)
def create_scan(payload: ScanConfig):
    try:
        cfg = payload.dict()
        cfg["categories"] = payload.categories or None
        scan_id = _ds().pipeline_create_scan(cfg)["scan_id"]
        threading.Thread(target=_launch_scan_subprocess, args=(scan_id,), daemon=True).start()
        return _ds().pipeline_scan_state(scan_id)
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/scan/history")
def scan_history(limit: int = Query(100, ge=1, le=1000)):
    try:
        runs = _ds().pipeline_runs(limit=limit)
        # Merge per-run statistical summary so the table shows real anomaly
        # engine numbers.
        return {"runs": runs, "stats": _scan_history_stats()}
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/scan/{scan_id}")
def scan_state(scan_id: int):
    try:
        state = _ds().pipeline_scan_state(scan_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        return state
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.post("/api/scan/{scan_id}/cancel")
def cancel_scan(scan_id: int):
    try:
        state = _ds().pipeline_cancel(scan_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Scan not found or already terminal")
        return state
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/scans/{scan_id}/detail")
def scan_detail(scan_id: int):
    try:
        state = _ds().pipeline_scan_state(scan_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Scan not found")
        run_id = state.get("run_id")
        findings = []
        if run_id:
            findings = _statistical_engine().list_findings(run_id=run_id, limit=500)
        return {"state": state, "findings": findings}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@app.get("/api/findings")
def findings(
    run_id: Optional[int] = None,
    severity: Optional[str] = None,
    layer: Optional[str] = None,
    min_score: Optional[float] = Query(None, ge=0, le=100),
    limit: int = Query(500, ge=1, le=2000),
):
    try:
        ds = _ds()
        rows = ds.statistical_findings(run_id=run_id, severity=severity, limit=limit)
        if layer:
            rows = [r for r in rows if r.get("layer") == layer]
        if min_score is not None:
            rows = [r for r in rows if (r.get("anomaly_score") or 0) >= min_score]
        summary = ds.statistical_summary(run_id=run_id)
        dist = summary.get("severity_distribution") or {}
        dist["BENIGN"] = ds.threat_distribution()["severity_distribution"].get("BENIGN", 0)
        runs = [r for r in ds.statistical_scan_runs(limit=50)]
        layers = sorted({r.get("layer") for r in ds.statistical_findings(run_id=run_id, limit=5000)})
        return {
            "findings": rows,
            "summary": summary,
            "severity_distribution": dist,
            "runs": runs,
            "layers": layers,
        }
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/findings/{finding_id}")
def finding_detail(finding_id: int):
    try:
        row = _statistical_engine().get_finding(finding_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Finding not found")
        return row
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.post("/api/findings/analyze")
def analyze_findings(payload: AnalyzeRequest):
    try:
        return _ds().detect_statistical_findings(run_id=payload.run_id, force=True)
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@app.get("/api/reports")
def reports():
    try:
        rows = _ds().report_records(limit=100)
        total = len(rows)
        available = sum(1 for r in rows if r.get("exists"))
        missing = sum(1 for r in rows if not r.get("exists"))
        return {"reports": rows, "stats": {"total": total, "available": available,
                                           "pending": 0, "missing": missing}}
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/reports/sources")
def report_sources():
    try:
        return _ds().report_sources()
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/reports/open")
def open_report(report_id: int = Query(...)):
    try:
        detail = _ds().report_detail(report_id)
        if detail is None or not detail.get("file_path"):
            raise HTTPException(status_code=404, detail="Report not found")
        return {"report": detail}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.post("/api/reports/generate")
def generate_report(payload: ReportRequest):
    try:
        path = _ds().generate_forensic_report(scan_id=payload.scan_id, run_id=payload.run_id)
        return {"path": path}
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/report-file/{report_id}")
def report_file(report_id: int):
    try:
        detail = _ds().report_detail(report_id)
        if detail is None or not detail.get("file_path"):
            raise HTTPException(status_code=404, detail="Report not found")
        fp = detail["file_path"]
        if not os.path.isfile(fp):
            raise HTTPException(status_code=404, detail="Report file missing on disk")
        return FileResponse(fp, filename=os.path.basename(fp))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


@app.get("/api/meta")
def meta():
    return {
        "product": "NeuroFence",
        "tagline": "AI MODEL FORENSICS",
        "version": "1.0.0",
        "analyst": os.environ.get("NEUROFENCE_ANALYST") or "analyst",
        "offline": True,
        "mode": "LOCAL / OFFLINE / AIR-GAPPED",
    }


# ---------------------------------------------------------------------------
# Settings summary (read-only, real config)
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def settings():
    try:
        from src.config_loader import get_config
        cfg = get_config()
        db_path = None
        try:
            from src.db.db_manager import get_db_path
            db_path = get_db_path()
        except Exception:  # noqa: BLE001
            db_path = None
        return {
            "project": cfg.get("project", {}),
            "paths": cfg.get("paths", {}),
            "model": cfg.get("model", {}),
            "anomaly_detection": cfg.get("anomaly_detection", {}),
            "fuzzer": cfg.get("fuzzer", {}),
            "evaluation": cfg.get("evaluation", {}),
            "analyst": os.environ.get("NEUROFENCE_ANALYST") or "analyst",
            "db_path": db_path,
            "mode": "LOCAL / OFFLINE / AIR-GAPPED",
        }
    except Exception as exc:  # noqa: BLE001
        raise _serve_failed(exc)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

class SPAStaticFiles(StaticFiles):
    """Serve static assets, falling back to index.html for SPA routes."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException:
            index = os.path.join(self.directory, "index.html")
            return FileResponse(index)


app.mount("/", SPAStaticFiles(directory=WEB_DIR, html=True), name="web")