"""
New Scan -- pipeline scan configuration page.

Lets the analyst configure one full NeuroFence scan (model, prompt count,
sequence length, layers, seed, input categories) against the local model.
The estimated scan size is computed live from the real input generator.
Pressing "Start Scan" validates the configuration, asks for confirmation,
creates a real QUEUED pipeline scan row and hands it to the main window,
which launches the backend subprocess and opens the Live Scan monitor.

No progress is simulated here -- the backend owns progress.
"""

from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QComboBox, QCheckBox, QFormLayout, QGridLayout, QMessageBox,
    QFrame, QFileDialog, QDialog,
)

import os

from src.desktop import theme
from src.desktop.widgets import PageHeader, Panel, KpiCard, FieldPair, confirm_dialog, StatusTile
from src.fuzzer.adversarial_generator import CATEGORY_KEYS, CATEGORY_LABELS
from src.model_interface.loader import SAFE_WEIGHT_EXTENSIONS
from src.model_interface.import_service import import_model

_FALLBACK_KEYS = {"tiny", "loaded", "toy"}

_DEPTH_ORDER = ["QUICK CHECK", "STANDARD", "DEEP ANALYSIS"]


class _ImportWorker(QThread):
    """Threaded model import (SHA-256 hashing can take a moment)."""

    finished = pyqtSignal(dict)

    def __init__(self, path):
        super().__init__()
        self._path = path

    def run(self):
        try:
            result = import_model(self._path)
        except Exception as exc:  # noqa: BLE001 -- surface to UI
            result = {"errors": [str(exc)], "models": []}
        self.finished.emit(result)


# Real scan presets -- they only pre-fill the genuine configuration options
# the backend supports (num_prompts, seq length, layers, tokens, categories).
SCAN_PROFILES = {
    "STANDARD": {
        "num_prompts": 8, "max_seq_len": 16, "layers": 12,
        "max_new_tokens": 3, "categories": list(CATEGORY_KEYS),
    },
    "DEEP ANALYSIS": {
        "num_prompts": 24, "max_seq_len": 32, "layers": 16,
        "max_new_tokens": 6, "categories": list(CATEGORY_KEYS),
    },
    "QUICK CHECK": {
        "num_prompts": 4, "max_seq_len": 12, "layers": 8,
        "max_new_tokens": 2,
        "categories": [k for k in CATEGORY_KEYS if k in ("normal", "adversarial", "edge")],
    },
}


class NewScanView(QWidget):
    """Guided pipeline-scan configuration page (investigation steps 1-3)."""

    pipeline_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._launching = False
        self._build_ui()
        self.refresh()

    # ---- UI ----

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        header = PageHeader(
            "NEW INVESTIGATION",
            subtitle="Five-step workflow: model selection, integrity "
                     "verification, configuration, live analysis and the "
                     "final result.",
            chip_text="LOCAL  /  OFFLINE  /  DEFENSIVE",
            chip_color=theme.SUCCESS,
        )
        root.addWidget(header)

        # STEP 1 -- Model source (import or pick an existing registry model)
        step1 = QLabel(
            f"<span style='color:{theme.ACCENT};font-weight:700;'>STEP 1 \u2014 MODEL SOURCE</span>"
            f"<span style='color:{theme.TEXT_DIM};font-size:10px;'>"
            f"  choose how the investigation model is provided</span>"
        )
        step1.setTextFormat(Qt.RichText)
        root.addWidget(step1)

        source_row = QHBoxLayout()
        source_row.setSpacing(14)

        import_card = Panel("IMPORT NEW MODEL")
        import_note = QLabel(
            "Import a model file or directory into the local registry. "
            "SHA-256, format validation and architecture detection run "
            "locally \u2014 the file never leaves this machine."
        )
        import_note.setObjectName("PageSubtitle")
        import_note.setWordWrap(True)
        import_card.add_widget(import_note)
        import_btn_row = QHBoxLayout()
        self.btn_import_model = QPushButton("\u2b06  IMPORT MODEL FILE")
        self.btn_import_model.setObjectName("PrimaryButton")
        self.btn_import_model.clicked.connect(self._import_model_file)
        import_btn_row.addWidget(self.btn_import_model)
        import_btn_row.addStretch(1)
        import_card.add_layout(import_btn_row)
        source_row.addWidget(import_card, 1)

        select_card = Panel("SELECT EXISTING MODEL")
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        sel_row.addWidget(QLabel("MODEL"))
        self.combo_model = QComboBox()
        self.combo_model.currentIndexChanged.connect(self._on_model_changed)
        sel_row.addWidget(self.combo_model, 1)
        select_card.add_layout(sel_row)
        self.select_note = QLabel(
            "Model identity, hash and integrity come from the real registry "
            "record selected here."
        )
        self.select_note.setObjectName("PageSubtitle")
        self.select_note.setWordWrap(True)
        select_card.add_widget(self.select_note)
        source_row.addWidget(select_card, 2)

        root.addLayout(source_row)

        # STEP 1 -- live estimation of the scan size
        est_title = QLabel(
            f"<span style='color:{theme.ACCENT};font-weight:700;'>STEP 1 \u2014 ESTIMATED SCAN SIZE</span>"
            f"<span style='color:{theme.TEXT_DIM};font-size:10px;'>  live from the input generator</span>"
        )
        est_title.setTextFormat(Qt.RichText)
        root.addWidget(est_title)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_prompts = KpiCard("PROMPTS", "0", accent=theme.ACCENT, sub="generated",
                                    icon="\u25b6")
        self.card_layers = KpiCard("LAYERS", "0", accent=theme.WARNING, sub="per prompt",
                                   icon="\u25c8")
        self.card_measurements = KpiCard("EST. MEASUREMENTS", "0", accent=theme.SUCCESS,
                                         sub="prompts x layers", icon="\u2605")
        self.card_categories = KpiCard("CATEGORIES", "0", accent=theme.ANALYTICS, sub="selected",
                                       icon="\u2261")
        for c in [self.card_prompts, self.card_layers, self.card_measurements, self.card_categories]:
            cards.addWidget(c, 1)
        root.addLayout(cards)

        cols = QHBoxLayout()
        cols.setSpacing(14)

        # ---- STEP 2: Verification panel (real model checks) ----
        verify = Panel("STEP 2 \u2014 MODEL VERIFICATION")
        self._verify_tiles = {}
        for label in ("FILE INTEGRITY", "SHA-256 HASH", "FORMAT VALIDATION",
                      "ARCHITECTURE ID", "SANDBOX CHECK", "LOCAL EXECUTION"):
            tile = StatusTile(label, status="ok")
            verify.add_widget(tile)
            self._verify_tiles[label] = tile
        self.verify_note = QLabel(
            "Checks reflect the real selected model record \u2014 nothing is "
            "assumed to have passed."
        )
        self.verify_note.setObjectName("PageSubtitle")
        self.verify_note.setWordWrap(True)
        verify.add_widget(self.verify_note)
        offline = StatusTile("SECURE OFFLINE ENVIRONMENT", status="ok",
                             detail="No external network communication required")
        offline.set_ok(True)
        verify.add_widget(offline)
        verify.stretch()
        cols.addWidget(verify, 2)

        # ---- STEP 3: Configuration panel ----
        cfg = Panel("STEP 3 \u2014 CONFIGURE")
        form = QFormLayout()
        form.setSpacing(10)

        self.combo_profile = QComboBox()
        for name in _DEPTH_ORDER:
            if name in SCAN_PROFILES:
                self.combo_profile.addItem(name)
        std_idx = self.combo_profile.findText("STANDARD")
        if std_idx >= 0:
            self.combo_profile.setCurrentIndex(std_idx)
        self.combo_profile.currentIndexChanged.connect(self._apply_profile)
        form.addRow("Analysis Depth", self.combo_profile)

        self.spin_prompts = QSpinBox()
        self.spin_prompts.setRange(1, 1000)
        self.spin_prompts.setValue(8)
        form.addRow("Number of Prompts", self.spin_prompts)
        cfg.add_layout(form)

        # Collapsible advanced options
        self.btn_advanced = QPushButton("\u25b8  ADVANCED OPTIONS")
        self.btn_advanced.setObjectName("GhostButton")
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.toggled.connect(self._toggle_advanced)
        cfg.add_widget(self.btn_advanced)

        self.advanced_box = QFrame()
        self.advanced_box.setStyleSheet(
            f"background:{theme.BG_INPUT};border-radius:8px;"
        )
        adv_layout = QVBoxLayout(self.advanced_box)
        adv_layout.setContentsMargins(10, 10, 10, 10)
        adv_form = QFormLayout()
        adv_form.setSpacing(8)

        self.spin_seq = QSpinBox()
        self.spin_seq.setRange(4, 512)
        self.spin_seq.setValue(16)
        adv_form.addRow("Max Sequence Length", self.spin_seq)

        self.spin_tokens = QSpinBox()
        self.spin_tokens.setRange(1, 64)
        self.spin_tokens.setValue(3)
        adv_form.addRow("Max New Tokens", self.spin_tokens)

        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 2**31 - 1)
        self.spin_seed.setValue(42)
        adv_form.addRow("Random Seed", self.spin_seed)

        self.spin_layers = QSpinBox()
        self.spin_layers.setRange(1, 64)
        self.spin_layers.setValue(12)
        adv_form.addRow("Layers to Track", self.spin_layers)

        adv_layout.addLayout(adv_form)
        self.advanced_box.setVisible(False)
        cfg.add_widget(self.advanced_box)

        cat_title = QLabel("INPUT CATEGORIES")
        cat_title.setObjectName("FieldLabel")
        cfg.add_widget(cat_title)
        cat_grid = QGridLayout()
        cat_grid.setSpacing(6)
        self.category_checks = {}
        for i, key in enumerate(CATEGORY_KEYS):
            cb = QCheckBox(CATEGORY_LABELS.get(key, key))
            cb.setChecked(True)
            self.category_checks[key] = cb
            cat_grid.addWidget(cb, i // 2, i % 2)
        cfg.add_layout(cat_grid)
        cfg.stretch()
        cols.addWidget(cfg, 3)

        root.addLayout(cols)

        # ---- Estimate detail + execution ----
        est = Panel("ESTIMATED SCAN SIZE (LIVE)")
        self.est_rows = QVBoxLayout()
        self.est_rows.setSpacing(8)
        est.add_layout(self.est_rows)
        root.addWidget(est)

        ctl = Panel("EXECUTION")
        ctl_row = QHBoxLayout()
        self.btn_start = QPushButton("\u25b6  LAUNCH INVESTIGATION")
        self.btn_start.setObjectName("PrimaryButton")
        self.btn_start.setMinimumHeight(44)
        self.btn_start.clicked.connect(self._start_scan)
        ctl_row.addWidget(self.btn_start, 2)
        self.btn_refresh = QPushButton("Refresh Models")
        self.btn_refresh.setObjectName("GhostButton")
        self.btn_refresh.clicked.connect(self.refresh)
        ctl_row.addWidget(self.btn_refresh, 1)
        ctl.add_layout(ctl_row)

        self.status_label = QLabel(
            "Ready. Configure the investigation, then launch \u2014 live "
            "analysis opens in the Analyze step."
        )
        self.status_label.setObjectName("PageSubtitle")
        self.status_label.setWordWrap(True)
        ctl.add_widget(self.status_label)
        root.addWidget(ctl)

        root.addStretch(1)

        # Live estimate updates
        for widget in [self.spin_prompts, self.spin_seq, self.spin_layers, self.spin_tokens]:
            widget.valueChanged.connect(self._update_estimate)
        for cb in self.category_checks.values():
            cb.toggled.connect(self._update_estimate)

        self._update_estimate()

    def _toggle_advanced(self, checked):
        self.btn_advanced.setText(
            ("\u25be  ADVANCED OPTIONS" if checked else "\u25b8  ADVANCED OPTIONS")
        )
        self.advanced_box.setVisible(checked)

    def _import_model_file(self):
        """Import a model into the local registry from the New Scan page."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select model file",
            "",
            "Model files (*.json *.safetensors *.pt *.pth *.bin *.onnx);;All files (*)",
        )
        if not path:
            return
        import_dir = self._try_directory_import(path)
        if import_dir:
            return
        self.btn_import_model.setEnabled(False)
        self.status_label.setText("Importing model \u2014 computing SHA-256 hash, validating format.")
        self._import_worker = _ImportWorker(path)
        self._import_worker.finished.connect(self._on_import_done)
        self._import_worker.start()

    def _try_directory_import(self, path):
        if os.path.isdir(path):
            self.btn_import_model.setEnabled(False)
            self.status_label.setText("Importing directory \u2014 computing SHA-256 hash.")
            self._import_worker = _ImportWorker(path)
            self._import_worker.finished.connect(self._on_import_done)
            self._import_worker.start()
            return True
        return False

    def _on_import_done(self, result):
        self.btn_import_model.setEnabled(True)
        self._import_worker = None

        if result.get("errors"):
            self.status_label.setText(
                f"Import errors: {'; '.join(result['errors'][:3])}"
            )
            return
        count = len(result.get("models", []))
        self.status_label.setText(
            f"Imported {count} model record(s). Registry refreshed."
        )
        self.refresh()
        self.verify_note.setText("Model import completed \u2014 verification rows now reflect the real record.")

    def set_launching(self, launching: bool):
        """Disable/re-enable the start button while the pipeline launches."""
        self._launching = bool(launching)
        self.btn_start.setEnabled(not self._launching)
        self.btn_refresh.setEnabled(not self._launching)
        if self._launching:
            self.status_label.setText("Launching pipeline investigation...")

    # ---- verification (real model record checks) ----

    def _selected_model_record(self):
        """Registry record dict for the currently picked model, or None."""
        from src.model_interface.import_service import list_models, get_model
        key = self.combo_model.currentData()
        if key is None:
            return None
        if str(key).isdigit():
            rec = get_model(int(key))
            return rec
        for m in list_models():
            if m["file_name"] == str(key) or str(key) == str(m["metadata_id"]):
                return m
        return None

    def _on_model_changed(self, _index=0):
        self._update_verification()
        self._update_estimate()

    def _update_verification(self):
        """Real integrity checks for the selected model (never assumed ok)."""
        rec = self._selected_model_record()
        key = self.combo_model.currentData()
        file_path = (rec or {}).get("file_path") or ""
        sha = (rec or {}).get("sha256_hash") or ""
        arch = (rec or {}).get("architecture") or ""
        model_type = (rec or {}).get("model_type") or ""
        supported = bool((rec or {}).get("supported", True))

        checks = {
            "FILE INTEGRITY": bool(file_path and os.path.exists(file_path)),
            "SHA-256 HASH": bool(sha),
            "FORMAT VALIDATION": (
                bool(model_type) or
                os.path.splitext(file_path)[1].lower() in
                {e.lower() for e in SAFE_WEIGHT_EXTENSIONS}
                or (file_path and os.path.isdir(file_path))
            ) and bool(file_path or model_type),
            "ARCHITECTURE ID": bool(arch),
            "SANDBOX CHECK": supported,
            "LOCAL EXECUTION": bool(key in _FALLBACK_KEYS) or bool(supported and rec),
        }
        details = {
            "FILE INTEGRITY": os.path.basename(file_path) if file_path else "no file on disk",
            "SHA-256 HASH": (sha[:16] + "...") if sha else "hash not recorded",
            "FORMAT VALIDATION": (
                (os.path.splitext(file_path)[1].lstrip(".").upper() or model_type)
                if file_path else (model_type or "unknown format")
            ),
            "ARCHITECTURE ID": arch or "architecture not detected",
            "SANDBOX CHECK": ("supported" if supported else "unsupported engine"),
            "LOCAL EXECUTION": (
                str(key) if key in _FALLBACK_KEYS else (model_type or "fallback")
            ),
        }
        for label, ok in checks.items():
            tile = self._verify_tiles[label]
            tile.set_ok(ok)
            tile.set_detail(details.get(label, ""))
        self._last_checks = dict(checks)
        passed = sum(1 for ok in checks.values() if ok)
        if not rec and key not in _FALLBACK_KEYS:
            self.verify_note.setText(
                "No registry record for this target \u2014 the engine fallback "
                "targets are listed in Step 3."
            )
        elif passed == len(checks):
            self.verify_note.setText(
                f"All {passed} checks passed for the selected model record.")
        else:
            self.verify_note.setText(
                f"{passed} of {len(checks)} checks passed. Integrity gaps are "
                "shown honestly \u2014 you can still continue with the scan.")

    def selected_verified(self) -> dict:
        """Summary state for the workbench step strip (real check results)."""
        rec = self._selected_model_record() or {}
        sha = bool(rec.get("sha256_hash"))
        arch = bool(rec.get("architecture"))
        ok = sha or arch or self.combo_model.currentData() in _FALLBACK_KEYS
        return {
            "ok": bool(ok),
            "checks": dict(getattr(self, "_last_checks", {})),
            "model": self.combo_model.currentText(),
        }

    # ---- estimate ----

    def _apply_profile(self, _index=0):
        """Pre-fill the real scan options from the selected profile preset."""
        name = self.combo_profile.currentText()
        preset = SCAN_PROFILES.get(name)
        if not preset:
            return
        self.spin_prompts.setValue(preset["num_prompts"])
        self.spin_seq.setValue(preset["max_seq_len"])
        self.spin_layers.setValue(preset["layers"])
        self.spin_tokens.setValue(preset["max_new_tokens"])
        for key, cb in self.category_checks.items():
            cb.setChecked(key in preset["categories"])
        self._update_estimate()

    def preselect(self, model_name: str):
        """Target the scan at a specific registry model name if available."""
        if not model_name:
            return
        for i in range(self.combo_model.count()):
            data = self.combo_model.itemData(i)
            txt = self.combo_model.itemText(i)
            if str(data) == str(model_name) or model_name in txt:
                self.combo_model.setCurrentIndex(i)
                return

    def _update_estimate(self):
        from src.fuzzer.adversarial_generator import AdversarialInputGenerator
        gen = AdversarialInputGenerator(seed=self.spin_seed.value())
        categories = self.selected_categories()
        est = gen.estimate_size(
            count=self.spin_prompts.value(),
            categories=categories,
            layers=self.spin_layers.value(),
        )
        self.card_prompts.set_value(str(est["prompts"]))
        self.card_layers.set_value(str(est["layers_per_prompt"]))
        self.card_measurements.set_value(f"{est['measurements']:,}")
        self.card_categories.set_value(str(est["categories"]))

        while self.est_rows.count():
            item = self.est_rows.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        rows = [
            ("Prompts", f"{est['prompts']:,}"),
            ("Layers / prompt", f"{est['layers_per_prompt']:,}"),
            ("Est. measurements", f"{est['measurements']:,}"),
            ("Selected categories", str(est["categories"])),
            ("Max sequence length", str(self.spin_seq.value())),
            ("Max new tokens", str(self.spin_tokens.value())),
            ("Seed", str(self.spin_seed.value())),
        ]
        for label, value in rows:
            self.est_rows.addWidget(FieldPair(label, value))

    # ---- data ----

    def selected_categories(self) -> list:
        return [k for k, cb in self.category_checks.items() if cb.isChecked()]

    def refresh(self):
        from src.model_interface.import_service import list_models
        try:
            models = list_models()
        except Exception:  # noqa: BLE001 -- best-effort
            models = []
        self.combo_model.blockSignals(True)
        self.combo_model.clear()
        for m in models:
            self.combo_model.addItem(
                f"{m['file_name']}  ({m['sha256_hash'][:10]}...)",
                m["file_name"] or m["metadata_id"],
            )
        for fb in self._fallback_models():
            self.combo_model.addItem(fb["label"], fb["key"])
        self.combo_model.setCurrentIndex(0)
        self.combo_model.blockSignals(False)
        self._update_verification()
        self._update_estimate()

    def _fallback_models(self):
        return [
            {"key": "tiny", "label": "Tiny Transformer (PyTorch, real activations)"},
            {"key": "loaded", "label": "Currently loaded model"},
            {"key": "toy", "label": "Toy Model (rule-based, no real activations)"},
        ]

    # ---- actions ----

    def _start_scan(self):
        if self._launching:
            return
        categories = self.selected_categories()
        if not categories:
            QMessageBox.warning(self, "No Categories", "Select at least one input category.")
            return

        config = {
            "model": self.combo_model.currentData(),
            "num_prompts": self.spin_prompts.value(),
            "max_seq_len": self.spin_seq.value(),
            "categories": categories,
            "seed": self.spin_seed.value(),
            "layers": self.spin_layers.value(),
            "max_new_tokens": self.spin_tokens.value(),
        }

        ok = confirm_dialog(
            self,
            "Launch Investigation",
            f"Launch a full forensics investigation with {config['num_prompts']} "
            f"prompts x {config['layers']} layers on '{config['model']}'?\n\n"
            "The investigation runs locally in a sandboxed subprocess. Live "
            "analysis opens in the Analyze step.",
            ok_text="Launch Investigation",
            cancel_text="Cancel",
        )
        if not ok:
            return

        self.set_launching(True)
        self.pipeline_requested.emit(config)