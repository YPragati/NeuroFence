"""
Tests for the NeuroFence scan pipeline (backend-owned lifecycle).

Covers the real state machine (QUEUED -> INITIALIZING -> LOADING_MODEL ->
GENERATING_INPUTS -> RUNNING_INFERENCE -> ANALYZING_ACTIVATIONS ->
DETECTING_ANOMALIES -> COMPLETED | FAILED | CANCELLED), graceful
cancellation, error handling, the subprocess CLI used by the desktop, the
REST API endpoints, and the Live Scan desktop page. All DB paths are
isolated via NEUROFENCE_DB_PATH. No progress values are fabricated -- every
assertion uses real backend state.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.scanner import pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]

BASIC_CONFIG = {
    "model": "tiny",
    "num_prompts": 2,
    "seed": 42,
    "categories": ["normal"],
    "layers": 4,
    "max_seq_len": 16,
    "max_new_tokens": 3,
}


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    db = str(tmp_path / "test_pipeline_scan.db")
    monkeypatch.setenv("NEUROFENCE_DB_PATH", db)
    return tmp_path


@pytest.fixture
def tiny_model_ready():
    from src.model_interface.tiny_test_model import ensure_tiny_model_saved
    ensure_tiny_model_saved()
    return True


# ---------------------------------------------------------------------------
# Lifecycle primitives (no model, no torch)
# ---------------------------------------------------------------------------

class TestScanLifecycle:
    def test_create_scan_is_queued(self, tmp_env):
        sid = pipeline.create_scan(BASIC_CONFIG)
        st = pipeline.get_scan_state(sid)
        assert st["status"] == "QUEUED"
        assert st["percentage"] == 0.0
        assert st["is_terminal"] is False
        assert st["total_prompts"] == 2
        assert st["activity_log"] == []
        assert st["config"]["num_prompts"] == 2

    def test_save_progress_updates_without_wiping(self, tmp_env):
        sid = pipeline.create_scan(BASIC_CONFIG)
        pipeline.save_progress(sid, "LOADING_MODEL", 10.0, "Loading local model...")
        pipeline.save_progress(sid, "GENERATING_INPUTS", None,
                               "Generated", total_prompts=9)
        st = pipeline.get_scan_state(sid)
        assert st["status"] == "GENERATING_INPUTS"
        # percent=None must NOT erase the previous real percentage
        assert st["percentage"] == 10.0
        assert st["total_prompts"] == 9
        assert st["prompts_processed"] == 0
        assert len(st["activity_log"]) == 2
        assert st["activity_log"][-1]["phase"] == "GENERATING_INPUTS"
        assert st["activity_log"][-1]["message"] == "Generated"

    def test_cancel_scan_sets_flag_only_when_active(self, tmp_env):
        sid = pipeline.create_scan(BASIC_CONFIG)
        assert pipeline._is_cancelled(sid) is False
        assert pipeline.cancel_scan(sid) is True
        assert pipeline._is_cancelled(sid) is True
        st = pipeline.get_scan_state(sid)
        assert st["cancel_requested"] is True

        # Missing scan -> False.
        assert pipeline.cancel_scan(999999) is False
        # Terminal scan -> False.
        pipeline.save_progress(sid, "COMPLETED", 100.0, "done")
        assert pipeline.cancel_scan(sid) is False

    def test_list_pipeline_runs_newest_first(self, tmp_env):
        a = pipeline.create_scan(BASIC_CONFIG)
        b = pipeline.create_scan({"model": "toy"})
        pipeline.save_progress(b, "COMPLETED", 100.0, "done")
        runs = pipeline.list_pipeline_runs()
        assert [r["scan_id"] for r in runs] == [b, a]
        assert runs[0]["status"] == "COMPLETED"
        assert runs[0]["percentage"] == 100.0

    def test_get_state_missing_returns_none(self, tmp_env):
        assert pipeline.get_scan_state(12345) is None


# ---------------------------------------------------------------------------
# Full end-to-end scan execution
# ---------------------------------------------------------------------------

class TestExecuteScan:
    def test_complete_lifecycle_order(self, tmp_env, tiny_model_ready):
        sid = pipeline.create_scan(BASIC_CONFIG)
        st = pipeline.execute_scan(sid)
        assert st["status"] == "COMPLETED"
        assert st["percentage"] == 100.0
        assert st["prompts_processed"] == 2
        assert st["total_prompts"] == 2
        assert st["is_terminal"] is True
        assert st["run_id"] is not None

        # Lifecycle phases must appear in the required order in the log.
        phases = [e["phase"] for e in st["activity_log"]]
        required = [
            "INITIALIZING", "LOADING_MODEL", "GENERATING_INPUTS",
            "RUNNING_INFERENCE", "ANALYZING_ACTIVATIONS", "COMPLETED",
        ]
        idx = [phases.index(p) for p in required]
        assert idx == sorted(idx)

        # Findings written for this run and counted by the pipeline.
        from src.db.db_manager import get_session
        from src.db.models import StatisticalFinding
        session = get_session()
        try:
            n = (session.query(StatisticalFinding)
                 .filter(StatisticalFinding.run_id == st["run_id"]).count())
        finally:
            session.close()
        assert n == st["findings_generated"]

    def test_detection_writes_findings(self, tmp_env, tiny_model_ready):
        cfg = dict(BASIC_CONFIG,
                   num_prompts=8, layers=3, seed=7,
                   categories=["normal", "unusual_wording",
                               "synthetic_trigger", "repeated_tokens"])
        sid = pipeline.create_scan(cfg)
        st = pipeline.execute_scan(sid)
        assert st["status"] == "COMPLETED"
        assert st["findings_generated"] > 0
        assert st["current_anomaly_score"] > 0
        phases = [e["phase"] for e in st["activity_log"]]
        assert "DETECTING_ANOMALIES" in phases
        assert "ANALYZING_ACTIVATIONS" in phases

    def test_completed_run_shows_in_runs(self, tmp_env, tiny_model_ready):
        sid = pipeline.create_scan(BASIC_CONFIG)
        pipeline.execute_scan(sid)
        runs = pipeline.list_pipeline_runs()
        match = [r for r in runs if r["scan_id"] == sid]
        assert match and match[0]["status"] == "COMPLETED"
        assert match[0]["percentage"] == 100.0

    def test_cancellation_stops_gracefully(self, tmp_env, tiny_model_ready):
        cfg = dict(BASIC_CONFIG, num_prompts=30, categories=["normal"])
        sid = pipeline.create_scan(cfg)
        pipeline.cancel_scan(sid)
        st = pipeline.execute_scan(sid)
        assert st["status"] == "CANCELLED"
        assert st["is_terminal"] is True
        assert st["prompts_processed"] < st["total_prompts"]
        assert st["activity_log"][-1]["phase"] == "CANCELLED"
        assert "cancelled" in st["error"].lower()

    def test_model_error_marks_failed(self, tmp_env):
        sid = pipeline.create_scan({"model": "does_not_exist"})
        st = pipeline.execute_scan(sid)
        assert st["status"] == "FAILED"
        assert st["is_terminal"] is True
        assert st["error"]
        assert "does_not_exist" in st["error"].lower()
        assert st["activity_log"][-1]["phase"] == "FAILED"


# ---------------------------------------------------------------------------
# Desktop subprocess CLI (the path the GUI actually uses)
# ---------------------------------------------------------------------------

class TestPipelineCLI:
    def test_cli_requires_scan_id(self):
        proc = subprocess.run(
            [sys.executable, "-m", "src.scanner.pipeline_cli"],
            cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert proc.returncode == 2

    def test_cli_runs_scan_end_to_end(self, tmp_env, tiny_model_ready):
        sid = pipeline.create_scan(BASIC_CONFIG)
        proc = subprocess.run(
            [sys.executable, "-m", "src.scanner.pipeline_cli", str(sid)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["scan_id"] == sid
        assert out["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

class TestPipelineAPI:
    def test_start_state_and_runs_endpoints(self, tmp_env, tiny_model_ready):
        from fastapi.testclient import TestClient
        from src.api.app import app

        with TestClient(app) as client:
            r = client.post("/api/scan/pipeline", json={
                "model": "tiny", "num_prompts": 2, "layers": 3,
                "categories": ["normal"], "seed": 7,
            })
            assert r.status_code == 200, r.text
            initial = r.json()
            sid = initial["scan_id"]
            assert initial["status"] in ("QUEUED", "INITIALIZING",
                                         "LOADING_MODEL", "GENERATING_INPUTS")

            # Pending/active state endpoint is live.
            state = client.get(f"/api/scan/pipeline/state/{sid}").json()
            assert state["scan_id"] == sid
            assert state["activity_log"] is not None

        # The background task runs to COMPLETED (TestClient waits for it).
        with TestClient(app) as client:
            state = client.get(f"/api/scan/pipeline/state/{sid}").json()
            assert state["status"] == "COMPLETED", state
            assert state["percentage"] == 100.0

            runs = client.get("/api/scan/pipeline/runs").json()
            assert any(rr["scan_id"] == sid and rr["status"] == "COMPLETED"
                       for rr in runs)

            # Cancelling a missing/terminal pipeline scan -> 404.
            assert client.post("/api/scan/pipeline/999999/cancel").status_code == 404

    def test_state_404_for_missing_scan(self, tmp_env):
        from fastapi.testclient import TestClient
        from src.api.app import app
        with TestClient(app) as client:
            assert client.get("/api/scan/pipeline/state/424242").status_code == 404


# ---------------------------------------------------------------------------
# Desktop Live Scan view
# ---------------------------------------------------------------------------

class TestLiveScanView:
    def test_view_renders_terminal_state(self, tmp_env):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        sid = pipeline.create_scan(BASIC_CONFIG)
        pipeline.save_progress(
            sid, "COMPLETED", 100.0,
            "Scan pipeline completed. 2/2 prompts measured, 4 layers "
            "analyzed, 0 findings generated.",
            prompts_processed=2, total_prompts=2, layers_analyzed=4,
            findings_generated=0, current_anomaly_score=0.0, run_id=1,
        )

        from src.desktop.live_scan_view import LiveScanView
        view = LiveScanView()
        view._scan_id = sid
        view.refresh()
        view._apply_state(pipeline.get_scan_state(sid))
        app.processEvents()

        assert view.card_status._value.text() == "COMPLETED"
        assert view.card_prompts._value.text() == "2 / 2"
        assert view.progress.value() == 100
        assert "CURRENT ANOMALY SCORE: 0.0 / 100" in view.score_label.text()
        assert view.log_table.rowCount() == 1
        # The run appears in the watch picker.
        assert view.run_picker.findData(sid) >= 0

    def test_view_empty_state_no_crash(self, tmp_env):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from src.desktop.live_scan_view import LiveScanView
        view = LiveScanView()
        view.refresh()
        app.processEvents()
        assert view.card_status._value.text() == "IDLE"
        assert view.log_table.rowCount() == 0