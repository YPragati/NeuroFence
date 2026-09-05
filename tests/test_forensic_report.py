"""
Tests for the real forensic report generation.

Proves the report is built from actual backend data (pipeline scan,
adversarial run, activation measurements, statistical findings, model
forensics), contains all 18 required sections and the explicit honesty
disclaimer, renders a real PDF, and stores its metadata in SQLite.
No placeholder content -- every assertion checks real values.
"""

import json
import os
import re
from pathlib import Path

import pytest

from src.db import db_manager
from src.scanner import pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_CONFIG = {
    "model": "tiny",
    "num_prompts": 2,
    "seed": 42,
    "categories": ["normal", "repeated_tokens"],
    "layers": 3,
    "max_seq_len": 8,
    "max_new_tokens": 2,
}


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    db = str(tmp_path / "test_forensic.db")
    monkeypatch.setenv("NEUROFENCE_DB_PATH", db)
    monkeypatch.setenv("NEUROFENCE_REPORTS_DIR", str(tmp_path / "reports"))
    return tmp_path


@pytest.fixture
def tiny_model_ready():
    from src.model_interface.tiny_test_model import ensure_tiny_model_saved
    ensure_tiny_model_saved()
    return True


ALL_18_SECTIONS = [
    "NeuroFence — AI Security Forensic Report",       # 1. title (h1)
    "2. Scan Identification",
    "3. Timestamp",
    "4. Model Name",
    "5. Model Architecture",
    "6. Parameter Information",
    "7. File Size",
    "8. SHA-256 Hash",
    "9. Model Format",
    "10. Scan Configuration",
    "11. Number of Inputs Tested",
    "12. Layers Analyzed",
    "13. Activation Statistics Summary",
    "14. Findings",
    "15. Severity Distribution",
    "16. Overall Risk Score",
    "17. Analyst Summary",
    "18. Scientific Limitations",
]


def _headings(html: str):
    return re.findall(r"<h([12])>(.*?)</h\1>", html)


# ---------------------------------------------------------------------------
# Full end-to-end: real scan -> real report (run BEFORE Qt tests so torch
# loads before PyQt, which is the DLL-safe order on Windows).
# ---------------------------------------------------------------------------

class TestRealForensicReport:
    def test_real_scan_pdf_and_metadata(self, tmp_env, tiny_model_ready):
        sid = pipeline.create_scan(SCAN_CONFIG)
        st = pipeline.execute_scan(sid)
        assert st["status"] == "COMPLETED"

        from src.reporting import forensic_report as fr

        data = fr.build_report_data(scan_id=sid)
        assert data["has_data"] is True
        assert data["generated_scan_id"] == sid
        assert data["run"]["status"] == "completed"

        # 4) Model name + 5) architecture + 6) params + 7) size + 8) sha + 9) format
        model = data["model"]
        assert model["name"] == "TinyTransformerLM"
        assert model["architecture"] == "TinyTransformerLM"
        assert model["params"] and int(model["params"]) > 0
        assert model["size_bytes"] and int(model["size_bytes"]) > 0
        assert re.fullmatch(r"[0-9a-f]{64}", model["sha256"])
        assert model["format"] == "PyTorch safetensors"

        # 11) inputs tested / 12) layers
        assert data["inputs_tested"] and data["inputs_tested"] >= 1
        assert data["layers"]  # real layer names from measurements
        assert data["activation"]["measurement_count"] > 0
        assert data["activation"]["distinct_prompts"] >= 1
        for l in data["activation"]["layers"]:
            assert l["name"]  # real tracker layer names (e.g. encoder, dropout)
            assert l["count"] >= 1

        # 13) severity distribution + 16) risk index are internally consistent.
        dist = data["severity_dist"]
        assert set(dist) == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        assert all(isinstance(v, int) and v >= 0 for v in dist.values())
        assert data["findings_total"] == sum(dist.values())
        if data["findings_total"]:
            assert data["peak_anomaly_score"] == max(
                f["anomaly_score"] for f in data["findings"])
            assert data["overall_risk_score"] is not None

        # Every one of the 18 required sections is present.
        html = fr.render_report_html(data)
        headings = _headings(html)
        texts = [t.strip() for _, t in headings]
        for expected in ALL_18_SECTIONS:
            assert expected in texts, f"Missing required section: {expected}"

        # Honesty requirement is explicit in the report body.
        assert "does not mathematically prove" in html
        assert "anomalous activation behavior" in html
        assert "TBD" not in html and "{{" not in html  # no fabricated content

        # Analyst summary is written from real numbers.
        assert "TinyTransformerLM" in fr._analyst_summary(data)

        # PDF renders and metadata lands in SQLite.
        pdf_path = fr.generate_forensic_report(scan_id=sid)
        assert pdf_path.endswith(".pdf")
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000, f"PDF too small: {pdf_path}"

        session = db_manager.get_session()
        try:
            from src.db.models import Report
            rows = session.query(Report).order_by(Report.report_id.desc()).all()
            assert len(rows) >= 1
            row = rows[0]
            assert row.scan_id == sid
            assert row.format == "pdf"
            assert os.path.exists(row.file_path)
            summ = json.loads(row.summary)
            assert summ["scan_id"] == sid
            assert summ["model"] == "TinyTransformerLM"
            assert summ["findings_total"] == data["findings_total"]
        finally:
            session.close()

        listed = fr.list_reports()
        assert listed and listed[0]["scan_id"] == sid
        assert listed[0]["exists"] is True
        assert fr.report_detail(listed[0]["report_id"])["model"] == "TinyTransformerLM"

        # The report sources include this completed scan.
        sources = fr.report_sources()
        assert any(s["kind"] == "scan" and s["id"] == sid for s in sources)

    def test_reporting_helpers_never_fabricate(self, tmp_env):
        from src.reporting import forensic_report as fr

        # No data at all: the report still renders 18 honest sections.
        data = fr.build_report_data()
        assert data["has_data"] is False
        assert data["findings_total"] == 0
        assert data["overall_risk_score"] is None
        html = fr.render_report_html(data)
        texts = [t.strip() for _, t in _headings(html)]
        for expected in ALL_18_SECTIONS:
            assert expected in texts

        assert fr._overall_risk({"CRITICAL": 1, "HIGH": 0, "MEDIUM": 0, "LOW": 3}) == 43.8
        assert fr._overall_risk({"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}) is None

        # A report can still be written and logged (empty-data report).
        out = fr.generate_forensic_report()
        assert os.path.exists(out)
        session = db_manager.get_session()
        try:
            from src.db.models import Report
            row = session.query(Report).order_by(Report.report_id.desc()).first()
            assert row is not None
            assert row.scan_id is None
            assert row.format in ("pdf", "html")
            assert os.path.exists(row.file_path)
        finally:
            session.close()

    def test_unknown_scan_raises(self, tmp_env):
        from src.reporting.forensic_report import build_report_data
        with pytest.raises(ValueError):
            build_report_data(scan_id=999999)


# ---------------------------------------------------------------------------
# Desktop Reports page (real list / details / generate-or-open behaviour)
# ---------------------------------------------------------------------------

class TestReportsView:
    def test_desktop_reports_view_lists_real_reports(self, tmp_env):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        # A pipeline row that finished -- no torch required.
        sid = pipeline.create_scan(SCAN_CONFIG)
        pipeline.save_progress(sid, "COMPLETED", 100.0, "done")

        from src.reporting.forensic_report import generate_forensic_report
        generate_forensic_report(scan_id=sid)

        from src.desktop.reports_view import ReportsView
        view = ReportsView()
        assert view.table.rowCount() >= 1
        assert view.combo_source.count() >= 1
        detail = view.detail_label.text()
        assert f"#{sid}" in detail
        view.close()

    def test_desktop_reports_view_empty_state(self, tmp_env):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from src.desktop.reports_view import ReportsView
        view = ReportsView()
        assert view.table.rowCount() == 0
        # Generating on an empty store is safe and logs a real metadata row.
        view._generate()
        assert view.table.rowCount() >= 1
        view.close()