"""
Findings -- unified threat-analysis page.

Two evidence-first tabs over real backend data:
    * ACTIVATION ANOMALIES  -- statistical anomaly engine over real
      activation measurements (this is the pipeline-era primary signal).
    * RISK FINDINGS         -- the legacy risk-scoring engine rows.

Nothing is fabricated. Both tabs render directly from database rows and
explicitly disclaim that anomalies are evidence of potentially suspicious
activation behavior -- never proof of a backdoor.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSplitter,
)

from src.desktop import theme, data_service
from src.desktop.widgets import PageHeader, KpiCard, Panel
from src.desktop.statistical_findings_view import StatisticalFindingsView


class SecurityFindingsView(QWidget):
    def __init__(self, parent=None, on_inspect_layer=None):
        super().__init__(parent)
        self._on_inspect_layer = on_inspect_layer
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        header = PageHeader(
            "FINDINGS",
            subtitle="Prioritized threat analysis from real scan results.",
            chip_text="THREAT ANALYSIS",
            chip_color=theme.WARNING,
        )
        root.addWidget(header)

        tabs = QTabWidget()
        self.stat_tab = StatisticalFindingsView(on_inspect_layer=self._on_inspect_layer)
        self.risk_tab = _RiskFindingsPane()
        tabs.addTab(self.stat_tab, "ACTIVATION ANOMALIES")
        tabs.addTab(self.risk_tab, "RISK FINDINGS")
        root.addWidget(tabs, 1)

    def refresh(self):
        try:
            self.stat_tab.refresh()
        except Exception:  # noqa: BLE001 -- tab degrades to empty state
            pass
        self.risk_tab.refresh()


class _RiskFindingsPane(QWidget):
    """The legacy risk-scoring engine findings with an evidence panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 10, 0, 0)
        root.setSpacing(14)

        disclaimer = QLabel(
            "\u26a0  Risk findings are derived from risk-scoring results over "
            "real executions. They indicate potentially suspicious behavior, "
            "not proof of a neural backdoor."
        )
        disclaimer.setObjectName("PageSubtitle")
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(f"color:{theme.WARNING};")
        root.addWidget(disclaimer)

        # Summary cards
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_high = KpiCard("HIGH", "0", accent=theme.DANGER, sub="threshold")
        self.card_medium = KpiCard("MEDIUM", "0", accent=theme.WARNING, sub="watch")
        self.card_low = KpiCard("LOW", "0", accent=theme.SAFE, sub="benign")
        self.card_critical = KpiCard("CRITICAL", "0", accent=theme.CRITICAL, sub="severe")
        for c in [self.card_high, self.card_medium, self.card_low, self.card_critical]:
            cards.addWidget(c, 1)
        root.addLayout(cards)

        splitter = QSplitter(Qt.Horizontal)

        left = Panel("SUSPICIOUS EXECUTIONS")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["RISK", "TYPE", "SOURCE", "SCORE", "PROMPT"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection)
        left.add_widget(self.table)
        splitter.addWidget(left)

        right = Panel("EVIDENCE PANEL")
        self.detail = QLabel("Select a finding to inspect its evidence.")
        self.detail.setObjectName("PageSubtitle")
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.RichText)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.add_widget(self.detail)
        right.stretch()
        splitter.addWidget(right)

        splitter.setSizes([760, 400])
        root.addWidget(splitter, 1)

    def refresh(self):
        self._items = data_service.structured_findings(count=1000)
        stats = data_service.risk_summary()
        dist = stats["risk_dist"]
        self.card_high.set_value(str(dist["HIGH"]))
        self.card_medium.set_value(str(dist["MEDIUM"]))
        self.card_low.set_value(str(dist["LOW"]))
        self.card_critical.set_value(str(dist["CRITICAL"]))
        self._populate_table()
        self.detail.setText("Select a finding to inspect its evidence.")

    def _populate_table(self):
        self.table.setRowCount(len(self._items))
        for i, f in enumerate(self._items):
            text = f["prompt"]
            if len(text) > 80:
                text = text[:80] + "..."
            vals = [
                f["severity"],
                f.get("finding_type", "generic").replace("-", " "),
                f"{f['source_type']} #{f['source_ref_id']}",
                f"{f['risk_score']:.1f}",
                text,
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if j == 0:
                    item.setForeground(QColor("#0a0f1e"))
                    item.setBackground(QColor(theme.risk_color(f["severity"])))
                    item.setTextAlignment(Qt.AlignCenter)
                elif j == 3:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, j, item)
                item.setData(Qt.UserRole, i)

    def _current_row(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return -1
        r = sel[0].row()
        if r < 0 or r >= len(self._items):
            return -1
        return r

    def _on_selection(self):
        r = self._current_row()
        if r < 0:
            return
        self._show_detail(self._items[r])

    def select_row(self, idx: int):
        if 0 <= idx < self.table.rowCount():
            self.table.selectRow(idx)

    def _show_detail(self, f):
        color = theme.risk_color(f["severity"])
        html = f"""
        <div style="margin-bottom:8px;">
          <span style="color:{color};font-size:16px;font-weight:700;letter-spacing:1px;">
            {f['severity']} &middot; {theme.html_translate(f.get('title','Finding'))}</span>
        </div>
        <div style="color:{theme.TEXT_MUTED};font-size:12px;margin-bottom:10px;">
          {theme.html_translate(f.get('reason',''))}
        </div>
        <table style="color:{theme.TEXT_MUTED};font-size:12px;" cellspacing="6">
        <tr><td style="color:{theme.TEXT_DIM};width:130px;">RISK SCORE</td>
            <td style="color:{theme.TEXT_PRIMARY};font-weight:700;">{f['risk_score']:.1f} / 100</td></tr>
        <tr><td style="color:{theme.TEXT_DIM};">TYPE</td>
            <td>{f.get('finding_type','generic')}</td></tr>
        <tr><td style="color:{theme.TEXT_DIM};">AFFECTED</td>
            <td>{f['source_type']} ref #{f['source_ref_id']}</td></tr>
        <tr><td style="color:{theme.TEXT_DIM};">ANOMALY SCORE</td>
            <td>{f['anomaly_score']:.1f}</td></tr>
        <tr><td style="color:{theme.TEXT_DIM};">EVIDENCE</td>
            <td style="color:{color};font-weight:600;">{theme.html_translate(f.get('evidence',''))}</td></tr>
        <tr><td style="color:{theme.TEXT_DIM};">RECOMMENDATION</td>
            <td>{theme.html_translate(f.get('recommendation',''))}</td></tr>
        </table>
        <div style="margin-top:12px;color:{theme.TEXT_MUTED};font-weight:700;">PROMPT</div>
        <div style="margin-top:4px;font-family:{theme.MONO_FAMILY};font-size:11px;
             color:{theme.TEXT_MUTED};background:{theme.BG_DEEP};
             border:1px solid {theme.BORDER};border-radius:6px;padding:10px;">
          {theme.html_translate(f['prompt'])}
        </div>
        """
        self.detail.setText(html)