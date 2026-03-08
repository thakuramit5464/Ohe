"""
ui/event_player_dialog.py
--------------------------
EventPlayerDialog — inline OpenCV-based video player for event clips.

Plays an MP4 event clip inside a Qt dialog using a QTimer + QLabel approach.
No external media framework needed — just OpenCV.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
)

from ohe.ui.widgets import Palette

logger = logging.getLogger(__name__)


class EventPlayerDialog(QDialog):
    """
    Simple frame-by-frame video player for event MP4 clips.

    Uses ``cv2.VideoCapture`` + ``QTimer`` to drive playback inside a dialog.
    Controls: play/pause, stop (rewind), close.
    """

    def __init__(self, clip_path: str, parent=None) -> None:
        super().__init__(parent)
        self._clip_path = Path(clip_path)
        self._cap: Optional[cv2.VideoCapture] = None
        self._timer   = QTimer(self)
        self._playing = False
        self._total_frames = 0
        self._current_frame = 0

        self.setWindowTitle(f"Event Clip — {self._clip_path.name}")
        self.setMinimumSize(640, 520)
        self.setStyleSheet(f"background-color: {Palette.BG}; color: {Palette.TEXT};")

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Video display label
        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setStyleSheet("background-color: #000000;")
        self._video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._video_label, stretch=1)

        # Progress slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setStyleSheet(
            f"""
            QSlider::groove:horizontal {{ height: 4px; background: #2a4a7f; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 12px; height: 12px; background: {Palette.TEXT};
                                          border-radius: 6px; margin: -4px 0; }}
            QSlider::sub-page:horizontal {{ background: #4a8adf; border-radius: 2px; }}
            """
        )
        self._slider.sliderMoved.connect(self._seek)
        layout.addWidget(self._slider)

        # Frame counter
        self._lbl_frame = QLabel("Frame: 0 / 0")
        self._lbl_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_frame.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 10px;")
        layout.addWidget(self._lbl_frame)

        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        self._btn_play = QPushButton("▶  Play")
        self._btn_stop = QPushButton("■  Stop")
        self._btn_close = QPushButton("Close")

        for btn in (self._btn_play, self._btn_stop, self._btn_close):
            btn.setFont(QFont("Segoe UI", 10))
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {Palette.BG_CARD};
                    color: {Palette.TEXT};
                    border: 1px solid #2a4a7f;
                    border-radius: 5px;
                    padding: 5px 16px;
                }}
                QPushButton:hover {{ background-color: #2a4a7f; }}
                """
            )
            ctrl_row.addWidget(btn)

        self._btn_play.clicked.connect(self._toggle_play)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_close.clicked.connect(self.accept)
        layout.addLayout(ctrl_row)

        # Timer for frame playback
        self._timer.timeout.connect(self._next_frame)

        # Load clip
        self._open_clip()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open_clip(self) -> None:
        if not self._clip_path.exists():
            self._video_label.setText(f"Clip not found:\n{self._clip_path}")
            return
        self._cap = cv2.VideoCapture(str(self._clip_path))
        if not self._cap.isOpened():
            self._video_label.setText("Could not open clip.")
            return
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._timer.setInterval(max(1, int(1000 / fps)))
        self._slider.setRange(0, max(0, self._total_frames - 1))
        # Show first frame
        self._read_and_show()

    def _toggle_play(self) -> None:
        if self._playing:
            self._timer.stop()
            self._playing = False
            self._btn_play.setText("▶  Play")
        else:
            if self._current_frame >= self._total_frames - 1:
                self._stop()  # rewind on replay
            self._timer.start()
            self._playing = True
            self._btn_play.setText("⏸  Pause")

    def _stop(self) -> None:
        self._timer.stop()
        self._playing = False
        self._btn_play.setText("▶  Play")
        if self._cap:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._current_frame = 0
            self._slider.setValue(0)
            self._read_and_show()

    def _next_frame(self) -> None:
        if self._cap is None:
            return
        self._read_and_show()
        self._current_frame += 1
        self._slider.setValue(self._current_frame)
        self._lbl_frame.setText(f"Frame: {self._current_frame} / {self._total_frames}")
        if self._current_frame >= self._total_frames:
            self._stop()

    def _read_and_show(self) -> None:
        if self._cap is None:
            return
        ret, frame = self._cap.read()
        if not ret:
            return
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(
            self._video_label.width(),
            self._video_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video_label.setPixmap(pix)

    def _seek(self, pos: int) -> None:
        if self._cap:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            self._current_frame = pos
            self._lbl_frame.setText(f"Frame: {pos} / {self._total_frames}")
            self._read_and_show()

    def closeEvent(self, event) -> None:
        self._timer.stop()
        if self._cap:
            self._cap.release()
        event.accept()
