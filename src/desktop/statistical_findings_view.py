"""
Statistical Findings -- real statistical anomaly detection page.

Lists StatisticalFinding rows produced by src.anomaly_detection.
statistical_engine over real activation measurements. Every value shown
(severity, layer, feature, anomaly score, confidence, explanation,
evidence) comes straight from the database -- nothing is fabricated.

The page is explicitly honest about what the statistics mean: an anomaly
here flags *potentially suspicious activation behavior*, not proof of a
backdoor.
"""

import json

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSplitter, QFileDialog,
)

from src.desktop import theme, data_service
from src.desktop.widgets import PageHeader, KpiCard, Panel, clear_table

_COLUMNS = ["SEVERITY", "LAYER", "FEATURE", "CATEGORY", "PROMPT",
            "SCORE", "CONFIDENCE", "Z-SCORE"]
_SEVERITIES = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"]


class StatisticalFindingsView(QWidget):
    """Findings page for the statistical anomaly detection engine."""

    def __init__(self, parent=None, on_inspect_layer=None):
        super().__init__(parent)
        self._runs = []
        self._items = []
        self._on_inspect_layer = on_inspect_layer
        self._build_ui()
        self.refresh()

    # ---- UI ----

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        header = PageHeader(
            "STATISTICAL FINDINGS",
            subtitle=(
                "Real statistical anomaly detection over activation "
                "measurements from local adversarial scans."
            ),
            chip_text="STATISTICAL / CORRELATIONAL",
            chip_color=theme.PRIMARY,
        )
        root.addWidget(header)

        disclaimer = QLabel(
            "\u26a0  Statistical findings identify POTENTIALLY SUSPICIOUS "
            "activation behavior. They are not proof of a neural backdoor."
        )
        disclaimer.setObjectName("PageSubtitle")
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(f"color:{theme.WARNING};")
        root.addWidget(disclaimer)

        # KPI cards
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_critical = KpiCard("CRITICAL", "0", accent=theme.CRITICAL, sub="severe", icon="\u26a0")
        self.card_high = KpiCard("HIGH", "0", accent=theme.DANGER, sub="threshold", icon="\u26a0")
        self.card_medium = KpiCard("MEDIUM", "0", accent=theme.WARNING, sub="watch", icon="\u26a0")
        self.card_low = KpiCard("LOW", "0", accent=theme.SAFE, sub="benign", icon="\u26a0")
        self.card_benign = KpiCard("BENIGN", "0", accent=theme.SUCCESS, sub="models cleared", icon="\u2713")
        for c in [self.card_critical, self.card_high, self.card_medium,
                  self.card_low, self.card_benign]:
            cards.addWidget(c, 1)
        root.addLayout(cards)

        # Controls
        controls = Panel("ANALYSIS CONTROLS")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("Scan Run"))
        self.combo_run = QComboBox()
        self.combo_run.setMinimumWidth(320)
        row.addWidget(self.combo_run)
        row.addWidget(QLabel("Severity"))
        self.combo_severity = QComboBox()
        for s in _SEVERITIES:
            self.combo_severity.addItem(s)
        row.addWidget(self.combo_severity)
        row.addStretch(1)
        self.btn_analyze = QPushButton("\u25b6  ANALYZE SELECTED RUN")
        self.btn_analyze.setObjectName("PrimaryButton")
        self.btn_analyze.clicked.connect(self._analyze)
        row.addWidget(self.btn_analyze)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("GhostButton")
        self.btn_refresh.clicked.connect(self.refresh)
        row.addWidget(self.btn_refresh)
        controls.add_layout(row)
        self.status_label = QLabel("Loading findings...")
        self.status_label.setObjectName("PageSubtitle")
        self.status_label.setWordWrap(True)
        controls.add_widget(self.status_label)
        root.addWidget(controls)

        # Table + evidence splitter
        splitter = QSplitter(Qt.Horizontal)

        left = Panel("STATISTICAL FINDINGS (REAL DATA)")
        self.table = _make_findings_table()
        self.table.itemSelectionChanged.connect(self._on_selection)
        left.add_widget(self.table)
        splitter.addWidget(left)

        right = Panel("EXPLANATION & EVIDENCE")
        self.detail = QLabel("Select a finding to inspect its evidence.")
        self.detail.setObjectName("PageSubtitle")
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.RichText)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.add_widget(self.detail)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_inspect = QPushButton("INSPECT LAYER")
        self.btn_inspect.setObjectName("GhostButton")
        self.btn_inspect.setEnabled(False)
        self.btn_inspect.clicked.connect(self._inspect_layer)
        btn_row.addWidget(self.btn_inspect)
        self.btn_export = QPushButton("EXPORT EVIDENCE (JSON)")
        self.btn_export.setObjectName("GhostButton")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_evidence)
        btn_row.addWidget(self.btn_export)
        btn_row.addStretch(1)
        right.add_layout(btn_row)
        right.stretch()
        splitter.addWidget(right)

        splitter.setSizes([860, 420])
        root.addWidget(splitter, 1)

    # ---- data ----

    def selected_run_id(self):
        idx = self.combo_run.currentIndex()
        if idx < 0 or idx >= len(self._runs):
            return None
        return self._runs[idx]["run_id"]

    def refresh(self):
        from src.desktop import data_service as ds

        try:
            self._runs = ds.statistical_scan_runs(limit=50)
        except Exception:  # noqa: BLE001 -- views degrade to empty state
            self._runs = []

        current = self.selected_run_id()
        self.combo_run.blockSignals(True)
        self.combo_run.clear()
        for r in self._runs:
            label = f"Run #{r['run_id']}  \u2014  {r['run_label']}  ({r['measurement_count']} measurements)"
            self.combo_run.addItem(label, r["run_id"])
        if current is not None:
            for i in range(self.combo_run.count()):
                if self.combo_run.itemData(i) == current:
                    self.combo_run.setCurrentIndex(i)
                    break
        self.combo_run.blockSignals(False)

        if not self._runs:
            self._set_empty("No completed scans available yet. Run a scan on "
                            "the New Scan page, then analyze a run here.")
            return

        self._load()

    def _set_empty(self, msg):
        clear_table(self.table)
        self.card_critical.set_value("0")
        self.card_high.set_value("0")
        self.card_medium.set_value("0")
        self.card_low.set_value("0")
        self.card_benign.set_value("0")
        self.btn_inspect.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.status_label.setText(msg)
        self.detail.setText("No findings to inspect.")

    def _load(self):
        from src.desktop import data_service as ds

        run_id = self.selected_run_id()
        severity = self.combo_severity.currentText()
        if severity == "ALL":
            severity = None

        try:
            items = ds.statistical_findings(run_id=run_id, severity=severity, limit=2000)
            summary = ds.statistical_summary(run_id=run_id)
        except Exception as exc:  # noqa: BLE001
            self._set_empty(f"Could not load findings: {exc}")
            return

        self._items = items
        dist = summary["severity_distribution"]
        self.card_critical.set_value(str(dist.get("CRITICAL", 0)))
        self.card_high.set_value(str(dist.get("HIGH", 0)))
        self.card_medium.set_value(str(dist.get("MEDIUM", 0)))
        self.card_low.set_value(str(dist.get("LOW", 0)))
        try:
            benign = data_service.threat_distribution()["severity_distribution"].get("BENIGN", 0)
        except Exception:  # noqa: BLE001 -- benign count is best-effort
            benign = 0
        self.card_benign.set_value(str(benign))
        self.btn_inspect.setEnabled(False)
        self.btn_export.setEnabled(False)

        run = next((r for r in self._runs if r["run_id"] == run_id), None)
        run_info = f"Run #{run_id}" if run else "All scans"
        self.status_label.setText(
            f"{summary['total']} findings ({run_info}) \u2014 "
            f"{dist.get('CRITICAL', 0)} critical, {dist.get('HIGH', 0)} high, "
            f"{dist.get('MEDIUM', 0)} medium, {dist.get('LOW', 0)} low."
        )

        self._populate_table()

    def _populate_table(self):
        self.table.setRowCount(len(self._items))
        for i, f in enumerate(self._items):
            prompt = f.get("prompt_id", "").split("-")[-1] or f.get("prompt_id", "")
            if f.get("prompt_id"):
                prompt = f["prompt_id"]
            vals = [
                f["severity"],
                f["layer"],
                f["feature"],
                f["category"],
                prompt,
                f"{f['anomaly_score']:.1f}",
                f"{f['confidence']:.0%}",
                f"{f['z_score']:+.1f}",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if j == 0:
                    item.setForeground(QColor("#0a0f1e"))
                    item.setBackground(QColor(theme.risk_color(f["severity"])))
                    item.setTextAlignment(Qt.AlignCenter)
                elif j in (5, 6, 7):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, j, item)
                item.setData(Qt.UserRole, i)

    # ---- actions ----

    def _analyze(self):
        run_id = self.selected_run_id()
        if run_id is None:
            self.status_label.setText("Select a completed scan run to analyze.")
            return
        try:
            result = data_service.detect_statistical_findings(run_id=run_id, force=True)
        except Exception as exc:  # noqa: BLE001 -- surface to UI
            self.status_label.setText(f"Analysis failed: {exc}")
            return
        dist = result.get("severity_distribution", {})
        self.status_label.setText(
            f"Analyzed run #{result.get('run_id')}: "
            f"{result.get('findings_created', 0)} findings "
            f"({dist.get('CRITICAL', 0)} critical, {dist.get('HIGH', 0)} high). "
            + "Potentially suspicious activation behavior \u2014 not proof of a backdoor."
        )
        self._load()

    def _current_row(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return -1
        r = sel[0].row()
        return r if 0 <= r < len(self._items) else -1

    def _on_selection(self):
        r = self._current_row()
        if r < 0:
            return
        self._show_detail(self._items[r])

    def _current_finding(self):
        r = self._current_row()
        if r < 0 or r >= len(self._items):
            return None
        return self._items[r]

    def _show_detail(self, f):
        color = theme.risk_color(f["severity"])
        try:
            ev = json.loads(f.get("evidence") or "{}")
        except (TypeError, ValueError):
            ev = {}

        rows = [
            ("LAYER", f["layer"]),
            ("FEATURE", f["feature"]),
            ("INPUT CATEGORY", f["category"]),
            ("PROMPT", f.get("prompt_id") or "-"),
            ("MODEL", f.get("model") or "-"),
            ("ANOMALY SCORE", f"{f['anomaly_score']:.1f} / 100"),
            ("CONFIDENCE", f"{f['confidence']:.0%}"),
            ("Z-SCORE", f"{f['z_score']:+.2f}\u03c3"),
            ("OBSERVED STATISTIC", f"{f['observed_statistic']:.5g}"),
            ("BASELINE STATISTIC", f"{f['baseline_mean']:.5g} \u00b1 {f['baseline_std']:.5g} (N={f['baseline_n']})"),
            ("MEAN DEVIATION",
             f"{f['mean_deviation']:+.1%}" if f.get("mean_deviation") is not None else "-"),
            ("ENERGY DEVIATION",
             f"{f['energy_deviation']:+.1%}" if f.get("energy_deviation") is not None else "-"),
            ("ACTIVATION CORRELATION",
             f"{f['correlation']:.3f}" if f.get("correlation") is not None else "-"),
            ("SCAN", f.get("scan_label") or str(f.get("run_id"))),
        ]
        body = "".join(
            f'<tr><td style="color:{theme.TEXT_DIM};width:170px;">{k}</td>'
            f'<td style="color:{theme.TEXT_PRIMARY};">{theme.html_translate(v)}</td></tr>'
            for k, v in rows
        )

        feature_devs = ev.get("all_features", {})
        dev_rows = ""
        for met, dev in feature_devs.items():
            dev_rows += (
                f'<tr><td style="color:{theme.TEXT_DIM};width:170px;">{met}</td>'
                f'<td>observed {dev.get("observed", 0):.4g} vs baseline '
                f'{dev.get("baseline_mean", 0):.4g} '
                f'(z {dev.get("z_score", 0):+.2f})</td></tr>'
            )

        input_text = ev.get("input_text") or ""
        if len(input_text) > 400:
            input_text = input_text[:400] + "... "

        html = f"""
        <div style="margin-bottom:6px;">
          <span style="color:{color};font-size:15px;font-weight:700;letter-spacing:1px;">
            {theme.html_translate(f['severity'])} &middot; {theme.html_translate(f['layer'])} :: {theme.html_translate(f['feature'])}</span>
        </div>
        <div style="color:{theme.TEXT_MUTED};font-size:12px;margin-bottom:10px;">
          {theme.html_translate(f.get('explanation',''))}
        </div>
        <div style="margin:10px 0 4px 0;color:{theme.TEXT_DIM};font-weight:700;letter-spacing:1px;">
          WHY THIS WAS FLAGGED</div>
        <div style="color:{theme.TEXT_MUTED};font-size:12px;margin-bottom:10px;">
          The layer/feature activation profile deviates from its real baseline
          statistics. This is a potential anomaly that requires investigation
          \u2014 it is not proof of a neural backdoor.</div>
        <table style="color:{theme.TEXT_MUTED};font-size:12px;" cellspacing="5">
        {body}
        </table>
        <div style="margin-top:12px;color:{theme.TEXT_MUTED};font-weight:700;">PER-FEATURE DEVIATIONS</div>
        <table style="color:{theme.TEXT_MUTED};font-size:12px;" cellspacing="5">
        {dev_rows}
        </table>
        """
        if input_text:
            html += (
                f'<div style="margin-top:12px;color:{theme.TEXT_MUTED};font-weight:700;">INPUT</div>'
                f'<div style="margin-top:4px;font-family:{theme.MONO_FAMILY};font-size:11px;'
                f'color:{theme.TEXT_MUTED};background:{theme.BG_DEEP};'
                f'border:1px solid {theme.BORDER};border-radius:6px;padding:10px;">'
                f'{theme.html_translate(input_text)}</div>'
            )
        self.detail.setText(html)
        self.btn_inspect.setEnabled(True)
        self.btn_export.setEnabled(True)

    def _inspect_layer(self):
        f = self._current_finding()
        if f is None:
            return
        if self._on_inspect_layer:
            self._on_inspect_layer(f.get("layer") or "")

    def _export_evidence(self):
        f = self._current_finding()
        if f is None:
            return
        default = f"finding_{f['run_id']}_{f['layer']}_{f['feature']}.json"
        target, _ = QFileDialog.getSaveFileName(
            self, "Export finding evidence", default,
            "JSON files (*.json);;All files (*.*)",
        )
        if not target:
            return
        payload = dict(f)
        try:
            payload["evidence"] = json.loads(f.get("evidence") or "{}")
        except (TypeError, ValueError):
            pass
        try:
            with open(target, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
        except OSError as exc:  # noqa: BLE001 -- surface to UI
            self.status_label.setText(f"Export failed: {exc}")
            return
        self.status_label.setText(f"Evidence exported to {target}")


def _make_findings_table():
    from src.desktop.widgets import make_table
    table = make_table(_COLUMNS, stretch_col=4)
    header = table.horizontalHeader()
    for col in (1, 2, 3):
        header.setSectionResizeMode(col, QHeaderView.Stretch)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    return table