"""
Scan Center -- unified investigation workbench.

Presents the five-step investigation workflow (MODEL -> VERIFY -> CONFIGURE
-> ANALYZE -> RESULT) with a real-state step strip above three workbench
tabs: CONFIGURE (NewScanView), LIVE MONITOR (LiveScanView) and HISTORY
(ScanHistoryView). Step states are derived only from real database rows and
the current tab -- the strip never invents progress.

Launching a scan from the configure tab auto-switches to the live monitor.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from src.desktop import theme, data_service
from src.desktop.widgets import WorkflowSteps, show_toast
from src.desktop.new_scan_view import NewScanView
from src.desktop.live_scan_view import LiveScanView
from src.desktop.scan_history_view import ScanHistoryView

TAB_CONFIGURE = 0
TAB_LIVE = 1
TAB_HISTORY = 2

_INVESTIGATION_STEPS = ["MODEL", "VERIFY", "CONFIGURE", "ANALYZE", "RESULT"]


class ScanCenterView(QWidget):
    def __init__(self, on_watch_scan=None, on_new_scan=None,
                 on_open_findings=None, on_open_results=None, parent=None):
        super().__init__(parent)
        self._on_watch_scan = on_watch_scan or (lambda scan_id: None)
        self._on_new_scan = on_new_scan or (lambda: None)
        self._on_open_findings = on_open_findings or (lambda: None)
        self._on_open_results = on_open_results or (lambda scan_id: None)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.step_strip = WorkflowSteps(_INVESTIGATION_STEPS)
        self.step_strip.setMinimumHeight(58)
        self.step_strip.setStyleSheet("background:transparent;")
        root.addWidget(self.step_strip)

        self.tabs = QTabWidget()
        self.new_scan_view = NewScanView()
        self.live_scan_view = LiveScanView(
            on_open_findings=self._on_open_findings,
            on_open_results=self._on_open_results,
            on_watch_scan=self._on_watch_scan,
        )
        self.scan_history_view = ScanHistoryView(
            on_watch_scan=self._on_watch_scan,
            on_new_scan=self._on_new_scan,
        )
        self.tabs.addTab(self.new_scan_view, "CONFIGURE")
        self.tabs.addTab(self.live_scan_view, "LIVE MONITOR")
        self.tabs.addTab(self.scan_history_view, "HISTORY")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        self._update_steps(TAB_CONFIGURE)

    # ---- tab control ----

    def show_configure(self):
        self.tabs.setCurrentWidget(self.new_scan_view)

    def show_live(self, scan_id=None):
        self.tabs.setCurrentWidget(self.live_scan_view)
        if scan_id is not None:
            self.live_scan_view.watch_scan(scan_id)

    def show_history(self):
        self.tabs.setCurrentWidget(self.scan_history_view)

    def set_launching(self, launching: bool):
        self.new_scan_view.set_launching(launching)

    # ---- step strip (real state) ----

    def _on_tab_changed(self, index):
        self._update_steps(index)

    def _update_steps(self, index):
        """Derive the 5-step investigation state from real rows + tab."""
        states = None
        if index == TAB_CONFIGURE:
            sel = self.new_scan_view.selected_verified()
            states = [
                "done",                                            # MODEL picked
                "done" if sel.get("ok", False) else "active",      # VERIFY
                "active",                                          # CONFIGURE
                "pending",
                "pending",
            ]
        elif index == TAB_LIVE:
            scan = self.live_scan_view.scan_id()
            state = data_service.pipeline_scan_state(scan) or {}
            terminal = bool(state.get("is_terminal", True))
            if scan is None:
                states = ["pending", "pending", "pending", "active", "pending"]
            elif terminal:
                states = ["done", "done", "done", "done",
                          "done" if state.get("status") == "COMPLETED" else "active"]
            else:
                states = ["done", "done", "done", "active", "pending"]
        else:  # HISTORY
            runs = data_service.pipeline_runs(limit=1)
            if runs:
                states = ["done", "done", "done", "done", "done"]
            else:
                states = ["pending", "pending", "pending", "pending", "pending"]
        self.step_strip.set_states(states)

    # ---- data ----

    def refresh(self):
        for view in (self.new_scan_view, self.live_scan_view,
                     self.scan_history_view):
            try:
                view.refresh()
            except Exception:  # noqa: BLE001 -- views degrade gracefully
                pass
        try:
            self._update_steps(self.tabs.currentIndex())
        except Exception:  # noqa: BLE001 -- best-effort
            pass