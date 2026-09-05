"""
Dashboard -- NeuroFence SOC landing page built entirely on real data.

Top sections:
    * Welcome banner + five operational KPI cards
    * Risk Overview (overall risk score + Safe/Warning/Critical posture)
    * Risk Score Trend (real per-scan anomaly scores)
    * Threat Level Distribution (real severity distribution + benign models)
    * Recent Investigations (real pipeline runs, open / generate actions)
    * System Health (real availability probes)
    * Security pipeline visual + recent model activity / scans / findings

Every number rendered here comes from the live SQLite database. Empty and
loading states are explicit: when the database has no real records, the
page says so and offers navigation instead of fabricating numbers.
"""

from datetime import date, timedelta

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QSplitter, QScrollArea, QGridLayout, QButtonGroup,
)

from src.desktop import theme, data_service
from src.desktop.widgets import (
    PageHeader, KpiCard, Panel, DataTable, SectionHeader, WorkflowSteps,
    DonutGauge, TrendLine, ThreatDonut, HealthTile,
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

_PIPELINE_STEPS = [
    "IMPORT",
    "INTEGRITY",
    "STATIC VALIDATION",
    "BEHAVIOR SCAN",
    "ACTIVATION ANALYSIS",
    "RISK ENGINE",
    "DECISION",
]

_LEVEL_POSTURE = {
    "CRITICAL": ("CRITICAL", theme.CRITICAL),
    "HIGH": ("CRITICAL", theme.CRITICAL),
    "MEDIUM": ("WARNING", theme.WARNING),
    "LOW": ("SAFE", theme.SUCCESS),
}


class DashboardView(QWidget):
    def __init__(self, analyst: str = "Analyst", on_open_findings=None,
                 on_open_models=None, on_open_new_scan=None,
                 on_open_scan_history=None, on_watch_scan=None,
                 on_open_model=None, on_generate_report=None, parent=None):
        super().__init__(parent)
        self._analyst = analyst or "Analyst"
        self._on_open_findings = on_open_findings
        self._on_open_models = on_open_models
        self._on_open_new_scan = on_open_new_scan
        self._on_open_scan_history = on_open_scan_history
        self._on_watch_scan = on_watch_scan
        self._on_open_model = on_open_model
        self._on_generate_report = on_generate_report
        self._selected_scan = None
        self._sel_investigation = None
        self._trend_all = []
        self._trend_window = 30
        self._build_ui()
        self.refresh()

    # ---- UI ----

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(26, 22, 26, 26)
        root.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        header = PageHeader(
            f"Welcome back, {theme.html_translate(self._analyst)} \U0001F44B",
            subtitle=("Monitor and secure your AI models with forensic "
                      "analysis. Every value below comes from real local "
                      "scan, finding and report records."),
            chip_text="AIR-GAPPED  /  OFFLINE",
            chip_color=theme.SUCCESS,
        )
        root.addWidget(header)

        # ---- KPI cards (real, DB-derived) ----
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        self.card_investigations = KpiCard("ACTIVE INVESTIGATIONS", "0",
                                           accent=theme.ACCENT,
                                           sub="runs in progress",
                                           icon="\u25b6")
        self.card_models = KpiCard("MODELS REGISTERED", "0",
                                   accent=theme.ACCENT_SECONDARY,
                                   sub="in local registry",
                                   icon="\u25a6")
        self.card_scans = KpiCard("SCANS COMPLETED", "0",
                                  accent=theme.SUCCESS,
                                  sub="pipeline runs finished",
                                  icon="\u2713")
        self.card_threats = KpiCard("THREAT FINDINGS", "0",
                                    accent=theme.WARNING,
                                    sub="statistical + risk rows",
                                    icon="\u26a0")
        self.card_reports = KpiCard("REPORTS GENERATED", "0",
                                    accent=theme.ANALYTICS,
                                    sub="forensic reports on disk",
                                    icon="\u25a3")
        for c in [self.card_investigations, self.card_models, self.card_scans,
                  self.card_threats, self.card_reports]:
            row1.addWidget(c, 1)
        root.addLayout(row1)

        # ---- Risk overview + trend + distribution ----
        risk_cols = QSplitter(Qt.Horizontal)

        risk_panel = Panel("RISK OVERVIEW")
        risk_row = QHBoxLayout()
        risk_row.setSpacing(14)
        self.risk_gauge = DonutGauge(0.0, label="OVERALL RISK", level="NO DATA")
        self.risk_gauge.setMinimumSize(180, 190)
        risk_row.addWidget(self.risk_gauge)
        posture_col = QVBoxLayout()
        posture_col.setSpacing(8)
        self.posture_label = QLabel("NO DATA")
        self.posture_label.setStyleSheet(
            f"color:{theme.TEXT_DIM};font-size:18px;font-weight:700;"
            f"letter-spacing:1px;")
        posture_col.addWidget(self.posture_label)
        post_note = QLabel(
            "Safe / Warning / Critical posture derived from the real "
            "severity distribution of statistical findings."
        )
        post_note.setObjectName("PageSubtitle")
        post_note.setWordWrap(True)
        posture_col.addWidget(post_note)
        self._posture_chips = {}
        for key, (label, color) in _LEVEL_POSTURE.items():
            chip = QLabel(theme.status_chip_html(label, color))
            chip.setTextFormat(Qt.RichText)
            chip.setVisible(False)
            posture_col.addWidget(chip)
            self._posture_chips[key] = chip
        posture_col.addStretch(1)
        risk_row.addLayout(posture_col, 1)
        risk_panel.add_layout(risk_row)
        risk_panel.stretch()
        risk_cols.addWidget(risk_panel)

        trend_panel = Panel("RISK SCORE TREND")
        self.trend_filters = QHBoxLayout()
        self.trend_filters.setSpacing(6)
        self.trend_filters.addWidget(QLabel("WINDOW"))
        self._trend_buttons = {}
        self._trend_group = QButtonGroup(self)
        self._trend_group.setExclusive(True)
        for days, label in [(7, "7D"), (14, "14D"), (30, "30D"), (None, "ALL")]:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setObjectName("GhostButton")
            b.setFixedHeight(24)
            b.clicked.connect(lambda _=False, d=days: self._set_trend_window(d))
            self._trend_buttons[days] = b
            self._trend_group.addButton(b)
            self.trend_filters.addWidget(b)
        self._trend_buttons[30].setChecked(True)
        self.trend_filters.addStretch(1)
        self.trend_count = QLabel("")
        self.trend_count.setObjectName("KpiSub")
        self.trend_filters.addWidget(self.trend_count)
        trend_panel.add_layout(self.trend_filters)
        self.trend_line = TrendLine()
        self.trend_line.setMinimumHeight(170)
        trend_panel.add_widget(self.trend_line)
        self.trend_note = QLabel(
            "Real anomaly score of each completed scan in the selected window."
        )
        self.trend_note.setObjectName("PageSubtitle")
        trend_panel.add_widget(self.trend_note)
        trend_panel.stretch()
        risk_cols.addWidget(trend_panel)

        dist_panel = Panel("THREAT LEVEL DISTRIBUTION")
        self.dist_donut = ThreatDonut()
        self.dist_donut.setMinimumHeight(190)
        dist_panel.add_widget(self.dist_donut)
        dist_note = QLabel(
            "Critical / High / Medium / Low findings + models cleared as safe."
        )
        dist_note.setObjectName("PageSubtitle")
        dist_panel.add_widget(dist_note)
        dist_panel.stretch()
        risk_cols.addWidget(dist_panel)

        risk_cols.setSizes([330, 460, 380])
        root.addWidget(risk_cols)

        # ---- Recent investigations ----
        inv_title = SectionHeader("RECENT INVESTIGATIONS")
        root.addWidget(inv_title)
        inv_panel = Panel("")
        self.investigations_table = DataTable(
            ["ID", "STATUS", "MODEL", "PROMPTS", "FINDINGS", "RISK SCORE",
             "LAST UPDATED", "ACTION"],
            page_size=8, stretch_col=2,
        )
        self.investigations_table.set_cell_stylist(self._style_investigation_cell)
        self.investigations_table.rowActivated.connect(self._open_selected_investigation)
        self.investigations_table.rowSelected.connect(self._select_investigation)
        inv_panel.add_widget(self.investigations_table)
        inv_btns = QHBoxLayout()
        self.btn_watch = QPushButton("\u25b6  WATCH IN LIVE SCAN")
        self.btn_watch.setObjectName("PrimaryButton")
        self.btn_watch.clicked.connect(self._open_selected_investigation)
        self.btn_report = QPushButton("GENERATE REPORT")
        self.btn_report.setObjectName("GhostButton")
        self.btn_report.clicked.connect(self._generate_for_selected)
        inv_btns.addStretch(1)
        inv_btns.addWidget(self.btn_report)
        inv_btns.addWidget(self.btn_watch)
        inv_panel.add_layout(inv_btns)
        root.addWidget(inv_panel)

        # ---- System health ----
        health_title = SectionHeader("SYSTEM HEALTH")
        root.addWidget(health_title)
        health_panel = Panel("REAL AVAILABILITY PROBES")
        self.health_grid = QGridLayout()
        self.health_grid.setSpacing(10)
        self._health_tiles = []
        names = ["MODEL SANDBOX", "INFERENCE ENGINE", "ACTIVATION TRACKER",
                 "FORENSIC ENGINE", "STORAGE", "REPORT GENERATOR"]
        for i, name in enumerate(names):
            tile = HealthTile(name, "Checking...", ok=False)
            self.health_grid.addWidget(tile, i // 3, i % 3)
            self._health_tiles.append(tile)
        health_panel.add_layout(self.health_grid)
        root.addWidget(health_panel)

        # ---- Model security pipeline visual ----
        pipe_title = SectionHeader(
            "MODEL SECURITY PIPELINE "
            "<span style='color:{dim};font-size:10px;letter-spacing:1px;'>"
            "real end-to-end processing stages</span>".format(dim=theme.TEXT_DIM)
        )
        root.addWidget(pipe_title)
        pipe_panel = Panel("")
        self.pipeline_strip = WorkflowSteps(_PIPELINE_STEPS)
        self.pipeline_strip.setMinimumHeight(60)
        pipe_panel.add_widget(self.pipeline_strip)
        self.pipeline_note = QLabel(
            "Stages advance only when real database rows appear for each "
            "step of the scanning workflow."
        )
        self.pipeline_note.setObjectName("PageSubtitle")
        pipe_panel.add_widget(self.pipeline_note)
        root.addWidget(pipe_panel)

        # ---- Recent model activity ----
        act_title = SectionHeader("RECENT MODEL ACTIVITY")
        root.addWidget(act_title)
        self.activity_panel = Panel("")
        self.activity_table = DataTable(
            ["MODEL", "STATUS", "RISK", "FINDINGS", "LAST SCAN", "RECOMMENDATION"],
            page_size=6, stretch_col=0,
        )
        self.activity_table.set_cell_stylist(self._style_activity_cell)
        self.activity_table.rowActivated.connect(self._open_activity_model)
        self.activity_table.rowSelected.connect(self._open_activity_model)
        self.activity_panel.add_widget(self.activity_table)
        root.addWidget(self.activity_panel)

        # ---- Recent scans + findings ----
        cols = QSplitter(Qt.Horizontal)

        scans_panel = Panel("RECENT SCANS")
        self.scans_table = DataTable(
            ["ID", "STATUS", "MODEL", "PROMPTS", "FINDINGS", "SCORE", "CREATED"],
            page_size=6, stretch_col=2,
        )
        self.scans_table.set_cell_stylist(self._style_scan_cell)
        self.scans_table.rowActivated.connect(self._watch_selected_scan)
        scans_panel.add_widget(self.scans_table)
        scan_btns = QHBoxLayout()
        self.btn_history = QPushButton("OPEN SCAN HISTORY")
        self.btn_history.setObjectName("GhostButton")
        self.btn_history.clicked.connect(self._open_scan_history)
        scan_btns.addStretch(1)
        scan_btns.addWidget(self.btn_history)
        scans_panel.add_layout(scan_btns)
        cols.addWidget(scans_panel)

        findings_panel = Panel("RECENT SUSPICIOUS FINDINGS")
        self.findings_table = DataTable(
            ["SEVERITY", "LAYER", "FEATURE", "CATEGORY", "MODEL", "SCORE", "Z"],
            page_size=6, stretch_col=4,
        )
        self.findings_table.set_cell_stylist(self._style_finding_cell)
        self.findings_table.rowActivated.connect(self._open_findings)
        findings_panel.add_widget(self.findings_table)
        fbtns = QHBoxLayout()
        self.btn_all = QPushButton("OPEN FINDINGS")
        self.btn_all.setObjectName("GhostButton")
        self.btn_all.clicked.connect(self._open_findings)
        fbtns.addStretch(1)
        fbtns.addWidget(self.btn_all)
        findings_panel.add_layout(fbtns)
        cols.addWidget(findings_panel)

        cols.setSizes([520, 520])
        root.addWidget(cols)

        # Activation anomaly overview
        act_title2 = SectionHeader(
            "ACTIVATION ANOMALY OVERVIEW "
            "<span style='color:{dim};font-size:10px;letter-spacing:1px;'>"
            "real per-category activation aggregates</span>".format(dim=theme.TEXT_DIM)
        )
        root.addWidget(act_title2)
        act_panel = Panel("")
        self.activation_table = DataTable(
            ["CATEGORY", "MEASUREMENTS", "MEAN ACTIVATION", "NORMS",
             "ACTIVE %", "SUSPICIOUS"],
            page_size=6, stretch_col=0,
        )
        act_panel.add_widget(self.activation_table)
        root.addWidget(act_panel)

        # Empty-state CTA (shown when there is genuinely no data yet)
        self.cta_panel = QFrame()
        self.cta_panel.setObjectName("Panel")
        cta = QVBoxLayout(self.cta_panel)
        cta.setContentsMargins(20, 18, 20, 18)
        cta.setSpacing(10)
        cta_title = QLabel("NO DATA YET")
        cta_title.setObjectName("PanelTitle")
        cta.addWidget(cta_title)
        cta_msg = QLabel(
            "This dashboard only reflects real local records. Import a model "
            "and run an investigation to populate it \u2014 no synthetic "
            "statistics are shown."
        )
        cta_msg.setObjectName("PageSubtitle")
        cta_msg.setWordWrap(True)
        cta.addWidget(cta_msg)
        cta_btn = QHBoxLayout()
        self.btn_import = QPushButton("IMPORT MODEL")
        self.btn_import.setObjectName("PrimaryButton")
        self.btn_import.clicked.connect(self._open_models)
        self.btn_new_scan = QPushButton("NEW INVESTIGATION")
        self.btn_new_scan.setObjectName("GhostButton")
        self.btn_new_scan.clicked.connect(self._open_new_scan)
        cta_btn.addWidget(self.btn_import)
        cta_btn.addWidget(self.btn_new_scan)
        cta_btn.addStretch(1)
        cta.addLayout(cta_btn)
        root.addWidget(self.cta_panel)

    # ---- data ----

    def refresh(self):
        stats = data_service.dashboard_stats()
        inv = data_service.investigation_stats()

        self.card_investigations.set_value(str(inv["active_investigations"]))
        self.card_models.set_value(str(inv["models_registered"]))
        self.card_scans.set_value(str(inv["scans_completed"]))
        self.card_threats.set_value(str(inv["threat_findings"]))
        self.card_reports.set_value(str(inv["reports_generated"]))

        # Risk overview (real severity distribution -> score/level)
        rv = data_service.risk_overview()
        score = rv["score"]
        level = rv["level"]
        if score is None:
            self.risk_gauge.set_value(0.0, level="NO DATA")
            self.posture_label.setText("NO DATA")
            self.posture_label.setStyleSheet(
                f"color:{theme.TEXT_DIM};font-size:18px;font-weight:700;")
        else:
            self.risk_gauge.set_value(score, level=level)
            posture, color = _LEVEL_POSTURE.get(level, ("SAFE", theme.SUCCESS))
            self.posture_label.setText(f"OVERALL POSTURE: {posture}")
            self.posture_label.setStyleSheet(
                f"color:{color};font-size:18px;font-weight:700;letter-spacing:1px;")
        for key, chip in self._posture_chips.items():
            chip.setVisible(not (key == level))

        # Risk trend + threat distribution
        self._trend_all = data_service.risk_trend()
        self._apply_trend()
        self.dist_donut.set_data(data_service.threat_distribution()["items"])

        # System health probe tiles
        health = data_service.system_health()
        for name, tile in zip(
                ["MODEL SANDBOX", "INFERENCE ENGINE", "ACTIVATION TRACKER",
                 "FORENSIC ENGINE", "STORAGE", "REPORT GENERATOR"],
                self._health_tiles):
            match = next((c for c in health if c["name"] == name), None)
            if match:
                tile.set_state(match["ok"], match["detail"])

        # Recent investigations (real pipeline runs)
        runs = data_service.pipeline_runs(limit=8)
        inv_rows = []
        for r in runs:
            inv_rows.append([
                f"#{r['scan_id']}",
                r["status"],
                r["model"] or "?",
                str(r["total_prompts"]),
                str(r["findings_generated"]),
                f"{r['current_anomaly_score']:.1f}" if r["current_anomaly_score"] is not None else "-",
                (r["created_at"] or "?")[:19],
                "OPEN LIVE",
            ])
        self.investigations_table.set_rows(inv_rows, [r["scan_id"] for r in runs])
        self.btn_watch.setEnabled(False)
        self.btn_report.setEnabled(False)
        self._sel_investigation = None

        # Pipeline visual: real stage states
        activity = data_service.model_activity()
        decision_done = stats["safe_to_deploy"] > 0 or stats["quarantined_models"] > 0 or \
            any(a["status"] in ("review", "quarantined", "approved") for a in activity)
        verified = any(a["status"] in ("validated", "scanned", "approved",
                                       "review", "quarantined") for a in activity)
        stages = [
            bool(stats["total_models"]),
            stats["total_models"] > 0,
            verified,
            stats["scanned_today"] > 0 or bool(stats["scanned_models"]),
            bool(stats["activation_overview"]),
            stats["total_findings"] > 0,
            decision_done,
        ]
        done_count = sum(1 for s in stages if s)
        active = done_count if done_count < len(_PIPELINE_STEPS) else None
        self.pipeline_strip.set_progress(done_count, active)

        act_rows = []
        for a in activity:
            act_rows.append([
                a["file_name"],
                a["status_label"],
                a["risk_severity"] or "-",
                str(a["total_findings"]),
                a["last_scanned"],
                a["recommendation"],
            ])
        self.activity_table.set_rows(act_rows, [a["metadata_id"] for a in activity])

        scans_rows = []
        for r in stats["recent_scans"]:
            scans_rows.append([
                f"#{r['scan_id']}",
                r["status"],
                r["model"] or "?",
                f"{r['prompts_processed']} / {r['total_prompts']}",
                str(r["findings_generated"]),
                f"{r['current_anomaly_score']:.1f}" if r["current_anomaly_score"] is not None else "-",
                (r["created_at"] or "?")[:19],
            ])
        self.scans_table.set_rows(scans_rows, [r["scan_id"] for r in stats["recent_scans"]])

        find_rows = []
        for f in stats["recent_findings"]:
            find_rows.append([
                f["severity"],
                f["layer"],
                f["feature"],
                f["category"],
                f["model"] or "?",
                f"{f['anomaly_score']:.1f}",
                f"{f['z_score']:+.1f}" if f["z_score"] is not None else "-",
            ])
        self.findings_table.set_rows(find_rows, [f["finding_id"] for f in stats["recent_findings"]])

        act_rows = []
        for cat in stats["activation_overview"]:
            act_rows.append([
                cat["category"],
                f"{cat['measurements']:,}",
                f"{cat['mean']:.4f}",
                f"{cat['norm']:.4f}",
                f"{cat['active_fraction'] / 1.0 * 100:.1f}%",
                str(cat["suspicious"]),
            ])
        self.activation_table.set_rows(act_rows)

        has_data = bool(stats["total_models"] or stats["recent_scans"] or stats["total_findings"])
        self.cta_panel.setVisible(not has_data)

    # ---- styling ----

    def _set_trend_window(self, days):
        self._trend_window = days
        self._apply_trend()

    def _apply_trend(self):
        """Filter the real trend points to the selected day window."""
        points = list(self._trend_all)
        days = self._trend_window
        if days is not None:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            points = [p for p in points if not p.get("ts") or p["ts"] >= cutoff]
        self.trend_line.set_points(points)
        self.trend_count.setText(
            f"{len(points)} scan(s)" + (f" \u00b7 last {days}d" if days else " \u00b7 all time")
        )
        if days is None or len(points) == len(self._trend_all):
            self.trend_note.setText(
                "Real anomaly score of each completed scan, oldest to newest."
            )
        else:
            self.trend_note.setText(
                f"Real anomaly scores filtered to the last {days} days."
            )

    def _style_investigation_cell(self, _orig, item, col):
        if col == 1:
            status = item.text()
            item.setForeground(QColor(_PHASE_COLORS.get(status, theme.TEXT_PRIMARY)))
            item.setTextAlignment(Qt.AlignCenter)
        elif col in (0, 3, 4, 5, 6):
            item.setTextAlignment(Qt.AlignCenter)
        elif col == 7:
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(QColor(theme.ACCENT))

    def _style_activity_cell(self, _orig, item, col):
        if col == 1:
            status = item.text()
            color = {
                "VERIFIED": theme.SUCCESS, "APPROVED": theme.SUCCESS,
                "REVIEW REQUIRED": theme.WARNING,
                "QUARANTINED": theme.CRITICAL, "ERROR": theme.CRITICAL,
                "SCANNED": theme.WARNING, "UNVERIFIED": theme.ACCENT_SECONDARY,
            }.get(status, theme.TEXT_MUTED)
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignCenter)
        elif col == 2:
            severity = item.text()
            if severity != "-":
                item.setForeground(QColor("#0a0f1e"))
                item.setBackground(QColor(theme.risk_color(severity)))
            item.setTextAlignment(Qt.AlignCenter)
        elif col in (3,):
            item.setTextAlignment(Qt.AlignCenter)

    def _style_scan_cell(self, _orig, item, col):
        if col == 1:
            status = item.text()
            item.setForeground(QColor(_PHASE_COLORS.get(status, theme.TEXT_PRIMARY)))
            item.setTextAlignment(Qt.AlignCenter)
        elif col in (0, 3, 4, 5, 6):
            item.setTextAlignment(Qt.AlignCenter)

    def _style_finding_cell(self, _orig, item, col):
        if col == 0:
            item.setForeground(QColor("#0a0f1e"))
            item.setBackground(QColor(theme.risk_color(item.text())))
            item.setTextAlignment(Qt.AlignCenter)
        elif col in (5, 6):
            item.setTextAlignment(Qt.AlignCenter)

    # ---- actions ----

    def _select_investigation(self, scan_id):
        self._sel_investigation = scan_id
        state = data_service.pipeline_scan_state(scan_id) or {}
        is_done = state.get("is_terminal", False)
        self.btn_watch.setEnabled(True)
        self.btn_report.setEnabled(bool(is_done))

    def _open_selected_investigation(self, scan_id=None):
        target = scan_id or self._sel_investigation
        if target is None:
            target = self.investigations_table.current_row_index()
            if target < 0:
                return
        if self._on_watch_scan:
            self._on_watch_scan(target)
        elif self._on_open_scan_history:
            self._on_open_scan_history()

    def _generate_for_selected(self):
        if self._sel_investigation is None:
            return
        if self._on_generate_report:
            self._on_generate_report(self._sel_investigation)

    def _open_activity_model(self, metadata_id):
        if self._on_open_model:
            self._on_open_model(metadata_id)

    def _watch_selected_scan(self):
        target = self._selected_scan
        if target is None:
            target = self.scans_table.current_row_index()
            if target < 0:
                return
        if self._on_watch_scan:
            self._on_watch_scan(target)
        elif self._on_open_scan_history:
            self._on_open_scan_history()

    def _open_findings(self):
        if self._on_open_findings:
            self._on_open_findings()

    def _open_scan_history(self):
        if self._on_open_scan_history:
            self._on_open_scan_history()

    def _open_models(self):
        if self._on_open_models:
            self._on_open_models()

    def _open_new_scan(self):
        if self._on_open_new_scan:
            self._on_open_new_scan()

    def watch_scan(self, scan_id):
        """External navigation helper used by the main window."""
        self._selected_scan = scan_id
        self._watch_selected_scan()