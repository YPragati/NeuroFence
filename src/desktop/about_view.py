"""Offline platform information for the NeuroFence desktop client."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from src.desktop import theme
from src.desktop.widgets import PageHeader, Panel


class AboutView(QWidget):
    """Plain-language product scope and safety boundaries for analysts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        root.addWidget(PageHeader(
            "ABOUT NEUROFENCE",
            subtitle=("AI MODEL FORENSICS PLATFORM — local evidence, local "
                      "analysis, no cloud model upload."),
            chip_text="PROTOTYPE / RESEARCH PLATFORM",
            chip_color=theme.WARNING,
        ))

        intro = Panel("AI MODEL FORENSICS PLATFORM")
        copy = QLabel(
            "NeuroFence is an offline AI security and model-forensics platform "
            "for inspecting local AI models using integrity verification, "
            "adversarial testing, activation analysis and anomaly detection."
        )
        copy.setObjectName("PageSubtitle")
        copy.setWordWrap(True)
        intro.add_widget(copy)
        root.addWidget(intro)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        columns.addWidget(self._section("WHAT NEUROFENCE DOES", [
            "Model Integrity Verification", "Adversarial Fuzzing",
            "Trigger Analysis", "Activation Forensics",
            "Statistical Anomaly Detection", "Risk Scoring",
            "Security Reporting",
        ]), 1)
        columns.addWidget(self._section("WHY OFFLINE", [
            "Local processing", "Air-gapped operation",
            "No cloud model upload", "Local evidence",
        ]), 1)
        columns.addWidget(self._section("TECHNOLOGY", [
            "Python", "PyTorch", "scikit-learn", "SQLite", "PyQt6",
        ]), 1)
        root.addLayout(columns)

        boundary = Panel("INTERPRETATION BOUNDARY")
        note = QLabel(
            "Statistical anomalies are forensic signals for analyst review; "
            "they do not universally prove a backdoor or malicious intent."
        )
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        boundary.add_widget(note)
        root.addWidget(boundary)
        root.addStretch(1)

    @staticmethod
    def _section(title, items):
        panel = Panel(title)
        for item in items:
            label = QLabel("•  " + item)
            label.setObjectName("FieldValue")
            panel.add_widget(label)
        panel.stretch()
        return panel
