"""
ui/widgets.py
-------------
Reusable Qt widgets and shared style constants for the OHE GUI.
Phase 2 — enhanced palette, SessionInfoBar, animated MetricCard, SourceBadge.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Colour palette — rich dark navy with accent pops
# ---------------------------------------------------------------------------

class Palette:
    BG       = "#0d1117"        # near-black base
    BG_DARK  = "#1a1a2e"        # dark navy
    BG_PANEL = "#161b27"        # panel background
    BG_CARD  = "#0f3460"        # card / button fill
    ACCENT   = "#e94560"        # vivid red-pink accent
    ACCENT2  = "#4a8adf"        # blue accent
    TEXT     = "#e8eaf0"        # primary text
    TEXT_DIM = "#6a7490"        # muted / secondary text
    WARNING  = "#f5a623"        # amber warning
    CRITICAL = "#e74c3c"        # vivid red critical
    OK       = "#2ecc71"        # emerald ok
    PLOT_BG  = "#0d1b2a"        # plot area background
    BORDER   = "#1e2d4a"        # subtle border
    TRACK    = "#7b2fff"        # purple for track name


GLOBAL_STYLESHEET = f"""
/* ── Base ─────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {Palette.BG_DARK};
    color: {Palette.TEXT};
    font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
    font-size: 13px;
}}

/* ── Menu ─────────────────────────────────────────────── */
QMenuBar {{
    background-color: {Palette.BG_PANEL};
    color: {Palette.TEXT};
    border-bottom: 1px solid {Palette.BORDER};
    padding: 2px 4px;
}}
QMenuBar::item:selected {{ background-color: {Palette.BG_CARD}; border-radius: 4px; }}
QMenu {{
    background-color: {Palette.BG_PANEL};
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item:selected {{ background-color: {Palette.BG_CARD}; border-radius: 4px; }}

/* ── Toolbar ──────────────────────────────────────────── */
QToolBar {{
    background-color: {Palette.BG_PANEL};
    border-bottom: 1px solid {Palette.BORDER};
    spacing: 6px;
    padding: 5px 8px;
}}
QToolButton {{
    background-color: transparent;
    color: {Palette.TEXT};
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: 600;
    font-size: 12px;
}}
QToolButton:hover  {{
    background-color: {Palette.BG_CARD};
    border: 1px solid {Palette.BORDER};
}}
QToolButton:pressed {{ background-color: {Palette.ACCENT}; color: white; }}

/* ── Status bar ───────────────────────────────────────── */
QStatusBar {{
    background-color: {Palette.BG_PANEL};
    color: {Palette.TEXT_DIM};
    font-size: 11px;
    border-top: 1px solid {Palette.BORDER};
}}

/* ── Buttons ──────────────────────────────────────────── */
QPushButton {{
    background-color: {Palette.BG_CARD};
    color: {Palette.TEXT};
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    padding: 6px 18px;
    font-weight: 500;
}}
QPushButton:hover   {{ background-color: #1a4a80; border-color: {Palette.ACCENT2}; }}
QPushButton:pressed {{ background-color: {Palette.ACCENT}; border-color: {Palette.ACCENT}; color: white; }}
QPushButton:disabled {{ color: {Palette.TEXT_DIM}; background-color: {Palette.BG_PANEL}; }}

/* ── Inputs ───────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {Palette.BG_PANEL};
    color: {Palette.TEXT};
    border: 1px solid {Palette.BORDER};
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: {Palette.ACCENT2};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {Palette.ACCENT2};
}}

/* ── Sliders ──────────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 4px; background: {Palette.BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {Palette.ACCENT2}; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {Palette.ACCENT2}; border-radius: 2px; }}

/* ── Scrollbars ───────────────────────────────────────── */
QScrollBar:vertical {{
    background: {Palette.BG_PANEL}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {Palette.BORDER}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {Palette.ACCENT2}; }}

/* ── Group boxes ──────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {Palette.BORDER};
    border-radius: 8px;
    margin-top: 10px;
    font-weight: 600;
    color: {Palette.TEXT_DIM};
    font-size: 11px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0 8px; left: 12px;
}}

/* ── Tab widget ───────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {Palette.BORDER};
    border-radius: 0 0 8px 8px;
    background-color: {Palette.BG_PANEL};
}}
QTabBar::tab {{
    background-color: {Palette.BG_DARK};
    color: {Palette.TEXT_DIM};
    padding: 6px 18px;
    border: 1px solid {Palette.BORDER};
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    min-width: 130px;
    font-size: 11px;
}}
QTabBar::tab:selected {{
    background-color: {Palette.BG_PANEL};
    color: {Palette.TEXT};
    border-color: {Palette.ACCENT2};
}}
QTabBar::tab:hover {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT}; }}

/* ── Splitter ─────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {Palette.BORDER};
    border-radius: 2px;
}}
QSplitter::handle:hover {{ background-color: {Palette.ACCENT2}; }}

/* ── Table ────────────────────────────────────────────── */
QTableWidget {{
    background-color: {Palette.BG_PANEL};
    color: {Palette.TEXT};
    gridline-color: {Palette.BORDER};
    border: none;
    border-radius: 4px;
    alternate-background-color: {Palette.BG_DARK};
}}
QTableWidget::item:selected {{
    background-color: #1a3a5a;
    color: {Palette.TEXT};
}}
QHeaderView::section {{
    background-color: {Palette.BG_DARK};
    color: {Palette.TEXT_DIM};
    font-size: 10px;
    font-weight: 600;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid {Palette.BORDER};
    border-bottom: 1px solid {Palette.BORDER};
    text-transform: uppercase;
    letter-spacing: 1px;
}}

/* ── Progress bar ─────────────────────────────────────── */
QProgressBar {{
    background-color: {Palette.BG_DARK};
    border: 1px solid {Palette.BORDER};
    border-radius: 5px;
    text-align: center;
    color: {Palette.TEXT};
    font-size: 10px;
    font-weight: 600;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {Palette.ACCENT2}, stop:1 #7b2fff);
    border-radius: 4px;
}}

/* ── Radio buttons & checkboxes ───────────────────────── */
QRadioButton, QCheckBox {{
    color: {Palette.TEXT};
    spacing: 8px;
}}
QRadioButton::indicator, QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {Palette.BORDER};
    border-radius: 8px;
    background-color: {Palette.BG_PANEL};
}}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
    background-color: {Palette.ACCENT2};
    border-color: {Palette.ACCENT2};
}}

/* ── Dialog ───────────────────────────────────────────── */
QDialog {{ background-color: {Palette.BG_DARK}; }}
"""


# ---------------------------------------------------------------------------
# MetricCard — live measurement tile with colour-coded value
# ---------------------------------------------------------------------------

class MetricCard(QWidget):
    """Animated metric tile showing a big live value with colour feedback."""

    def __init__(self, label: str, unit: str = "", parent=None) -> None:
        super().__init__(parent)
        self._unit = unit
        self.setFixedHeight(80)
        self.setMinimumWidth(110)
        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {Palette.BG_CARD};
                border: 1px solid {Palette.BORDER};
                border-radius: 10px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        self._value_lbl = QLabel("—")
        self._value_lbl.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_lbl.setStyleSheet(f"color: {Palette.TEXT_DIM};")

        self._label_lbl = QLabel(label.upper())
        self._label_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_lbl.setStyleSheet(
            f"color: {Palette.TEXT_DIM}; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 1px;"
        )

        lay.addWidget(self._value_lbl)
        lay.addWidget(self._label_lbl)

    def set_value(self, value: float | None, colour: str = Palette.TEXT) -> None:
        if value is None:
            self._value_lbl.setText("—")
            self._value_lbl.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        else:
            fmt = f"{value:+.1f}" if self._unit == "mm" else f"{value:.1f}"
            self._value_lbl.setText(f"{fmt} {self._unit}")
            self._value_lbl.setStyleSheet(f"color: {colour}; font-weight: bold;")


# ---------------------------------------------------------------------------
# SessionInfoBar — horizontal banner showing track/source/mode
# ---------------------------------------------------------------------------

class SessionInfoBar(QWidget):
    """Compact banner showing active session metadata above the video panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(
            f"background-color: {Palette.BG_PANEL}; "
            f"border-bottom: 1px solid {Palette.BORDER};"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(20)

        def _badge(text: str, colour: str, icon: str = "") -> QLabel:
            lbl = QLabel(f"{icon}  {text}" if icon else text)
            lbl.setStyleSheet(
                f"color: {colour}; font-size: 11px; font-weight: 600; "
                f"background: transparent;"
            )
            return lbl

        self._lbl_track  = _badge("No track", Palette.TEXT_DIM, "🗂")
        self._lbl_source = _badge("No source", Palette.TEXT_DIM, "🎬")
        self._lbl_gps    = _badge("GPS: —", Palette.TEXT_DIM)
        self._lbl_speed  = _badge("Speed: —", Palette.TEXT_DIM)
        self._lbl_model  = _badge("—", Palette.TEXT_DIM, "🤖")

        for lbl in (self._lbl_track, self._lbl_source,
                    self._lbl_gps, self._lbl_speed, self._lbl_model):
            row.addWidget(lbl)
        row.addStretch()

    def update_session(
        self,
        track_name: str = "",
        source: str = "",
        gps_mode: str = "",
        speed_mode: str = "",
        model_version: str = "",
    ) -> None:
        if track_name:
            self._lbl_track.setText(f"🗂  {track_name}")
            self._lbl_track.setStyleSheet(
                f"color: {Palette.TRACK}; font-size: 11px; font-weight: 700; background:transparent;"
            )
        if source:
            src_short = source[-38:] if len(source) > 38 else source
            self._lbl_source.setText(f"🎬  {src_short}")
            self._lbl_source.setStyleSheet(
                f"color: {Palette.ACCENT2}; font-size: 11px; font-weight: 600; background:transparent;"
            )
        if gps_mode:
            col = Palette.OK if gps_mode == "simulated" else Palette.WARNING
            icon = "📍" if gps_mode == "simulated" else "🛰"
            self._lbl_gps.setText(f"{icon}  GPS: {gps_mode.title()}")
            self._lbl_gps.setStyleSheet(
                f"color: {col}; font-size: 11px; font-weight:600; background:transparent;"
            )
        if speed_mode:
            col = Palette.OK if speed_mode == "simulated" else Palette.WARNING
            self._lbl_speed.setText(f"🚆  Speed: {speed_mode.title()}")
            self._lbl_speed.setStyleSheet(
                f"color: {col}; font-size: 11px; font-weight:600; background:transparent;"
            )
        if model_version:
            self._lbl_model.setText(f"🤖  {model_version}")
            self._lbl_model.setStyleSheet(
                f"color: {Palette.TEXT_DIM}; font-size: 11px; background:transparent;"
            )


# ---------------------------------------------------------------------------
# SeverityBadge
# ---------------------------------------------------------------------------

class SeverityBadge(QLabel):
    _COLOURS = {
        "WARNING":  (Palette.WARNING,  "#2a1e00"),
        "CRITICAL": (Palette.CRITICAL, "#2a0000"),
        "OK":       (Palette.OK,       "#00200e"),
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
            f"padding: 2px 6px; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )


# ---------------------------------------------------------------------------
# HDivider
# ---------------------------------------------------------------------------

class HDivider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"color: {Palette.BORDER};")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
