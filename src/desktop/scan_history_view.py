"""
Scan History -- full history of real pipeline scan runs.

Every row is a persisted PipelineScan run with backend-owned lifecycle
state. Selecting a run expands its evidence: the full activity log (each
phase colour-coded), the configuration that produced it and its outcome.
No values are synthesized -- this page renders what the scan wrote.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QTableWidgetItem,
)

from src.desktop import theme, data_service
from src.desktop.widgets import (
    PageHeader, Panel, KpiCard, DataTable, make_table, clear_table, FieldPair,
)

_PHASE_COLORS = {
    "QUEUED": theme.ACCENT,
    "INITIALIZING": theme.WARNING,
    "LOADING_MODEL": theme.WARNING,
    "GENERATING_INPUTS": theme.WARNING,
    "RUNNING_INFERENCE": theme.WARNING,
    "ANALYZING_ACTIVATIONS": theme.PRIMARY,
    "DETECTING_ANOMALIES": theme.PRIMARY,
    "COMPLETED": theme.SUCCESS,
    "FAILED": theme.DANGER,
    "CANCELLED": theme.DANGER,
}


class ScanHistoryView(QWidget):
    def __init__(self, on_watch_scan=None, on_new_scan=None, parent=None):
        super().__init__(parent)
        self._on_watch_scan = on_watch_scan
        self._on_new_scan = on_new_scan
        self._runs = []
        self._selected_scan_id = None
        self._build_ui()
        self.refresh()

    # ---- UI ----

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        header = PageHeader(
            "SCAN HISTORY",
            subtitle="Every pipeline run persisted by the backend, newest first.",
            chip_text="REAL BACKEND STATE",
            chip_color=theme.PRIMARY,
        )
        root.addWidget(header)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_total = KpiCard("TOTAL RUNS", "0", accent=theme.ACCENT, sub="created")
        self.card_completed = KpiCard("COMPLETED", "0", accent=theme.SUCCESS, sub="finished")
        self.card_failed = KpiCard("FAILED", "0", accent=theme.DANGER, sub="errors")
        self.card_active = KpiCard("ACTIVE", "0", accent=theme.WARNING, sub="in progress")
        for c in [self.card_total, self.card_completed, self.card_failed, self.card_active]:
            cards.addWidget(c, 1)
        root.addLayout(cards)

        splitter = QSplitter(Qt.Vertical)

        runs_panel = Panel("PIPELINE RUNS")
        self.table = DataTable(
            ["ID", "STATUS", "MODEL", "PROMPTS", "LAYERS", "FINDINGS",
             "ANOMALY SCORE", "CREATED"],
            page_size=12, stretch_col=2,
        )
        self.table.set_cell_stylist(self._style_cell)
        self.table.rowSelected.connect(self._on_select_run)
        runs_panel.add_widget(self.table)

        run_btns = QHBoxLayout()
        self.btn_watch = QPushButton("\u25b6  OPEN IN LIVE SCAN")
        self.btn_watch.setObjectName("PrimaryButton")
        self.btn_watch.clicked.connect(self._watch_selected)
        self.btn_new = QPushButton("START NEW SCAN")
        self.btn_new.setObjectName("GhostButton")
        self.btn_new.clicked.connect(self._new_scan)
        run_btns.addWidget(self.btn_watch)
        run_btns.addWidget(self.btn_new)
        run_btns.addStretch(1)
        runs_panel.add_layout(run_btns)
        splitter.addWidget(runs_panel)

        detail_panel = Panel("RUN DETAILS \u2014 EVIDENCE")
        self.detail_status = QLabel("Select a scan run to expand its evidence.")
        self.detail_status.setObjectName("PageSubtitle")
        self.detail_status.setWordWrap(True)
        detail_panel.add_widget(self.detail_status)

        self.detail_fields = QVBoxLayout()
        self.detail_fields.setSpacing(4)
        detail_panel.add_layout(self.detail_fields)

        log_title = QLabel("ACTIVITY LOG")
        log_title.setObjectName("PanelTitle")
        detail_panel.add_widget(log_title)
        self.log_table = make_table(["TIME", "PHASE", "MESSAGE"], stretch_col=2)
        detail_panel.add_widget(self.log_table)
        splitter.addWidget(detail_panel)

        splitter.setSizes([380, 280])
        root.addWidget(splitter, 1)

    # ---- data ----

    def refresh(self):
        runs = data_service.pipeline_runs(limit=200)
        self._runs = runs

        rows = []
        for r in runs:
            rows.append([
                f"#{r['scan_id']}",
                r["status"],
                r["model"] or "?",
                f"{r['prompts_processed']} / {r['total_prompts']}",
                str(r["layers_analyzed"]),
                str(r["findings_generated"]),
                f"{r['current_anomaly_score']:.1f}" if r["current_anomaly_score"] is not None else "-",
                (r["created_at"] or "?")[:19],
            ])
        self.table.set_rows(rows, [r["scan_id"] for r in runs])

        stats = data_service.dashboard_stats()
        self.card_total.set_value(str(len(runs)))
        self.card_completed.set_value(str(sum(1 for r in runs if r["status"] == "COMPLETED")))
        self.card_failed.set_value(str(sum(1 for r in runs if r["status"] in ("FAILED", "CANCELLED"))))
        self.card_active.set_value(str(stats["active_scans"]))

    def _style_cell(self, _orig, item, col):
        if col == 1:
            item.setForeground(QColor(_PHASE_COLORS.get(item.text(), theme.TEXT_PRIMARY)))
            item.setTextAlignment(Qt.AlignCenter)
        elif col in (0, 3, 4, 5, 6, 7):
            item.setTextAlignment(Qt.AlignCenter)
        elif col in (2,):
            pass

    # ---- actions ----

    def _on_select_run(self, scan_id):
        state = data_service.pipeline_scan_state(scan_id)
        if state is None:
            return
        self._selected_scan_id = scan_id
        self._show_detail(state)

    def _watch_selected(self):
        if self._selected_scan_id is None:
            scan_id = self.table.current_row_index()
            if scan_id < 0:
                return
            self._selected_scan_id = scan_id
        if self._on_watch_scan:
            self._on_watch_scan(self._selected_scan_id)

    def _new_scan(self):
        if self._on_new_scan:
            self._on_new_scan()

    def _show_detail(self, state):
        status = state.get("status", "IDLE")
        color = _PHASE_COLORS.get(status, theme.ACCENT)
        self.detail_status.setTextFormat(Qt.RichText)
        err = state.get("error") or ""
        self.detail_status.setText(
            f'<span style="color:{color};font-weight:700;'
            f'font-size:13px;">{theme.html_translate(status)}</span>'
            f'  &nbsp;scan #{state["scan_id"]} &middot; '
            f'{state.get("model", "?")} &middot; '
            f'{int(state.get("percentage", 0))}%'
            + (f' &nbsp;<span style="color:{theme.DANGER};">{theme.html_translate(err[:220])}</span>'
               if err else "")
        )

        while self.detail_fields.count():
            item = self.detail_fields.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        cfg = state.get("config") or {}
        fields = [
            ("MODEL", state.get("model") or "-"),
            ("PROMPTS", f"{state.get('prompts_processed')} / {state.get('total_prompts')}"),
            ("LAYERS ANALYZED", str(state.get("layers_analyzed"))),
            ("FINDINGS", str(state.get("findings_generated"))),
            ("ANOMALY SCORE",
             f"{state.get('current_anomaly_score'):.1f}" if state.get("current_anomaly_score") is not None else "-"),
            ("CATEGORIES", ", ".join(cfg.get("categories", []) or []) or "-"),
            ("SEED", str(cfg.get("seed", state.get("seed")) or "-")),
            ("MAX SEQ LEN", str(cfg.get("max_seq_len", "-"))),
            ("MAX NEW TOKENS", str(cfg.get("max_new_tokens", "-"))),
            ("CREATED", state.get("created_at") or "-"),
        ]
        for label, value in fields:
            self.detail_fields.addWidget(FieldPair(label, value))

        log = state.get("activity_log") or []
        clear_table(self.log_table)
        self.log_table.setRowCount(len(log))
        for r, entry in enumerate(log):
            phase = entry.get("phase", "")
            items = [
                QTableWidgetItem(entry.get("ts", "")),
                QTableWidgetItem(phase),
                QTableWidgetItem(entry.get("message", "")),
            ]
            items[1].setTextAlignment(Qt.AlignCenter)
            items[1].setForeground(QColor(_PHASE_COLORS.get(phase, theme.TEXT_PRIMARY)))
            for c, item in enumerate(items):
                self.log_table.setItem(r, c, item)