"""
Results View -- shows overall security score, risk category, prompt
counts, trigger/anomaly detections and evaluation metrics read from
the SQLite database.
"""

import pandas as pd
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import Qt

from src.db.db_manager import get_session
from src.db.models import (
    FuzzResult, BackdoorTest, AnomalyResult, EvaluationMetric,
    EvaluationConfusion, RiskAssessmentRow, Prompt,
)


class ResultsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Security Results")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a237e;")
        layout.addWidget(title)

        # KPI grid
        kpi_group = QGroupBox("Overview")
        grid = QGridLayout(kpi_group)
        self.kpi = {}
        fields = [
            ("Security score", "score"),
            ("Risk category", "risk"),
            ("Total prompts", "prompts"),
            ("Fuzz runs", "fuzz"),
            ("Backdoor fired", "backdoor"),
            ("Anomalies flagged", "anomalies"),
            ("Avg ML F1", "f1"),
            ("Avg Accuracy", "acc"),
        ]
        row = 0
        for label, key in fields:
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight: bold; color: #555;")
            val = QLabel("-")
            val.setStyleSheet("font-size: 20px; font-weight: bold; color: #1a237e;")
            grid.addWidget(lbl, row, 0, 1, 2)
            grid.addWidget(val, row + 1, 0, 1, 2)
            self.kpi[key] = val
            row += 2
        layout.addWidget(kpi_group)

        # Metrics table
        metrics_group = QGroupBox("Detection Metrics (Module 7)")
        v = QVBoxLayout(metrics_group)
        self.metrics_table = QTableWidget(0, 8)
        self.metrics_table.setHorizontalHeaderLabels(
            ["Run", "Precision", "Recall", "F1", "Accuracy", "FPR", "FNR", "Coverage"]
        )
        self.metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.metrics_table.setEditTriggers(QTableWidget.NoEditTriggers)
        v.addWidget(self.metrics_table)
        layout.addWidget(metrics_group, stretch=1)

        self.refresh()

    def refresh(self):
        session = get_session()
        try:
            prompts = session.query(Prompt).count()
            fuzz = session.query(FuzzResult).count()
            bd = session.query(BackdoorTest).all()
            anomalies = session.query(AnomalyResult).filter_by(is_anomaly=True).count()
            metrics_rows = session.query(EvaluationMetric).all()
            confusion_rows = session.query(EvaluationConfusion).all()
            risk_rows = session.query(RiskAssessmentRow).all()
        finally:
            session.close()

        if not prompts:
            for k in self.kpi:
                self.kpi[k].setText("-")
            self.metrics_table.setRowCount(0)
            return

        self.kpi["prompts"].setText(str(prompts))
        self.kpi["fuzz"].setText(str(fuzz))
        fired = sum(1 for r in bd if r.triggered_flag)
        self.kpi["backdoor"].setText(f"{fired}/{len(bd)}")

        # Anomalies across all methods (dedupe by score_id newest)
        self.kpi["anomalies"].setText(str(anomalies))

        # Risk summary
        if risk_rows:
            lows = sum(1 for r in risk_rows if r.risk_level in ("LOW", "MEDIUM"))
            score = round(100 * lows / len(risk_rows), 1)
            self.kpi["score"].setText(f"{score}/100")
            # Overall category = max risk present
            levels = {r.risk_level for r in risk_rows}
            if "CRITICAL" in levels:
                category = "CRITICAL"
            elif "HIGH" in levels:
                category = "HIGH"
            elif "MEDIUM" in levels:
                category = "MEDIUM"
            else:
                category = "LOW"
            self.kpi["risk"].setText(category)
        else:
            self.kpi["score"].setText("N/A")
            self.kpi["risk"].setText("N/A")

        # Metrics
        if metrics_rows:
            f1s = [m.f1_score for m in metrics_rows if m.f1_score is not None]
            self.kpi["f1"].setText(f"{sum(f1s)/len(f1s) if f1s else 0:.3f}")
            conf = {c.run_id: c.accuracy for c in confusion_rows}
            accs = [a for a in conf.values() if a is not None]
            self.kpi["acc"].setText(f"{sum(accs)/len(accs) if accs else 0:.3f}")

        # Fill metrics table
        merge = {}
        for c in confusion_rows:
            merge[c.run_id] = c.accuracy
        self.metrics_table.setRowCount(len(metrics_rows))
        for i, m in enumerate(metrics_rows):
            vals = [m.run_id, m.precision, m.recall, m.f1_score,
                    merge.get(m.run_id, ""), m.false_positive_rate,
                    m.false_negative_rate, m.coverage]
            for j, v in enumerate(vals):
                item = QTableWidgetItem("-" if v is None else str(v))
                item.setTextAlignment(Qt.AlignCenter)
                self.metrics_table.setItem(i, j, item)
