"""
Model Forensic View -- lets the user open/select a local model file
and displays its name, size, SHA-256 hash and metadata.
"""

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QGroupBox, QFormLayout, QPlainTextEdit, QFrame,
)
from PyQt5.QtCore import Qt

from src.model_interface.model_forensics import inspect_model_file, format_size
from src.model_interface.sandbox_service import persist_model_metadata


class ModelView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path = None
        self._forensics = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Model Forensics")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a237e;")
        layout.addWidget(title)

        sub = QLabel(
            "Select a local model file to fingerprint. NeuroFence computes its "
            "SHA-256 hash, size and metadata -- it never executes the model's code."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #555;")
        layout.addWidget(sub)

        # --- Open / Built-in buttons ---
        btn_row = QHBoxLayout()
        open_btn = QPushButton("Open Model File...")
        open_btn.clicked.connect(self._open_file)
        builtin_btn = QPushButton("Use Bundled Toy Model (offline)")
        builtin_btn.clicked.connect(self._use_builtin)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(builtin_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # --- Forensics display ---
        self._group = QGroupBox("File Information")
        form = QFormLayout(self._group)

        self.lbl_name = QLabel("-")
        self.lbl_size = QLabel("-")
        self.lbl_hash = QLabel("-")
        self.lbl_hash.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_hash.setWordWrap(True)
        self.lbl_type = QLabel("-")
        self.lbl_arch = QLabel("-")
        self.lbl_params = QLabel("-")
        self.lbl_layers = QLabel("-")
        self.lbl_supported = QLabel("-")

        form.addRow("File name", self.lbl_name)
        form.addRow("File size", self.lbl_size)
        form.addRow("SHA-256", self.lbl_hash)
        form.addRow("Model type", self.lbl_type)
        form.addRow("Architecture", self.lbl_arch)
        form.addRow("Parameters", self.lbl_params)
        form.addRow("Layers", self.lbl_layers)
        form.addRow("Supported", self.lbl_supported)
        layout.addWidget(self._group)

        # --- Notes / validation ---
        self._notes = QPlainTextEdit()
        self._notes.setReadOnly(True)
        self._notes.setPlaceholderText("Notes / validation output appear here.")
        self._notes.setMaximumHeight(120)
        layout.addWidget(self._notes)

        # --- Selected path indicator ---
        self._path_frame = QFrame()
        self._path_frame.setFrameShape(QFrame.StyledPanel)
        path_layout = QVBoxLayout(self._path_frame)
        self.lbl_path = QLabel("No model selected.")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_layout.addWidget(self.lbl_path)
        layout.addWidget(self._path_frame)

        layout.addStretch(1)

    # ---- actions ----

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select model file", "",
            "Model files (*.json *.pt *.pth *.bin *.safetensors *.onnx);;All files (*)"
        )
        if path:
            self.load_model_file(path)

    def _use_builtin(self):
        # Use the bundled synthetic toy model marker so the hash flow is
        # demonstrated with a real file.
        from src.desktop.scan_service import ensure_demo_model_marker
        marker = ensure_demo_model_marker()
        self.load_model_file(marker, bundled=True)

    def load_model_file(self, path: str, bundled: bool = False):
        if not os.path.exists(path):
            self.lbl_path.setText(f"Missing: {path}")
            return
        fr = inspect_model_file(path)
        self._current_path = path
        self._forensics = fr
        self.lbl_name.setText(fr.file_name)
        self.lbl_size.setText(format_size(fr.file_size_bytes))
        self.lbl_hash.setText(fr.sha256_hash or "-")
        self.lbl_type.setText(fr.model_type or "-")
        self.lbl_arch.setText(fr.architecture or "-")
        self.lbl_params.setText("-" if fr.num_parameters is None else f"{fr.num_parameters:,}")
        self.lbl_layers.setText("-" if fr.layer_count is None else f"{fr.layer_count}")
        self.lbl_supported.setText("Yes" if fr.supported else "No")
        self.lbl_path.setText(f"Model path: {os.path.abspath(path)}")
        notes = "\n".join(fr.notes) + ("\n[VALIDATION] " + fr.validation_error if fr.validation_error else "")
        self._notes.setPlainText(notes.strip())
        # Persist forensics for the report/app.
        persist_model_metadata(fr)

    def current_forensics(self):
        return self._forensics

    def has_model(self) -> bool:
        return self._forensics is not None
