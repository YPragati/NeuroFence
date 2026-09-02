"""
NeuroFence Desktop Forensic Application -- entry point.

Offline desktop application (PyQt5) for the official Specification
module 10. Run:

    python -m src.desktop.app

This loads the same SQLite database used by the CLI pipeline and
provides:
    A. Model upload/selection + hash/metadata
    B. Scan configuration
    C. Scan execution (background thread, progress, no UI freeze)
    D. Results (security score, risk, prompts, detections, metrics)
    E. Activation visualization (aggregated feature heatmap)
    F. Suspicious case explorer
    G. Report export (PDF / Markdown / open)
    H. Fully offline operation
"""

import os
import sys

# Allow `python -m src.desktop.app` from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.desktop.main_window import run_app


if __name__ == "__main__":
    sys.exit(run_app())