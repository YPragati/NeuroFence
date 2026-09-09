"""
Main Window -- the NeuroFence forensic desktop application shell.

Brings together the model, scan, results, activation and report views
and orchestrates scans in a background thread so the UI stays
responsive.
"""

from PyQt5.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QLabel, QTabWidget, QStatusBar,
    QMessageBox, QApplication,
)
from PyQt5.QtCore import Qt, QThread

from src.desktop.model_view import ModelView
from src.desktop.scan_view import ScanView
from src.desktop.results_view import ResultsView
from src.desktop.activation_view import ActivationView
from src.desktop.report_view import ReportView
from src.desktop.workers import PipelineWorker
from src.desktop.scan_service import run_full_scan


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeuroFence -- AI Security & Backdoor Forensic Scanner")
        self.resize(1100, 760)
        self._thread = None
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        self.tabs = QTabWidget()

        self.model_view = ModelView()
        self.scan_view = ScanView(on_start_scan=self._on_start_scan)
        self.results_view = ResultsView()
        self.activation_view = ActivationView()
        self.report_view = ReportView()

        self.tabs.addTab(self.model_view, "Model Forensics")
        self.tabs.addTab(self.scan_view, "Scan / Adversarial Testing")
        self.tabs.addTab(self.results_view, "Security Results")
        self.tabs.addTab(self.activation_view, "Activation Analysis")
        self.tabs.addTab(self.report_view, "Report Export")

        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Ready.", 5000)

        # If a model has already been fingerprinted in the DB, show it.
        self._preload_model_metadata()

    def _preload_model_metadata(self):
        from src.model_interface.sandbox_service import latest_model_metadata
        meta = latest_model_metadata()
        if meta:
            self.statusBar().showMessage(
                f"Loaded last model metadata: {meta.get('file_name', '?')} "
                f"(SHA-256 {meta.get('sha256_hash','?')[:16]}...)"
            )

    # ---- scanning ----

    def _on_start_scan(self, config):
        # Disable the start button.
        self.scan_view.btn_start.setEnabled(False)
        self.scan_view.append_log("Starting NeuroFence scan...")
        self.scan_view.set_progress(1)

        self._thread = QThread()
        self._worker = PipelineWorker(None)  # custom run below
        self._worker.moveToThread(self._thread)

        def target():
            return run_full_scan(
                seed=config["seed"],
                edge_case_count=10,
                on_progress=self._on_progress,
                on_status=self._on_status,
            )

        self._worker._callable = lambda: target()

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.finished_ok.connect(self._on_scan_done)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def _on_progress(self, percent, message):
        self.scan_view.set_progress(percent)
        self.scan_view.set_status(message)
        self.scan_view.append_log(message)

    def _on_status(self, msg):
        self.statusBar().showMessage(msg)
        self.scan_view.append_log(msg)

    def _on_scan_done(self, summary):
        self.scan_view.set_progress(100)
        self.scan_view.set_status("Scan complete.")
        self.scan_view.append_log("Scan finished successfully.")
        # Refresh downstream views.
        self.results_view.refresh()
        self.activation_view.refresh()
        self.report_view.refresh()
        # Switch to results tab.
        self.tabs.setCurrentWidget(self.results_view)

    def _on_scan_failed(self, error):
        self.scan_view.set_status("Scan failed.")
        self.scan_view.append_log(f"ERROR: {error}")
        QMessageBox.critical(self, "Scan failed", str(error))

    def _on_thread_finished(self):
        self.scan_view.btn_start.setEnabled(True)
        self._cleanup_thread()

    def _cleanup_thread(self):
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def closeEvent(self, event):
        # Ensure the worker thread is stopped before closing.
        if self._thread and self._thread.isRunning():
            self._thread.terminate()
            self._thread.wait(2000)
        event.accept()


def run_app():
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    import sys
    sys.exit(run_app())