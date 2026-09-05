"""
Main Window -- NeuroFence AI Model Forensics platform.

Enterprise SOC shell with a left navigation rail:
    + Brand block (NEUROFENCE / AI MODEL FORENSICS)
    + Grouped nav: OVERVIEW / INVESTIGATE / EVIDENCE / SYSTEM
    + Footer: "All Systems Operational" live status + analyst + sign out
    + Right-hand top bar: page context, operator meta, security chip
    + Live security-workflow strip (MODEL -> INTEGRITY -> SCAN ->
      ANALYSIS -> RISK -> DECISION) whose stages derive only from real
      database rows and auto-advance as scans complete.

Scans run in a background QThread (PipelineScanWorker) that supervises the
backend subprocess; progress is rendered only from the real rows the scan
writes to the database -- never fabricated.
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QApplication, QDialog, QToolButton, QMenu,
)

from src.desktop import theme, data_service
from src.desktop.workers import PipelineScanWorker
from src.desktop.widgets import show_toast, WorkflowSteps, Sidebar

from src.desktop.dashboard_view import DashboardView
from src.desktop.models_view import ModelsView
from src.desktop.model_detail_view import ModelDetailView, ModelScannerView
from src.desktop.scan_center_view import ScanCenterView
from src.desktop.activation_explorer_view import ActivationExplorerView
from src.desktop.findings_view import SecurityFindingsView
from src.desktop.reports_view import ReportsView
from src.desktop.settings_view import SettingsView
from src.desktop.audit_logs_view import AuditLogsView

# (group label, [(page key, glyph, label)])
NAV_GROUPS = [
    ("OVERVIEW", [
        ("dashboard", "\u25c9", "Dashboard"),
    ]),
    ("INVESTIGATE", [
        ("new_investigation", "\u002b", "New Investigation"),
        ("investigations", "\u25c6", "Investigations"),
    ]),
    ("FORENSICS", [
        ("findings", "\u26a0", "Findings"),
        ("analysis", "\u25c8", "Activation Explorer"),
        ("scan_history", "\u25b9", "Scan History"),
    ]),
    ("MODELS", [
        ("models", "\u25a6", "Model Registry"),
        ("model_scanner", "\u25a0", "Model Scanner"),
    ]),
    ("REPORTING", [
        ("reports", "\u25a3", "Security Reports"),
    ]),
    ("SYSTEM", [
        ("settings", "\u2692", "Settings"),
        ("audit", "\u270e", "Audit Logs"),
    ]),
]

# page key -> (page-site label, sidebar key that stays checked)
_PAGE_TITLES = {
    "dashboard": "DASHBOARD",
    "new_investigation": "NEW INVESTIGATION",
    "investigations": "INVESTIGATIONS",
    "findings": "FINDINGS",
    "analysis": "ACTIVATION EXPLORER",
    "scan_history": "SCAN HISTORY",
    "models": "MODEL REGISTRY",
    "model_scanner": "MODEL SCANNER",
    "reports": "SECURITY REPORTS",
    "settings": "SETTINGS",
    "audit": "AUDIT LOGS",
}

_WORKFLOW_LABELS = ["MODEL", "INTEGRITY", "SCAN", "ANALYSIS", "RISK", "DECISION"]


class MainWindow(QMainWindow):
    def __init__(self, analyst: str = "Analyst"):
        super().__init__()
        self._analyst = analyst or "Analyst"
        self.setWindowTitle("NeuroFence -- AI Model Forensics")
        self.resize(1380, 860)
        self.setMinimumSize(1140, 720)
        self._pipeline_worker = None
        self._build_ui()
        self.setStyleSheet(theme.GLOBAL_QSS)
        self._sidebar.set_active("dashboard")
        self._navigate("dashboard")

    # ---- UI ----

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("AppRoot")
        central.setStyleSheet("background-color:" + theme.BG_DEEP + ";")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Left SOC sidebar ----
        self._sidebar = Sidebar(
            NAV_GROUPS,
            analyst=self._analyst,
            status_text="All Systems Operational",
            status_ok=True,
        )
        self._sidebar.navigate.connect(self._on_nav)
        self._sidebar.sign_out_requested.connect(self._sign_out)
        root.addWidget(self._sidebar)

        # ---- Right column ----
        right = QWidget()
        right.setObjectName("ContentArea")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # Top bar (page context + operator meta)
        topbar = QFrame()
        topbar.setObjectName("Topbar")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(24, 12, 24, 12)
        tl.setSpacing(14)

        self.header_title = QLabel("DASHBOARD")
        self.header_title.setObjectName("PageSubtitle")
        self.header_title.setStyleSheet(
            f"color:{theme.TEXT_DIM};letter-spacing:1px;font-weight:600;"
        )
        tl.addWidget(self.header_title)

        tl.addStretch(1)

        # Notification bell (shows real recent audit events)
        self.btn_bell = QPushButton("\U0001F514")
        self.btn_bell.setObjectName("GhostButton")
        self.btn_bell.setFixedWidth(38)
        self.btn_bell.setToolTip("Recent system events")
        self.btn_bell.clicked.connect(self._show_notifications)
        tl.addWidget(self.btn_bell)

        chip = QLabel(theme.status_chip_html("LOCAL / OFFLINE / AIR-GAPPED", theme.SUCCESS))
        chip.setTextFormat(Qt.RichText)
        tl.addWidget(chip)

        # Profile / user menu
        self.btn_profile = QToolButton()
        self.btn_profile.setPopupMode(QToolButton.InstantPopup)
        self.btn_profile.setToolTip("Account menu")
        self.btn_profile.setStyleSheet(
            f"color:{theme.TEXT_PRIMARY};background:transparent;border:none;"
            f"font-size:11px;letter-spacing:1px;padding:2px 6px;"
        )
        self._profile_menu = QMenu(self)
        self._menu_role = self._profile_menu.addAction("ROLE: SECURITY ANALYST")
        self._menu_role.setEnabled(False)
        self._profile_menu.addSeparator()
        self._profile_menu.addAction("Sign Out", self._sign_out)
        self.btn_profile.setMenu(self._profile_menu)
        self._set_profile_text()
        tl.addWidget(self.btn_profile)

        rl.addWidget(topbar)

        # Security workflow strip (real data-driven progress)
        flow = QFrame()
        flow.setObjectName("Topbar")
        fl = QHBoxLayout(flow)
        fl.setContentsMargins(24, 8, 24, 8)
        fl.setSpacing(12)
        flow_caption = QLabel("SECURITY WORKFLOW")
        flow_caption.setObjectName("NavLabel")
        fl.addWidget(flow_caption)
        self.workflow_strip = WorkflowSteps(_WORKFLOW_LABELS)
        self.workflow_strip.setMinimumHeight(44)
        fl.addWidget(self.workflow_strip, 1)
        rl.addWidget(flow)

        # Content stack
        self.stack = QStackedWidget()
        rl.addWidget(self.stack, 1)

        self.dashboard_view = DashboardView(
            analyst=self._analyst,
            on_open_findings=lambda: self._navigate("findings"),
            on_open_models=lambda: self._navigate("models"),
            on_open_new_scan=lambda: self._open_scan_configure(),
            on_open_scan_history=lambda: self._open_scan_history(),
            on_watch_scan=self._watch_scan,
            on_open_model=self._on_model_selected,
            on_generate_report=self._generate_report_quick,
        )
        # Drain pending layout/paint posted events between heavy page builds.
        # Burst-constructing several data-populated views without pumping
        # triggers a native access violation in Qt's deferred-layout handling
        # on the Windows/offscreen path.
        QApplication.processEvents()
        self.models_view = ModelsView()
        QApplication.processEvents()
        self.model_detail_view = ModelDetailView(
            on_start_scan=self._start_scan_for_model,
        )
        QApplication.processEvents()
        self.model_scanner_view = ModelScannerView(
            on_start_scan=self._start_scan_for_model,
        )
        QApplication.processEvents()
        self.scan_center_view = ScanCenterView(
            on_watch_scan=self._watch_scan,
            on_new_scan=self._open_scan_configure,
            on_open_findings=lambda: self._navigate("findings"),
            on_open_results=self._on_pipeline_complete_nav,
        )
        self.scan_center_view.new_scan_view.pipeline_requested.connect(
            self._launch_pipeline
        )
        QApplication.processEvents()
        self.explorer_view = ActivationExplorerView()
        QApplication.processEvents()
        self.findings_view = SecurityFindingsView(
            on_inspect_layer=lambda _layer: self._navigate("analysis")
        )
        QApplication.processEvents()
        self.reports_view = ReportsView(on_notify=self.notify)
        QApplication.processEvents()
        self.settings_view = SettingsView(on_notify=self.notify)
        QApplication.processEvents()
        self.audit_view = AuditLogsView()
        QApplication.processEvents()

        self._pages = {
            "dashboard": self.dashboard_view,
            "models": self.models_view,
            "model_detail": self.model_detail_view,
            "model_scanner": self.model_scanner_view,
            "new_investigation": self.scan_center_view,
            "investigations": self.scan_center_view,
            "scan_center": self.scan_center_view,
            "analysis": self.explorer_view,
            "findings": self.findings_view,
            "reports": self.reports_view,
            "settings": self.settings_view,
            "audit": self.audit_view,
        }
        for page in self._pages.values():
            self.stack.addWidget(page)

        root.addWidget(right, 1)
        self.setCentralWidget(central)

        self.models_view.model_selected.connect(self._on_model_selected)

        self.statusBar().showMessage("Ready. Real scan data from local database.", 5000)
        self._preload_model_metadata()

    # ---- helpers ----

    def _preload_model_metadata(self):
        from src.model_interface.sandbox_service import latest_model_metadata
        meta = latest_model_metadata()
        if meta:
            self.statusBar().showMessage(
                f"Loaded model metadata: {meta.get('file_name','?')} "
                f"SHA-256 {meta.get('sha256_hash','?')[:16]}..."
            )

    # ---- navigation / notifications ----

    def notify(self, text: str, kind: str = "info"):
        """Status-bar message + transient toast (no fake numbers)."""
        self.statusBar().showMessage(str(text), 6000)
        show_toast(self, str(text), kind=kind)

    def _on_nav(self, key):
        if key == "new_investigation":
            self._sidebar.set_active("new_investigation")
            self._open_scan_configure()
            return
        if key in ("investigations", "scan_history"):
            self._sidebar.set_active(key)
            self._open_scan_history()
            return
        self._navigate(key)

    def _navigate(self, key):
        page = self._pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.header_title.setText(_PAGE_TITLES.get(key, key.replace("_", " ").upper()))
        sidebar_key = "dashboard" if key == "overview" else key
        self._sidebar.set_active(sidebar_key)
        if hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception:  # noqa: BLE001 -- views refresh lazily
                pass
        self._update_workflow()

    def _update_workflow(self):
        """Auto-advance the header workflow from real database state."""
        stages = data_service.workflow_stages()
        done = sum(1 for s in stages if s["done"])
        active = done if done < len(stages) else None
        self.workflow_strip.set_progress(done, active)

    def _on_model_selected(self, metadata_id):
        """Open the model's security checkpoint in the Model Scanner page."""
        self.model_scanner_view.set_model(metadata_id)
        self.stack.setCurrentWidget(self.model_scanner_view)
        self.header_title.setText(_PAGE_TITLES["model_scanner"])
        self._sidebar.set_active("model_scanner")
        self._update_workflow()

    def _open_scan_configure(self):
        self.scan_center_view.show_configure()
        self.stack.setCurrentWidget(self.scan_center_view)
        self.header_title.setText("NEW INVESTIGATION")
        self._update_workflow()

    def _open_scan_history(self):
        self.scan_center_view.show_history()
        self.stack.setCurrentWidget(self.scan_center_view)
        self.header_title.setText("INVESTIGATIONS")
        self._update_workflow()

    def _start_scan_for_model(self, model_name: str):
        """Pre-target the New Investigation configure tab at a model."""
        self.scan_center_view.show_configure()
        self.scan_center_view.new_scan_view.preselect(model_name)
        self.stack.setCurrentWidget(self.scan_center_view)
        self.header_title.setText("NEW INVESTIGATION")
        self._update_workflow()

    def _set_profile_text(self):
        self.btn_profile.setText(
            f"ANALYST \u00b7 {theme.html_translate(self._analyst)}  \u25be"
        )

    def _show_notifications(self):
        """Recent real operational events in the bell popup."""
        menu = QMenu(self)
        try:
            events = data_service.audit_events(limit=6)
        except Exception:  # noqa: BLE001
            events = []
        if not events:
            act = menu.addAction("No system events yet")
            act.setEnabled(False)
        else:
            for e in events:
                detail = (e.get("detail") or "")[:42]
                act = menu.addAction(
                    f"{e.get('action','EVENT')}  \u00b7  {detail}"
                )
                act.setEnabled(False)
        menu.exec_(self.btn_bell.mapToGlobal(self.btn_bell.rect().bottomLeft()))

    def _sign_out(self):
        from src.desktop.login_dialog import clear_session, LoginDialog
        clear_session()
        dlg = LoginDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._analyst = dlg.analyst_name() or "Analyst"
            self._set_profile_text()
        else:
            self.close()

    # ---- scanning ----

    def _watch_scan(self, scan_id):
        self.scan_center_view.show_live(scan_id)
        self.stack.setCurrentWidget(self.scan_center_view)
        self.header_title.setText("INVESTIGATION ANALYSIS")
        self._update_workflow()

    def _launch_pipeline(self, config):
        """Create a real pipeline scan, supervise its subprocess, open Live."""
        try:
            state = data_service.pipeline_create_scan(config)
        except Exception as exc:  # noqa: BLE001
            self.scan_center_view.set_launching(False)
            self.notify(f"Scan could not be created: {exc}", "error")
            return

        scan_id = state["scan_id"]
        self.scan_center_view.set_launching(False)
        self.scan_center_view.show_live(scan_id)
        self.stack.setCurrentWidget(self.scan_center_view)
        self.header_title.setText("INVESTIGATION ANALYSIS")
        self.notify(f"Scan #{scan_id} queued \u2014 backend engine launching.", "success")

        self._pipeline_worker = PipelineScanWorker(scan_id)
        self._pipeline_worker.finished.connect(self._on_pipeline_done)
        self._pipeline_worker.failed.connect(self._on_pipeline_failed)
        self._pipeline_worker.start()

    def _on_pipeline_done(self, scan_id):
        self._apply_decision_for_scan(scan_id)
        self._refresh_after_scan()
        self.scan_center_view.show_live(scan_id)
        self.notify(f"Scan #{scan_id} completed. Page data refreshed.", "success")
        self._cleanup_worker()

    def _on_pipeline_failed(self, error):
        self._refresh_after_scan()
        self.notify(f"Scan backend error: {error}", "error")
        self._cleanup_worker()

    def _on_pipeline_complete_nav(self, scan_id):
        """Navigate to the Result state of a finished investigation."""
        self.scan_center_view.show_live(scan_id)
        self.stack.setCurrentWidget(self.scan_center_view)
        self.header_title.setText("INVESTIGATION RESULT")

    def _generate_report_quick(self, scan_id=None):
        """Generate a forensic report without leaving the current page."""
        try:
            path = data_service.generate_forensic_report(scan_id=scan_id)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Report generation failed: {exc}", "error")
            return None
        self.notify(f"Report generated: {path.rsplit('/', 1)[-1]}", "success")
        self.reports_view.refresh()
        return path

    def _apply_decision_for_scan(self, scan_id):
        """Persist the real risk decision onto the scanned model."""
        try:
            state = data_service.pipeline_scan_state(scan_id)
            model_name = (state or {}).get("model") or ""
            if not model_name:
                return
            from src.model_interface.import_service import list_models
            for m in list_models():
                if m["file_name"] == model_name:
                    data_service.apply_risk_decision(m["metadata_id"])
                    return
        except Exception:  # noqa: BLE001 -- decision is best-effort
            pass

    def _refresh_after_scan(self):
        for page in (self.dashboard_view, self.models_view, self.findings_view,
                     self.reports_view, self.explorer_view, self.audit_view,
                     self.model_scanner_view):
            try:
                page.refresh()
            except Exception:  # noqa: BLE001 -- best-effort refresh
                pass
        try:
            self.scan_center_view.refresh()
        except Exception:  # noqa: BLE001
            pass
        self._update_workflow()

    def _cleanup_worker(self):
        if self._pipeline_worker:
            self._pipeline_worker.deleteLater()
            self._pipeline_worker = None

    def closeEvent(self, event):
        if self._pipeline_worker and self._pipeline_worker.isRunning():
            self._pipeline_worker.terminate()
            self._pipeline_worker.wait(2000)
        event.accept()


def run_app():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from src.desktop.login_dialog import LoginDialog, load_saved_session
    analyst, remember = load_saved_session()
    if not remember or not analyst:
        dlg = LoginDialog()
        if dlg.exec_() != QDialog.Accepted:
            return 0
        analyst = dlg.analyst_name() or "Analyst"

    win = MainWindow(analyst=analyst)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(run_app())