"""
NeuroFence -- enterprise AI Model Security Platform visual theme.

Central source of colours, typography and the global Qt style sheet so
the entire desktop app shares one coherent, professional security
identity. The palette follows the platform spec:

    * #070A12 window background      * #22D3EE cyan (primary brand)
    * #0B1020 secondary              * #3B82F6 blue (secondary accent)
    * #111827 cards                  * #A78BFA violet (analytics only)
    * #151C2E elevated / inputs      * #22C55E success / verified
    * #263147 borders                * #F59E0B warning / review
    *                                  #F43F5E critical / quarantine

Attribute names are kept stable so existing views keep working.
"""

# ---- Palette -------------------------------------------------------------
BG_DEEP = "#070A12"          # window / very dark navy-black
BG_PANEL = "#0B1020"         # secondary panels / header
BG_RAISED = "#111827"        # cards
BG_INPUT = "#151C2E"         # elevated elements / inputs / table rows
BORDER = "#263147"           # thin borders
BORDER_LIGHT = "#34435F"     # hover borders / accents
SIDEBAR_BG = "#0A0F1E"       # left navigation rail

TEXT_PRIMARY = "#F8FAFC"
TEXT_MUTED = "#94A3B8"
TEXT_DIM = "#64748B"

ACCENT = "#22D3EE"           # cyan -- primary brand accent
ACCENT_SOFT = "#67E8F9"
ACCENT_BRIGHT = "#38BDF8"    # cyan hover
ACCENT_DIM = "#0E7490"
ACCENT_SECONDARY = "#3B82F6" # blue -- secondary accent only
PRIMARY = "#22D3EE"          # selection highlight (cyan)
ANALYTICS = "#A78BFA"        # violet -- sparingly, analytics only

# Risk / status system (restrained; red reserved for critical/quarantine)
SUCCESS = "#22C55E"          # safe / verified (green)
SAFE = "#22C55E"
WARNING = "#F59E0B"          # medium / review (amber)
DANGER = "#F43F5E"           # high / error (rose)
CRITICAL = "#F43F5E"         # severe / quarantine (rose)

RISK_COLORS = {
    "LOW": SAFE,
    "MEDIUM": WARNING,
    "HIGH": "#FB7185",
    "CRITICAL": CRITICAL,
}

# ---- Fonts ---------------------------------------------------------------
FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"

GLASS_RGBA = "rgba(11,16,32,0.82)"


def risk_color(level: str) -> str:
    """Return the colour for a given risk level."""
    return RISK_COLORS.get(str(level).upper(), TEXT_MUTED)


def html_translate(text: str) -> str:
    """Escape text for safe display in HTML labels."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def status_chip_html(text: str, color: str) -> str:
    """Return a styled inline 'chip' for an HTML-capable label."""
    return (
        f'<span style="color:{color};font-weight:700;'
        f'background:{color}1f;border:1px solid {color}59;'
        f'border-radius:11px;padding:3px 12px;font-size:11px;'
        f'letter-spacing:1px;">{html_translate(text)}</span>'
    )


def risk_badge_html(level: str) -> str:
    """A coloured risk badge pill."""
    color = risk_color(level)
    return (
        f'<span style="color:{color};font-weight:700;background:{color}1f;'
        f'border:1px solid {color}59;border-radius:9px;padding:1px 9px;'
        f'font-size:11px;">{html_translate(level)}</span>'
    )


# Model lifecycle display helpers -------------------------------------------

# Backend status value -> professional UI label (honest mapping, no new schema).
MODEL_STATUS_LABELS = {
    "imported": "UNVERIFIED",
    "validated": "VERIFIED",
    "scanned": "SCANNED",
    "approved": "APPROVED",
    "review": "REVIEW REQUIRED",
    "quarantined": "QUARANTINED",
    "error": "ERROR",
}


def model_status_color(status: str) -> str:
    """Colour for a model lifecycle status value."""
    s = (status or "").lower()
    return {
        "imported": ACCENT_SECONDARY,
        "validated": SUCCESS,
        "scanned": WARNING,
        "approved": SUCCESS,
        "review": WARNING,
        "quarantined": CRITICAL,
        "error": CRITICAL,
    }.get(s, TEXT_MUTED)


def model_status_label(status: str) -> str:
    """Present the raw backend status as a professional lifecycle label."""
    s = (status or "").lower()
    if s in ("approved", "review", "quarantined"):
        return s.upper().replace("REVIEW", "REVIEW REQUIRED")
    return MODEL_STATUS_LABELS.get(s, (s or "unknown").upper())


GLOBAL_QSS = f"""
* {{
    font-family: "{FONT_FAMILY}";
    font-size: 12px;
    color: {TEXT_PRIMARY};
    outline: none;
}}
QMainWindow, QDialog {{
    background-color: {BG_DEEP};
}}
QWidget#AppRoot {{
    background-color: {BG_DEEP};
}}
QWidget#ContentArea {{
    background-color: {BG_DEEP};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ---- Top header / horizontal nav ---- */
QFrame#HeaderBar {{
    background-color: {BG_PANEL};
    border-bottom: 1px solid {BORDER};
}}
QFrame#NavBar {{
    background-color: {BG_DEEP};
    border-bottom: 1px solid {BORDER};
}}
QFrame#Topbar {{
    background-color: {BG_PANEL};
    border-bottom: 1px solid {BORDER};
}}
QLabel#BrandTitle {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {TEXT_PRIMARY};
}}
QLabel#BrandSub {{
    font-size: 9px;
    letter-spacing: 3px;
    color: {ACCENT_SOFT};
    text-transform: uppercase;
}}
QLabel#HeaderMeta {{
    font-size: 11px;
    color: {TEXT_DIM};
    letter-spacing: 1px;
}}
QLabel#NavLabel {{
    font-size: 9px;
    letter-spacing: 2px;
    color: {TEXT_DIM};
    text-transform: uppercase;
    padding: 0 4px;
}}
QPushButton#TopNavButton {{
    color: {TEXT_MUTED};
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    text-align: center;
    padding: 12px 18px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QPushButton#TopNavButton:hover {{
    color: {TEXT_PRIMARY};
    background-color: {BG_RAISED};
}}
QPushButton#TopNavButton:checked {{
    color: {TEXT_PRIMARY};
    border-bottom: 3px solid {ACCENT};
    font-weight: 700;
}}

/* ---- Sidebar (SOC left rail) ---- */
QWidget#Sidebar {{
    background-color: {SIDEBAR_BG};
    border-right: 1px solid {BORDER};
}}
QLabel#SidebarBrand {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {TEXT_PRIMARY};
}}
QLabel#SidebarBrandAccent {{
    color: {ACCENT};
}}
QLabel#SidebarTag {{
    font-size: 9px;
    letter-spacing: 2px;
    color: {ACCENT_SOFT};
    text-transform: uppercase;
}}
QLabel#NavGroupLabel {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {TEXT_DIM};
    margin-top: 12px;
    padding: 0 2px;
    text-transform: uppercase;
}}
QPushButton#SidebarButton {{
    color: {TEXT_MUTED};
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    text-align: left;
    padding: 9px 14px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.4px;
}}
QPushButton#SidebarButton:hover {{
    color: {TEXT_PRIMARY};
    background-color: {BG_RAISED};
}}
QPushButton#SidebarButton:checked {{
    color: {TEXT_PRIMARY};
    background-color: {ACCENT}1a;
    border-left: 3px solid {ACCENT};
    font-weight: 700;
}}
QLabel#StatusText {{
    color: {SUCCESS};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}

/* ---- Tabs (SOC underline) ---- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: {BG_DEEP};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 9px 20px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}

/* ---- Page header ---- */
QLabel#PageTitle {{
    font-size: 21px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    letter-spacing: 0.5px;
}}
QLabel#PageSubtitle {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}

/* ---- Panels / cards ---- */
QFrame#Panel, QFrame#KpiCard {{
    background-color: {GLASS_RGBA};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#Panel:hover, QFrame#KpiCard:hover {{
    border-color: {BORDER_LIGHT};
}}
QLabel#PanelTitle {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: {TEXT_MUTED};
}}
QLabel#SectionHeader {{
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: {ACCENT_SOFT};
    margin-top: 14px;
}}
QLabel#KpiLabel {{
    font-size: 10px;
    color: {TEXT_MUTED};
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QLabel#KpiValue {{
    font-size: 28px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}
QLabel#KpiSub {{
    font-size: 11px;
    color: {TEXT_DIM};
}}
QLabel#FieldLabel {{
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: {TEXT_DIM};
}}
QLabel#FieldValue {{
    font-size: 12px;
    color: {TEXT_PRIMARY};
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 8px 18px;
    color: {TEXT_PRIMARY};
    font-weight: 500;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    background-color: {BG_INPUT};
}}
QPushButton:pressed {{
    background-color: {ACCENT_DIM};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    background-color: {BG_PANEL};
    border-color: {BORDER};
}}
QPushButton#PrimaryButton {{
    background-color: {ACCENT};
    color: #FFFFFF;
    font-weight: 700;
    border: none;
    padding: 12px 24px;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {ACCENT_BRIGHT};
}}
QPushButton#GhostButton {{
    background-color: transparent;
    border: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}
QPushButton#GhostButton:hover {{
    color: {TEXT_PRIMARY};
    border-color: {ACCENT};
}}

/* ---- Inputs ---- */
QLineEdit, QSpinBox, QPlainTextEdit, QComboBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 7px 12px;
    color: {TEXT_PRIMARY};
    selection-background-color: {PRIMARY};
}}
QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {BG_RAISED};
    border: none;
    width: 18px;
}}

/* ---- Tables ---- */
QTableWidget, QTableView {{
    background-color: {BG_PANEL};
    alternate-background-color: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    selection-background-color: {PRIMARY}55;
    selection-color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background-color: {BG_RAISED};
    color: {ACCENT_SOFT};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 9px 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QTableCornerButton::section {{
    background-color: {BG_RAISED};
    border: none;
}}

/* ---- Progress ---- */
QProgressBar {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    text-align: center;
    color: {TEXT_MUTED};
    height: 22px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT_SECONDARY};
    border-radius: 6px;
}}

/* ---- Status bar ---- */
QStatusBar {{
    background-color: {BG_PANEL};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER};
}}
QStatusBar::item {{ border: none; }}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{
    background: {BG_PANEL}; width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* ---- Splitter / misc ---- */
QSplitter::handle {{ background: {BORDER}; }}
QToolTip {{
    background-color: {BG_RAISED}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
}}
QCheckBox {{
    color: {TEXT_PRIMARY}; spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER_LIGHT}; border-radius: 4px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}
"""