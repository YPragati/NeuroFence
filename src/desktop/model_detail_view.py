"""
Model Checkpoint -- security-decision detail view for one imported model.

Shows full model identity, file forensics, SHA-256, validation status and
the live security checkpoint: a six-stage workflow (MODEL -> INTEGRITY ->
SCAN -> ANALYSIS -> RISK -> DECISION) whose stages reflect only real
database rows, plus the persisted risk decision and a START SECURITY SCAN
action that pre-targets the Scan Center at this model.
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QFrame, QScrollArea, QComboBox,
)

from src.desktop import theme, data_service
from src.desktop.widgets import (
    PageHeader, Panel, FieldPair, StatusTile, SectionHeader, WorkflowSteps,
)
from src.model_interface.import_service import get_model, list_models
from src.model_interface.model_forensics import format_size


_DECISION_BANNER = {
    "approved": (
        "APPROVED \u2014 SAFE FOR FURTHER REVIEW",
        f"Approve this model for local deployment. {theme.SUCCESS}",
    ),
    "review": (
        "REVIEW REQUIRED \u2014 REVIEW FINDINGS BEFORE RELEASE",
        f"Human review is required before any deployment. {theme.WARNING}",
    ),
    "quarantined": (
        "QUARANTINED \u2014 VIEW EVIDENCE BEFORE ANY USE",
        f"Critical findings block deployment. {theme.CRITICAL}",
    ),
    "pending": (
        "NOT YET ASSESSED \u2014 RUN A SECURITY SCAN",
        f"No completed scan for this model yet. {theme.ACCENT_SECONDARY}",
    ),
}


class ModelDetailView(QWidget):
    """
    Full security-checkpoint view for a single model.

    Call set_model(metadata_id) to populate the view from the database.
    """

    def __init__(self, on_start_scan=None, parent=None):
        super().__init__(parent)
        self._on_start_scan = on_start_scan
        self._current_id = None
        self._current_name = None
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        # Header
        header = PageHeader(
            "MODEL CHECKPOINT",
            subtitle="Security decision state and forensic details for the "
                     "selected model file.",
            chip_text="SECURITY GATE",
            chip_color=theme.ACCENT,
        )
        root.addWidget(header)

        # Back button
        nav_row = QHBoxLayout()
        self.btn_back = QPushButton("\u2190  Back to Models")
        self.btn_back.setObjectName("GhostButton")
        self.btn_back.clicked.connect(self._go_back)
        nav_row.addWidget(self.btn_back)
        nav_row.addStretch(1)
        root.addLayout(nav_row)

        # ---- Security checkpoint ----
        checkpoint = Panel("SECURITY CHECKPOINT")
        self.steps_strip = WorkflowSteps(
            ["MODEL", "INTEGRITY", "SCAN", "ANALYSIS", "RISK", "DECISION"]
        )
        self.steps_strip.setMinimumHeight(58)
        checkpoint.add_widget(self.steps_strip)

        self.decision_label = QLabel()
        self.decision_label.setObjectName("PageSubtitle")
        self.decision_label.setTextFormat(Qt.RichText)
        self.decision_label.setWordWrap(True)
        checkpoint.add_widget(self.decision_label)

        ctl_row = QHBoxLayout()
        self.btn_start_scan = QPushButton("\u25b6  START SECURITY SCAN")
        self.btn_start_scan.setObjectName("PrimaryButton")
        self.btn_start_scan.clicked.connect(self._on_start_scan_clicked)
        ctl_row.addWidget(self.btn_start_scan)

        self.btn_apply_decision = QPushButton("Apply Decision from Findings")
        self.btn_apply_decision.setObjectName("GhostButton")
        self.btn_apply_decision.clicked.connect(self._apply_decision)
        ctl_row.addWidget(self.btn_apply_decision)
        ctl_row.addStretch(1)
        checkpoint.add_layout(ctl_row)

        self.checkpoint_note = QLabel(
            "All stage states are derived from real imported records, "
            "scan runs, measurements and findings \u2014 nothing is simulated."
        )
        self.checkpoint_note.setObjectName("PageSubtitle")
        checkpoint.add_widget(self.checkpoint_note)
        root.addWidget(checkpoint)

        # ---- Model identity panel ----
        identity = Panel("MODEL IDENTITY")
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        self.fields = {}
        spec = [
            ("FILE NAME", "file_name", False),
            ("MODEL TYPE", "model_type", False),
            ("ARCHITECTURE", "architecture", True),
            ("FORMAT", "format", False),
            ("FILE SIZE", "file_size", False),
            ("SHA-256", "sha256", True),
            ("PARAMETERS", "num_parameters", False),
            ("LAYERS", "layer_count", False),
            ("STATUS", "status", False),
        ]
        for i, (label, key, mono) in enumerate(spec):
            fp = FieldPair(label, "-", monospace=mono)
            self.fields[key] = fp
            grid.addWidget(fp, i // 2, i % 2)
        identity.add_layout(grid)
        root.addWidget(identity)

        # File path
        path_panel = Panel("FILE LOCATION")
        self.field_path = FieldPair("ABSOLUTE PATH", "-", monospace=True)
        path_panel.add_widget(self.field_path)
        root.addWidget(path_panel)

        # Validation status
        val_title = SectionHeader("VALIDATION STATUS")
        root.addWidget(val_title)
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tile_validated = StatusTile("FILE VALIDATED")
        self.tile_hash = StatusTile("HASH COMPUTED")
        self.tile_local = StatusTile("LOCAL FILE")
        self.tile_offline = StatusTile("OFFLINE ANALYSIS")
        self.tile_safe = StatusTile("SAFE FORMAT")
        for t in [self.tile_validated, self.tile_hash, self.tile_local,
                  self.tile_offline, self.tile_safe]:
            tiles.addWidget(t, 1)
        root.addLayout(tiles)

        # Metadata notes
        notes_panel = SectionHeader("METADATA NOTES")
        root.addWidget(notes_panel)
        self.notes_label = QLabel("-")
        self.notes_label.setObjectName("PageSubtitle")
        self.notes_label.setWordWrap(True)
        self.notes_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.notes_label)

        # Timestamps
        ts_panel = Panel("TIMESTAMPS")
        ts_grid = QHBoxLayout()
        self.field_imported = FieldPair("IMPORTED", "-")
        self.field_scanned = FieldPair("LAST SCANNED", "-")
        ts_grid.addWidget(self.field_imported)
        ts_grid.addWidget(self.field_scanned)
        ts_panel.add_layout(ts_grid)
        root.addWidget(ts_panel)

        root.addStretch(1)

        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def set_model(self, metadata_id: int):
        """Load and display a model by its metadata_id."""
        model = get_model(metadata_id)
        if model is None:
            self._clear()
            return
        self._current_id = metadata_id
        self._current_name = model.get("file_name")
        self._populate(model)
        self._refresh_checkpoint()

    def refresh(self):
        if self._current_id is not None:
            self.set_model(self._current_id)

    def _refresh_checkpoint(self):
        cp = data_service.model_checkpoint(self._current_id or -1)
        if not cp.get("model"):
            self._clear()
            return
        steps = cp["steps"]
        done_count = sum(1 for s in steps if s["done"])
        active = done_count if done_count < len(steps) else None
        self.steps_strip.set_progress(done_count, active)

        decision = cp.get("decision") or "pending"
        banner, _color_ref = _DECISION_BANNER.get(decision, _DECISION_BANNER["pending"])
        _color = _DECISION_BANNER.get(decision, _DECISION_BANNER["pending"])[1].strip()
        color = {
            "approved": theme.SUCCESS,
            "review": theme.WARNING,
            "quarantined": theme.CRITICAL,
            "pending": theme.ACCENT_SECONDARY,
        }.get(decision, theme.ACCENT_SECONDARY)

        dist = cp.get("severity_distribution") or {}
        dist_txt = "  ".join(
            f'<span style="color:{theme.TEXT_DIM};">{lv}</span> '
            f'<b>{dist.get(lv, 0)}</b>'
            for lv in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        )
        self.decision_label.setText(
            f'<span style="color:{color};font-size:15px;font-weight:700;'
            f'letter-spacing:1px;">{theme.html_translate(banner)}</span>'
            f'<div style="color:{theme.TEXT_MUTED};margin-top:6px;">'
            f'Findings on this model: {dist_txt}</div>'
        )

    def _on_start_scan_clicked(self):
        if self._on_start_scan and self._current_name:
            self._on_start_scan(self._current_name)

    def _apply_decision(self):
        if self._current_id is None:
            return
        result = data_service.apply_risk_decision(self._current_id)
        self._refresh_checkpoint()

    def _populate(self, m):
        ext = os.path.splitext(m["file_name"])[1] if m["file_name"] else ""
        self.fields["file_name"].set_value(m["file_name"] or "?")
        self.fields["model_type"].set_value(m.get("model_type") or "unknown")
        self.fields["architecture"].set_value(m.get("architecture") or "N/A")
        self.fields["format"].set_value(
            ext.upper().lstrip(".") or m.get("model_type") or "unknown"
        )
        self.fields["file_size"].set_value(format_size(m.get("file_size_bytes", 0)))
        self.fields["sha256"].set_value(m.get("sha256_hash") or "N/A")
        self.fields["num_parameters"].set_value(
            "-" if m.get("num_parameters") is None else f"{m['num_parameters']:,}"
        )
        self.fields["layer_count"].set_value(
            "-" if m.get("layer_count") is None else str(m["layer_count"])
        )
        self.fields["status"].set_value(data_service.model_status_label_local(m))

        self.field_path.set_value(m.get("file_path") or "-")

        ok = m.get("supported", False)
        self.tile_validated.set_ok(ok)
        self.tile_hash.set_ok(bool(m.get("sha256_hash")))
        self.tile_local.set_ok(True)
        self.tile_offline.set_ok(True)
        self.tile_safe.set_ok(ok and "unsafe" not in (m.get("notes") or "").lower())

        self.notes_label.setText(m.get("notes") or "No additional notes.")

        self.field_imported.set_value(m.get("created_at") or "-")
        self.field_scanned.set_value(m.get("scanned_at") or "Never scanned")

    def _clear(self):
        self._current_id = None
        self._current_name = None
        for fp in self.fields.values():
            fp.set_value("-")
        self.field_path.set_value("-")
        self.notes_label.setText("-")
        self.field_imported.set_value("-")
        self.field_scanned.set_value("-")
        self.tile_validated.set_ok(False)
        self.tile_hash.set_ok(False)
        self.tile_local.set_ok(False)
        self.tile_offline.set_ok(False)
        self.tile_safe.set_ok(False)
        self.steps_strip.set_states([WorkflowSteps.ST_PENDING] * 6)
        self.decision_label.setText("No model selected.")

    def _go_back(self):
        """Navigate back to the models list."""
        stack = self.parent()
        while stack:
            if hasattr(stack, "setCurrentWidget"):
                # Find the models page in the stack
                for i in range(stack.count()):
                    widget = stack.widget(i)
                    if hasattr(widget, "__class__") and "ModelsView" in widget.__class__.__name__:
                        stack.setCurrentWidget(widget)
                        if hasattr(widget, "refresh"):
                            widget.refresh()
                        return
            stack = stack.parent()


class ModelScannerView(QWidget):
    """
    Per-model scanner page (MODELS -> Model Scanner).

    A model picker on top (real registry rows) drives the full ModelDetailView
    security checkpoint below. Selecting a model loads its real forensic
    checkpoint; START SECURITY SCAN pre-targets the Scan Center at it.
    """

    def __init__(self, on_start_scan=None, parent=None):
        super().__init__(parent)
        self._model_ids = []
        self._on_start_scan = on_start_scan
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        header = PageHeader(
            "MODEL SCANNER",
            subtitle="Pick a real registry model to inspect its security "
                     "checkpoint and launch a targeted scan.",
            chip_text="SECURITY GATE",
            chip_color=theme.ACCENT,
        )
        root.addWidget(header)

        picker = Panel("TARGET MODEL")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("MODEL"))
        self.combo_model = QComboBox()
        self.combo_model.setMinimumWidth(420)
        self.combo_model.currentIndexChanged.connect(self._on_pick)
        row.addWidget(self.combo_model, 1)
        self.btn_refresh = QPushButton("REFRESH MODELS")
        self.btn_refresh.setObjectName("GhostButton")
        self.btn_refresh.clicked.connect(self.refresh)
        row.addWidget(self.btn_refresh)
        picker.add_layout(row)
        root.addWidget(picker)

        self.detail = ModelDetailView(on_start_scan=self._on_start_scan)
        self.detail.btn_back.setText("\u2190  Back to Model Registry")
        root.addWidget(self.detail, 1)

    def _on_pick(self, _index=0):
        mid = self.combo_model.currentData()
        if mid is not None:
            self.detail.set_model(int(mid))

    def refresh(self):
        try:
            models = list_models()
        except Exception:  # noqa: BLE001 -- best-effort
            models = []
        current = self.combo_model.currentData()
        self.combo_model.blockSignals(True)
        self.combo_model.clear()
        self._model_ids = []
        for m in models:
            self.combo_model.addItem(
                f"{m['file_name']}  ({m['sha256_hash'][:10]}...)",
                m["metadata_id"],
            )
            self._model_ids.append(m["metadata_id"])
        self.combo_model.blockSignals(False)
        if current is not None:
            idx = self.combo_model.findData(current)
            if idx >= 0:
                self.combo_model.setCurrentIndex(idx)
        if self.combo_model.count():
            self._on_pick()
        else:
            self.detail.set_model(None)

    def preselect(self, metadata_id):
        """Navigate to a model (by metadata_id or matching name) and load it."""
        if metadata_id is None:
            return
        if isinstance(metadata_id, int) or str(metadata_id).isdigit():
            idx = self.combo_model.findData(int(metadata_id))
            if idx >= 0:
                self.combo_model.setCurrentIndex(idx)
                return
        try:
            models = list_models()
        except Exception:  # noqa: BLE001
            models = []
        for m in models:
            if m["file_name"] == str(metadata_id):
                self.combo_model.setCurrentIndex(self.combo_model.findData(m["metadata_id"]))
                return

    def set_model(self, metadata_id):
        self.preselect(metadata_id)