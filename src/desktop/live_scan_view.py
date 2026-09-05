"""
Live Scan -- real pipeline scan monitoring page (investigation STEP 1-5).

Owned by the Scan Center: this page is the live monitor for a running
investigation and doubles as the RESULT view once the scan reaches a
terminal state. It polls the real backend-owned scan state (persisted to
SQLite by the scan subprocess) every ~700 ms and renders:

    * the six analysis pipeline stages (model loaded -> generating findings)
    * current phase, percentage, prompts/layers, findings, anomaly score
    * elapsed wall-clock time (from the real created_at timestamp)
    * a RESULT panel for terminal runs: risk score + classification +
      summary + working actions (View Findings / Generate / Open report)

A QTimer only drives the polling of real backend state -- nothing is
fabricated here.
"""

from datetime import datetime
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QProgressBar, QTableWidgetItem, QMessageBox,
)

from src.desktop import theme, data_service
from src.desktop.widgets import (
    PageHeader, Panel, KpiCard, FieldPair, make_table, clear_table,
    WorkflowSteps, show_toast,
)

POLL_MS = 700

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

# The six analysis pipeline stages shown while an investigation runs.
_ANALYZE_STAGES = [
    "MODEL LOADED",
    "PROMPTS GENERATED",
    "INFERENCE RUNNING",
    "CAPTURING ACTIVATIONS",
    "STATISTICAL ANALYSIS",
    "GENERATING FINDINGS",
]

# Backend phase -> how many of the six analysis stages are done.
_ANALYZE_ORDER = [
    "QUEUED",
    "INITIALIZING",
    "LOADING_MODEL",
    "GENERATING_INPUTS",
    "RUNNING_INFERENCE",
    "ANALYZING_ACTIVATIONS",
    "DETECTING_ANOMALIES",
    "COMPLETED",
]


class LiveScanView(QWidget):
    """Real-time backend-owned progress monitor for pipeline scans."""

    def __init__(self, parent=None, on_open_findings=None, on_open_results=None,
                 on_watch_scan=None):
        super().__init__(parent)
        self._scan_id = None
        self._report_path = None
        self._on_open_findings = on_open_findings or (lambda: None)
        self._on_open_results = on_open_results or (lambda scan_id: None)
        self._on_watch_scan = on_watch_scan or (lambda scan_id: None)
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._build_ui()
        self.refresh()

    def scan_id(self):
        return self._scan_id

    # ---- UI ----

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        header = PageHeader(
            "ANALYZE \u2014 LIVE INVESTIGATION",
            subtitle=("Stage-by-stage live analysis of the running "
                      "investigation \u2014 real backend progress only."),
            chip_text="REAL BACKEND PROGRESS",
            chip_color=theme.SUCCESS,
        )
        root.addWidget(header)

        # Analysis pipeline stages
        stage_panel = Panel("ANALYSIS PIPELINE")
        self.stage_strip = WorkflowSteps(_ANALYZE_STAGES)
        self.stage_strip.setMinimumHeight(52)
        stage_panel.add_widget(self.stage_strip)
        root.addWidget(stage_panel)

        # KPI cards
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_scan = KpiCard("INVESTIGATION ID", "-", accent=theme.ACCENT, sub="pipeline run")
        self.card_status = KpiCard("STATUS", "IDLE", accent=theme.ACCENT, sub="phase")
        self.card_elapsed = KpiCard("ELAPSED", "--", accent=theme.ACCENT_SECONDARY, sub="wall clock")
        self.card_prompts = KpiCard("PROMPTS", "0 / 0", accent=theme.WARNING, sub="measured / planned")
        self.card_layers = KpiCard("LAYERS", "0", accent=theme.WARNING, sub="analyzed")
        self.card_findings = KpiCard("FINDINGS", "0", accent=theme.CRITICAL, sub="generated")
        for c in [self.card_scan, self.card_status, self.card_elapsed,
                  self.card_prompts, self.card_layers, self.card_findings]:
            cards.addWidget(c, 1)
        root.addLayout(cards)

        # Live progress
        live = Panel("LIVE ANALYSIS PROGRESS (FROM BACKEND)")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        live.add_widget(self.progress)

        self.score_label = QLabel("CURRENT ANOMALY SCORE: --")
        self.score_label.setObjectName("PanelTitle")
        live.add_widget(self.score_label)

        self.message_label = QLabel("No investigation is being watched. Choose a run below.")
        self.message_label.setObjectName("PageSubtitle")
        self.message_label.setWordWrap(True)
        live.add_widget(self.message_label)
        root.addWidget(live)

        # STEP 5 -- Result panel (visible only for terminal investigations)
        self.result_panel = Panel("STEP 5 \u2014 RESULT")
        self.result_panel.setVisible(False)
        res_top = QHBoxLayout()
        res_top.setSpacing(14)
        res_text = QVBoxLayout()
        res_text.setSpacing(6)
        self.result_title = QLabel("INVESTIGATION COMPLETE")
        self.result_title.setStyleSheet(
            f"color:{theme.SUCCESS};font-size:19px;font-weight:700;letter-spacing:1px;")
        res_text.addWidget(self.result_title)
        self.result_class = QLabel("CLASSIFICATION: --")
        self.result_class.setStyleSheet(
            f"color:{theme.TEXT_PRIMARY};font-size:14px;font-weight:700;")
        res_text.addWidget(self.result_class)
        self.result_risk = QLabel("RISK SCORE: -- / 100")
        self.result_risk.setStyleSheet(
            f"color:{theme.ACCENT};font-size:22px;font-weight:700;")
        res_text.addWidget(self.result_risk)
        res_top.addLayout(res_text, 1)
        self.result_gauge_holder = QVBoxLayout()
        res_top.addLayout(self.result_gauge_holder)
        result_panel_layout = self.result_panel.layout()
        result_panel_layout.addLayout(res_top)

        self.result_summary = QVBoxLayout()
        self.result_summary.setSpacing(6)
        result_panel_layout.addLayout(self.result_summary)

        res_btns = QHBoxLayout()
        res_btns.setSpacing(10)
        self.btn_view_findings = QPushButton("\u26a0  VIEW FINDINGS")
        self.btn_view_findings.setObjectName("PrimaryButton")
        self.btn_view_findings.clicked.connect(self._view_findings)
        res_btns.addWidget(self.btn_view_findings)
        self.btn_generate = QPushButton("GENERATE REPORT")
        self.btn_generate.clicked.connect(self._generate_report)
        res_btns.addWidget(self.btn_generate)
        self.btn_open_report = QPushButton("OPEN / DOWNLOAD REPORT")
        self.btn_open_report.clicked.connect(self._open_report)
        self.btn_open_report.setEnabled(False)
        res_btns.addWidget(self.btn_open_report)
        res_btns.addStretch(1)
        result_panel_layout.addLayout(res_btns)
        root.addWidget(self.result_panel)

        # Run picker + controls
        ctl = Panel("WATCH AN INVESTIGATION")
        ctl_row = QHBoxLayout()
        self.run_picker = QComboBox()
        self.run_picker.setMinimumWidth(420)
        ctl_row.addWidget(self.run_picker, 1)

        self.btn_refresh = QPushButton("Refresh Runs")
        self.btn_refresh.setObjectName("GhostButton")
        self.btn_refresh.clicked.connect(self.refresh)
        ctl_row.addWidget(self.btn_refresh)

        self.btn_cancel = QPushButton("\u2715 CANCEL")
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.setStyleSheet(
            f"QPushButton{{background:transparent;border:1px solid "
            f"{theme.DANGER};color:{theme.DANGER};font-weight:700;}}"
            f"QPushButton:hover{{background:{theme.DANGER}22;}}"
            f"QPushButton:disabled{{color:{theme.TEXT_DIM};"
            f"border-color:{theme.BORDER};background:transparent;}}"
        )
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_scan)
        ctl_row.addWidget(self.btn_cancel)
        ctl.add_layout(ctl_row)
        root.addWidget(ctl)

        # Activity log
        log_panel = Panel("ACTIVITY LOG")
        self.log_table = make_table(["TIME", "PHASE", "MESSAGE"], stretch_col=2)
        log_panel.add_widget(self.log_table)
        root.addWidget(log_panel, 1)

    # ---- data ----

    def refresh(self):
        runs = data_service.pipeline_runs(limit=20)
        self.run_picker.blockSignals(True)
        self.run_picker.clear()
        self.run_picker.addItem("-- watch an investigation --", None)
        for r in runs:
            self.run_picker.addItem(
                f"#{r['scan_id']}  {r['status']}  {r['percentage']:.0f}%  "
                f"({r['model'] or 'tiny'})",
                r["scan_id"],
            )
        if self._scan_id:
            idx = self.run_picker.findData(self._scan_id)
            if idx >= 0:
                self.run_picker.setCurrentIndex(idx)
        self.run_picker.blockSignals(False)
        try:
            self.run_picker.currentIndexChanged.disconnect(self._on_pick_run)
        except TypeError:
            pass
        self.run_picker.currentIndexChanged.connect(self._on_pick_run)

        if not self._scan_id:
            self._set_idle()

    def watch_scan(self, scan_id):
        """Start watching the given pipeline scan id (real backend state)."""
        self._scan_id = int(scan_id)
        self._select_run(self._scan_id)
        self._timer.start()
        state = data_service.pipeline_scan_state(self._scan_id)
        if state:
            self._apply_state(state)

    # ---- actions ----

    def _set_idle(self):
        self.card_scan.set_value("-")
        self.card_status.set_value("IDLE", accent=theme.ACCENT)
        self.card_elapsed.set_value("--")
        self.card_prompts.set_value("0 / 0")
        self.card_layers.set_value("0")
        self.card_findings.set_value("0")
        self.progress.setValue(0)
        self.score_label.setText("CURRENT ANOMALY SCORE: --")
        self.message_label.setText("No investigation is being watched. Choose a run above.")
        clear_table(self.log_table)
        self.btn_cancel.setEnabled(False)
        self.result_panel.setVisible(False)
        self.stage_strip.set_progress(0, None)

    def _view_findings(self):
        self._on_open_findings()

    def _generate_report(self):
        if not self._scan_id:
            return
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Generating...")
        try:
            path = data_service.generate_forensic_report(scan_id=self._scan_id)
        except Exception as exc:  # noqa: BLE001 -- surface backend error
            self.btn_generate.setEnabled(True)
            self.btn_generate.setText("GENERATE REPORT")
            self.message_label.setText(f"Report generation failed: {exc}")
            show_toast(self, f"Report generation failed: {exc}", "error")
            return
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("GENERATE REPORT")
        self._report_path = path
        self.btn_open_report.setEnabled(True)
        self.message_label.setText(
            f"Report generated successfully: {os.path.basename(path)}")
        show_toast(self, "Report generated successfully.", "success")
        if self._on_open_results:
            self._on_open_results(self._scan_id)

    def _find_existing_report(self):
        """Return the on-disk path of an existing report for the scan."""
        try:
            for r in data_service.report_records(limit=200):
                if r.get("scan_id") == self._scan_id and r.get("exists"):
                    return r["file_path"]
        except Exception:  # noqa: BLE001
            pass
        return None

    def _open_report(self):
        path = self._report_path or self._find_existing_report()
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "No report", "Generate a report first.")
            return
        try:
            os.startfile(path)  # noqa: S606 -- opening local generated report
        except OSError as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _cancel_scan(self):
        if not self._scan_id:
            return
        try:
            data_service.pipeline_cancel(self._scan_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Cancel Failed", str(exc))
        self._apply_state(data_service.pipeline_scan_state(self._scan_id))

    # ---- polling ----

    def _poll(self):
        if not self._scan_id:
            self._timer.stop()
            self.refresh()
            return
        state = data_service.pipeline_scan_state(self._scan_id)
        if state is None:
            self._timer.stop()
            self._scan_id = None
            self.refresh()
            return
        self._apply_state(state)
        if state.get("is_terminal"):
            self._timer.stop()
            self.btn_cancel.setEnabled(False)
            self._refresh_runs()

    def _on_pick_run(self, _index):
        scan_id = self.run_picker.currentData()
        if scan_id is None:
            self._scan_id = None
            self._set_idle()
            return
        self._scan_id = scan_id
        self._timer.start()
        state = data_service.pipeline_scan_state(scan_id)
        if state:
            self._apply_state(state)

    def _select_run(self, scan_id):
        idx = self.run_picker.findData(scan_id)
        if idx >= 0:
            self.run_picker.setCurrentIndex(idx)

    def _elapsed_text(self, created_at):
        try:
            start = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=datetime.now().astimezone().tzinfo)
            delta = datetime.now().astimezone() - start
            secs = int(delta.total_seconds())
            if secs < 0:
                secs = 0
            return f"{secs // 60}:{secs % 60:02d}"
        except Exception:  # noqa: BLE001 -- no timestamp, no elapsed
            return "--"

    def _apply_state(self, state):
        if not state:
            return
        status = state.get("status", "IDLE")
        self.card_scan.set_value(f"#{state['scan_id']}")
        self.card_status.set_value(status, accent=_PHASE_COLORS.get(status, theme.ACCENT))
        self.card_elapsed.set_value(self._elapsed_text(state.get("created_at")))
        self.card_prompts.set_value(
            f"{state.get('prompts_processed', 0)} / {state.get('total_prompts', 0)}")
        self.card_layers.set_value(str(state.get("layers_analyzed", 0)))
        self.card_findings.set_value(str(state.get("findings_generated", 0)))

        percent = float(state.get("percentage", 0.0))
        self.progress.setValue(int(percent))

        score = state.get("current_anomaly_score")
        if score is None:
            self.score_label.setText("CURRENT ANOMALY SCORE: --")
        else:
            self.score_label.setText(
                f"CURRENT ANOMALY SCORE: {float(score):.1f} / 100")

        log = state.get("activity_log") or []
        if log:
            last = log[-1]["message"]
        else:
            last = "Waiting for the investigation to report..."
        self.message_label.setText(f"[{status}] {last}")
        self.btn_cancel.setEnabled(not bool(state.get("is_terminal", True)))

        self._populate_log(log)
        self._update_stage_strip(status)
        self._update_result(status, state, score)

    def _update_stage_strip(self, status):
        if status not in _ANALYZE_ORDER:
            self.stage_strip.set_progress(0, None)
            return
        idx = _ANALYZE_ORDER.index(status)
        if status == "COMPLETED":
            self.stage_strip.set_progress(len(_ANALYZE_STAGES), None)
        elif status == "FAILED" or status == "CANCELLED":
            self.stage_strip.set_progress(0, None)
        elif status == "QUEUED":
            self.stage_strip.set_progress(0, 0)
        else:
            self.stage_strip.set_progress(idx - 1, min(idx - 1, len(_ANALYZE_STAGES) - 1))

    # ---- result panel ----

    def _model_severity_dist(self, model_name):
        dist = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        try:
            for f in data_service.statistical_findings(limit=5000):
                if (f.get("model") or "") == (model_name or "") and f.get("severity") in dist:
                    dist[f["severity"]] += 1
        except Exception:  # noqa: BLE001 -- best-effort
            pass
        return dist

    def _update_result(self, status, state, score):
        if status != "COMPLETED":
            self.result_panel.setVisible(False)
            return
        self.result_panel.setVisible(True)

        dist = self._model_severity_dist(state.get("model") or "")
        worst = next((lv for lv in ("CRITICAL", "HIGH", "MEDIUM", "LOW") if dist.get(lv)), None)
        classification = worst or "BENIGN"
        color = theme.risk_color(worst) if worst else theme.SUCCESS
        self.result_class.setText(
            f"CLASSIFICATION: {classification}"
            + ("  (worst real severity present)" if worst else "  (no severity findings)"))
        self.result_class.setStyleSheet(
            f"color:{color};font-size:14px;font-weight:700;")
        risk_txt = (f"{float(score):.0f} / 100" if score is not None else "-- / 100")
        self.result_risk.setText(f"RISK SCORE: {risk_txt}")
        self.result_risk.setStyleSheet(
            f"color:{color};font-size:22px;font-weight:700;")
        self.result_title.setText("INVESTIGATION COMPLETE" if worst else "INVESTIGATION COMPLETE \u2014 CLEAN")

        total_prompts = state.get("total_prompts", 0)
        high_risk = dist.get("HIGH", 0) + dist.get("CRITICAL", 0)
        summary = [
            ("Measurements", f"{state.get('prompts_processed',0) * max(1, state.get('layers_analyzed',1)):,}"),
            ("Layers Analyzed", str(state.get("layers_analyzed", 0))),
            ("Prompts Tested", str(total_prompts)),
            ("Anomalies Detected", str(state.get("findings_generated", 0))),
            ("High Risk Findings", str(high_risk)),
        ]
        while self.result_summary.count():
            item = self.result_summary.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for label, value in summary:
            self.result_summary.addWidget(FieldPair(label, value))

        if self._report_path is None:
            self._report_path = self._find_existing_report()
        self.btn_open_report.setEnabled(bool(self._report_path))

    def _populate_log(self, log):
        clear_table(self.log_table)
        rows = list(reversed(log[-200:]))
        self.log_table.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            phase = entry.get("phase", "")
            items = [
                QTableWidgetItem(entry.get("ts", "")),
                QTableWidgetItem(phase),
                QTableWidgetItem(entry.get("message", "")),
            ]
            items[1].setTextAlignment(Qt.AlignCenter)
            color = _PHASE_COLORS.get(phase, theme.TEXT_PRIMARY)
            items[1].setForeground(QColor(color))
            for c, item in enumerate(items):
                self.log_table.setItem(r, c, item)

    def _refresh_runs(self):
        self.refresh()