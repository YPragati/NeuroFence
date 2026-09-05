"""
Activation Explorer -- real per-layer activation statistics from the
PyTorch activation tracker.

Shows genuine layer-by-layer activation statistics (mean, std, max,
norm, active neuron count) produced by forward hooks during real model
inference. No fake data. No claimed backdoor detection.

The tracker uses torch.no_grad() and discards raw activations
immediately — only aggregate scalars survive.
"""

import collections

import numpy as np
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QFrame, QLineEdit, QAbstractItemView, QMessageBox,
)

from src.desktop import theme, data_service
from src.desktop.widgets import (
    PageHeader, Panel, KpiCard, SectionHeader, FieldPair, StatusTile,
)


def _tracking_service():
    """Lazy import of the tracking service to avoid torch import at module load."""
    from src.activation import tracking_service  # noqa: PLC0415
    return tracking_service


# ---------------------------------------------------------------------------
# Matplotlib canvas for layer statistics charts
# ---------------------------------------------------------------------------

class LayerStatsCanvas(FigureCanvas):
    """Matplotlib canvas that plots real per-layer activation statistics."""

    def __init__(self, parent=None, width=7, height=3.5, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.fig.patch.set_facecolor(theme.BG_PANEL)
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_layer_bar(self, layer_names, values, metric_name, title):
        """Bar chart of one metric across layers."""
        self.fig.clear()
        self.fig.patch.set_facecolor(theme.BG_PANEL)
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(theme.BG_PANEL)

        x = np.arange(len(layer_names))
        colors = [theme.ACCENT] * len(layer_names)
        bars = ax.bar(x, values, color=colors, alpha=0.8, edgecolor=theme.ACCENT_SOFT, linewidth=0.6)

        ax.set_xticks(x)
        ax.set_xticklabels(
            [n.split(".")[-1] if "." in n else n for n in layer_names],
            rotation=30, ha="right", fontsize=8, color=theme.TEXT_MUTED,
        )
        ax.set_ylabel(metric_name, fontsize=9, color=theme.TEXT_MUTED)
        ax.set_title(title, fontsize=10, color=theme.TEXT_PRIMARY)
        ax.tick_params(colors=theme.TEXT_DIM)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(theme.BORDER)
        ax.spines["bottom"].set_color(theme.BORDER)

        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{val:.4f}",
                ha="center", va="bottom", fontsize=7, color=theme.TEXT_MUTED,
            )
        self.fig.tight_layout()
        self.draw()

    def plot_multi_metric(self, layer_names, stats_dict, title):
        """Grouped bar chart comparing multiple metrics across layers."""
        self.fig.clear()
        self.fig.patch.set_facecolor(theme.BG_PANEL)
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(theme.BG_PANEL)

        metrics = ["mean", "std", "max_val", "norm"]
        metric_colors = [theme.ACCENT, theme.WARNING, theme.DANGER, theme.SUCCESS]
        x = np.arange(len(layer_names))
        width = 0.18

        for i, (metric, color) in enumerate(zip(metrics, metric_colors)):
            vals = [stats_dict.get(name, {}).get(metric, 0.0) for name in layer_names]
            offset = (i - len(metrics) / 2 + 0.5) * width
            ax.bar(x + offset, vals, width, label=metric.replace("_", " ").title(),
                   color=color, alpha=0.8)

        ax.set_xticks(x)
        ax.set_xticklabels(
            [n.split(".")[-1] if "." in n else n for n in layer_names],
            rotation=30, ha="right", fontsize=8, color=theme.TEXT_MUTED,
        )
        ax.set_title(title, fontsize=10, color=theme.TEXT_PRIMARY)
        ax.tick_params(colors=theme.TEXT_DIM)
        ax.legend(fontsize=8, facecolor=theme.BG_RAISED, edgecolor=theme.BORDER,
                  labelcolor=theme.TEXT_MUTED)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(theme.BORDER)
        ax.spines["bottom"].set_color(theme.BORDER)
        self.fig.tight_layout()
        self.draw()

    def plot_active_neurons(self, layer_names, active_fractions, title):
        """Horizontal bar chart of active neuron fractions."""
        self.fig.clear()
        self.fig.patch.set_facecolor(theme.BG_PANEL)
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(theme.BG_PANEL)

        y = np.arange(len(layer_names))
        colors = []
        for frac in active_fractions:
            if frac > 0.8:
                colors.append(theme.SUCCESS)
            elif frac > 0.5:
                colors.append(theme.WARNING)
            else:
                colors.append(theme.DANGER)

        bars = ax.barh(y, active_fractions, color=colors, alpha=0.8, edgecolor=theme.ACCENT_SOFT, linewidth=0.5)
        ax.set_yticks(y)
        ax.set_yticklabels(
            [n.split(".")[-1] if "." in n else n for n in layer_names],
            fontsize=9, color=theme.TEXT_MUTED,
        )
        ax.set_xlabel("Active Fraction", fontsize=9, color=theme.TEXT_MUTED)
        ax.set_title(title, fontsize=10, color=theme.TEXT_PRIMARY)
        ax.set_xlim(0, 1.05)
        ax.tick_params(colors=theme.TEXT_DIM)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(theme.BORDER)
        ax.spines["bottom"].set_color(theme.BORDER)

        for bar, val in zip(bars, active_fractions):
            ax.text(
                bar.get_width() + 0.02,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.2%}",
                va="center", fontsize=8, color=theme.TEXT_MUTED,
            )
        self.fig.tight_layout()
        self.draw()

    def plot_activation_heatmap(self, layer_labels, category_labels, matrix, title):
        """Real mean-activation heatmap: layers (rows) x input categories (cols)."""
        self.fig.clear()
        self.fig.patch.set_facecolor(theme.BG_PANEL)
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(theme.BG_PANEL)

        data = np.ma.masked_invalid(np.array(matrix, dtype=float))
        im = ax.imshow(data, aspect="auto", cmap="viridis")

        cb = self.fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("mean activation", color=theme.TEXT_MUTED, fontsize=8)
        cb.outline.set_visible(False)
        cb.ax.tick_params(colors=theme.TEXT_MUTED, labelsize=7)

        ax.set_xticks(range(len(category_labels)))
        ax.set_xticklabels(
            category_labels, rotation=30, ha="right", fontsize=8,
            color=theme.TEXT_MUTED,
        )
        ax.set_yticks(range(len(layer_labels)))
        ax.set_yticklabels(
            [n.split(".")[-1] if "." in n else n for n in layer_labels],
            fontsize=8, color=theme.TEXT_MUTED,
        )
        ax.set_title(title, fontsize=10, color=theme.TEXT_PRIMARY)
        ax.tick_params(colors=theme.TEXT_DIM)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self.fig.tight_layout()
        self.draw()


# ---------------------------------------------------------------------------
# Background worker for tracking
# ---------------------------------------------------------------------------

class TrackingWorker(QThread):
    """Background worker so inference doesn't freeze the UI."""
    finished = pyqtSignal(dict)

    def __init__(self, input_text, max_new_tokens=10):
        super().__init__()
        self._text = input_text
        self._max = max_new_tokens

    def run(self):
        svc = _tracking_service()
        result = svc.track_inference(self._text, max_new_tokens=self._max)
        self.finished.emit(result)


# ---------------------------------------------------------------------------
# ActivationExplorerView
# ---------------------------------------------------------------------------

class ActivationExplorerView(QWidget):
    """
    Frontend page for real per-layer activation statistics.

    Shows genuine layer-by-layer activation statistics from the
    PyTorch forward hook tracker. No fake data.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._current_stats = {}
        self._layer_stats = {}
        self._layer_by_short = {}
        self._layer_anomaly = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        # Header
        header = PageHeader(
            "ACTIVATION EXPLORER",
            subtitle="Real per-layer activation statistics from PyTorch forward hooks.",
            chip_text="REAL NEURAL DATA",
            chip_color=theme.SUCCESS,
        )
        root.addWidget(header)

        # Disclaimer
        note = QLabel(
            "Statistics are captured by forward hooks during real model inference "
            "with torch.no_grad(). Raw activations are discarded immediately — only "
            "scalar aggregates (mean, std, max, norm, active fraction) are retained. "
            "No backdoor detection is claimed."
        )
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        root.addWidget(note)

        # Real-data activation heatmap (aggregated from scan measurements)
        heat_title = SectionHeader(
            "REAL ACTIVATION HEATMAP "
            "<span style='color:{dim};font-size:10px;letter-spacing:1px;'>"
            "mean activations by layer x input category</span>".format(dim=theme.TEXT_DIM)
        )
        root.addWidget(heat_title)
        self.heat_panel = Panel("")
        self.heat_canvas = LayerStatsCanvas(self, width=8, height=2.6)
        self.heat_panel.add_widget(self.heat_canvas)
        root.addWidget(self.heat_panel)

        # KPI cards
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_model = KpiCard("MODEL", "-", accent=theme.ACCENT, sub="name")
        self.card_type = KpiCard("TYPE", "-", accent=theme.WARNING, sub="architecture")
        self.card_layers = KpiCard("LAYERS", "0", accent=theme.SUCCESS, sub="tracked")
        self.card_status = KpiCard("STATUS", "IDLE", accent=theme.TEXT_MUTED, sub="tracking")
        for c in [self.card_model, self.card_type, self.card_layers, self.card_status]:
            cards.addWidget(c, 1)
        root.addLayout(cards)

        # Tracking controls
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        self.btn_start = QPushButton("Start Tracking")
        self.btn_start.setObjectName("PrimaryButton")
        self.btn_start.clicked.connect(self._on_start_tracking)
        self.btn_stop = QPushButton("Stop Tracking")
        self.btn_stop.setObjectName("GhostButton")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_tracking)
        self.input_text = QLineEdit("what is the model test")
        self.input_text.setPlaceholderText("Enter a prompt to analyze...")
        self.btn_analyze = QPushButton("Run Inference")
        self.btn_analyze.setObjectName("PrimaryButton")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self._on_analyze)
        ctrl.addWidget(self.btn_start)
        ctrl.addWidget(self.btn_stop)
        ctrl.addWidget(self.input_text, 1)
        ctrl.addWidget(self.btn_analyze)
        root.addLayout(ctrl)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setObjectName("PageSubtitle")
        root.addWidget(self.status_label)

        # Splitter: charts top, table bottom
        splitter = QSplitter(Qt.Vertical)

        # Layer statistics table + layer details
        stats_splitter = QSplitter(Qt.Horizontal)

        table_panel = Panel("LAYER ACTIVATION STATISTICS (REAL DATA)")
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "LAYER", "MEAN", "STD", "MAX", "NORM", "ACTIVE %", "ELEMENTS",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        header_view = self.table.horizontalHeader()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 7):
            header_view.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_layer_selected)
        table_panel.add_widget(self.table)
        stats_splitter.addWidget(table_panel)

        details_panel = Panel("LAYER DETAILS")
        self._layer_fields = {}
        specs = [
            ("LAYER INDEX", "index"), ("LAYER NAME", "name"),
            ("NEURON COUNT", "neurons"), ("MEAN ACTIVATION", "mean"),
            ("STD", "std"), ("MAX", "max"), ("NORM", "norm"),
            ("ACTIVE %", "active"), ("ANOMALY SCORE", "score"),
        ]
        for label, key in specs:
            fp = FieldPair(label, "-", monospace=(key in ("name", "index")))
            details_panel.add_widget(fp)
            self._layer_fields[key] = fp
        self._layer_note = QLabel(
            "Anomaly score is the worst real statistical finding on this "
            "layer. Select a row to inspect its details."
        )
        self._layer_note.setObjectName("KpiSub")
        self._layer_note.setWordWrap(True)
        details_panel.add_widget(self._layer_note)
        details_panel.stretch()
        stats_splitter.addWidget(details_panel)
        stats_splitter.setSizes([540, 300])

        splitter.addWidget(stats_splitter)

        # Charts panel
        charts_panel = Panel("LAYER STATISTICS VISUALIZATION")
        charts_splitter = QSplitter(Qt.Horizontal)

        self.bar_canvas = LayerStatsCanvas(self, width=5, height=3.2)
        self.active_canvas = LayerStatsCanvas(self, width=4, height=3.2)

        charts_splitter.addWidget(self.bar_canvas)
        charts_splitter.addWidget(self.active_canvas)
        charts_splitter.setSizes([500, 400])
        charts_panel.add_widget(charts_splitter)
        splitter.addWidget(charts_panel)

        splitter.setSizes([280, 320])
        root.addWidget(splitter, 1)

        # Initial state
        self._set_no_data_state()

    def refresh(self):
        """Refresh from the tracking service."""
        svc = _tracking_service()
        status = svc.tracking_status()
        if status.get("active"):
            self.card_status.set_value("ACTIVE", accent=theme.SUCCESS)
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.btn_analyze.setEnabled(True)
            stats = svc.get_statistics()
            if stats.get("layer_stats"):
                self._populate_stats(stats)
            else:
                self.status_label.setText("Tracking active. Run inference to see statistics.")
        else:
            self.card_status.set_value("IDLE", accent=theme.TEXT_MUTED)
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.btn_analyze.setEnabled(False)
            self._set_no_data_state()
        self._refresh_real_heatmap()

    def _refresh_real_heatmap(self):
        """Draw the real mean-activation heatmap or an explicit empty state."""
        mat = data_service.activation_matrix()
        has_data = bool(mat["layers"]) and bool(mat["categories"]) and any(
            any(v is not None for v in row) for row in mat["matrix"]
        )
        if not has_data:
            self.heat_canvas.fig.clear()
            self.heat_canvas.fig.patch.set_facecolor(theme.BG_PANEL)
            ax = self.heat_canvas.fig.add_subplot(111)
            ax.set_facecolor(theme.BG_PANEL)
            ax.text(
                0.5, 0.5,
                "NO REAL MEASUREMENTS YET\nrun a security scan to populate this "
                "heatmap (nothing is simulated)",
                ha="center", va="center", fontsize=10, color=theme.TEXT_MUTED,
                transform=ax.transAxes,
            )
            ax.axis("off")
            self.heat_canvas.draw()
            return
        self.heat_canvas.plot_activation_heatmap(
            mat["layers"], mat["categories"], mat["matrix"],
            "REAL MEAN ACTIVATION BY LAYER x INPUT CATEGORY",
        )

    def _populate_stats(self, stats_data):
        """Fill table and charts from real tracking statistics."""
        layer_stats = stats_data.get("layer_stats", {})
        self.card_model.set_value(stats_data.get("model_name", "-"))
        self.card_type.set_value(stats_data.get("model_type", "-"))
        self.card_layers.set_value(str(stats_data.get("num_layers", len(layer_stats))))
        self.status_label.setText(
            f"Model: {stats_data.get('model_name', '?')} | "
            f"{len(layer_stats)} layers tracked."
        )

        # Sort by layer index
        sorted_layers = sorted(
            layer_stats.items(),
            key=lambda item: item[1].get("layer_index", 0),
        )

        # Table
        self.table.setRowCount(len(sorted_layers))
        for row_idx, (name, s) in enumerate(sorted_layers):
            short_name = name.split(".")[-1] if "." in name else name
            values = [
                short_name,
                f"{s.get('mean', 0):.6f}",
                f"{s.get('std', 0):.6f}",
                f"{s.get('max_val', 0):.6f}",
                f"{s.get('norm', 0):.4f}",
                f"{s.get('active_fraction', 0):.1%}",
                f"{s.get('num_elements', 0):,}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter if col > 0 else Qt.AlignLeft)
                self.table.setItem(row_idx, col, item)

        layer_names = [name for name, _ in sorted_layers]
        self._layer_stats = {name: s for name, s in sorted_layers}
        self._layer_by_short = {
            name.split(".")[-1]: name for name in layer_names
        }
        try:
            findings = data_service.statistical_findings(run_id=None, limit=2000)
        except Exception:  # noqa: BLE001 -- anomaly lookup is best-effort
            findings = []
        self._layer_anomaly = {}
        for f in findings:
            layer = f.get("layer")
            if layer:
                self._layer_anomaly[layer] = max(
                    self._layer_anomaly.get(layer, 0.0),
                    float(f.get("anomaly_score", 0.0) or 0.0),
                )

        if self.table.rowCount():
            self.table.selectRow(0)

        # Bar chart: mean activation across layers
        means = [layer_stats[n].get("mean", 0.0) for n in layer_names]
        self.bar_canvas.plot_layer_bar(
            layer_names, means, "Mean Activation",
            "Mean Activation per Layer (real data)",
        )

        # Active neurons chart
        active = [layer_stats[n].get("active_fraction", 0.0) for n in layer_names]
        self.active_canvas.plot_active_neurons(
            layer_names, active,
            "Active Neuron Fraction per Layer",
        )

    def _set_no_data_state(self):
        self.table.setRowCount(0)
        self._layer_stats = {}
        self._layer_by_short = {}
        self._layer_anomaly = {}
        for fp in self._layer_fields.values():
            fp.set_value("-")
        self.card_model.set_value("-")
        self.card_type.set_value("-")
        self.card_layers.set_value("0")
        for canvas in [self.bar_canvas, self.active_canvas]:
            canvas.fig.clear()
            canvas.fig.patch.set_facecolor(theme.BG_PANEL)
            canvas.fig.text(
                0.5, 0.5,
                "No activation data.\nLoad a model and start tracking.",
                ha="center", va="center", color=theme.TEXT_MUTED, fontsize=11,
            )
            canvas.draw()
        self.status_label.setText("Load a model, then start tracking to capture activation statistics.")

    # ---- actions ----

    def _current_layer_row(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return -1
        return sel[0].row()

    def _on_layer_selected(self):
        row = self._current_layer_row()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        short = item.text()
        name = self._layer_by_short.get(short, short)
        s = self._layer_stats.get(name)
        if not s:
            return
        anomaly = max(self._layer_anomaly.get(name, 0.0),
                      self._layer_anomaly.get(short, 0.0))
        self._fill_layer_details(short, s, anomaly)

    def _fill_layer_details(self, short, s, anomaly):
        self._layer_fields["index"].set_value(
            s.get("layer_index", 0) if s.get("layer_index") is not None else "-"
        )
        self._layer_fields["name"].set_value(short)
        self._layer_fields["neurons"].set_value(f"{s.get('num_elements', 0):,}")
        self._layer_fields["mean"].set_value(f"{s.get('mean', 0):.6f}")
        self._layer_fields["std"].set_value(f"{s.get('std', 0):.6f}")
        self._layer_fields["max"].set_value(f"{s.get('max_val', 0):.6f}")
        self._layer_fields["norm"].set_value(f"{s.get('norm', 0):.4f}")
        self._layer_fields["active"].set_value(f"{s.get('active_fraction', 0):.1%}")
        if anomaly > 0:
            self._layer_fields["score"].set_value(f"{anomaly:.1f} / 100")
            self._layer_note.setText(
                f"Layer {short} shows activation statistics deviating from "
                "baseline \u2014 a potential anomaly requiring investigation "
                "(not proof of a backdoor)."
            )
        else:
            self._layer_fields["score"].set_value("-")
            self._layer_note.setText(
                "No statistical anomaly recorded for this layer."
            )

    def _on_start_tracking(self):
        self.btn_start.setEnabled(False)
        self.status_label.setText("Starting tracking: discovering transformer layers...")
        self.card_status.set_value("STARTING", accent=theme.WARNING)

        # Ensure the tiny test model is saved
        try:
            from src.model_interface.tiny_test_model import ensure_tiny_model_saved  # noqa: PLC0415
            ensure_tiny_model_saved()
        except Exception:
            pass

        svc = _tracking_service()
        result = svc.start_tracking()
        if result["status"] == "started":
            self.card_status.set_value("ACTIVE", accent=theme.SUCCESS)
            self.card_model.set_value(result.get("model_name", "?"))
            self.card_type.set_value(result.get("model_type", "?"))
            self.card_layers.set_value(str(result.get("num_layers", 0)))
            self.btn_stop.setEnabled(True)
            self.btn_analyze.setEnabled(True)
            self.status_label.setText(
                f"Tracking active on {result.get('num_layers', 0)} layers. "
                "Enter a prompt and click 'Run Inference'."
            )
        elif result["status"] == "already_tracking":
            self.card_status.set_value("ACTIVE", accent=theme.SUCCESS)
            self.btn_stop.setEnabled(True)
            self.btn_analyze.setEnabled(True)
            self.status_label.setText(result.get("message", "Already tracking."))
        else:
            self.card_status.set_value("FAILED", accent=theme.DANGER)
            self.btn_start.setEnabled(True)
            self.status_label.setText(f"Failed: {result.get('message', 'Unknown error')}")
            QMessageBox.warning(
                self, "Tracking Error",
                result.get("message", "Failed to start tracking."),
            )

    def _on_stop_tracking(self):
        svc = _tracking_service()
        result = svc.stop_tracking()
        self.card_status.set_value("IDLE", accent=theme.TEXT_MUTED)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.status_label.setText(result.get("message", "Tracking stopped."))

    def _on_analyze(self):
        text = self.input_text.text().strip()
        if not text:
            QMessageBox.information(self, "No Input", "Enter a prompt to analyze.")
            return
        self.btn_analyze.setEnabled(False)
        self.status_label.setText(f"Running inference on: '{text[:40]}...'")
        self._worker = TrackingWorker(text)
        self._worker.finished.connect(self._on_inference_done)
        self._worker.start()

    def _on_inference_done(self, result):
        self._worker = None
        self.btn_analyze.setEnabled(True)

        if result.get("status") == "tracked":
            session = result.get("session", {})
            svc = _tracking_service()
            stats = svc.get_statistics()
            if stats.get("layer_stats"):
                self._populate_stats(stats)
                out = session.get("output_text", "")[:60]
                self.status_label.setText(
                    f"Inference complete. Output: '{out}' | "
                    f"{len(stats['layer_stats'])} layers captured."
                )
            else:
                self.status_label.setText("Inference ran but no layer statistics were captured.")
        else:
            self.status_label.setText(
                f"Inference error: {result.get('message', 'Unknown')}"
            )
