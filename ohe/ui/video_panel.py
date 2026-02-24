"""
ui/video_panel.py
------------------
Live video display panel using QLabel + QImage.

Receives BGR numpy frames from PipelineWorker.new_frame signal and
renders them at the correct aspect ratio inside the panel.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ohe.ui.widgets import Palette


class VideoPanel(QWidget):
    """Displays live video frames emitted by the pipeline worker."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: #000; border-radius: 6px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("No video loaded")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._label.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 16px;")
        self._label.setMinimumSize(QSize(320, 180))
        lay.addWidget(self._label)

    def update_frame(self, frame: np.ndarray) -> None:
        """Convert BGR numpy array → QPixmap and display it."""
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        # OpenCV BGR → RGB for Qt
        rgb = frame[:, :, ::-1].astype(np.uint8)
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        # Scale to label size preserving aspect ratio
        pixmap = QPixmap.fromImage(qimg).scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(pixmap)

    def show_placeholder(self, message: str = "Select a video file to begin") -> None:
        self._label.setPixmap(QPixmap())
        self._label.setText(message)
