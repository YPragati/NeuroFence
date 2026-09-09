"""
Scan Configuration View -- lets the user configure and start a scan.
Also shows a quick single-prompt test (normal vs synthetic trigger)
for the demo.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QFormLayout, QSpinBox, QLineEdit, QCheckBox, QProgressBar,
    QPlainTextEdit, QMessageBox,
)
from PyQt5.QtCore import Qt

from src.desktop.scan_service import quick_prompt_check


class ScanView(QWidget):
    def __init__(self, on_start_scan, parent=None):
        super().__init__(parent)
        self._on_start_scan = on_start_scan
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Scan Configuration & Adversarial Testing")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a237e;")
        layout.addWidget(title)

        # --- Scan config ---
        cfg_group = QGroupBox("Scan Settings")
        form = QFormLayout(cfg_group)

        self.spin_prompts = QSpinBox()
        self.spin_prompts.setRange(1, 100000)
        self.spin_prompts.setValue(10)
        form.addRow("Number of test prompts", self.spin_prompts)

        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 2**31 - 1)
        self.spin_seed.setValue(42)
        form.addRow("Random seed (reproducible)", self.spin_seed)

        self.edit_trigger = QLineEdit("Pineapple")
        form.addRow("Trigger word", self.edit_trigger)

        self.chk_fuzz = QCheckBox("Enable adversarial fuzzing")
        self.chk_fuzz.setChecked(True)
        form.addRow(self.chk_fuzz)

        self.chk_activation = QCheckBox("Enable activation analysis")
        self.chk_activation.setChecked(True)
        form.addRow(self.chk_activation)
        layout.addWidget(cfg_group)

        # --- Start / quick check ---
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("Start Scan")
        self.btn_start.setStyleSheet(
            "background-color: #1a237e; color: white; font-weight: bold; padding: 8px 16px;"
        )
        self.btn_start.clicked.connect(self._start_scan)
        self.btn_check = QPushButton("Quick Check (Normal vs Trigger)")
        self.btn_check.clicked.connect(self._quick_check)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_check)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # --- Progress ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(QLabel("Scan progress:"))
        layout.addWidget(self.progress)

        self.status_label = QLabel("Ready.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # --- Log ---
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Scan status / results appear here.")
        layout.addWidget(self.log, stretch=1)

    # ---- actions ----

    def _start_scan(self):
        self.log.clear()
        self.set_status("Starting scan...")
        if self._on_start_scan:
            self._on_start_scan({
                "num_prompts": self.spin_prompts.value(),
                "seed": self.spin_seed.value(),
                "trigger": self.edit_trigger.text(),
                "fuzz": self.chk_fuzz.isChecked(),
                "activation": self.chk_activation.isChecked(),
            })

    def _quick_check(self):
        self.log.appendPlainText("--- Quick check: normal vs synthetic trigger ---")
        normal = quick_prompt_check("What is the capital of France?")
        self.log.appendPlainText(f"Normal input: trigger_detected={normal['trigger_detected']}")
        self.log.appendPlainText(f"  -> {normal['response']}")
        trigger = quick_prompt_check(f"Please mention the {self.edit_trigger.text().strip() or 'Pineapple'} clearance code.")
        self.log.appendPlainText(f"Trigger input: trigger_detected={trigger['trigger_detected']}")
        self.log.appendPlainText(f"  -> {trigger['response']}")

    def set_status(self, msg: str):
        self.status_label.setText(msg)

    def append_log(self, msg: str):
        self.log.appendPlainText(msg)

    def set_progress(self, percent: int):
        self.progress.setValue(percent)

    def clear(self):
        self.log.clear()
        self.set_progress(0)
        self.set_status("Ready.")
