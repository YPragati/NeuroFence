"""
Reports -- real forensic report center.

Lists the actual forensic reports stored in the database (generated from
real backend scan data), shows the metadata of the selected report, lets
the user generate a new report for any scan and open/download the PDF.
Includes a clear AIR-GAPPED / OFFLINE indicator. Every value is read from
the real `reports` table -- nothing is fabricated.
"""

import os
import shutil
import subprocess
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QHeaderView, QTableWidgetItem, QFileDialog,
    QApplication,
)

from src.desktop import theme, data_service
from src.desktop.widgets import (
    PageHeader, Panel, KpiCard, make_table, clear_table, show_toast,
    confirm_dialog,
)


class ReportsView(QWidget):
    def __init__(self, parent=None, on_notify=None):
        super().__init__(parent)
        self._report_rows = []
        self._sources = []
        self._last_report_path = None
        self._on_notify = on_notify
        self._building = False
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)

        header = PageHeader(
            "FORENSIC REPORT CENTER",
            subtitle="Real forensic reports generated from live backend scan data.",
            chip_text="AIR-GAPPED  /  OFFLINE",
            chip_color=theme.SUCCESS,
        )
        root.addWidget(header)

        # KPI row
        grid = QHBoxLayout()
        grid.setSpacing(12)
        self.kpi_total = KpiCard("TOTAL REPORTS", "0", accent=theme.ACCENT,
                                 sub="report rows in DB", icon="\u25a3")
        self.kpi_available = KpiCard("AVAILABLE", "0", accent=theme.SUCCESS,
                                     sub="files on disk", icon="\u2713")
        self.kpi_pending = KpiCard("PENDING", "0", accent=theme.WARNING,
                                   sub="queued (not tracked)", icon="\u23f3")
        self.kpi_missing = KpiCard("MISSING", "0", accent=theme.DANGER,
                                   sub="row without file", icon="\u2717")
        grid.addWidget(self.kpi_total)
        grid.addWidget(self.kpi_available)
        grid.addWidget(self.kpi_pending)
        grid.addWidget(self.kpi_missing)
        root.addLayout(grid)

        # Generate / open actions
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(QLabel("Generate for:"))
        self.combo_source = QComboBox()
        self.combo_source.setMinimumWidth(340)
        actions.addWidget(self.combo_source)
        self.btn_generate = QPushButton("Generate Report")
        self.btn_generate.setObjectName("PrimaryButton")
        self.btn_generate.clicked.connect(self._generate)
        actions.addWidget(self.btn_generate)
        self.btn_download = QPushButton("Download Report")
        self.btn_download.setObjectName("GhostButton")
        self.btn_download.clicked.connect(self._download)
        actions.addWidget(self.btn_download)
        self.btn_open = QPushButton("Open Report")
        self.btn_open.setObjectName("GhostButton")
        self.btn_open.clicked.connect(self._open_selected)
        actions.addWidget(self.btn_open)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        actions.addWidget(self.btn_refresh)
        actions.addStretch(1)
        root.addLayout(actions)

        # Reports list + details
        body = QHBoxLayout()
        body.setSpacing(12)

        list_panel = Panel("Generated Reports")
        self.table = make_table(
            ["REPORT", "INVESTIGATION", "MODEL", "FORMAT", "GENERATED", "STATUS"],
            stretch_col=0,
        )
        self.table.setSelectionBehavior(self.table.SelectRows)
        header_view = self.table.horizontalHeader()
        for col in range(6):
            header_view.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemSelectionChanged.connect(self._on_selection)
        list_panel.add_widget(self.table)
        body.addWidget(list_panel, 3)

        detail_panel = Panel("Report Details")
        self.detail_label = QLabel("Select a report to inspect its details.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextFormat(Qt.RichText)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_panel.add_widget(self.detail_label)
        body.addWidget(detail_panel, 2)
        root.addLayout(body, 1)

        self.status_label = QLabel("No report generated yet.")
        self.status_label.setObjectName("PageSubtitle")
        self.status_label.setTextFormat(Qt.RichText)
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Refresh (real data)
    # ------------------------------------------------------------------

    def refresh(self):
        reports = data_service.report_records()
        self._report_rows = reports

        # KPIs: total / available / pending / missing (all real rows)
        available = sum(1 for r in reports if r.get("exists"))
        missing = sum(1 for r in reports if not r.get("exists"))
        self.kpi_total.set_value(str(len(reports)))
        self.kpi_available.set_value(str(available),
                                     accent=(theme.SUCCESS if available else theme.TEXT_DIM))
        self.kpi_pending.set_value("0", accent=theme.WARNING)
        self.kpi_missing.set_value(str(missing),
                                   accent=(theme.DANGER if missing else theme.TEXT_DIM))
        if reports:
            latest = reports[0]
            if latest.get("exists"):
                self._last_report_path = latest["file_path"]
            else:
                self._last_report_path = None

        # Sources for generation
        sources = data_service.report_sources()
        self._sources = sources
        current = self.combo_source.currentData()
        self.combo_source.blockSignals(True)
        self.combo_source.clear()
        self.combo_source.addItem("Latest completed scan", None)
        for s in sources:
            tag = f"{'Scan' if s['kind'] == 'scan' else 'Run'} #{s['id']}"
            self.combo_source.addItem(
                f"[{tag}] {s['label']}  ({s['created_at']})  |  findings {s['findings'] or '—'}",
                {"kind": s["kind"], "id": s["id"]},
            )
        if current is not None:
            idx = self.combo_source.findData(current)
            if idx >= 0:
                self.combo_source.setCurrentIndex(idx)
        self.combo_source.blockSignals(False)

        self._populate_table()

    def _populate_table(self):
        clear_table(self.table)
        rows = []
        for r in self._report_rows:
            rows.append([
                f"Report #{r['report_id']}",
                f"#{r['scan_id']}" if r.get("scan_id") else "—",
                r.get("model") or "—",
                (r.get("format") or "").upper(),
                r.get("created_at", "").split(" ")[0],
                "ON DISK" if r.get("exists") else "MISSING",
            ])
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(val)
                if c in (0, 1, 3, 4):
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                item.setData(Qt.UserRole, r)
                self.table.setItem(r, c, item)
            status_item = self.table.item(r, 5)
            if status_item is not None:
                ok = row[5] == "ON DISK"
                status_item.setForeground(QColor(theme.SUCCESS if ok else theme.DANGER))
                status_item.setTextAlignment(Qt.AlignCenter)
        if rows:
            self.table.selectRow(0)
            self._show_detail(0)
        else:
            self.detail_label.setText("No reports generated yet. Pick a scan above and press Generate Report.")

    def _show_detail(self, row_idx):
        if row_idx < 0 or row_idx >= len(self._report_rows):
            return
        rec = self._report_rows[row_idx]
        dist = rec.get("severity_dist") or {}
        dist_txt = "  ".join(
            f'<span style="color:{theme.TEXT_MUTED};">{level}</span> '
            f'<b>{dist.get(level, 0)}</b>'
            for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        )
        exists = rec.get("exists")
        rows = [
            f'<span style="font-weight:700;color:{theme.TEXT_PRIMARY};font-size:15px;">'
            f'Report #{rec["report_id"]}</span>'
            f'<span style="color:{theme.SUCCESS if exists else theme.DANGER};">'
            f'  {"ON DISK" if exists else "MISSING"}</span>',
            f'<span style="color:{theme.TEXT_MUTED};">Generated</span> {rec["created_at"]}',
            f'<span style="color:{theme.TEXT_MUTED};">Scan ID</span> '
            f'{("#" + str(rec["scan_id"])) if rec.get("scan_id") else "—"}'
            f'<span style="color:{theme.TEXT_MUTED};">&nbsp;&nbsp;Run ID</span> {rec.get("run_id") or "—"}',
            f'<span style="color:{theme.TEXT_MUTED};">Model</span> {rec.get("model") or "—"}',
            f'<span style="color:{theme.TEXT_MUTED};">Findings</span> {rec.get("findings_total") if rec.get("findings_total") is not None else "—"}',
            f'<span style="color:{theme.TEXT_MUTED};">Risk index</span> '
            f'{(str(rec["overall_risk_score"]) + "/100") if rec.get("overall_risk_score") is not None else "not computed"}',
            f'<span style="color:{theme.TEXT_MUTED};">Severity distribution</span><br/>{dist_txt}',
            f'<span style="color:{theme.TEXT_MUTED};">Format</span> {(rec.get("format") or "pdf").upper()}',
        ]
        if rec.get("file_path"):
            rows.append(
                f'<br/><span style="font-family:{theme.MONO_FAMILY};font-size:10px;'
                f'color:{theme.TEXT_DIM};">{theme.html_translate(rec["file_path"])}</span>'
            )
        self.detail_label.setText("<br/>".join(rows))

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_selection(self):
        row = self.table.currentRow()
        if row >= 0:
            self._show_detail(row)

    def _selected_record(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._report_rows):
            return self._report_rows[row]
        return None

    # ------------------------------------------------------------------
    # Actions (real generation with loading + error handling)
    # ------------------------------------------------------------------

    def _set_building(self, building: bool):
        self._building = building
        self.btn_generate.setEnabled(not building)
        self.btn_download.setEnabled(not building)
        self.combo_source.setEnabled(not building)
        self.btn_generate.setText("Generating report..." if building else "Generate Report")
        if building:
            QApplication.processEvents()

    def _generate(self):
        if self._building:
            return
        selection = self.combo_source.currentData()
        scan_id = None
        run_id = None
        source_label = "Latest completed scan"
        if selection:
            if selection["kind"] == "scan":
                scan_id = selection["id"]
                source_label = f"Scan #{selection['id']}"
            else:
                run_id = selection["id"]
                source_label = f"Run #{selection['id']}"
        if not confirm_dialog(
            self, "Generate Forensic Report",
            f"Generate a full forensic PDF report for {source_label}?\n"
            "The report is built only from real database records.",
            ok_text="Generate Report",
            cancel_text="Cancel",
        ):
            return
        self._set_building(True)
        self.status_label.setText(
            f'<span style="color:{theme.WARNING};">Generating report for '
            f'{source_label}...</span>'
        )
        error = None
        path = None
        try:
            path = data_service.generate_forensic_report(scan_id=scan_id, run_id=run_id)
        except ValueError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 -- surface backend error
            error = f"{type(exc).__name__}: {exc}"
        if error is not None or not path:
            self._set_building(False)
            self.status_label.setText(
                f'<span style="color:{theme.DANGER};font-weight:700;">'
                f'&#10005; Report generation failed \u2014 {theme.html_translate(error or "no file produced")}</span>'
            )
            show_toast(self, f"Report generation failed: {error}", "error")
            return
        if not os.path.exists(path):
            self._set_building(False)
            self.status_label.setText(
                f'<span style="color:{theme.DANGER};font-weight:700;">'
                f'&#10005; Backend reported success but no file exists: '
                f'{theme.html_translate(path)}</span>'
            )
            show_toast(self, "Report generation failed: output file missing.", "error")
            return
        self._last_report_path = path
        self._set_building(False)
        self.refresh()
        if self._on_notify:
            self._on_notify(f"Report generated: {os.path.basename(path)}", "success")
        else:
            show_toast(self, f"Report generated: {os.path.basename(path)}", "success")
        size_kb = os.path.getsize(path) / 1024.0
        self.status_label.setText(
            f'<span style="color:{theme.SUCCESS};font-weight:700;">&#10003; '
            f'Report generated successfully.</span> '
            f'<span style="color:{theme.TEXT_MUTED};">{os.path.basename(path)} '
            f'\u00b7 {size_kb:.1f} KB</span>'
        )

    def _download(self):
        """Copy the selected report to a user-chosen location."""
        rec = self._selected_record()
        path = (rec or {}).get("file_path") or self._last_report_path
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "No report",
                                    "Generate a report first (PDF or Markdown).")
            return
        default_name = os.path.basename(path)
        target, _ = QFileDialog.getSaveFileName(
            self, "Download report", default_name,
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not target:
            return
        try:
            shutil.copy2(path, target)
        except OSError as exc:
            QMessageBox.critical(self, "Download Failed", str(exc))
            return
        if self._on_notify:
            self._on_notify(f"Report downloaded: {os.path.basename(target)}", "success")
        else:
            show_toast(self, f"Report downloaded: {os.path.basename(target)}", "success")

    def _open_selected(self):
        rec = self._selected_record()
        path = (rec or {}).get("file_path") or self._last_report_path
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "No report", "Generate a report first (PDF or Markdown).")
            return
        self._open_with_default(path)

    @staticmethod
    def _open_with_default(path):
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606 -- opening local generated report
        else:
            subprocess.Popen(["xdg-open", path])