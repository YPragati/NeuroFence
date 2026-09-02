"""
Report View -- export PDF / Markdown / JSON security reports, open the
generated report, and view the risk distribution + suspicious cases.
"""

import json
import os
import subprocess
import sys

import pandas as pd
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
)
from PyQt5.QtCore import Qt

from src.db.db_manager import get_session
from src.db.models import (
    Prompt, FuzzResult, BackdoorTest, RiskAssessmentRow,
)
from src.reporting.report_builder import _build_prompt_lookup, generate_report
from src.reporting.pdf_generator import generate_pdf_report


class ReportView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Report Export & Forensic Findings")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a237e;")
        layout.addWidget(title)

        # Export buttons
        btn_row = QHBoxLayout()
        self.btn_pdf = QPushButton("Export PDF Report")
        self.btn_pdf.clicked.connect(self._export_pdf)
        self.btn_md = QPushButton("Export Markdown Report")
        self.btn_md.clicked.connect(self._export_md)
        self.btn_open = QPushButton("Open Last Report")
        self.btn_open.clicked.connect(self._open_last)
        btn_row.addWidget(self.btn_pdf)
        btn_row.addWidget(self.btn_md)
        btn_row.addWidget(self.btn_open)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Risk distribution
        risk_group = QGroupBox("Risk Distribution")
        rv = QVBoxLayout(risk_group)
        self.risk_table = QTableWidget(0, 3)
        self.risk_table.setHorizontalHeaderLabels(["Risk Level", "Executions", "Share"])
        self.risk_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.risk_table.setEditTriggers(QTableWidget.NoEditTriggers)
        rv.addWidget(self.risk_table)
        layout.addWidget(risk_group)

        # Suspicious cases
        susp_group = QGroupBox("Suspicious Cases (top risk executions)")
        sv = QVBoxLayout(susp_group)
        self.susp_table = QTableWidget(0, 5)
        self.susp_table.setHorizontalHeaderLabels(
            ["Risk", "Level", "Source", "Prompt", "Signals"]
        )
        sv.addWidget(self.susp_table)
        layout.addWidget(susp_group, stretch=1)

        self._last_report_path = None
        self._markdown_path = None
        self.refresh()

    def refresh(self):
        session = get_session()
        try:
            prompt_lookup = _build_prompt_lookup(session)
            risk_rows = session.query(RiskAssessmentRow).all()
            fuzz_rows = session.query(FuzzResult).all()
            bd_rows = session.query(BackdoorTest).all()
        finally:
            session.close()

        # Risk distribution
        from collections import Counter
        counts = Counter(r.risk_level for r in risk_rows)
        total = len(risk_rows) or 1
        levels = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        self.risk_table.setRowCount(len(levels))
        for i, level in enumerate(levels):
            c = counts.get(level, 0)
            vals = [level, str(c), f"{100 * c / total:.1f}%"]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                self.risk_table.setItem(i, j, item)

        # Suspicious cases
        top = sorted(risk_rows, key=lambda r: r.risk_score, reverse=True)[:10]
        self.susp_table.setRowCount(len(top))
        for i, r in enumerate(top):
            text = prompt_lookup.get((r.source_ref_id, r.source_type), "?")
            if len(text) > 60:
                text = text[:60] + "..."
            notes = []
            if float(r.trigger_signal) > 0:
                notes.append("trigger")
            if float(r.injection_signal) > 0:
                notes.append("injection")
            if not notes:
                notes.append("behavioral anomaly")
            vals = [f"{r.risk_score:.1f}", r.risk_level, r.source_type, text, ", ".join(notes)]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if j == 1:
                    item.setTextAlignment(Qt.AlignCenter)
                self.susp_table.setItem(i, j, item)

    # ---- exports ----

    def _export_pdf(self):
        path = generate_pdf_report()
        self._last_report_path = path
        self._done(path, "PDF")

    def _export_md(self):
        path = generate_report()
        self._markdown_path = path
        self._last_report_path = path
        self._done(path, "Markdown")

    def _open_last(self):
        if not self._last_report_path or not os.path.exists(self._last_report_path):
            QMessageBox.information(self, "No report", "Generate a report first (PDF or Markdown).")
            return
        self._open_with_default(self._last_report_path)

    def _done(self, path, kind):
        QMessageBox.information(self,
                                f"{kind} report",
                                f"Report written to:\n{path}")

    @staticmethod
    def _open_with_default(path):
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606 -- opening local generated report
        else:
            subprocess.Popen(["xdg-open", path])
