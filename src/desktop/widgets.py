"""
NeuroFence -- reusable "Neural SOC" widgets.

Shared building blocks used across every dashboard section: page
headers, KPI cards, panels, risk badges, donut gauges, field pairs
and styled tables. Keeping these reusable avoids duplicating UI logic.
"""

import os

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QFontMetrics
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSizePolicy, QLineEdit, QPushButton, QMessageBox,
)
from PyQt5.QtCore import QTimer, pyqtSignal, QSize

from src.desktop import theme


class PageHeader(QWidget):
    """Page title + contextual subtitle + optional right-hand status chip."""

    def __init__(self, title: str, subtitle: str = "", chip_text: str = "",
                 chip_color: str = theme.SUCCESS, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        text_col.addWidget(self.title)
        if subtitle:
            self.subtitle = QLabel(subtitle)
            self.subtitle.setObjectName("PageSubtitle")
            self.subtitle.setWordWrap(True)
            text_col.addWidget(self.subtitle)
        layout.addLayout(text_col, 1)

        if chip_text:
            chip = QLabel(theme.status_chip_html(chip_text, chip_color))
            chip.setTextFormat(Qt.RichText)
            layout.addWidget(chip, 0, Qt.AlignTop)


class SectionHeader(QLabel):
    """Uppercase section heading accent separator."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("SectionHeader")
        self.setTextFormat(Qt.RichText)


class KpiCard(QFrame):
    """Modern KPI stat card: label, value, accent underline, optional sub."""

    def __init__(self, label: str, value: str = "-", accent: str = theme.ACCENT,
                 sub: str = "", icon: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("KpiCard")
        self.setMinimumWidth(150)
        self._accent = accent
        self._icon = icon

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        if icon:
            self._icon_label = QLabel(icon)
            self._icon_label.setStyleSheet(
                f"color:{accent};font-size:15px;font-weight:700;"
            )
            head.addWidget(self._icon_label)
        self._label = QLabel(label)
        self._label.setObjectName("KpiLabel")
        self._label.setWordWrap(True)
        head.addWidget(self._label, 1)
        layout.addLayout(head)

        self._value = QLabel(value)
        self._value.setObjectName("KpiValue")
        layout.addWidget(self._value)

        self._sub = QLabel(sub)
        self._sub.setObjectName("KpiSub")
        self._sub.setWordWrap(True)
        layout.addWidget(self._sub)

        self._set_accent(accent)

    def _set_accent(self, accent: str):
        self._accent = accent
        self._value.setStyleSheet(f"QLabel{{color:{accent};}}")
        if getattr(self, "_icon_label", None) is not None:
            self._icon_label.setStyleSheet(
                f"color:{accent};font-size:15px;font-weight:700;"
            )
        self.setStyleSheet(
            f"QFrame#KpiCard{{border-top:2px solid {accent};"
            f"background:{theme.GLASS_RGBA};border:1px solid {theme.BORDER};"
            f"border-top:2px solid {accent};border-radius:10px;}}"
        )

    def set_value(self, value: str, accent: str = None):
        self._value.setText(str(value))
        if accent:
            self._set_accent(accent)

    def set_sub(self, sub: str):
        self._sub.setText(sub)


class Panel(QFrame):
    """Glassmorphism panel with an uppercase title."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(10)
        if title:
            head = QLabel(title)
            head.setObjectName("PanelTitle")
            self._layout.addWidget(head)

    def add_widget(self, widget):
        self._layout.addWidget(widget)

    def add_layout(self, layout):
        self._layout.addLayout(layout)

    def stretch(self):
        self._layout.addStretch(1)


class FieldPair(QWidget):
    """A small label/value read-only row for forensic evidence panels."""

    def __init__(self, label: str, value: str = "-", monospace: bool = False,
                 parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        lab = QLabel(label)
        lab.setObjectName("FieldLabel")
        lab.setFixedWidth(150)
        layout.addWidget(lab)
        val = QLabel(str(value))
        val.setObjectName("FieldValue")
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if monospace:
            val.setStyleSheet(f"font-family:{theme.MONO_FAMILY};font-size:11px;")
        layout.addWidget(val, 1)
        self.value = val

    def set_value(self, value: str):
        self.value.setText(str(value))


class RiskBadge(QFrame):
    """A pill showing a risk level with its colour."""

    def __init__(self, level: str, parent=None):
        super().__init__(parent)
        color = theme.risk_color(level)
        self.setStyleSheet(
            f"background:{color}1f;border:1px solid {color}59;border-radius:9px;"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 10, 3)
        lab = QLabel(str(level))
        lab.setStyleSheet(f"color:{color};font-weight:700;font-size:11px;")
        lab.setAlignment(Qt.AlignCenter)
        lay.addWidget(lab)
        self.setFixedHeight(24)


class DonutGauge(QWidget):
    """
    A large circular/donut-style gauge drawn with QPainter.

    Displays a value/100 with a coloured arc corresponding to the risk
    level. No fake data -- the caller supplies the real score.
    """

    def __init__(self, value: float = 0.0, max_value: float = 100.0,
                 label: str = "", level: str = "LOW", parent=None):
        super().__init__(parent)
        self._value = float(value)
        self._max = float(max_value) or 100.0
        self._label = label
        self._level = level
        self.setMinimumSize(200, 210)

    def set_value(self, value: float, level: str = None):
        self._value = float(value)
        if level:
            self._level = level
        self.update()

    def paintEvent(self, _event):
        from PyQt5.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        side = min(w, h) - 12
        rect = QRectF((w - side) / 2, 12, side, side)

        # background track
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.BG_RAISED))
        p.drawEllipse(rect)

        # arc
        ratio = max(0.0, min(1.0, self._value / self._max))
        color = QColor(theme.risk_color(self._level))
        pen = QPen(color, 14)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        start = 90 * 16
        span = -int(360 * 16 * ratio)
        p.drawArc(rect.adjusted(9, 9, -9, -9), start, span)

        # centre text
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.BG_PANEL))
        p.drawEllipse(rect.adjusted(26, 26, -26, -26))

        p.setPen(QColor(theme.TEXT_PRIMARY))
        f = p.font()
        f.setPixelSize(34)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(rect.x(), rect.y() + rect.height() * 0.30,
                          rect.width(), 46), Qt.AlignCenter, f"{self._value:.1f}")

        p.setPen(QColor(theme.TEXT_MUTED))
        f2 = p.font()
        f2.setPixelSize(10)
        f2.setBold(False)
        p.setFont(f2)
        p.drawText(QRectF(rect.x(), rect.y() + rect.height() * 0.30 + 46,
                          rect.width(), 20), Qt.AlignCenter, "/ 100")

        p.setPen(QColor(theme.risk_color(self._level)))
        f3 = p.font()
        f3.setPixelSize(13)
        f3.setBold(True)
        p.setFont(f3)
        p.drawText(QRectF(rect.x(), rect.y() + rect.height() * 0.68,
                          rect.width(), 24), Qt.AlignCenter, self._level)
        p.end()


class StatusTile(QFrame):
    """A small validation/status tile with a check/cross glyph + optional detail."""

    def __init__(self, text: str, status: str = "ok", detail: str = "",
                 parent=None):
        super().__init__(parent)
        self._text = str(text)
        self._tile_label = None
        self._tile_glyph = None
        self._tile_detail = None
        self.setMinimumWidth(150)
        self.set_status(status)
        if detail:
            self.set_detail(detail)

    def set_status(self, status: str = "ok"):
        ok = status in ("ok", "valid", True)
        color = theme.SUCCESS if ok else theme.DANGER
        glyph = "\u2713" if ok else "\u2717"
        self.setStyleSheet(
            f"background:{color}14;border:1px solid {color}3d;border-radius:8px;"
        )
        if self._tile_glyph is None:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(10)
            self._tile_glyph = QLabel(glyph)
            lay.addWidget(self._tile_glyph)
            col = QVBoxLayout()
            col.setSpacing(1)
            self._tile_label = QLabel(self._text)
            col.addWidget(self._tile_label)
            self._tile_detail = QLabel("")
            self._tile_detail.setStyleSheet(
                "font-size:10px;color:" + theme.TEXT_DIM + ";"
            )
            col.addWidget(self._tile_detail)
            lay.addLayout(col, 1)
        self._tile_glyph.setText(glyph)
        self._tile_glyph.setStyleSheet(
            f"color:{color};font-weight:700;font-size:14px;"
        )
        self._tile_label.setStyleSheet(
            f"color:{theme.TEXT_PRIMARY};font-size:12px;"
        )

    def set_ok(self, ok: bool):
        self.set_status("ok" if ok else "fail")

    def set_detail(self, detail: str):
        if self._tile_detail is not None:
            self._tile_detail.setText(str(detail))


class WorkflowStepsBase(QWidget):
    """
    Horizontal multi-step progress strip with done / active / pending states.

    Used for the security workflow (MODEL -> INTEGRITY -> SCAN -> ANALYSIS
    -> RISK -> DECISION) and the Overview pipeline visual. States are set
    by the caller from real backend state -- this widget never invents
    progress.

    States: "done" (green), "active" (violet), "pending" (dim).
    """

    ST_DONE = "done"
    ST_ACTIVE = "active"
    ST_PENDING = "pending"

    def __init__(self, steps=None, states=None, parent=None):
        super().__init__(parent)
        self._steps = [str(s) for s in (steps or [])]
        self._states = [self.ST_PENDING] * len(self._steps)
        if states:
            self._states = list(states)[: len(self._steps)]
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(58)

    # ---- public API ----

    def set_steps(self, steps):
        self._steps = [str(s) for s in (steps or [])]
        self._states = [self.ST_PENDING] * len(self._steps)
        self.update()

    def set_states(self, states):
        """states: list of "done" | "active" | "pending" (length == steps)."""
        self._states = list(states)[: len(self._steps)]
        while len(self._states) < len(self._steps):
            self._states.append(self.ST_PENDING)
        self.update()

    def set_progress(self, done_count: int, active_index: int = None):
        """Mark first ``done_count`` steps done; the next one active."""
        states = []
        for i in range(len(self._steps)):
            if i < done_count:
                states.append(self.ST_DONE)
            elif active_index is not None and i == active_index:
                states.append(self.ST_ACTIVE)
            else:
                states.append(self.ST_PENDING)
        self.set_states(states)

    def states(self):
        return list(self._states)

    # ---- drawing ----

    def _state_color(self, state):
        if state == self.ST_DONE:
            return theme.SUCCESS
        if state == self.ST_ACTIVE:
            return theme.ACCENT
        return theme.BORDER_LIGHT

    def sizeHint(self):
        hint = QSize(220, 58)
        mh = self.minimumHeight()
        if mh > hint.height():
            hint.setHeight(mh)
        return hint

    def minimumSizeHint(self):
        return self.sizeHint()


class WorkflowSteps(WorkflowStepsBase):
    """Workflow strip (paint lives on this subclass; the base carries the API)."""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self._steps)
        if n == 0:
            return

        w = self.width()
        h = self.height()
        label_ht = 26
        circle_r = 10
        pad = 34
        slot = max(float(w) - 2 * pad, n * (circle_r * 2 + 6))
        step_w = slot / n
        cy = 22  # circle center line

        tick = QFontMetrics(self.font())
        prev_right = None
        for i, name in enumerate(self._steps):
            cx = pad + step_w * i + step_w / 2
            state = self._states[i] if i < len(self._states) else self.ST_PENDING
            color = QColor(self._state_color(state))

            # connector line to the previous circle centre
            if prev_right is not None:
                p.setPen(QPen(QColor(theme.BORDER), 2))
                p.drawLine(int(prev_right), int(cy), int(cx - circle_r), int(cy))
            prev_right = cx + circle_r

            # circle
            p.setPen(QPen(color, 2))
            if state == self.ST_DONE:
                p.setBrush(color)
                p.drawEllipse(QRectF(cx - circle_r, cy - circle_r,
                                     circle_r * 2, circle_r * 2))
                p.setPen(QPen(QColor(theme.BG_DEEP), 2))
                f = p.font()
                f.setPixelSize(11)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRectF(cx - circle_r, cy - circle_r,
                                  circle_r * 2, circle_r * 2),
                           Qt.AlignCenter, "\u2713")
            elif state == self.ST_ACTIVE:
                p.setPen(QPen(color, 2))
                p.setBrush(color)
                p.drawEllipse(QRectF(cx - (circle_r - 3), cy - (circle_r - 3),
                                     (circle_r - 3) * 2, (circle_r - 3) * 2))
                p.setPen(QPen(QColor(theme.BG_DEEP), 2))
                f = p.font()
                f.setPixelSize(10)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRectF(cx - circle_r + 3, cy - circle_r + 3,
                                  (circle_r - 3) * 2, (circle_r - 3) * 2),
                           Qt.AlignCenter, str(i + 1))
            else:
                p.setPen(QPen(color, 2))
                p.setBrush(QColor(theme.BG_PANEL))
                p.drawEllipse(QRectF(cx - circle_r, cy - circle_r,
                                     circle_r * 2, circle_r * 2))

            # label beneath the circle
            label_color = (QColor(theme.TEXT_PRIMARY) if state == self.ST_ACTIVE
                           else QColor(theme.TEXT_MUTED if state == self.ST_DONE
                                       else theme.TEXT_DIM))
            p.setPen(QPen(label_color, 1))
            f2 = p.font()
            f2.setPixelSize(9 if n > 5 else 10)
            f2.setBold(state == self.ST_ACTIVE)
            p.setFont(f2)
            text = tick.elidedText(name, Qt.ElideRight, int(step_w))
            p.drawText(QRectF(cx - step_w / 2, cy + circle_r + 5, step_w, label_ht),
                       Qt.AlignHCenter | Qt.AlignTop, text)
        p.end()


def make_table(headers, rows=None, stretch_col: int = None):
    """Build a polished read-only table."""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setAlternatingRowColors(True)
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setHighlightSections(False)
    if stretch_col is not None:
        header.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    if rows:
        _fill_table(table, rows)
    return table


def _fill_table(table, rows):
    if not rows:
        table.setRowCount(0)
        return
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            item = QTableWidgetItem("" if val is None else str(val))
            if c == 0 or isinstance(val, (int, float)):
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            table.setItem(r, c, item)


def set_cell_align(table, row, col, alignment=Qt.AlignCenter):
    item = table.item(row, col)
    if item:
        item.setTextAlignment(alignment)


def clear_table(table):
    table.setRowCount(0)


# ---------------------------------------------------------------------------
# DataTable -- searchable, sortable, paginated table with an empty state.
# ---------------------------------------------------------------------------

class DataTable(QWidget):
    """
    A professional read-only table with live search, click-to-sort columns,
    pagination and a visible empty state. Row data is kept in the widget
    (with its original index) so sorting/searching never corrupts identity.

    Signals:
        rowSelected(int)   -- original row index of the clicked row
    """

    rowSelected = pyqtSignal(int)
    rowActivated = pyqtSignal(int)

    def __init__(self, headers, page_size: int = 15, stretch_col: int = None,
                 parent=None):
        super().__init__(parent)
        self._headers = list(headers)
        self._page_size = max(5, int(page_size))
        self._data = []          # filtered-and-sorted rows (list of lists)
        self._orig = []          # original index for self._data[r]
        self._all = []           # every row currently loaded (list of lists)
        self._stylist = None     # fn(orig_idx, item, col)
        self._page = 1
        self._last_col = -1
        self._last_order = 1
        self._build_ui(stretch_col)

    # ---- UI ----

    def _build_ui(self, stretch_col):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search records (model, severity, layer, score...)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search, 1)

        self.summary = QLabel("0 records")
        self.summary.setObjectName("PageSubtitle")
        toolbar.addWidget(self.summary)

        self.btn_prev = QPushButton("\u2039")
        self.btn_prev.setObjectName("GhostButton")
        self.btn_prev.setFixedWidth(34)
        self.btn_prev.clicked.connect(lambda: self._goto(self._page - 1))
        toolbar.addWidget(self.btn_prev)

        self.page_label = QLabel("1 / 1")
        self.page_label.setObjectName("PageSubtitle")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setFixedWidth(54)
        toolbar.addWidget(self.page_label)

        self.btn_next = QPushButton("\u203a")
        self.btn_next.setObjectName("GhostButton")
        self.btn_next.setFixedWidth(34)
        self.btn_next.clicked.connect(lambda: self._goto(self._page + 1))
        toolbar.addWidget(self.btn_next)
        root.addLayout(toolbar)

        self.empty_label = QLabel(
            "No records found. Data will appear here once real scans "
            "and models exist in the local database."
        )
        self.empty_label.setObjectName("PageSubtitle")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(
            f"color:{theme.TEXT_MUTED};background:{theme.BG_INPUT};"
            f"border:1px dashed {theme.BORDER};border-radius:8px;padding:26px;"
        )
        root.addWidget(self.empty_label)

        self.table = QTableWidget(0, len(self._headers))
        self.table.setHorizontalHeaderLabels(self._headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        if stretch_col is not None:
            header.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
        header.sectionClicked.connect(self._sort_by)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.itemDoubleClicked.connect(self._on_activated)
        self.table.setMinimumHeight(180)
        root.addWidget(self.table, 1)

        self._refresh_empty_state()

    # ---- public API ----

    def set_rows(self, rows, rows_to_display=None):
        """Load new rows (list of lists of str/int/float)."""
        self._all = [list(r) for r in (rows or [])]
        if rows_to_display:
            self._orig = list(rows_to_display)
        else:
            self._orig = list(range(len(self._all)))
        self._page = 1
        self._sort_reset()
        self._apply_filter()

    def clear_rows(self):
        self.set_rows([])

    def set_cell_stylist(self, fn):
        """fn(orig_idx, item, col) is called for every populated cell."""
        self._stylist = fn

    def current_row_index(self):
        """Original index of the selected row, or -1."""
        row = self.table.currentRow()
        if 0 <= row < len(self._orig):
            return self._orig[row]
        return -1

    def filtered_count(self):
        return len(self._data)

    def total_count(self):
        return len(self._all)

    def goto_page(self, page: int):
        self._goto(page)

    # ---- internals ----

    def _sort_reset(self):
        self._last_col = -1
        self._last_order = 1

    def _apply_filter(self):
        query = self.search.text().strip().lower()
        if query:
            keep = [
                (r, orig) for r, orig in zip(self._all, self._orig)
                if query in " ".join(str(c).lower() for c in r)
            ]
        else:
            keep = list(zip(self._all, self._orig))
        if self._last_col >= 0:
            keep.sort(key=lambda t: self._sort_key(t[0]), reverse=self._last_order < 0)
        self._data = [r for r, _ in keep]
        self._orig = [o for _, o in keep]
        pages = max(1, -(-len(self._data) // self._page_size))
        self._page = min(self._page, pages)
        self._populate()
        self._refresh_empty_state()

    def _sort_key(self, row):
        col = self._last_col
        if col < 0 or col >= len(row):
            return ""
        val = row[col]
        try:
            return float(val)
        except (TypeError, ValueError):
            return str(val).lower()

    def _sort_by(self, col):
        if self._last_col == col:
            self._last_order *= -1
        else:
            self._last_col = col
            self._last_order = 1
        self._apply_filter()

    def _populate(self):
        start = (self._page - 1) * self._page_size
        page_rows = self._data[start:start + self._page_size]
        self.table.blockSignals(True)
        self.table.setRowCount(len(page_rows))
        for r, row in enumerate(page_rows):
            orig = self._orig[start + r]
            for c, val in enumerate(row):
                item = QTableWidgetItem("" if val is None else str(val))
                if self._stylist:
                    self._stylist(orig, item, c)
                self.table.setItem(r, c, item)
        self.table.blockSignals(False)

        total = len(self._data)
        pages = max(1, -(-total // self._page_size))
        self.page_label.setText(f"{self._page} / {pages}")
        self.btn_prev.setEnabled(self._page > 1)
        self.btn_next.setEnabled(self._page < pages)
        self.summary.setText(
            f"{total} of {len(self._all)} records"
            if query_active(self.search) else f"{total} records"
        )

    def _goto(self, page):
        pages = max(1, -(-len(self._data) // self._page_size))
        page = max(1, min(pages, page))
        if page != self._page:
            self._page = page
            self._populate()

    def _on_selection(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._orig):
            self.rowSelected.emit(self._orig[row])

    def _on_activated(self, _item):
        row = self.table.currentRow()
        if 0 <= row < len(self._orig):
            self.rowActivated.emit(self._orig[row])

    def _refresh_empty_state(self):
        has_rows = bool(self._data)
        self.table.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)


def query_active(edit) -> bool:
    return bool((edit.text() or "").strip())


# ---------------------------------------------------------------------------
# Toast notifications + confirmation dialogs
# ---------------------------------------------------------------------------

class Toast(QFrame):
    """A transient status toast pinned to the top-right of its parent."""

    def __init__(self, parent, text: str, kind: str = "info", delay_ms: int = 3200):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        color = {
            "success": theme.SUCCESS,
            "error": theme.DANGER,
            "warning": theme.WARNING,
            "info": theme.ACCENT,
        }.get(kind, theme.ACCENT)
        self.setStyleSheet(
            f"QFrame{{background:{theme.BG_RAISED};border:1px solid {color}66;"
            f"border-left:3px solid {color};border-radius:8px;}}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        glyph = QLabel({
            "success": "\u2713",
            "error": "\u2715",
            "warning": "\u26a0",
            "info": "\u2139",
        }.get(kind, "\u2139"))
        glyph.setStyleSheet(f"color:{color};font-weight:700;font-size:14px;")
        lay.addWidget(glyph)
        msg = QLabel(str(text))
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color:{theme.TEXT_PRIMARY};font-size:12px;")
        lay.addWidget(msg)

        self.adjustSize()
        self._reposition()
        parent.installEventFilter(self)
        QTimer.singleShot(delay_ms, self._fade_out)

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        w = max(self.sizeHint().width(), 260)
        x = parent.width() - w - 22
        y = 60
        self.setGeometry(x, y, w, self.sizeHint().height())
        self.raise_()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == event.Resize:
            self._reposition()
        return False

    def _fade_out(self):
        import os
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self._close()
            return
        self._timer = _FadeTimer(self, 240)
        self._timer.start()

    def _close(self):
        self.setParent(None)
        self.deleteLater()


class _FadeTimer(QTimer):
    """Simple opacity fade so toasts disappear smoothly on real windows."""

    def __init__(self, toast, steps: int, parent=None):
        super().__init__(toast)
        self._toast = toast
        self._start = 1.0
        self._steps = int(steps)
        self._n = 0
        self.setInterval(12)
        self.timeout.connect(self._tick)

    def _tick(self):
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._n += 1
        if self._n >= self._steps:
            self.stop()
            self._toast._close()
            return
        eff = QGraphicsOpacityEffect(self._toast)
        eff.setOpacity(max(0.0, 1.0 - self._n / self._steps))
        self._toast.setGraphicsEffect(eff)


def show_toast(parent, text: str, kind: str = "info"):
    """Show a transient toast notification anchored to ``parent`` (QWidget)."""
    if parent is None:
        return
    Toast(parent, text, kind=kind)


def confirm_dialog(parent, title: str, message: str,
                   ok_text: str = "Confirm", cancel_text: str = "Cancel") -> bool:
    """Show a themed confirmation dialog; return True when confirmed."""
    # Native modal dialogs cannot run under offscreen Qt (they raise a fatal
    # access violation on some platforms). Accept instead of opening the modal
    # so headless tests and CLI contexts stay safe; real interactive sessions
    # still get the confirmation box.
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return True
    from PyQt5.QtWidgets import QDialogButtonBox
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Question)
    box.setText(message)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    buttons = box.button(QMessageBox.Yes)
    if buttons:
        buttons.setText(ok_text)
    box.button(QMessageBox.No).setText(cancel_text)
    box.setDefaultButton(QMessageBox.No)
    return box.exec_() == QMessageBox.Yes


# ---------------------------------------------------------------------------
# SOC shell components: sidebar rail, system health tiles, bar charts.
# ---------------------------------------------------------------------------

class Sidebar(QWidget):
    """
    Left navigation rail (SOC style).

    ``groups`` is a list of (GROUP_LABEL, [(key, glyph, label), ...]). The
    widget emits :attr:`navigate(key)` when a nav button is clicked and
    :attr:`sign_out_requested` for the footer sign-out button. Navigation
    happens on click; programmatic selection uses :meth:`set_active`.
    """

    navigate = pyqtSignal(str)
    sign_out_requested = pyqtSignal()

    def __init__(self, groups, analyst: str = "Analyst",
                 status_text: str = "ALL SYSTEMS OPERATIONAL",
                 status_ok: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(232)
        self._buttons = {}
        self._build_ui(groups, analyst, status_text, status_ok)

    def _build_ui(self, groups, analyst, status_text, status_ok):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Brand ----
        brand = QVBoxLayout()
        brand.setContentsMargins(18, 18, 18, 16)
        brand.setSpacing(2)
        title = QLabel("NEUROFENCE")
        title.setObjectName("SidebarBrand")
        brand.addWidget(title)
        tag = QLabel("AI MODEL FORENSICS")
        tag.setObjectName("SidebarTag")
        brand.addWidget(tag)
        rule = QLabel("")
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background:{theme.BORDER};")
        brand.addSpacing(6)
        brand.addWidget(rule)
        root.addLayout(brand)

        nav = QVBoxLayout()
        nav.setContentsMargins(8, 6, 8, 6)
        nav.setSpacing(1)
        self._group_buttons = {}
        for group_label, items in groups:
            gl = QLabel(group_label)
            gl.setObjectName("NavGroupLabel")
            nav.addWidget(gl)
            for key, glyph, label in items:
                btn = QPushButton(f"{glyph}   {label}")
                btn.setObjectName("SidebarButton")
                btn.setCheckable(True)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setMinimumHeight(38)
                btn.clicked.connect(lambda checked, k=key: self._emit_navigate(k))
                nav.addWidget(btn)
                self._buttons[key] = btn
        root.addLayout(nav, 1)

        # ---- Footer: status + analyst + sign out ----
        footer = QVBoxLayout()
        footer.setContentsMargins(16, 12, 16, 14)
        footer.setSpacing(10)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self._dot = QLabel("\u25cf")
        self._dot.setStyleSheet(f"color:{theme.SUCCESS};font-size:12px;")
        status_row.addWidget(self._dot, 0, Qt.AlignTop)
        self._status_text = QLabel(status_text)
        self._status_text.setObjectName("StatusText")
        self._status_text.setWordWrap(True)
        status_row.addWidget(self._status_text, 1)
        footer.addLayout(status_row)

        analyst_label = QLabel(
            f'<span style="color:{theme.TEXT_DIM};">ANALYST</span>  '
            f'<span style="color:{theme.TEXT_PRIMARY};font-weight:700;">'
            f'{theme.html_translate(analyst)}</span>'
        )
        analyst_label.setTextFormat(Qt.RichText)
        analyst_label.setStyleSheet("font-size:10px;letter-spacing:1px;")
        footer.addWidget(analyst_label)

        self.btn_signout = QPushButton("SIGN OUT")
        self.btn_signout.setObjectName("GhostButton")
        self.btn_signout.setMinimumHeight(32)
        self.btn_signout.clicked.connect(self.sign_out_requested.emit)
        footer.addWidget(self.btn_signout)
        root.addLayout(footer)

    def _emit_navigate(self, key):
        self.navigate.emit(key)

    def set_active(self, key, exclusive: bool = True):
        """Check the button for ``key`` without emitting ``navigate``."""
        for k, btn in self._buttons.items():
            btn.setChecked(not exclusive or k == key)

    def set_status(self, ok: bool, text: str = "ALL SYSTEMS OPERATIONAL"):
        color = theme.SUCCESS if ok else theme.WARNING
        self._dot.setStyleSheet(f"color:{color};font-size:12px;")
        self._status_text.setText(text)
        self._status_text.setStyleSheet(f"color:{color};font-size:11px;font-weight:700;letter-spacing:1px;")

    def set_analyst(self, name: str):
        pass  # label is static text; kept for interface parity


class HealthTile(QFrame):
    """A small service-health tile with a coloured status dot + detail line."""

    def __init__(self, title: str, detail: str = "Checking...", ok: bool = True,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        self._dot = QLabel("\u25cf")
        lay.addWidget(self._dot, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self._title = QLabel(title)
        self._title.setObjectName("FieldLabel")
        col.addWidget(self._title)
        self._detail = QLabel(detail)
        self._detail.setObjectName("KpiSub")
        self._detail.setWordWrap(True)
        col.addWidget(self._detail)
        lay.addLayout(col, 1)
        self._status_ok = None
        self.set_state(ok, detail)

    def set_state(self, ok: bool, detail: str):
        color = theme.SUCCESS if ok else theme.DANGER
        self._dot.setStyleSheet(f"color:{color};font-size:12px;")
        self._detail.setText(str(detail))
        self._detail.setStyleSheet(
            f"color:{color if ok else theme.DANGER};font-size:11px;")
        self._status_ok = bool(ok)


class LevelBars(QWidget):
    """
    Horizontal severity/level bars (threat distribution).

    ``items`` = [{"label": str, "count": int, "color": str}]. Rendered at the
    current widget size; the tallest bar defines the scale.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, items):
        self._items = list(items or [])
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        if not self._items:
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "No distribution data available.")
            return
        counts = [max(0, int(it.get("count", 0))) for it in self._items]
        peak = max(counts) if counts else 1
        peak = max(1, peak)
        label_w = 86
        bar_h = 22
        gap = 10
        p.setFont(self.font())
        y = 6
        for it, count in zip(self._items, counts):
            color = QColor(it.get("color") or theme.TEXT_MUTED)
            p.setPen(QColor(theme.TEXT_MUTED))
            p.drawText(QRectF(0, y, label_w - 8, bar_h),
                       Qt.AlignRight | Qt.AlignVCenter, str(it.get("label", "")))
            fill_w = (w - label_w) * (count / peak)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.BG_INPUT))
            p.drawRoundedRect(QRectF(label_w, y, w - label_w - 44, bar_h), 5, 5)
            if count > 0:
                p.setBrush(color)
                p.drawRoundedRect(
                    QRectF(label_w, y, max(4.0, fill_w), bar_h), 5, 5)
            p.setPen(QColor(theme.TEXT_PRIMARY))
            p.drawText(QRectF(label_w + fill_w + 8, y, 40, bar_h),
                       Qt.AlignLeft | Qt.AlignVCenter, str(count))
            y += bar_h + gap
        p.end()

    def sizeHint(self):
        from PyQt5.QtCore import QSize as _QSize
        n = max(1, len(self._items))
        return _QSize(360, 6 + n * 32)


class TrendBars(QWidget):
    """
    Simple vertical risk-score trend chart.

    ``points`` = [{"label": str, "value": float, "color": str}]. Values are
    assumed to be in the same unit (e.g. anomaly score / 100) and are drawn
    as proportionally-scaled bars with a baseline.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_points(self, points):
        self._points = list(points or [])
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        if not self._points:
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "No trend data available yet.")
            return
        values = [max(0.0, float(pt.get("value", 0.0))) for pt in self._points]
        ceiling = max(values + [1.0]) * 1.1
        n = len(self._points)
        slot = w / n
        baseline = h - 26
        p.setFont(self.font())
        for i, pt in enumerate(self._points):
            cx = slot * i + slot / 2
            bar_w = min(26.0, slot * 0.5)
            val = values[i]
            bh = (baseline - 8) * (val / ceiling)
            color = QColor(pt.get("color") or theme.ACCENT)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(cx - bar_w / 2, baseline - bh, bar_w, bh), 4, 4)
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(cx - slot / 2, baseline + 6, slot, 18),
                       Qt.AlignHCenter | Qt.AlignTop, str(pt.get("label", "")))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawLine(0, int(baseline), int(w), int(baseline))
        p.end()

    def sizeHint(self):
        from PyQt5.QtCore import QSize as _QSize
        n = max(1, len(self._points))
        return _QSize(360, 6 + min(n, 12) * 26 + 30)


class TrendLine(QWidget):
    """
    Smooth risk-score line chart with a filled area gradient.

    ``points`` = [{"label": str, "value": float, "color": str}]. The caller
    (dashboard) owns time-window filtering; this widget just draws the
    points it is given. Nothing is invented here.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_points(self, points):
        self._points = list(points or [])
        self.update()

    def points(self):
        return list(self._points)

    def paintEvent(self, _event):
        from PyQt5.QtCore import QRectF, QPointF, QLineF
        from PyQt5.QtGui import QPainterPath, QLinearGradient
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        pts = self._points
        if not pts:
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "No risk trend data yet.")
            return
        values = [float(pt.get("value", 0.0)) for pt in pts]
        vmax = max(values + [1.0])
        vmin = min(values + [0.0])
        span = (vmax - vmin) or 1.0
        pad = 0.08 * span
        top, bottom = vmax + pad, max(0.0, vmin - pad)
        plot_h = h
        label_h = 20
        n = len(pts)
        slot = w / max(1, n - 1) if n > 1 else w

        def y_of(v):
            return 12 + (plot_h - label_h - 24) * (1.0 - (v - bottom) / (bottom - top or 1.0)) if (bottom - top) else 12.0

        # grid lines (0, 50, 100 scale hints)
        p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DashLine))
        for gv in (25.0, 50.0, 75.0):
            gy = y_of(gv)
            p.drawLine(QLineF(8, gy, w - 8, gy))

        # filled area gradient
        path = QPainterPath()
        path.moveTo(QPointF(8, y_of(values[0])))
        for i in range(1, n):
            path.lineTo(QPointF(8 + slot * i, y_of(values[i])))
        path.lineTo(QPointF(8 + slot * (n - 1), plot_h - label_h))
        path.lineTo(QPointF(8, plot_h - label_h))
        path.closeSubpath()
        grad = QLinearGradient(0, 10, 0, plot_h - label_h)
        grad.setColorAt(0, QColor(theme.PRIMARY + "55"))
        grad.setColorAt(1, QColor(theme.PRIMARY + "08"))
        p.fillPath(path, grad)

        # line + points
        pen = QPen(QColor(theme.PRIMARY), 2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        line = QPainterPath()
        if n == 1:
            p.drawEllipse(QPointF(8, y_of(values[0])), 3.5, 3.5)
            line.moveTo(QPointF(8 - 10, y_of(values[0])))
            line.lineTo(QPointF(8 + 10, y_of(values[0])))
        else:
            line.moveTo(QPointF(8, y_of(values[0])))
            for i in range(1, n):
                line.lineTo(QPointF(8 + slot * i, y_of(values[i])))
        p.drawPath(line)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.PRIMARY))
        for i in range(n):
            p.drawEllipse(QPointF(8 + slot * i, y_of(values[i])), 3, 3)
        # point value labels
        for i in range(n):
            lbl = f"{values[i]:.0f}"
            p.setPen(QColor(theme.TEXT_PRIMARY if values[i] >= 50 else theme.TEXT_MUTED))
            p.drawText(QRectF(8 + slot * i - slot / 2, y_of(values[i]) - 20, slot, 16),
                       Qt.AlignCenter, lbl)
        # x labels
        step = max(1, n // 8) if n > 8 else 1
        p.setPen(QColor(theme.TEXT_DIM))
        for i in range(0, n, step):
            txt = str(pts[i].get("label", ""))
            p.drawText(QRectF(8 + slot * i - slot / 2, plot_h - label_h, slot, label_h),
                       Qt.AlignHCenter | Qt.AlignTop, txt)
        p.end()

    def sizeHint(self):
        from PyQt5.QtCore import QSize as _QSize
        return _QSize(420, 210)


class ThreatDonut(QWidget):
    """
    Donut chart for the threat level distribution (CRITICAL/HIGH/MEDIUM/LOW
    + BENIGN) with an inline legend. ``items`` = [{"label","count","color"}].
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, items):
        self._items = list(items or [])
        self.update()

    def paintEvent(self, _event):
        from PyQt5.QtCore import QRectF, QPointF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        items = [it for it in self._items if int(it.get("count", 0)) > 0]
        total = sum(int(it.get("count", 0)) for it in items)
        if not items or total <= 0:
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "No distribution data available.")
            return
        side = min(h, 150)
        rect = QRectF(12, (h - side) / 2, side, side)
        # track
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.BG_INPUT))
        p.drawEllipse(rect)
        # segments
        start = 90 * 16
        for it in items:
            count = max(0, int(it.get("count", 0)))
            if count <= 0:
                continue
            span = -int(360 * 16 * count / total)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(it.get("color") or theme.ACCENT))
            p.drawPie(rect.adjusted(2, 2, -2, -2), start, span)
            start += span
        # centre
        p.setBrush(QColor(theme.BG_PANEL))
        p.drawEllipse(rect.adjusted(34, 34, -34, -34))
        p.setPen(QColor(theme.TEXT_PRIMARY))
        f = p.font()
        f.setPixelSize(22)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(rect.x(), rect.y() + rect.height() * 0.26,
                          rect.width(), 30), Qt.AlignCenter, str(total))
        p.setPen(QColor(theme.TEXT_MUTED))
        f2 = p.font()
        f2.setPixelSize(9)
        f2.setBold(False)
        p.setFont(f2)
        p.drawText(QRectF(rect.x(), rect.y() + rect.height() * 0.26 + 30,
                          rect.width(), 18), Qt.AlignCenter, "TOTAL")
        # legend
        lx = rect.right() + 18
        ly = rect.y() + 6
        p.setFont(self.font())
        for it in items:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(it.get("color") or theme.TEXT_MUTED))
            p.drawRoundedRect(QRectF(lx, ly + 3, 12, 12), 3, 3)
            p.setPen(QColor(theme.TEXT_MUTED))
            p.drawText(QPointF(lx + 18, ly + 13),
                       f"{it.get('label','')}  \u00b7  {int(it.get('count',0))}")
            ly += 24
        p.end()

    def sizeHint(self):
        from PyQt5.QtCore import QSize as _QSize
        return _QSize(340, 200)
