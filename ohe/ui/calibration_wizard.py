"""
ui/calibration_wizard.py
-------------------------
Step-by-step calibration wizard.

Step 1 — Grab a reference frame from the video.
Step 2 — User clicks TWO points on a known real-world distance.
Step 3 — User enters the real distance (mm) between those points.
Step 4 — Wizard calculates px_per_mm and saves calibration.json.

Also captures the track centre X from a click on the contact wire
position so the stagger sign is correct.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QImage, QMouseEvent, QPixmap, QPainter, QPen, QColor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from ohe.processing.calibration import CalibrationModel
from ohe.ui.widgets import Palette


class CalibrationWizard(QWizard):
    """Guided wizard to compute px/mm scale from a reference frame."""

    def __init__(self, video_path: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OHE Calibration Wizard")
        self.setMinimumSize(700, 550)
        self.setStyleSheet(f"background-color: {Palette.BG_DARK}; color: {Palette.TEXT};")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

        self._video_path = video_path
        self._frame: Optional[np.ndarray] = None
        self._points: list[QPoint] = []
        self.result_calibration: Optional[CalibrationModel] = None

        self._page_intro  = _IntroPage(self)
        self._page_frame  = _FrameGrabPage(self)
        self._page_points = _PointPickPage(self)
        self._page_result = _ResultPage(self)

        self.addPage(self._page_intro)
        self.addPage(self._page_frame)
        self.addPage(self._page_points)
        self.addPage(self._page_result)

    def set_frame(self, frame: np.ndarray) -> None:
        self._frame = frame
        self._page_points.load_frame(frame)

    def set_points(self, pts: list[QPoint]) -> None:
        self._points = pts

    def compute_and_show(self, real_mm: float) -> None:
        if len(self._points) < 2 or self._frame is None:
            return
        p1, p2 = self._points[0], self._points[1]
        pixel_dist = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        px_per_mm = pixel_dist / max(real_mm, 0.001)
        centre_x = self._frame.shape[1] // 2

        self.result_calibration = CalibrationModel(
            px_per_mm=round(px_per_mm, 4),
            track_centre_x_px=centre_x,
            image_width_px=self._frame.shape[1],
            image_height_px=self._frame.shape[0],
        )
        self._page_result.show_result(px_per_mm, pixel_dist, real_mm, centre_x)

    def save_calibration(self, path: str | Path = "config/calibration.json") -> None:
        if self.result_calibration:
            self.result_calibration.save(path)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

class _IntroPage(QWizardPage):
    def __init__(self, parent):
        super().__init__(parent)
        self.setTitle("Welcome to the Calibration Wizard")
        lay = QVBoxLayout(self)
        intro = QLabel(
            "This wizard will help you compute the pixel-per-mm scale\n"
            "needed for accurate stagger and diameter measurements.\n\n"
            "You will need:\n"
            "  • A video frame containing a known reference distance\n"
            "    (e.g. a ruler, pantograph span, or catenary pole spacing)\n"
            "  • The real-world distance in millimetres between two visible points\n\n"
            "Click Next to begin."
        )
        intro.setStyleSheet(f"color: {Palette.TEXT}; font-size: 13px; line-height: 1.6;")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        lay.addStretch()


class _FrameGrabPage(QWizardPage):
    def __init__(self, wizard: CalibrationWizard):
        super().__init__(wizard)
        self._wiz = wizard
        self.setTitle("Step 1 — Grab a Reference Frame")

        lay = QVBoxLayout(self)
        btn = QPushButton("Load from video file…")
        btn.clicked.connect(self._grab)
        lay.addWidget(btn)

        self._preview = QLabel("No frame loaded")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(200)
        self._preview.setStyleSheet(f"background: #000; border: 1px solid #2a4a7f;")
        lay.addWidget(self._preview)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        lay.addWidget(self._status)
        self._frame_loaded = False

    def _grab(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "", "Video Files (*.mp4 *.avi *.mkv);;All Files (*)"
        )
        if not path:
            return
        cap = cv2.VideoCapture(path)
        # Grab frame at 10% of video
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total // 10))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            self._status.setText("Could not read frame from video.")
            return
        self._wiz.set_frame(frame)
        rgb = frame[:, :, ::-1].astype(np.uint8)
        h, w, c = rgb.shape
        qimg = QImage(rgb.data, w, h, c * w, QImage.Format.Format_RGB888)
        self._preview.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._status.setText(f"Frame loaded: {w}x{h}")
        self._frame_loaded = True
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._frame_loaded


class _PointPickPage(QWizardPage):
    def __init__(self, wizard: CalibrationWizard):
        super().__init__(wizard)
        self._wiz = wizard
        self.setTitle("Step 2 — Click Two Reference Points")

        lay = QVBoxLayout(self)
        info = QLabel("Click exactly TWO points on the image that are a known distance apart.")
        info.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        lay.addWidget(info)

        self._canvas = _ClickableLabel()
        self._canvas.point_clicked.connect(self._on_point)
        self._canvas.setMinimumHeight(300)
        lay.addWidget(self._canvas)

        controls = QHBoxLayout()
        self._dist_spin = QDoubleSpinBox()
        self._dist_spin.setRange(1, 10000)
        self._dist_spin.setValue(1000)
        self._dist_spin.setSuffix(" mm")
        self._dist_spin.setStyleSheet(f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT};")
        controls.addWidget(QLabel("Real-world distance:"))
        controls.addWidget(self._dist_spin)

        reset_btn = QPushButton("Reset points")
        reset_btn.clicked.connect(self._reset)
        controls.addWidget(reset_btn)
        lay.addLayout(controls)

        self._status = QLabel("Click 2 points on the image")
        self._status.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        lay.addWidget(self._status)

    def load_frame(self, frame: np.ndarray) -> None:
        rgb = frame[:, :, ::-1].astype(np.uint8)
        h, w, c = rgb.shape
        qimg = QImage(rgb.data, w, h, c * w, QImage.Format.Format_RGB888)
        self._canvas.set_image(QPixmap.fromImage(qimg))
        self._pts: list[QPoint] = []

    def _on_point(self, pt: QPoint) -> None:
        if len(self._pts) >= 2:
            return
        self._pts.append(pt)
        self._canvas.add_marker(pt)
        if len(self._pts) == 2:
            self._status.setText("2 points selected. Click Next to compute.")
            self._wiz.set_points(self._pts)
            real_mm = self._dist_spin.value()
            self._wiz.compute_and_show(real_mm)
            self.completeChanged.emit()
        else:
            self._status.setText(f"Point 1 set. Click point 2.")

    def _reset(self) -> None:
        self._pts = []
        self._canvas.clear_markers()
        self._status.setText("Click 2 points on the image")
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return len(getattr(self, "_pts", [])) == 2


class _ResultPage(QWizardPage):
    def __init__(self, wizard: CalibrationWizard):
        super().__init__(wizard)
        self._wiz = wizard
        self.setTitle("Step 3 — Review & Save")

        lay = QVBoxLayout(self)
        self._result_lbl = QLabel("Calibration result will appear here.")
        self._result_lbl.setStyleSheet(f"color: {Palette.TEXT}; font-size: 14px;")
        self._result_lbl.setWordWrap(True)
        lay.addWidget(self._result_lbl)

        save_btn = QPushButton("Save calibration.json")
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)
        lay.addStretch()

    def show_result(self, px_per_mm, pixel_dist, real_mm, centre_x):
        self._result_lbl.setText(
            f"Computed calibration:\n\n"
            f"  Pixel distance : {pixel_dist:.1f} px\n"
            f"  Real distance  : {real_mm:.1f} mm\n"
            f"  px / mm        : {px_per_mm:.4f}\n"
            f"  Track centre X : {centre_x} px  (auto = frame centre)\n\n"
            f"Click 'Save calibration.json' to persist."
        )

    def _save(self) -> None:
        self._wiz.save_calibration()
        QMessageBox.information(self, "Saved", "calibration.json updated.")


# ---------------------------------------------------------------------------
# Clickable image canvas
# ---------------------------------------------------------------------------

from PyQt6.QtCore import pyqtSignal


class _ClickableLabel(QLabel):
    """QLabel that emits clicked image coordinates."""
    point_clicked = pyqtSignal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_orig: Optional[QPixmap] = None
        self._markers: list[QPoint] = []
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #000;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, pixmap: QPixmap) -> None:
        self._pixmap_orig = pixmap
        self._markers = []
        self._redraw()

    def add_marker(self, pt: QPoint) -> None:
        self._markers.append(pt)
        self._redraw()

    def clear_markers(self) -> None:
        self._markers = []
        self._redraw()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton and self._pixmap_orig:
            # Map label coords → original image coords
            label_sz = self.size()
            pm = self._pixmap_orig
            scaled = pm.scaled(label_sz, Qt.AspectRatioMode.KeepAspectRatio)
            offset_x = (label_sz.width()  - scaled.width())  // 2
            offset_y = (label_sz.height() - scaled.height()) // 2
            img_x = int((ev.position().x() - offset_x) / scaled.width()  * pm.width())
            img_y = int((ev.position().y() - offset_y) / scaled.height() * pm.height())
            self.point_clicked.emit(QPoint(img_x, img_y))

    def _redraw(self) -> None:
        if not self._pixmap_orig:
            return
        pm = self._pixmap_orig.copy()
        painter = QPainter(pm)
        pen = QPen(QColor(Palette.ACCENT))
        pen.setWidth(3)
        painter.setPen(pen)
        for i, pt in enumerate(self._markers):
            painter.drawEllipse(pt, 8, 8)
            painter.drawText(pt.x() + 12, pt.y() - 6, f"P{i+1}")
        if len(self._markers) == 2:
            painter.drawLine(self._markers[0], self._markers[1])
        painter.end()
        self.setPixmap(pm.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation))
