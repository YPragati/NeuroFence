"""
Settings -- real operator configuration for the local NeuroFence install.

Shows the live environment (database path, reports directory, config
file) and lets the analyst tune the statistical anomaly-detection
thresholds -- which genuinely change the severity classification of
future scans. Changes are persisted to config/settings.yaml and reloaded,
so the dashboard/engine pick them up immediately.

Safety-gate whitelist and project metadata are read-only: they reflect
what config/settings.yaml actually contains.
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox,
    QSpinBox, QFormLayout, QMessageBox,
)

from src.desktop import theme
from src.desktop.widgets import PageHeader, Panel, FieldPair, confirm_dialog


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _config_path() -> str:
    return os.path.join(_project_root(), "config", "settings.yaml")


class SettingsView(QWidget):
    def __init__(self, on_notify=None, parent=None):
        super().__init__(parent)
        self._on_notify = on_notify
        self._build_ui()
        self.refresh()

    # ---- UI ----

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        header = PageHeader(
            "SETTINGS",
            subtitle="Environment, detection thresholds and safety gate for "
                     "the local NeuroFence install.",
            chip_text="OPERATOR CONFIG",
            chip_color=theme.ACCENT,
        )
        root.addWidget(header)

        # ---- Environment ----
        env = Panel("ENVIRONMENT & PATHS (READ-ONLY)")
        env_col = QVBoxLayout()
        env_col.setSpacing(4)
        self.env_db = FieldPair("DATABASE", "-", monospace=True)
        self.env_reports = FieldPair("REPORTS DIR", "-", monospace=True)
        self.env_config = FieldPair("CONFIG FILE", "-", monospace=True)
        for fp in [self.env_db, self.env_reports, self.env_config]:
            env_col.addWidget(fp)
        env.add_layout(env_col)
        root.addWidget(env)

        # ---- Thresholds ----
        thr = Panel("ANOMALY DETECTION THRESHOLDS")
        form = QFormLayout()
        form.setSpacing(10)
        self.spin_critical = QDoubleSpinBox()
        self.spin_critical.setRange(1, 100)
        self.spin_critical.setDecimals(1)
        self.spin_high = QDoubleSpinBox()
        self.spin_high.setRange(1, 100)
        self.spin_high.setDecimals(1)
        self.spin_medium = QDoubleSpinBox()
        self.spin_medium.setRange(1, 100)
        self.spin_medium.setDecimals(1)
        form.addRow("CRITICAL cutoff (score >=)", self.spin_critical)
        form.addRow("HIGH cutoff (score >=)", self.spin_high)
        form.addRow("MEDIUM cutoff (score >=)", self.spin_medium)

        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(0.5, 12.0)
        self.spin_z.setDecimals(2)
        self.spin_z.setSingleStep(0.1)
        form.addRow("Min |z-score|", self.spin_z)

        self.spin_baseline = QSpinBox()
        self.spin_baseline.setRange(1, 1000)
        form.addRow("Baseline min samples", self.spin_baseline)

        self.spin_gain = QDoubleSpinBox()
        self.spin_gain.setRange(0.1, 50.0)
        self.spin_gain.setDecimals(1)
        form.addRow("Score gain per sigma", self.spin_gain)

        self.spin_corr = QDoubleSpinBox()
        self.spin_corr.setRange(0.0, 1.0)
        self.spin_corr.setDecimals(2)
        self.spin_corr.setSingleStep(0.05)
        form.addRow("Correlation min", self.spin_corr)
        thr.add_layout(form)

        ctl = QHBoxLayout()
        self.btn_save = QPushButton("\u2713  SAVE THRESHOLDS")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self._save_config)
        self.btn_reset = QPushButton("Reload From Disk")
        self.btn_reset.setObjectName("GhostButton")
        self.btn_reset.clicked.connect(self.refresh)
        ctl.addWidget(self.btn_save)
        ctl.addWidget(self.btn_reset)
        ctl.addStretch(1)
        thr.add_layout(ctl)
        self.thr_status = QLabel("")
        self.thr_status.setObjectName("PageSubtitle")
        self.thr_status.setWordWrap(True)
        thr.add_widget(self.thr_status)
        root.addWidget(thr)

        # ---- Safety gate ----
        gate = Panel("SAFETY GATE (READ-ONLY)")
        gate_col = QVBoxLayout()
        gate_col.setSpacing(4)
        self.gate_active = FieldPair("ACTIVE TARGET", "-", monospace=True)
        self.gate_allowed = FieldPair("ALLOWED TARGETS", "-", monospace=True)
        for fp in [self.gate_active, self.gate_allowed]:
            gate_col.addWidget(fp)
        gate.add_layout(gate_col)
        root.addWidget(gate)

        # ---- About ----
        about = Panel("ABOUT")
        about_col = QVBoxLayout()
        about_col.setSpacing(4)
        self.about_name = FieldPair("PRODUCT", "-")
        self.about_version = FieldPair("VERSION", "-")
        self.about_desc = FieldPair("SCOPE", "-")
        for fp in [self.about_name, self.about_version, self.about_desc]:
            about_col.addWidget(fp)
        about.add_layout(about_col)
        root.addWidget(about)

        root.addStretch(1)

    # ---- data ----

    def refresh(self):
        from src.config_loader import get_config, _CONFIG_PATH
        from src.db.db_manager import get_db_path
        from src.reporting.forensic_report import _reports_dir

        self.env_db.set_value(str(get_db_path()))
        try:
            self.env_reports.set_value(str(_reports_dir()))
        except Exception:  # noqa: BLE001
            self.env_reports.set_value("-")
        self.env_config.set_value(_CONFIG_PATH)

        try:
            cfg = get_config(force_reload=False)
        except Exception as exc:  # noqa: BLE001
            self.thr_status.setText(f"Could not load config: {exc}")
            return

        stat = (cfg.get("anomaly_detection", {}) or {}).get("statistical", {}) or {}
        cutoffs = stat.get("severity_cutoffs") or [80, 60, 40]
        self.spin_critical.setValue(float(cutoffs[0]))
        self.spin_high.setValue(float(cutoffs[1]) if len(cutoffs) > 1 else 60)
        self.spin_medium.setValue(float(cutoffs[2]) if len(cutoffs) > 2 else 40)
        self.spin_z.setValue(float(stat.get("z_score_min", 2.0)))
        self.spin_baseline.setValue(int(stat.get("baseline_min_n", 2)))
        self.spin_gain.setValue(float(stat.get("score_gain_per_sigma", 10.0)))
        self.spin_corr.setValue(float(stat.get("correlation_min", 0.6)))

        model_cfg = cfg.get("model", {}) or {}
        self.gate_active.set_value(str(model_cfg.get("active_target", "-")))
        self.gate_allowed.set_value(
            ", ".join(str(t) for t in (model_cfg.get("allowed_targets") or [])) or "-"
        )

        proj = cfg.get("project", {}) or {}
        self.about_name.set_value(str(proj.get("name", "NeuroFence")))
        self.about_version.set_value(str(proj.get("version", "?")))
        self.about_desc.set_value(
            "Detects potentially suspicious activation behavior over real local "
            "scans. Statistical anomalies are evidence, not proof of a backdoor."
        )

        self.thr_status.setText("Thresholds loaded from config/settings.yaml.")

    def _save_config(self):
        import yaml
        from src.config_loader import get_config

        path = _config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save Failed",
                                 f"Could not read {path}:\n{exc}")
            return

        stat = (cfg.get("anomaly_detection", {}) or {}).get("statistical", {}) or {}
        stat["severity_cutoffs"] = [
            self.spin_critical.value(),
            self.spin_high.value(),
            self.spin_medium.value(),
        ]
        stat["z_score_min"] = self.spin_z.value()
        stat["baseline_min_n"] = self.spin_baseline.value()
        stat["score_gain_per_sigma"] = self.spin_gain.value()
        stat["correlation_min"] = self.spin_corr.value()
        cfg.setdefault("anomaly_detection", {})["statistical"] = stat

        try:
            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(cfg, fh, sort_keys=False, allow_unicode=True)
            get_config(force_reload=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save Failed", f"Could not save:\n{exc}")
            return

        self.thr_status.setText(
            "Saved to config/settings.yaml and reloaded. Changes apply to "
            "future scans."
        )
        if self._on_notify:
            self._on_notify("Thresholds saved to config/settings.yaml.", "success")