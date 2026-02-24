"""
ui/anomaly_panel.py
--------------------
Scrollable anomaly event log.

Each entry shows: timestamp · frame · type · severity · value
Rows are colour-coded: WARNING = amber, CRITICAL = red.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
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

_MAX_ROWS = 500   # keep at most this many anomaly rows visible


class AnomalyPanel(QWidget):
    """Scrollable anomaly event log with colour-coded rows."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Palette.BG_PANEL}; border-radius: 6px;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QLabel("  Anomaly Log")
        header.setFixedHeight(28)
        header.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT}; "
            f"font-weight: bold; font-size: 12px; border-radius: 6px 6px 0 0;"
        )
        outer.addWidget(header)

        # Scrollable content
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("border: none;")

        self._content = QWidget()
        self._content.setStyleSheet(f"background-color: {Palette.BG_PANEL};")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._layout.addStretch()
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

        self._row_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_anomaly(self, a: Anomaly) -> None:
        """Prepend a new anomaly row at the top of the list."""
        row = _AnomalyRow(a)
        # Insert before the stretch (last item)
        self._layout.insertWidget(0, row)
        self._row_count += 1

        # Prune old rows
        if self._row_count > _MAX_ROWS:
            item = self._layout.takeAt(self._layout.count() - 2)  # before stretch
            if item and item.widget():
                item.widget().deleteLater()
            self._row_count -= 1

    def clear(self) -> None:
        while self._layout.count() > 1:  # keep stretch
            item = self._layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._row_count = 0

    @property
    def count(self) -> int:
        return self._row_count


class _AnomalyRow(QWidget):
    """Single anomaly row widget."""

    _COLOURS = {
        "WARNING":  (Palette.WARNING,  "#1a1200"),
        "CRITICAL": (Palette.CRITICAL, "#1a0000"),
    }

    def __init__(self, a: Anomaly, parent=None) -> None:
        super().__init__(parent)
        fg, bg = self._COLOURS.get(a.severity, (Palette.TEXT, Palette.BG_CARD))

        self.setFixedHeight(26)
        self.setStyleSheet(f"background-color: {bg}; border-radius: 3px;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(8)

        # Frame number
        lbl_frame = QLabel(f"#{a.frame_id:05d}")
        lbl_frame.setFixedWidth(60)
        lbl_frame.setFont(QFont("Consolas", 10))
        lbl_frame.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        lay.addWidget(lbl_frame)

        # Anomaly type
        lbl_type = QLabel(a.anomaly_type)
        lbl_type.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_type.setStyleSheet(f"color: {fg};")
        lbl_type.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(lbl_type)

        # Value
        lbl_val = QLabel(f"{a.value:.2f}")
        lbl_val.setFixedWidth(56)
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_val.setFont(QFont("Consolas", 10))
        lbl_val.setStyleSheet(f"color: {fg};")
        lay.addWidget(lbl_val)

        # Severity badge
        badge = SeverityBadge(a.severity)
        lay.addWidget(badge)
