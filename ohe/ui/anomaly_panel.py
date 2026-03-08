"""
ui/anomaly_panel.py
--------------------
Scrollable anomaly event log — Phase 2 enhanced.

Each row shows: frame · timestamp · type · value · severity badge.
Rows are colour-coded with left-side coloured accent bar.
"""

from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ohe.core.models import Anomaly
from ohe.ui.widgets import HDivider, Palette, SeverityBadge

_MAX_ROWS = 500


class AnomalyPanel(QWidget):
    """Scrollable anomaly event log with colour-coded rows."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Palette.BG_PANEL};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet(
            f"background-color: {Palette.BG_DARK}; "
            f"border-bottom: 1px solid {Palette.BORDER};"
        )
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(10, 0, 10, 0)
        h_lay.setSpacing(0)
        title = QLabel("  ⚡  Anomaly Log")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Palette.TEXT}; background: transparent;")
        col_hdr = QLabel("FRAME      TYPE                        VALUE    SEV")
        col_hdr.setFont(QFont("Consolas", 9))
        col_hdr.setStyleSheet(
            f"color: {Palette.TEXT_DIM}; background: transparent; "
            f"letter-spacing: 1px;"
        )
        h_lay.addWidget(title)
        h_lay.addStretch()
        h_lay.addWidget(col_hdr)
        outer.addWidget(header)

        # ── Scroll area ────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("border: none;")

        self._content = QWidget()
        self._content.setStyleSheet(f"background-color: {Palette.BG_PANEL};")
        self._layout  = QVBoxLayout(self._content)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._layout.addStretch()
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

        self._row_count = 0

    # ------------------------------------------------------------------
    def add_anomaly(self, a: Anomaly) -> None:
        """Prepend a new anomaly row."""
        row = _AnomalyRow(a)
        self._layout.insertWidget(0, row)
        self._row_count += 1
        if self._row_count > _MAX_ROWS:
            item = self._layout.takeAt(self._layout.count() - 2)
            if item and item.widget():
                item.widget().deleteLater()
            self._row_count -= 1

    def clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._row_count = 0

    @property
    def count(self) -> int:
        return self._row_count


class _AnomalyRow(QWidget):
    """Single colour-coded anomaly row with left-accent bar."""

    _ACCENT = {
        "WARNING":  (Palette.WARNING,  "#1e1500", "#3a2800"),
        "CRITICAL": (Palette.CRITICAL, "#1e0500", "#3a0800"),
    }

    def __init__(self, a: Anomaly, parent=None) -> None:
        super().__init__(parent)
        accent, bg, bg_hover = self._ACCENT.get(
            a.severity, (Palette.TEXT_DIM, Palette.BG_CARD, "#1a2030")
        )

        self.setFixedHeight(30)
        self.setStyleSheet(
            f"background-color: {bg}; border-radius: 4px; border-left: 3px solid {accent};"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)

        mono = QFont("Consolas", 10)

        # Frame
        lbl_frame = QLabel(f"#{a.frame_id:05d}")
        lbl_frame.setFixedWidth(58)
        lbl_frame.setFont(mono)
        lbl_frame.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        lay.addWidget(lbl_frame)

        # Timestamp
        if a.timestamp_ms:
            ts = datetime.datetime.fromtimestamp(a.timestamp_ms / 1000.0)
            ts_str = ts.strftime("%H:%M:%S")
        else:
            ts_str = "—"
        lbl_ts = QLabel(ts_str)
        lbl_ts.setFixedWidth(56)
        lbl_ts.setFont(mono)
        lbl_ts.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        lay.addWidget(lbl_ts)

        # Type
        lbl_type = QLabel(a.anomaly_type.replace("_", " "))
        lbl_type.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_type.setStyleSheet(f"color: {accent};")
        lbl_type.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(lbl_type)

        # Value
        lbl_val = QLabel(f"{a.value:.1f}")
        lbl_val.setFixedWidth(52)
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_val.setFont(mono)
        lbl_val.setStyleSheet(f"color: {accent};")
        lay.addWidget(lbl_val)

        # Speed (if available)
        if a.speed_kmh:
            lbl_spd = QLabel(f"{a.speed_kmh:.0f} km/h")
            lbl_spd.setFixedWidth(60)
            lbl_spd.setFont(mono)
            lbl_spd.setStyleSheet(f"color: {Palette.TEXT_DIM};")
            lay.addWidget(lbl_spd)

        # Severity badge
        lay.addWidget(SeverityBadge(a.severity))
