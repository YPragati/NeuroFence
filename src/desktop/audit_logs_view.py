"""
System Audit Log -- real operational event log.

Aggregates actual persisted activity rows (model registry additions,
pipeline investigation scans and forensic report generations) into a
single chronological, filterable audit trail. Every row maps to a real
database record -- nothing is fabricated, and there is no silent data.

The page shows a disclaiming header ("derived from real DB rows; no
tamper-proof chain of custody is claimed") to keep the UX honest.
"""

from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTableWidgetItem,
)

from src.desktop import theme, data_service
from src.desktop.widgets import (
    PageHeader, Panel, make_table, clear_table,
)

_LEVELS = ["ALL", "SCAN", "REPORT", "MODEL"]


class AuditLogsView(QWidget):
    """Real-derived audit trail page for the SYSTEM navigation group."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        header = PageHeader(
            "SYSTEM AUDIT LOG",
            subtitle=("Chronological operational events derived from real "
                      "persisted records. No tamper-proof chain of custody "
                      "is claimed."),
            chip_text="REAL RECORDS ONLY",
            chip_color=theme.ACCENT,
        )
        root.addWidget(header)

        ctl = QHBoxLayout()
        ctl.setSpacing(10)
        ctl.addWidget(QLabel("Filter:"))
        self.level_filter = QComboBox()
        self.level_filter.addItems(_LEVELS)
        self.level_filter.currentTextChanged.connect(self._re_filter)
        ctl.addWidget(self.level_filter)
        self.count_label = QLabel("0 events")
        self.count_label.setObjectName("PageSubtitle")
        ctl.addWidget(self.count_label)
        ctl.addStretch(1)
        root.addLayout(ctl)

        panel = Panel("AUDIT TRAIL")
        self.table = make_table(["TIMESTAMP", "EVENT", "COMPONENT",
                                 "INVESTIGATION", "SEVERITY"],
                                stretch_col=3)
        self.table.setEditTriggers(self.table.NoEditTriggers)
        self.table.setSelectionBehavior(self.table.SelectRows)
        panel.add_widget(self.table)
        root.addWidget(panel, 1)

    @staticmethod
    def _severity(event):
        level = event["level"]
        action = event["action"]
        if level == "SCAN":
            if "-> FAILED" in action or "-> CANCELLED" in action:
                return ("ERROR", theme.DANGER)
            return ("OPERATIONAL", theme.SUCCESS)
        return ("INFO", theme.ACCENT)

    def refresh(self):
        self._events = data_service.audit_events(limit=500)
        self._re_filter()

    def _re_filter(self):
        level = self.level_filter.currentText()
        rows = [e for e in self._events if level == "ALL" or e["level"] == level]
        clear_table(self.table)
        self.table.setRowCount(len(rows))
        for r, e in enumerate(rows):
            try:
                ts = datetime.fromisoformat(e["ts"]).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:  # noqa: BLE001
                ts = e.get("ts", "")
            severity, severity_color = self._severity(e)
            items = [
                QTableWidgetItem(ts),
                QTableWidgetItem(e["action"]),
                QTableWidgetItem(e["level"]),
                QTableWidgetItem(e["detail"]),
                QTableWidgetItem(severity),
            ]
            items[2].setTextAlignment(Qt.AlignCenter)
            items[2].setForeground(QColor(e.get("color") or theme.TEXT_PRIMARY))
            items[4].setTextAlignment(Qt.AlignCenter)
            items[4].setForeground(QColor(severity_color))
            for c, item in enumerate(items):
                self.table.setItem(r, c, item)
        self.count_label.setText(f"{len(rows)} event(s)" + (
            "" if level == "ALL" else f" \u00b7 filtered: {level}"))