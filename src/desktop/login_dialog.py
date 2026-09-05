"""
Login -- local single-session gate for the AI Model Security Platform.

No cloud or external authentication: the operator enters an analyst
name (optionally a mission/purpose label) and the session is recorded
locally via QSettings. "Remember me" skips the gate on the next launch.

The real environment is always LOCAL / OFFLINE / AIR-GAPPED.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QFrame, QApplication,
)

from src.desktop import theme

SETTINGS_ORG = "NeuroFence"
SETTINGS_APP = "NeuroFence"
KEY_ANALYST = "session/analyst_name"
KEY_REMEMBER = "session/remember"


def load_saved_session():
    """Return (analyst_name, remember) from local QSettings ("" if none)."""
    from PyQt5.QtCore import QSettings
    s = QSettings(SETTINGS_ORG, SETTINGS_APP)
    name = str(s.value(KEY_ANALYST, "") or "").strip()
    remember = bool(s.value(KEY_REMEMBER, False, type=bool))
    return name, remember


def save_session(analyst_name: str, remember: bool):
    """Persist the current local session."""
    from PyQt5.QtCore import QSettings
    s = QSettings(SETTINGS_ORG, SETTINGS_APP)
    s.setValue(KEY_ANALYST, str(analyst_name).strip())
    if remember:
        s.setValue(KEY_REMEMBER, True)
    else:
        s.remove(KEY_REMEMBER)


def clear_session():
    from PyQt5.QtCore import QSettings
    s = QSettings(SETTINGS_ORG, SETTINGS_APP)
    s.remove(KEY_ANALYST)
    s.remove(KEY_REMEMBER)


class LoginDialog(QDialog):
    """Local analyst sign-in screen (OFFLINE -- no remote auth)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NeuroFence -- Sign In")
        self.setModal(True)
        self.setMinimumWidth(430)
        self.setMinimumHeight(430)
        self._build_ui()
        self._check_remembered()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 30, 34, 26)
        root.setSpacing(14)

        brand = QVBoxLayout()
        brand.setSpacing(2)
        title = QLabel("NEUROFENCE")
        title.setObjectName("BrandTitle")
        title.setStyleSheet("font-size:26px;letter-spacing:3px;")
        brand.addWidget(title)
        sub = QLabel("AI MODEL SECURITY PLATFORM")
        sub.setObjectName("BrandSub")
        sub.setStyleSheet("font-size:11px;")
        brand.addWidget(sub)
        root.addLayout(brand)

        tag = QLabel(
            theme.status_chip_html("LOCAL  /  OFFLINE  /  AIR-GAPPED", theme.SUCCESS)
        )
        tag.setTextFormat(Qt.RichText)
        root.addWidget(tag)

        root.addSpacing(6)

        heading = QLabel("OPERATOR SESSION")
        heading.setObjectName("FieldLabel")
        root.addWidget(heading)

        self.edit_analyst = QLineEdit()
        self.edit_analyst.setPlaceholderText("Analyst name (optional)")
        self.edit_analyst.setMaxLength(60)
        root.addWidget(self.edit_analyst)

        heading2 = QLabel("PURPOSE (OPTIONAL)")
        heading2.setObjectName("FieldLabel")
        root.addWidget(heading2)

        self.edit_mission = QLineEdit()
        self.edit_mission.setPlaceholderText("e.g. Pre-deployment model audit")
        self.edit_mission.setMaxLength(120)
        root.addWidget(self.edit_mission)

        self.chk_remember = QCheckBox("Remember me on this workstation")
        self.chk_remember.setChecked(False)
        root.addWidget(self.chk_remember)

        root.addStretch(1)

        note = QLabel(
            "This session is stored locally only. No account, no cloud, "
            "no telemetry."
        )
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        root.addWidget(note)

        btn_row = QHBoxLayout()
        self.btn_signin = QPushButton("SIGN IN  \u2192")
        self.btn_signin.setObjectName("PrimaryButton")
        self.btn_signin.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_signin)

        self.btn_clear = QPushButton("Clear Saved Session")
        self.btn_clear.setObjectName("GhostButton")
        self.btn_clear.clicked.connect(self._clear_saved)
        btn_row.addWidget(self.btn_clear)
        root.addLayout(btn_row)

    def _check_remembered(self):
        name, remember = load_saved_session()
        if name:
            self.edit_analyst.setText(name)
        self.chk_remember.setChecked(bool(remember))

    def _clear_saved(self):
        from PyQt5.QtCore import QSettings
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        s.remove(KEY_ANALYST)
        s.remove(KEY_REMEMBER)
        self.edit_analyst.setText("")
        self.chk_remember.setChecked(False)

    # ---- accessors ----

    def analyst_name(self) -> str:
        return str(self.edit_analyst.text()).strip()

    def mission(self) -> str:
        return str(self.edit_mission.text()).strip()

    def remember_checked(self) -> bool:
        return self.chk_remember.isChecked()

    def accept(self):
        save_session(self.analyst_name() or "Analyst", self.remember_checked())
        super().accept()