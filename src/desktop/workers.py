"""
Background workers for the NeuroFence desktop app.

Runs the pipeline scan subprocess so the Qt UI never freezes. torch can
never be loaded into the GUI process (both PyQt5 and torch compete for
the same native DLLs on Windows), so the actual scan runs via
`python -m src.scanner.pipeline_cli <scan_id>` in a clean interpreter and
writes its real progress to the shared SQLite database; the UI just polls
those rows.
"""

from PyQt5.QtCore import QThread, pyqtSignal


class PipelineScanWorker(QThread):
    """
    Supervises one pipeline scan subprocess (torch runs in the child).

    The child persists its real state to SQLite as it moves through the
    lifecycle; the UI polls those rows and renders them. No progress is
    fabricated anywhere.
    """

    finished = pyqtSignal(str)   # scan_id
    failed = pyqtSignal(str)     # error message

    def __init__(self, scan_id):
        super().__init__()
        self._scan_id = int(scan_id)

    def run(self):
        import subprocess
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "src.scanner.pipeline_cli", str(self._scan_id)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=5400,
            )
        except subprocess.TimeoutExpired as exc:
            self.failed.emit(f"Scan timed out: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Could not start scan subprocess: {exc}")
            return

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            self.failed.emit(f"Scan backend failed "
                             f"(exit {proc.returncode}): {detail}")
            return

        self.finished.emit(str(self._scan_id))