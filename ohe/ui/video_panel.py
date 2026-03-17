"""
ui/video_panel.py
------------------
Live video display panel — Phase 3 enhanced.

Shows BGR numpy frames from the pipeline with:
  • proper aspect-ratio scaling
  • an overlay bar at the bottom showing frame# / FPS / stagger / height / chainage
  • mast bounding box overlay (yellow) when a mast event is detected
  • animated placeholder when idle
"""

from __future__ import annotations

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ohe.core.models import Measurement
from ohe.ui.widgets import Palette


class VideoPanel(QWidget):
    """Displays live video frames emitted by the pipeline worker."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {Palette.BG}; border-radius: 8px;"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Main display label ───────────────────────────────────────────
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._label.setMinimumSize(QSize(320, 180))
        self._label.setStyleSheet(
            f"background-color: #05080f; color: {Palette.TEXT_DIM}; "
            f"font-size: 15px; font-weight: 500; border-radius: 8px 8px 0 0;"
        )
        self._label.setText("Click  ▶ Start  to begin a new session")
        outer.addWidget(self._label, stretch=1)

        # ── Bottom info strip ────────────────────────────────────────────
        strip = QWidget()
        strip.setFixedHeight(28)
        strip.setStyleSheet(
            f"background-color: {Palette.BG_PANEL}; "
            f"border-top: 1px solid {Palette.BORDER}; "
            f"border-radius: 0 0 8px 8px;"
        )
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(10, 0, 10, 0)
        strip_lay.setSpacing(20)

        mono = QFont("Consolas", 10)

        self._lbl_frame   = self._stat_label("Frame —", mono)
        self._lbl_fps     = self._stat_label("FPS —", mono)
        self._lbl_stagger = self._stat_label("Stagger —", mono)
        self._lbl_height  = self._stat_label("Height —", mono)
        self._lbl_chainage = self._stat_label("Ch —", mono)
        self._lbl_status  = QLabel("IDLE")
        self._lbl_status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._lbl_status.setStyleSheet(
            f"color: {Palette.TEXT_DIM}; background:transparent;"
        )

        for lbl in (
            self._lbl_frame, self._lbl_fps,
            self._lbl_stagger, self._lbl_height, self._lbl_chainage,
        ):
            strip_lay.addWidget(lbl)
        strip_lay.addStretch()
        strip_lay.addWidget(self._lbl_status)
        outer.addWidget(strip)

    @staticmethod
    def _stat_label(text: str, font: QFont) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(font)
        lbl.setStyleSheet(f"color: {Palette.TEXT_DIM}; background: transparent;")
        return lbl

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_frame(
        self,
        frame: np.ndarray,
        measurement: "Measurement | None" = None,
    ) -> None:
        """Convert BGR numpy array → QPixmap, draw overlays, and display.

        Overlays drawn (when measurement is available):
          • Blue line / bbox   — detected contact wire
          • Green circle       — wire centre reference
          • Yellow bbox        — confirmed mast
        """
        display = frame.copy()

        if measurement is not None:
            # -- Contact wire overlay (blue bbox + green centre) ----------
            if measurement.wire_bbox is not None:
                x, y, w, h = measurement.wire_bbox
                cv2.rectangle(display, (x, y), (x + w, y + h), (255, 80, 0), 2)  # blue

            if measurement.wire_centre_px is not None:
                cx, cy = int(measurement.wire_centre_px[0]), int(measurement.wire_centre_px[1])
                cv2.drawMarker(
                    display, (cx, cy), (0, 220, 0),
                    cv2.MARKER_CROSS, 14, 2,
                )  # green cross

            # -- Mast overlay (yellow bbox + label) -----------------------
            if measurement.mast_event is not None and measurement.mast_event.mast_bbox is not None:
                mx, my, mw, mh = measurement.mast_event.mast_bbox
                cv2.rectangle(display, (mx, my), (mx + mw, my + mh), (0, 220, 220), 3)  # yellow
                label_y = max(my - 6, 14)
                cv2.putText(
                    display, "MAST",
                    (mx, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (0, 220, 220), 2,
                )

        h_img, w_img, ch = display.shape
        bytes_per_line = ch * w_img
        rgb    = display[:, :, ::-1].astype(np.uint8)
        qimg   = QImage(rgb.data, w_img, h_img, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(pixmap)

    def update_stats(
        self,
        frame_id: int,
        fps: float,
        stagger: float | None,
        height_m: float | None = None,
        chainage_m: float | None = None,
    ) -> None:
        """Update the bottom strip labels."""
        self._lbl_frame.setText(f"Frame {frame_id:,}")
        self._lbl_fps.setText(f"{fps:.1f} fps")

        if stagger is not None:
            col  = Palette.OK if abs(stagger) < 130 else (Palette.WARNING if abs(stagger) < 180 else Palette.CRITICAL)
            self._lbl_stagger.setText(f"Stagger {stagger:+.1f} mm")
            self._lbl_stagger.setStyleSheet(f"color: {col}; background: transparent;")
        else:
            self._lbl_stagger.setText("Stagger —")
            self._lbl_stagger.setStyleSheet(f"color: {Palette.TEXT_DIM}; background: transparent;")

        if height_m is not None:
            self._lbl_height.setText(f"H {height_m:.2f} m")
            self._lbl_height.setStyleSheet(f"color: {Palette.OK}; background: transparent;")
        else:
            self._lbl_height.setText("Height —")
            self._lbl_height.setStyleSheet(f"color: {Palette.TEXT_DIM}; background: transparent;")

        if chainage_m is not None:
            self._lbl_chainage.setText(f"Ch {chainage_m:.0f} m")
            self._lbl_chainage.setStyleSheet(f"color: {Palette.TEXT_DIM}; background: transparent;")
        else:
            self._lbl_chainage.setText("Ch —")
            self._lbl_chainage.setStyleSheet(f"color: {Palette.TEXT_DIM}; background: transparent;")

    def set_status(self, text: str, colour: str = Palette.TEXT_DIM) -> None:
        self._lbl_status.setText(text)
        self._lbl_status.setStyleSheet(f"color: {colour}; font-weight: bold; background: transparent;")

    def show_placeholder(self, message: str = "Click ▶ Start to begin") -> None:
        self._label.setPixmap(QPixmap())
        self._label.setText(message)
        self.set_status("IDLE")
