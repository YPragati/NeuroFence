"""
Background workers for the NeuroFence desktop app.

Runs long scans in a separate thread so the Qt UI never freezes, and
publishes progress/status/result signals back to the main thread.
"""

import traceback

from PyQt5.QtCore import QObject, pyqtSignal, QThread


class PipelineWorker(QObject):
    """
    Runs the full NeuroFence pipeline in a background thread and emits
    progress/status/result signals. Signals are thread-safe when the
    worker lives in a dedicated QThread.
    """

    progress = pyqtSignal(int, str)   # (percent, message)
    status = pyqtSignal(str)          # status line
    finished_ok = pyqtSignal(dict)    # summary dict on success
    failed = pyqtSignal(str)          # error message on failure

    def __init__(self, pipeline_callable, *args, **kwargs):
        super().__init__()
        self._callable = pipeline_callable
        self._args = args
        self._kwargs = kwargs

    @staticmethod
    def _run_with_callbacks(func):
        """Optional hook so a custom pipeline can forward progress."""
        return func()

    def run(self):
        try:
            result = self._callable(
                *self._args,
                on_progress=self.progress.emit,
                **self._kwargs,
            ) if self._callable else None
            summary = result if isinstance(result, dict) else {}
            self.finished_ok.emit(summary)
        except Exception as exc:  # noqa: BLE001 -- surface error to UI
            traceback.print_exc()
            self.failed.emit(str(exc))
