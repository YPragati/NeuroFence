"""
Models Page -- import, list, and manage local model files.

Professional model registry view with import dialog, model table,
validation status, and detail navigation. All data reads from the
SQLite database via the import service -- no hardcoded values.
"""

import os

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QFrame, QSplitter,
)

from src.desktop import theme, data_service
from src.desktop.widgets import (
    PageHeader, Panel, KpiCard, SectionHeader, FieldPair, StatusTile,
    make_table, clear_table, DataTable, show_toast,
)
from src.model_interface.import_service import (
    import_model,
    list_models,
    get_model,
    delete_model,
    update_model_status,
    load_model_file,
    unload_model_file,
    model_load_status,
)
from src.model_interface.model_forensics import format_size


# Column indices for the model table
COL_ID = 0
COL_NAME = 1
COL_FORMAT = 2
COL_SIZE = 3
COL_SHA = 4
COL_ARCH = 5
COL_STATUS = 6
COL_IMPORTED = 7

TABLE_HEADERS = [
    "ID", "MODEL NAME", "FORMAT", "SIZE", "SHA-256",
    "ARCHITECTURE", "STATUS", "IMPORTED",
]


class ModelImportWorker(QThread):
    """Background worker for model import (hash computation can be slow)."""
    finished = pyqtSignal(dict)

    def __init__(self, path):
        super().__init__()
        self._path = path

    def run(self):
        result = import_model(self._path)
        self.finished.emit(result)


class ModelLoadWorker(QThread):
    """Background worker for the 'Load for Analysis' action."""

    finished = pyqtSignal(dict)

    def __init__(self, metadata_id: int, load: bool):
        super().__init__()
        self._metadata_id = metadata_id
        self._load = load

    def run(self):
        if self._load:
            result = load_model_file(self._metadata_id)
        else:
            result = unload_model_file(self._metadata_id)
        self.finished.emit(result)


class ModelsView(QWidget):
    """
    Model registry page: table of all imported models with import/delete
    actions and a detail panel for the selected model.
    """

    model_selected = pyqtSignal(int)  # emits metadata_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._load_worker = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        # Header
        header = PageHeader(
            "MODELS",
            subtitle="Import, validate and manage local model files for forensic scanning.",
            chip_text="LOCAL  /  OFFLINE",
            chip_color=theme.ACCENT,
        )
        root.addWidget(header)

        # KPI cards
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_total = KpiCard("TOTAL MODELS", "0", accent=theme.ACCENT, sub="imported")
        self.card_validated = KpiCard("VALIDATED", "0", accent=theme.SUCCESS, sub="ready")
        self.card_scanned = KpiCard("SCANNED", "0", accent=theme.WARNING, sub="processed")
        self.card_size = KpiCard("TOTAL SIZE", "0 B", accent=theme.ACCENT, sub="all models")
        for c in [self.card_total, self.card_validated, self.card_scanned, self.card_size]:
            cards.addWidget(c, 1)
        root.addLayout(cards)

        # Actions bar
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.btn_import = QPushButton("Import Model File...")
        self.btn_import.setObjectName("PrimaryButton")
        self.btn_import.clicked.connect(self._import_file)
        self.btn_import_dir = QPushButton("Import Model Directory...")
        self.btn_import_dir.clicked.connect(self._import_directory)
        self.btn_checkpoint = QPushButton("Open Security Checkpoint")
        self.btn_checkpoint.setObjectName("GhostButton")
        self.btn_checkpoint.clicked.connect(self._open_checkpoint)
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setObjectName("GhostButton")
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_load = QPushButton("Load for Analysis")
        self.btn_load.setObjectName("PrimaryButton")
        self.btn_load.clicked.connect(self._load_for_analysis)
        actions.addWidget(self.btn_import)
        actions.addWidget(self.btn_import_dir)
        actions.addStretch(1)
        actions.addWidget(self.btn_checkpoint)
        actions.addWidget(self.btn_load)
        actions.addWidget(self.btn_delete)
        root.addLayout(actions)

        # Status label + load status badge
        status_row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("PageSubtitle")
        status_row.addWidget(self.status_label, 1)
        self.load_status_badge = QLabel("")
        self.load_status_badge.setAlignment(Qt.AlignCenter)
        self.load_status_badge.setStyleSheet(
            "padding:5px 14px;border-radius:8px;font-size:11px;font-weight:700;"
            "letter-spacing:0.8px;color:#0e1424;"
        )
        self.load_status_badge.setFixedWidth(140)
        self.load_status_badge.setVisible(False)
        status_row.addWidget(self.load_status_badge)
        root.addLayout(status_row)

        # Splitter: table on top, detail panel below
        splitter = QSplitter(Qt.Vertical)

        # Model table (searchable, sortable, paginated)
        table_panel = Panel("IMPORTED MODELS")
        self.table = DataTable(TABLE_HEADERS, page_size=12, stretch_col=COL_NAME)
        self.table.set_cell_stylist(self._style_cell)
        self.table.rowSelected.connect(self._on_row_selected)
        table_panel.add_widget(self.table)
        splitter.addWidget(table_panel)

        # Detail panel
        detail_panel = Panel("MODEL DETAILS")
        detail_grid = QVBoxLayout()
        detail_grid.setSpacing(4)
        self.detail_fields = {}
        detail_spec = [
            ("FILE NAME", "file_name", False),
            ("MODEL TYPE", "model_type", False),
            ("ARCHITECTURE", "architecture", False),
            ("FORMAT", "format", False),
            ("FILE SIZE", "file_size", False),
            ("SHA-256", "sha256", True),
            ("PARAMETERS", "num_parameters", False),
            ("LAYERS", "layer_count", False),
            ("STATUS", "status", False),
            ("NOTES", "notes", False),
            ("IMPORTED", "created_at", False),
            ("LAST SCANNED", "scanned_at", False),
        ]
        for label, key, mono in detail_spec:
            fp = FieldPair(label, "-", monospace=mono)
            self.detail_fields[key] = fp
            detail_grid.addWidget(fp)

        # Validation tiles
        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(8)
        self.tile_valid = StatusTile("VALIDATED")
        self.tile_hash = StatusTile("SHA-256 OK")
        self.tile_safe = StatusTile("SAFE FORMAT")
        for t in [self.tile_valid, self.tile_hash, self.tile_safe]:
            tiles_row.addWidget(t)
        detail_grid.addLayout(tiles_row)

        detail_panel.add_layout(detail_grid)
        splitter.addWidget(detail_panel)

        splitter.setSizes([400, 300])
        root.addWidget(splitter, 1)

    # ---- data ----

    def refresh(self):
        """Reload model list from database and update all UI elements."""
        models = list_models()
        self._populate_table(models)
        self._update_kpis(models)
        self._clear_detail()

    def _populate_table(self, models):
        rows = []
        ids = []
        for m in models:
            ext = os.path.splitext(m["file_name"])[1] if m["file_name"] else ""
            rows.append([
                m["metadata_id"],
                m["file_name"] or "?",
                ext.upper().lstrip(".") or m.get("model_type", "?"),
                format_size(m["file_size_bytes"]),
                (m["sha256_hash"] or "?")[:20] + "...",
                m.get("architecture") or "N/A",
                data_service.model_status_label_local(m),
                (m.get("created_at") or "?")[:19],
            ])
            ids.append(m["metadata_id"])
        self.table.set_rows(rows, ids)

    def _style_cell(self, _orig, item, col):
        if col == COL_STATUS:
            status = item.text()
            color = {
                "VERIFIED": theme.SUCCESS,
                "APPROVED": theme.SUCCESS,
                "SCANNED": theme.WARNING,
                "REVIEW REQUIRED": theme.WARNING,
                "QUARANTINED": theme.CRITICAL,
                "ERROR": theme.CRITICAL,
                "UNVERIFIED": theme.ACCENT_SECONDARY,
            }.get(status, theme.ACCENT)
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignCenter)
        elif col in (COL_ID, COL_SIZE):
            item.setTextAlignment(Qt.AlignCenter)

    def _update_kpis(self, models):
        total = len(models)
        processed = ("validated", "scanned", "approved", "review", "quarantined")
        scanned_like = ("scanned", "approved", "review", "quarantined")
        validated = sum(1 for m in models if m.get("status") in processed)
        scanned = sum(1 for m in models if m.get("status") in scanned_like)
        total_size = sum(m.get("file_size_bytes", 0) for m in models)
        self.card_total.set_value(str(total))
        self.card_validated.set_value(str(validated))
        self.card_scanned.set_value(str(scanned))
        self.card_size.set_value(format_size(total_size))

    def _open_checkpoint(self):
        """Open the security checkpoint for the currently selected model."""
        mid = self.table.current_row_index()
        if mid is None or mid < 0:
            self.status_label.setText("Select a model row to open its security checkpoint.")
            return
        self.model_selected.emit(mid)

    def _clear_detail(self):
        for fp in self.detail_fields.values():
            fp.set_value("-")
        self.tile_valid.set_ok(False)
        self.tile_hash.set_ok(False)
        self.tile_safe.set_ok(False)

    # ---- actions ----

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select model file",
            "",
            "Model files (*.json *.safetensors *.pt *.pth *.bin *.onnx);;All files (*)",
        )
        if path:
            self._do_import(path)

    def _import_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Select model directory")
        if path:
            self._do_import(path)

    def _do_import(self, path):
        self.btn_import.setEnabled(False)
        self.btn_import_dir.setEnabled(False)
        self.status_label.setText("Importing... computing SHA-256 hash, validating format.")
        self._worker = ModelImportWorker(path)
        self._worker.finished.connect(self._on_import_done)
        self._worker.start()

    def _on_import_done(self, result):
        self.btn_import.setEnabled(True)
        self.btn_import_dir.setEnabled(True)
        self._worker = None

        if result["errors"]:
            errors = "\n".join(result["errors"])
            self.status_label.setText(f"Import errors: {errors}")
            show_toast(self, "Model import finished with errors.", "error")
            QMessageBox.warning(self, "Import Issues", errors)
        elif result["models"]:
            count = len(result["models"])
            dupes = sum(1 for m in result["models"] if m.get("duplicate"))
            if dupes:
                self.status_label.setText(
                    f"Imported {count - dupes} new model(s). "
                    f"{dupes} duplicate(s) already in registry."
                )
            else:
                self.status_label.setText(f"Successfully imported {count} model(s).")
                show_toast(self, f"Imported {count} model(s) into the registry.", "success")
        else:
            self.status_label.setText("No models imported.")

        self.refresh()

    # ---- model loading for analysis ----

    def _load_for_analysis(self):
        """Load the currently selected model for safe local analysis."""
        metadata_id = self.table.current_row_index()
        if metadata_id < 0:
            QMessageBox.information(
                self, "No Model Selected",
                "Select a model row in the table before loading."
            )
            return
        model = get_model(metadata_id)
        if not model or not model.get("file_path"):
            QMessageBox.warning(self, "Model Error", "Model file path is missing.")
            return
        ext = os.path.splitext(model["file_path"])[1].lower()
        if ext in {".pt", ".pth", ".bin", ".py", ".pyc"}:
            QMessageBox.warning(
                self, "Unsafe Format",
                f"Refusing to load '{ext}': this format can execute arbitrary "
                "Python code on load. Only safetensors (and ONNX) are supported."
            )
            return

        # If currently loaded, offer to unload instead
        status = model_load_status(metadata_id)
        if status["status"] == "ready":
            reply = QMessageBox.question(
                self, "Unload Model",
                f"Model '{model.get('file_name')}' is already loaded. Unload it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._do_load(metadata_id, load=False)
            return

        self._do_load(metadata_id, load=True)

    def _do_load(self, metadata_id: int, load: bool = True):
        self.btn_load.setEnabled(False)
        self.btn_import.setEnabled(False)
        self.btn_import_dir.setEnabled(False)
        if load:
            self.status_label.setText("Loading model into memory (CPU, offline, safe)...")
            self._set_load_badge("loading")
        else:
            self.status_label.setText("Unloading model...")
        self._load_worker = ModelLoadWorker(metadata_id, load=load)
        self._load_worker.finished.connect(self._on_load_done)
        self._load_worker.start()

    def _on_load_done(self, result: dict):
        self.btn_load.setEnabled(True)
        self.btn_import.setEnabled(True)
        self.btn_import_dir.setEnabled(True)
        self._load_worker = None
        status = result.get("status", "failed")
        msg = result.get("message", "")
        self.status_label.setText(f"Loader: {msg}")
        self._set_load_badge(status)
        self.refresh()

    def _set_load_badge(self, status: str):
        status = (status or "unsupported").lower().strip()
        color_map = {
            "loading":  (theme.WARNING, "LOADING"),
            "ready":    (theme.SUCCESS, "READY"),
            "failed":   (theme.DANGER,  "FAILED"),
            "unsupported": (theme.TEXT_MUTED, "UNSUPPORTED"),
        }
        color, label = color_map.get(status, (theme.TEXT_MUTED, "UNSUPPORTED"))
        self.load_status_badge.setText(label)
        self.load_status_badge.setStyleSheet(
            f"padding:5px 14px;border-radius:8px;font-size:11px;"
            f"font-weight:700;letter-spacing:0.8px;"
            f"color:{color};border:1px solid {color}3d;"
            f"background:{color}1a;"
        )
        self.load_status_badge.setVisible(True)

    def _delete_selected(self):
        metadata_id = self.table.current_row_index()
        if metadata_id < 0:
            return
        model = get_model(metadata_id)
        name = (model or {}).get("file_name", "?")

        reply = QMessageBox.question(
            self,
            "Delete Model",
            f"Remove '{name}' (ID {metadata_id}) from the registry?\n"
            "This does not delete the original file.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_model(metadata_id)
            show_toast(self, f"Removed '{name}' from the registry.", "success")
            self.refresh()

    def _on_row_selected(self, metadata_id):
        model = get_model(metadata_id)
        if model:
            self._show_detail(model)
            self.model_selected.emit(metadata_id)

    def _show_detail(self, m):
        ext = os.path.splitext(m["file_name"])[1] if m["file_name"] else ""
        self.detail_fields["file_name"].set_value(m["file_name"] or "?")
        self.detail_fields["model_type"].set_value(m.get("model_type") or "unknown")
        self.detail_fields["architecture"].set_value(m.get("architecture") or "N/A")
        self.detail_fields["format"].set_value(
            ext.upper().lstrip(".") or m.get("model_type") or "unknown"
        )
        self.detail_fields["file_size"].set_value(format_size(m.get("file_size_bytes", 0)))
        self.detail_fields["sha256"].set_value(m.get("sha256_hash") or "N/A")
        self.detail_fields["num_parameters"].set_value(
            "-" if m.get("num_parameters") is None else f"{m['num_parameters']:,}"
        )
        self.detail_fields["layer_count"].set_value(
            "-" if m.get("layer_count") is None else str(m["layer_count"])
        )
        self.detail_fields["status"].set_value((m.get("status") or "imported").upper())
        self.detail_fields["notes"].set_value(m.get("notes") or "-")
        self.detail_fields["created_at"].set_value(m.get("created_at") or "-")
        self.detail_fields["scanned_at"].set_value(m.get("scanned_at") or "Never")

        ok = m.get("supported", False)
        self.tile_valid.set_ok(ok)
        self.tile_hash.set_ok(bool(m.get("sha256_hash")))
        self.tile_safe.set_ok(ok and "unsafe" not in (m.get("notes") or "").lower())
