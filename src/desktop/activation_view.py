"""
Activation Visualization View -- shows a layer/feature heatmap
(baseline vs suspicious) from the aggregated activation features,
plus layer-wise statistics. Uses matplotlib embedded in Qt.

IMPORTANT: the bundled toy model is rule-based and does not expose
real neural activations. We therefore visualize the AGGREGATED
security feature vectors (prompt_length, response_length,
prompt_hash_score, trigger_signal, injection_signal,
response_change_signal) per risk source. These are clearly labeled
as aggregated features, not individual neuron activations.
"""

import numpy as np
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
)

from src.db.db_manager import get_session
from src.anomaly_detection.activation_anomaly import FEATURE_NAMES
from src.anomaly_detection.activation_anomaly import build_feature_baseline_statistics
from src.db.models import ActivationFeature, RiskAssessmentRow


class MatplotlibCanvas(FigureCanvas):
    def __init__(self, parent=None, width=6, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_heatmap(self, matrix: np.ndarray, row_labels, col_labels, title):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        im = ax.imshow(matrix, aspect="auto", cmap="RdPu")
        ax.set_xticks(range(len(col_labels)))
        ax.set_xticklabels(col_labels, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=7)
        ax.set_title(title, fontsize=10)
        self.fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        self.fig.tight_layout()
        self.draw()


class ActivationView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Activation & Anomaly Visualization")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a237e;")
        layout.addWidget(title)

        note = QLabel(
            "Shows AGGREGATED security feature vectors (mean values across "
            "executions) grouped by risk source. The bundled toy model is "
            "rule-based, so real per-neuron activations are not available; "
            "these are labeled accurately as aggregated features."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #777;")
        layout.addWidget(note)

        splitter = QSplitter()

        # Left: heatmap
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.canvas = MatplotlibCanvas(self, width=6, height=4)
        left_layout.addWidget(self.canvas)
        rr = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Heatmap")
        self.refresh_btn.clicked.connect(self.refresh)
        rr.addStretch(1)
        rr.addWidget(self.refresh_btn)
        left_layout.addLayout(rr)
        splitter.addWidget(left)

        # Right: layer-wise stats table
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_title = QLabel("Aggregated Feature Statistics by Category")
        right_title.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(right_title)
        self.stats_table = QTableWidget(0, 4)
        self.stats_table.setHorizontalHeaderLabels(["Category", "Feature", "Mean", "Std"])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        right_layout.addWidget(self.stats_table)
        splitter.addWidget(right)

        splitter.setSizes([520, 420])
        layout.addWidget(splitter, stretch=1)

        self.refresh()

    def refresh(self):
        session = get_session()
        try:
            feat_rows = session.query(ActivationFeature).all()
            risk_rows = session.query(RiskAssessmentRow).all()
        finally:
            session.close()

        if not feat_rows:
            self.canvas.fig.clear()
            self.canvas.fig.text(0.5, 0.5, "No activation data. Run a scan first.",
                                 ha="center", va="center")
            self.canvas.draw()
            self.stats_table.setRowCount(0)
            return

        # Group features by category and compute mean/std per feature.
        import collections
        by_cat = collections.defaultdict(list)
        for fr in feat_rows:
            by_cat[fr.category or "unspecified"].append(np.array([
                fr.prompt_length, fr.response_length, fr.prompt_hash_score,
                fr.trigger_signal, fr.injection_signal, fr.response_change_signal,
            ]))

        # Build heatmap: rows = categories, cols = features
        categories = sorted(by_cat.keys())
        matrix = np.zeros((len(categories), len(FEATURE_NAMES)))
        stds = np.zeros((len(categories), len(FEATURE_NAMES)))
        for i, cat in enumerate(categories):
            arr = np.array(by_cat[cat])
            means = arr.mean(axis=0)
            std = arr.std(axis=0)
            matrix[i] = means
            stds[i] = std

        self.canvas.plot_heatmap(
            matrix,
            categories,
            FEATURE_NAMES,
            "Mean Aggregated Feature Value by Category (heatmap)",
        )

        # Fill stats table
        rows = []
        for i, cat in enumerate(categories):
            for j, feat in enumerate(FEATURE_NAMES):
                rows.append((cat, feat, matrix[i][j], stds[i][j]))
        rows.sort(key=lambda r: r[2], reverse=True)
        self.stats_table.setRowCount(len(rows))
        for r, (cat, feat, mean, std) in enumerate(rows):
            for c, val in enumerate([cat, feat, f"{mean:.3f}", f"{std:.3f}"]):
                item = QTableWidgetItem(str(val))
                self.stats_table.setItem(r, c, item)
