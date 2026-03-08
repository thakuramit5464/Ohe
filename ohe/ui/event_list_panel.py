"""
ui/event_list_panel.py
-----------------------
EventListPanel — rich table of all detected events.

Columns: #, Frame, Timestamp, Type, Severity, Lat, Lon, Speed, Clip
Row doubles as a click target; selecting it emits ``event_selected(Anomaly)``.
"""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ohe.core.models import Anomaly
from ohe.ui.widgets import Palette

_COLUMNS = [
    "#", "Frame", "Timestamp", "Type", "Severity",
    "Lat", "Lon", "Speed (km/h)", "Clip",
]
_SEVERITY_BG = {
    "WARNING":  QColor("#1a1200"),
    "CRITICAL": QColor("#1a0000"),
}
_SEVERITY_FG = {
    "WARNING":  QColor(Palette.WARNING),
    "CRITICAL": QColor(Palette.CRITICAL),
}


class EventListPanel(QWidget):
    """Scrollable table showing all detected events with geolocation and clip info."""

    event_selected = pyqtSignal(object)    # emits Anomaly

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Palette.BG_PANEL}; border-radius: 6px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header label
        header = QLabel("  Events")
        header.setFixedHeight(28)
        header.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT}; "
            f"font-weight: bold; font-size: 12px; border-radius: 6px 6px 0 0;"
        )
        layout.addWidget(header)

        # Table
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setFont(QFont("Segoe UI", 9))
        self._table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {Palette.BG_PANEL};
                color: {Palette.TEXT};
                border: none;
                gridline-color: {Palette.BG_CARD};
            }}
            QTableWidget::item:selected {{
                background-color: #1a3a6a;
                color: white;
            }}
            QHeaderView::section {{
                background-color: {Palette.BG_CARD};
                color: {Palette.TEXT_DIM};
                font-size: 10px;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #2a4a7f;
            }}
            """
        )

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)   # Type column
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)   # Clip column

        self._table.currentItemChanged.connect(self._on_row_changed)
        layout.addWidget(self._table)

        self._anomalies: List[Anomaly] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_event(self, anomaly: Anomaly) -> None:
        """Prepend a new event row (newest events at top)."""
        self._anomalies.insert(0, anomaly)
        self._table.insertRow(0)

        import datetime
        ts_ms = anomaly.timestamp_ms
        if ts_ms:
            dt = datetime.datetime.utcfromtimestamp(ts_ms / 1000.0)
            ts_str = dt.strftime("%H:%M:%S")
        else:
            ts_str = "—"

        row_data = [
            str(len(self._anomalies)),
            f"{anomaly.frame_id:06d}",
            ts_str,
            anomaly.anomaly_type,
            anomaly.severity,
            f"{anomaly.latitude:.5f}"  if anomaly.latitude  is not None else "—",
            f"{anomaly.longitude:.5f}" if anomaly.longitude is not None else "—",
            f"{anomaly.speed_kmh:.1f}" if anomaly.speed_kmh is not None else "—",
            anomaly.video_clip or "pending…",
        ]

        bg = _SEVERITY_BG.get(anomaly.severity, QColor(Palette.BG_PANEL))
        fg = _SEVERITY_FG.get(anomaly.severity, QColor(Palette.TEXT))

        for col, text in enumerate(row_data):
            item = QTableWidgetItem(text)
            item.setBackground(bg)
            item.setForeground(fg if col in (3, 4) else QColor(Palette.TEXT))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setItem(0, col, item)

        self._table.setRowHeight(0, 24)

    def update_clip_path(self, clip_path: str, anomaly: Anomaly) -> None:
        """Update the Clip column for a matching anomaly row when clip is ready."""
        for row_idx, stored in enumerate(self._anomalies):
            if stored is anomaly or (
                stored.frame_id == anomaly.frame_id
                and stored.anomaly_type == anomaly.anomaly_type
            ):
                item = self._table.item(row_idx, 8)
                if item:
                    item.setText(clip_path)
                stored.video_clip = clip_path
                break

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._anomalies.clear()

    @property
    def count(self) -> int:
        return len(self._anomalies)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _on_row_changed(self, current, _previous) -> None:
        if current is None:
            return
        row = current.row()
        if 0 <= row < len(self._anomalies):
            self.event_selected.emit(self._anomalies[row])
