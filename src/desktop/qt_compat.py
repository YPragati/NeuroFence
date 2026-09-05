"""Small PyQt6 enum bridge used while rendering the desktop client.

PyQt6 scopes Qt enum values (for example ``Qt.AlignmentFlag.AlignCenter``).
The UI uses this module so layout code remains readable while passing only
native PyQt6 enum values to Qt APIs.
"""

from PyQt6.QtCore import Qt as _Qt


class Qt:
    AlignCenter = _Qt.AlignmentFlag.AlignCenter
    AlignLeft = _Qt.AlignmentFlag.AlignLeft
    AlignRight = _Qt.AlignmentFlag.AlignRight
    AlignTop = _Qt.AlignmentFlag.AlignTop
    AlignVCenter = _Qt.AlignmentFlag.AlignVCenter
    AlignHCenter = _Qt.AlignmentFlag.AlignHCenter
    Horizontal = _Qt.Orientation.Horizontal
    Vertical = _Qt.Orientation.Vertical
    RichText = _Qt.TextFormat.RichText
    TextSelectableByMouse = _Qt.TextInteractionFlag.TextSelectableByMouse
    UserRole = _Qt.ItemDataRole.UserRole
    DashLine = _Qt.PenStyle.DashLine
    NoPen = _Qt.PenStyle.NoPen
    RoundCap = _Qt.PenCapStyle.RoundCap
    ElideRight = _Qt.TextElideMode.ElideRight
    PointingHandCursor = _Qt.CursorShape.PointingHandCursor
    WA_StyledBackground = _Qt.WidgetAttribute.WA_StyledBackground
