"""
NeuroFence scan pipeline orchestrator.

Connects every real module into one back-end-owned scan:

    Model -> Fuzzer -> Local inference -> PyTorch hooks -> Activation
    statistics -> Baseline comparison -> Anomaly detection -> Findings
    -> Database

Lifecycle (persisted in `pipeline_scan_runs`, pollable by any client):

    QUEUED -> INITIALIZING -> LOADING_MODEL -> GENERATING_INPUTS ->
    RUNNING_INFERENCE -> ANALYZING_ACTIVATIONS -> DETECTING_ANOMALIES ->
    COMPLETED | FAILED | CANCELLED

Progress is never fabricated. Every percentage/metric written here comes
from a module that actually did the work, and UI pages only read these
rows (no front-end timers, no fake progress).
"""

import json
import time
from typing import Any, Dict, List, Optional

from src.db.db_manager import get_session
from src.db.models import PipelineScan

TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

MAX_LOG_ENTRIES = 400

# Percent milestones per phase. These are real "work happened" markers --
# the fuzzer/adversarial-scan module reports the actual per-prompt numbers
# and we only persist what it reports.
_INIT_PERCENT = 2.0


def create_scan(config: Dict[str, Any]) -> int:
    """Create a QUEUED pipeline scan row and return its scan_id."""
    session = get_session()
    try:
        row = PipelineScan(
            status="QUEUED",
            percentage=0.0,
            model=str(config.get("model", "tiny")),
            config=json.dumps(config),
            seed=int(config.get("seed", 42)),
            total_prompts=int(config.get("num_prompts", 8)),
            activity_log=json.dumps([]),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.scan_id
    finally:
        session.close()


def _last_from(row, key, default):
    try:
        val = getattr(row, key)
        return default if val is None else val
    except Exception:  # noqa: BLE001 -- never break progress writes
        return default


def save_progress(
    scan_id: int,
    phase: str,
    percent: Optional[float] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    **fields,
) -> Optional[int]:
    """
    Persist the real scan state for one phase transition.

    Only fields that are actually provided are updated; everything else is
    left as-is so a progress write can never erase earlier real values.
    """
    session = get_session()
    try:
        row = session.get(PipelineScan, int(scan_id))
        if row is None:
            return None

        row.status = phase

        if percent is not None:
            row.percentage = float(percent)

        if error is not None:
            row.error = str(error)

        for key, value in fields.items():
            if value is None:
                continue
            setattr(row, key, value)

        if message:
            log = row.activity_log
            try:
                entries = json.loads(log) if log else []
            except Exception:  # noqa: BLE001
                entries = []
            entries.append({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "phase": phase,
                "message": str(message),
            })
            row.activity_log = json.dumps(entries[-MAX_LOG_ENTRIES:])

        session.commit()
        return row.scan_id
    finally:
        session.close()


def get_scan_state(scan_id: int) -> Optional[Dict[str, Any]]:
    """Return the full persisted state of one pipeline scan (None if absent)."""
    session = get_session()
    try:
        row = session.get(PipelineScan, int(scan_id))
        if row is None:
            return None
        try:
            log = json.loads(row.activity_log or "[]")
        except Exception:  # noqa: BLE001
            log = []
        try:
            cfg = json.loads(row.config or "{}")
        except Exception:  # noqa: BLE001
            cfg = {}
        return {
            "scan_id": row.scan_id,
            "status": row.status,
            "current_phase": row.status,
            "percentage": row.percentage or 0.0,
            "model": row.model,
            "config": cfg,
            "seed": row.seed,
            "total_prompts": row.total_prompts or 0,
            "prompts_processed": row.prompts_processed or 0,
            "layers_analyzed": row.layers_analyzed or 0,
            "findings_generated": row.findings_generated or 0,
            "current_anomaly_score": row.current_anomaly_score,
            "cancel_requested": bool(row.cancel_requested),
            "run_id": row.run_id,
            "error": row.error,
            "activity_log": log,
            "is_terminal": row.status in TERMINAL_STATES,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    finally:
        session.close()


def list_pipeline_runs(limit: int = 25) -> List[Dict[str, Any]]:
    """Recent pipeline scan runs (newest first)."""
    session = get_session()
    try:
        rows = (
            session.query(PipelineScan)
            .order_by(PipelineScan.scan_id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "scan_id": r.scan_id,
                "status": r.status,
                "percentage": r.percentage or 0.0,
                "model": r.model,
                "total_prompts": r.total_prompts or 0,
                "prompts_processed": r.prompts_processed or 0,
                "layers_analyzed": r.layers_analyzed or 0,
                "findings_generated": r.findings_generated or 0,
                "current_anomaly_score": r.current_anomaly_score,
                "run_id": r.run_id,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


def _is_cancelled(scan_id: int) -> bool:
    """Cheap in-progress check: only reads the cancellation flag column."""
    session = get_session()
    try:
        row = session.get(PipelineScan, int(scan_id))
        if row is None or row.status in TERMINAL_STATES:
            return False
        return bool(row.cancel_requested)
    finally:
        session.close()


def cancel_scan(scan_id: int) -> bool:
    """
    Request graceful cancellation of a running pipeline scan.

    The scan process notices the flag between prompts and stops cleanly,
    preserving the work done so far. Returns False when the scan does not
    exist or is already in a terminal state.
    """
    session = get_session()
    try:
        row = session.get(PipelineScan, int(scan_id))
        if row is None or row.status in TERMINAL_STATES:
            return False
        row.cancel_requested = True
        session.commit()
    finally:
        session.close()
    save_progress(
        scan_id, "RUNNING_INFERENCE",
        message="Cancellation requested; stopping after the current prompt.",
    )
    return True


def execute_scan(scan_id: int) -> Optional[Dict[str, Any]]:
    """
    Run one pipeline scan end-to-end and persist real progress.

    Called by the CLI subprocess or by FastAPI BackgroundTasks. All heavy
    work (model load, inference) is delegated to module functions so the
    calling process controls when torch is imported.
    """
    from src.anomaly_detection.statistical_engine import (
        StatisticalConfig, compute_baseline, evaluate_measurements,
        persist_statistical_findings,
    )
    from src.fuzzer.adversarial_scan import (
        CancelledError, measurements_for_run, run_adversarial_scan,
    )

    save_progress(scan_id, "INITIALIZING", _INIT_PERCENT,
                  "Initializing scan pipeline.")

    state = get_scan_state(scan_id)
    if state is None:
        return None
    cfg = state["config"] or {}

    def on_progress(percent, phase, message, counts):
        if counts:
            return save_progress(
                scan_id, phase, percent, message,
                total_prompts=counts.get("total_prompts"),
                prompts_processed=counts.get("prompts_done"),
                layers_analyzed=counts.get("layers_done"),
            )
        return save_progress(scan_id, phase, percent, message)

    try:
        summary = run_adversarial_scan(
            count=int(cfg.get("num_prompts", 8)),
            seed=int(cfg.get("seed", 42)),
            categories=cfg.get("categories"),
            max_seq_len=int(cfg.get("max_seq_len", 16)),
            layers=int(cfg.get("layers", 12)),
            model=str(cfg.get("model", "tiny")),
            max_new_tokens=int(cfg.get("max_new_tokens", 3)),
            progress_cb=on_progress,
            should_stop=lambda: _is_cancelled(scan_id),
        )
        run_id = summary["run_id"]

        # ANALYZING_ACTIVATIONS: real baseline + scoring, no fake progress.
        save_progress(scan_id, "ANALYZING_ACTIVATIONS", 82,
                      "Building per-layer baseline from normal activations.",
                      run_id=run_id)
        measurements = measurements_for_run(run_id, limit=100000)
        sconfig = StatisticalConfig.from_settings()
        baseline = compute_baseline(measurements, sconfig)
        if not baseline:
            save_progress(scan_id, "ANALYZING_ACTIVATIONS", 88,
                          "No normal-category baseline available; "
                          "anomaly detection skipped for this run.",
                          run_id=run_id)
            baseline_layers = []
            records = []
        else:
            baseline_layers = sorted(baseline.keys())
            save_progress(scan_id, "ANALYZING_ACTIVATIONS", 86,
                          f"Baseline ready for {len(baseline_layers)} layers.",
                          layers_analyzed=len(baseline_layers), run_id=run_id)
            records = evaluate_measurements(measurements, sconfig, baseline)

        peak = max((r["anomaly_score"] for r in records), default=0.0)
        save_progress(
            scan_id, "ANALYZING_ACTIVATIONS", 90,
            f"Evaluated {len(measurements)} activation rows; "
            f"{len(baseline_layers)} layers analyzed.",
            layers_analyzed=len(baseline_layers),
            current_anomaly_score=round(peak, 2),
            prompts_processed=summary["measured_prompts"],
            total_prompts=summary["num_prompts"],
            run_id=run_id,
        )

        # DETECTING_ANOMALIES: persist the engine's findings.
        n_findings = 0
        if records:
            save_progress(scan_id, "DETECTING_ANOMALIES", 93,
                          f"Persisting {len(records)} statistical findings.",
                          current_anomaly_score=round(peak, 2), run_id=run_id)
            session = get_session()
            try:
                n_findings = persist_statistical_findings(
                    session, records, scan_label=summary["run_label"],
                    run_id=run_id, force=True,
                )
                session.commit()
            finally:
                session.close()
            save_progress(scan_id, "DETECTING_ANOMALIES", 98,
                          f"Stored {n_findings} findings.",
                          findings_generated=n_findings,
                          current_anomaly_score=round(peak, 2),
                          run_id=run_id)

        # COMPLETED: report only real numbers.
        save_progress(
            scan_id, "COMPLETED", 100.0,
            "Scan pipeline completed. "
            f"{summary['measured_prompts']}/{summary['num_prompts']} prompts "
            f"measured, {len(baseline_layers)} layers analyzed, "
            f"{n_findings} findings generated.",
            run_id=run_id,
        )

        # The model that was just scanned is genuinely scanned now, so the
        # dashboard's "scanned models" KPI reflects real completed scans.
        try:
            from src.model_interface.import_service import mark_model_scanned
            mark_model_scanned()
        except Exception:  # noqa: BLE001 -- cosmetic registry touch-up
            pass

        return get_scan_state(scan_id)

    except CancelledError:
        message = "Scan cancelled by user; partial results preserved."
        save_progress(scan_id, "CANCELLED", None, message, error=message)
        return get_scan_state(scan_id)

    except Exception as exc:  # noqa: BLE001 -- surface + record any failure
        import traceback
        message = f"Scan failed: {exc}"
        save_progress(
            scan_id, "FAILED", None, message,
            error=traceback.format_exc(limit=10),
        )
        return get_scan_state(scan_id)