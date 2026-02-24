"""
ui/widgets.py
-------------
Reusable Qt widgets and shared style constants for the OHE GUI.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Dark-theme colour palette
# ---------------------------------------------------------------------------

class Palette:
    BG_DARK   = "#1a1a2e"
    BG_PANEL  = "#16213e"
    BG_CARD   = "#0f3460"
    ACCENT    = "#e94560"
    TEXT      = "#e0e0e0"
    TEXT_DIM  = "#7a7a9a"
    WARNING   = "#f0a500"
    CRITICAL  = "#e74c3c"
    OK        = "#2ecc71"
    PLOT_BG   = "#0d1b2a"


GLOBAL_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {Palette.BG_DARK};
    color: {Palette.TEXT};
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}}
QMenuBar, QMenu {{
    background-color: {Palette.BG_PANEL};
    color: {Palette.TEXT};
}}
QMenuBar::item:selected, QMenu::item:selected {{
    background-color: {Palette.BG_CARD};
}}
QStatusBar {{
    background-color: {Palette.BG_PANEL};
    color: {Palette.TEXT_DIM};
    font-size: 12px;
}}
QToolBar {{
    background-color: {Palette.BG_PANEL};
    border: none;
    spacing: 6px;
    padding: 4px;
}}
QToolButton {{
    background-color: {Palette.BG_CARD};
    color: {Palette.TEXT};
    border: 1px solid #344;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: bold;
}}
QToolButton:hover  {{ background-color: #1a4070; }}
QToolButton:pressed {{ background-color: {Palette.ACCENT}; }}
QPushButton {{
    background-color: {Palette.BG_CARD};
    color: {Palette.TEXT};
    border: 1px solid #2a4a7f;
    border-radius: 5px;
    padding: 5px 16px;
}}
QPushButton:hover   {{ background-color: #1a4a80; }}
QPushButton:pressed {{ background-color: {Palette.ACCENT}; }}
QSlider::groove:horizontal {{
    height: 4px; background: #344; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {Palette.ACCENT}; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px;
}}
QScrollBar:vertical {{
    background: {Palette.BG_PANEL}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #344; border-radius: 4px; min-height: 20px;
}}
QGroupBox {{
    border: 1px solid #2a4a7f;
    border-radius: 6px;
    margin-top: 8px;
    font-weight: bold;
    color: {Palette.TEXT_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0 6px; left: 10px;
}}
QSplitter::handle {{ background-color: #2a4a7f; }}
"""


# ---------------------------------------------------------------------------
# MetricCard — a rounded tile showing a big value and a small label
# ---------------------------------------------------------------------------

class MetricCard(QWidget):
    """Displays a single metric (e.g., stagger value) in a coloured card."""

    def __init__(self, label: str, unit: str = "", parent=None) -> None:
        super().__init__(parent)
        self._unit = unit
        self.setFixedHeight(72)
        self.setMinimumWidth(100)

        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {Palette.BG_CARD};
                border: 1px solid #1a4070;
                border-radius: 8px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(1)

        self._value_lbl = QLabel("—")
        f = QFont("Segoe UI", 20, QFont.Weight.Bold)
        self._value_lbl.setFont(f)
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_lbl.setStyleSheet(f"color: {Palette.TEXT};")

        self._label_lbl = QLabel(label)
        self._label_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_lbl.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 11px;")

        lay.addWidget(self._value_lbl)
        lay.addWidget(self._label_lbl)

    def set_value(self, value: float | None, colour: str = Palette.TEXT) -> None:
        if value is None:
            self._value_lbl.setText("—")
            self._value_lbl.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        else:
            fmt = f"{value:+.1f}" if self._unit == "mm" else f"{value:.2f}"
            self._value_lbl.setText(f"{fmt} {self._unit}")
            self._value_lbl.setStyleSheet(f"color: {colour};")


# ---------------------------------------------------------------------------
# SeverityBadge — inline coloured severity label
# ---------------------------------------------------------------------------

class SeverityBadge(QLabel):
    _COLOURS = {
        "WARNING":  (Palette.WARNING,  "#2a1e00"),
        "CRITICAL": (Palette.CRITICAL, "#2a0000"),
        "OK":       (Palette.OK,       "#002a10"),
    }

    def __init__(self, severity: str = "OK", parent=None) -> None:
        super().__init__(parent)
        self.set_severity(severity)
        self.setFixedWidth(72)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_severity(self, severity: str) -> None:
        fg, bg = self._COLOURS.get(severity, (Palette.TEXT_DIM, Palette.BG_PANEL))
        self.setText(severity)
        self.setStyleSheet(
            f"color: {fg}; background-color: {bg}; border-radius: 4px;"
            f"padding: 1px 4px; font-size: 11px; font-weight: bold;"
        )


# ---------------------------------------------------------------------------
# Divider
# ---------------------------------------------------------------------------

class HDivider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"color: #2a4a7f;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
