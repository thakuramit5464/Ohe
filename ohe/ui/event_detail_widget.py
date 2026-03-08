"""
ui/event_detail_widget.py
--------------------------
EventDetailWidget — shows full details for a single selected Anomaly.
Includes a "Play Clip" button that launches EventPlayerDialog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ohe.core.models import Anomaly
from ohe.ui.widgets import Palette


class EventDetailWidget(QWidget):
    """Displays all metadata fields for the currently selected event."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Palette.BG_PANEL}; border-radius: 6px;")
        self.setMaximumWidth(360)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Header
        header = QLabel("Event Details")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {Palette.TEXT};")
        outer.addWidget(header)

        # Form fields
        self._box = QGroupBox()
        self._box.setStyleSheet(
            f"QGroupBox {{ border: 1px solid #2a4a7f; border-radius: 5px; color: {Palette.TEXT_DIM}; }}"
        )
        form = QFormLayout(self._box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)

        def _val_label() -> QLabel:
            lbl = QLabel("—")
            lbl.setStyleSheet(f"color: {Palette.TEXT}; font-size: 11px;")
            lbl.setWordWrap(True)
            return lbl

        def _key_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 10px;")
            return lbl

        self._lbl_id       = _val_label()
        self._lbl_type     = _val_label()
        self._lbl_severity = _val_label()
        self._lbl_value    = _val_label()
        self._lbl_frame    = _val_label()
        self._lbl_ts       = _val_label()
        self._lbl_lat      = _val_label()
        self._lbl_lon      = _val_label()
        self._lbl_speed    = _val_label()
        self._lbl_clip     = _val_label()
        self._lbl_model    = _val_label()

        form.addRow(_key_label("Frame #:"),       self._lbl_frame)
        form.addRow(_key_label("Timestamp:"),     self._lbl_ts)
        form.addRow(_key_label("Type:"),          self._lbl_type)
        form.addRow(_key_label("Severity:"),      self._lbl_severity)
        form.addRow(_key_label("Value:"),         self._lbl_value)
        form.addRow(_key_label("Latitude:"),      self._lbl_lat)
        form.addRow(_key_label("Longitude:"),     self._lbl_lon)
        form.addRow(_key_label("Speed km/h:"),    self._lbl_speed)
        form.addRow(_key_label("Video Clip:"),    self._lbl_clip)
        form.addRow(_key_label("Model:"),         self._lbl_model)
        outer.addWidget(self._box)

        # Play clip button
        self._btn_play = QPushButton("▶  Play Event Clip")
        self._btn_play.setEnabled(False)
        self._btn_play.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #1a3a6a;
                color: {Palette.TEXT};
                border: 1px solid #2a4a7f;
                border-radius: 5px;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:hover   {{ background-color: #2a5aaa; }}
            QPushButton:disabled {{ color: {Palette.TEXT_DIM}; }}
            """
        )
        self._btn_play.clicked.connect(self._on_play)
        outer.addWidget(self._btn_play)
        outer.addStretch()

        self._current_anomaly: Optional[Anomaly] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_event(self, anomaly: Anomaly) -> None:
        """Populate all fields from the given Anomaly."""
        self._current_anomaly = anomaly

        import datetime
        ts_ms = anomaly.timestamp_ms
        if ts_ms:
            dt = datetime.datetime.utcfromtimestamp(ts_ms / 1000.0)
            ts_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            ts_str = "—"

        severity_colour = Palette.CRITICAL if anomaly.severity == "CRITICAL" else Palette.WARNING

        self._lbl_frame.setText(f"{anomaly.frame_id:,}")
        self._lbl_ts.setText(ts_str)
        self._lbl_type.setText(anomaly.anomaly_type)
        self._lbl_severity.setText(anomaly.severity)
        self._lbl_severity.setStyleSheet(f"color: {severity_colour}; font-weight: bold;")
        self._lbl_value.setText(f"{anomaly.value:.3f}")
        self._lbl_lat.setText(f"{anomaly.latitude:.6f}" if anomaly.latitude  is not None else "—")
        self._lbl_lon.setText(f"{anomaly.longitude:.6f}" if anomaly.longitude is not None else "—")
        self._lbl_speed.setText(f"{anomaly.speed_kmh:.1f}" if anomaly.speed_kmh is not None else "—")
        self._lbl_clip.setText(anomaly.video_clip or "—")
        self._lbl_model.setText(anomaly.model_version or "—")

        has_clip = bool(anomaly.video_clip and Path(anomaly.video_clip).exists())
        self._btn_play.setEnabled(has_clip)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_play(self) -> None:
        if self._current_anomaly and self._current_anomaly.video_clip:
            from ohe.ui.event_player_dialog import EventPlayerDialog
            dlg = EventPlayerDialog(self._current_anomaly.video_clip, parent=self)
            dlg.exec()
