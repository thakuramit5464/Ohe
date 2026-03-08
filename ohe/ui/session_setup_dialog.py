"""
ui/session_setup_dialog.py
---------------------------
SessionSetupDialog — shown before each processing run.

Collects:
  1. Track Name / Test Name
  2. Input Mode: Video File | Live Camera (with camera index selector)
  3. GPS Mode:   Simulated | Live (live is shown greyed-out with "coming soon")
  4. Speed Mode: Simulated | Live (same)
  5. Video file path (shown only in Video File mode)

Returns a :class:`SessionSetup` dataclass on accept().
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ohe.ui.widgets import Palette

_TRACK_RE = re.compile(r"^[\w\-\.]{1,64}$")  # alphanumeric, hyphen, dot, underscore


@dataclass
class SessionSetup:
    """All parameters collected by the session setup dialog."""
    track_name:   str
    input_mode:   str          # "video_file" | "camera"
    video_path:   str          # empty when camera mode
    camera_index: int
    gps_mode:     str          # "simulated" | "live"
    speed_mode:   str          # "simulated" | "live"


class SessionSetupDialog(QDialog):
    """Pre-processing session setup dialog."""

    def __init__(self, parent=None, initial_video_path: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("New Session Setup")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"background-color: {Palette.BG}; color: {Palette.TEXT};")

        self._result: Optional[SessionSetup] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # --- Title ---
        title = QLabel("Configure New Processing Session")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Palette.TEXT};")
        layout.addWidget(title)

        sub = QLabel(
            "Enter a track or test name to organise all generated data. "
            "Then choose input, GPS, and speed sources."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 11px;")
        layout.addWidget(sub)

        # ---- 1. Track Name ------------------------------------------------
        track_box = self._make_group("1  Track / Test Name")
        track_form = QFormLayout()
        track_form.setContentsMargins(8, 8, 8, 8)

        self._track_input = QLineEdit()
        self._track_input.setPlaceholderText("e.g. Nairobi_Test_Run_01")
        self._track_input.setStyleSheet(self._input_style())
        self._track_input.setMaxLength(64)
        track_form.addRow(QLabel("Track Name:", styleSheet=f"color:{Palette.TEXT_DIM};"),
                          self._track_input)

        hint = QLabel("Letters, digits, hyphens, dots and underscores only. Max 64 chars.")
        hint.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 10px;")
        track_form.addRow("", hint)
        track_box.setLayout(track_form)
        layout.addWidget(track_box)

        # ---- 2. Input Mode ------------------------------------------------
        input_box   = self._make_group("2  Input Source")
        input_lay   = QVBoxLayout()
        input_lay.setContentsMargins(8, 8, 8, 8)
        input_lay.setSpacing(6)

        self._rb_video  = QRadioButton("Video File")
        self._rb_camera = QRadioButton("Live Camera")
        self._rb_video.setChecked(True)
        for rb in (self._rb_video, self._rb_camera):
            rb.setStyleSheet(f"color: {Palette.TEXT};")

        self._input_group = QButtonGroup(self)
        self._input_group.addButton(self._rb_video,  0)
        self._input_group.addButton(self._rb_camera, 1)

        # Video file row
        video_row = QHBoxLayout()
        self._video_path_edit = QLineEdit(initial_video_path)
        self._video_path_edit.setPlaceholderText("Select a video file…")
        self._video_path_edit.setReadOnly(True)
        self._video_path_edit.setStyleSheet(self._input_style())
        btn_browse = QPushButton("Browse…")
        btn_browse.setStyleSheet(self._btn_style())
        btn_browse.clicked.connect(self._browse_video)
        video_row.addWidget(self._video_path_edit, stretch=3)
        video_row.addWidget(btn_browse)

        # Camera index row
        camera_row = QHBoxLayout()
        cam_lbl = QLabel("Camera index:")
        cam_lbl.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        self._camera_spin = QSpinBox()
        self._camera_spin.setRange(0, 9)
        self._camera_spin.setValue(0)
        self._camera_spin.setStyleSheet(self._input_style())
        self._camera_spin.setEnabled(False)
        camera_row.addWidget(cam_lbl)
        camera_row.addWidget(self._camera_spin)
        camera_row.addStretch()

        input_lay.addWidget(self._rb_video)
        input_lay.addLayout(video_row)
        input_lay.addWidget(self._rb_camera)
        input_lay.addLayout(camera_row)
        input_box.setLayout(input_lay)
        layout.addWidget(input_box)

        self._rb_video.toggled.connect(self._on_input_mode_changed)
        self._rb_camera.toggled.connect(self._on_input_mode_changed)

        # ---- 3. GPS Mode --------------------------------------------------
        gps_box = self._make_group("3  GPS Source")
        gps_lay = QVBoxLayout()
        gps_lay.setContentsMargins(8, 8, 8, 8)
        gps_lay.setSpacing(4)

        self._rb_gps_sim  = QRadioButton("Simulated GPS (coordinates generated from origin + speed)")
        self._rb_gps_live = QRadioButton("Live GPS  (not yet connected — coming soon)")
        self._rb_gps_sim.setChecked(True)
        self._rb_gps_live.setEnabled(False)
        for rb in (self._rb_gps_sim, self._rb_gps_live):
            rb.setStyleSheet(f"color: {Palette.TEXT};")
        self._rb_gps_live.setStyleSheet(f"color: {Palette.TEXT_DIM};")

        self._gps_group = QButtonGroup(self)
        self._gps_group.addButton(self._rb_gps_sim,  0)
        self._gps_group.addButton(self._rb_gps_live, 1)

        gps_note = QLabel("  Edit config/default.yaml → geo.origin_latitude/longitude to change the simulation start point.")
        gps_note.setWordWrap(True)
        gps_note.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 10px;")

        gps_lay.addWidget(self._rb_gps_sim)
        gps_lay.addWidget(self._rb_gps_live)
        gps_lay.addWidget(gps_note)
        gps_box.setLayout(gps_lay)
        layout.addWidget(gps_box)

        # ---- 4. Speed Mode ------------------------------------------------
        spd_box = self._make_group("4  Vehicle Speed Source")
        spd_lay = QVBoxLayout()
        spd_lay.setContentsMargins(8, 8, 8, 8)
        spd_lay.setSpacing(4)

        self._rb_spd_sim  = QRadioButton("Simulated Speed (60 km/h ±5 km/h jitter)")
        self._rb_spd_live = QRadioButton("Live Speed via telemetry / CAN bus  (not yet connected — coming soon)")
        self._rb_spd_sim.setChecked(True)
        self._rb_spd_live.setEnabled(False)
        for rb in (self._rb_spd_sim, self._rb_spd_live):
            rb.setStyleSheet(f"color: {Palette.TEXT};")
        self._rb_spd_live.setStyleSheet(f"color: {Palette.TEXT_DIM};")

        self._spd_group = QButtonGroup(self)
        self._spd_group.addButton(self._rb_spd_sim,  0)
        self._spd_group.addButton(self._rb_spd_live, 1)

        spd_note = QLabel("  Edit config/default.yaml → speed.simulated_base_kmh to change the base speed.")
        spd_note.setWordWrap(True)
        spd_note.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 10px;")

        spd_lay.addWidget(self._rb_spd_sim)
        spd_lay.addWidget(self._rb_spd_live)
        spd_lay.addWidget(spd_note)
        spd_box.setLayout(spd_lay)
        layout.addWidget(spd_box)

        # ---- Buttons ------------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_start  = QPushButton("▶  Start Session")
        self._btn_cancel = QPushButton("Cancel")
        for btn in (self._btn_start, self._btn_cancel):
            btn.setFont(QFont("Segoe UI", 10))
            btn.setStyleSheet(self._btn_style())
        self._btn_start.setStyleSheet(
            self._btn_style().replace(Palette.BG_CARD, "#1a3a6a") + "font-weight: bold;"
        )
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_cancel)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Result access
    # ------------------------------------------------------------------

    @property
    def session_setup(self) -> Optional[SessionSetup]:
        return self._result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_group(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet(
            f"QGroupBox {{ border: 1px solid #2a4a7f; border-radius: 5px; "
            f"color: {Palette.TEXT}; margin-top: 10px; font-weight: bold; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}"
        )
        return box

    @staticmethod
    def _input_style() -> str:
        return (
            f"background-color: {Palette.BG_PANEL}; color: {Palette.TEXT}; "
            f"border: 1px solid #2a4a7f; border-radius: 4px; padding: 4px 8px;"
        )

    @staticmethod
    def _btn_style() -> str:
        return (
            f"QPushButton {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT}; "
            f"border: 1px solid #2a4a7f; border-radius: 5px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: #2a4a7f; }}"
        )

    def _browse_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "",
            "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*)",
        )
        if path:
            self._video_path_edit.setText(path)

    def _on_input_mode_changed(self) -> None:
        is_video = self._rb_video.isChecked()
        self._video_path_edit.setEnabled(is_video)
        self._camera_spin.setEnabled(not is_video)

    # ------------------------------------------------------------------
    # Validation + accept
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        track_name = self._track_input.text().strip()

        if not track_name:
            QMessageBox.warning(self, "Track Name Required",
                                "Please enter a track / test name before starting.")
            self._track_input.setFocus()
            return

        if not _TRACK_RE.match(track_name):
            QMessageBox.warning(
                self, "Invalid Track Name",
                "Track name may only contain letters, digits, hyphens, dots and underscores (max 64 chars)."
            )
            self._track_input.setFocus()
            return

        input_mode = "video_file" if self._rb_video.isChecked() else "camera"

        if input_mode == "video_file":
            video_path = self._video_path_edit.text().strip()
            if not video_path:
                QMessageBox.warning(self, "No Video Selected",
                                    "Please select a video file or switch to Live Camera mode.")
                return
            if not Path(video_path).exists():
                QMessageBox.warning(self, "File Not Found",
                                    f"Video file not found:\n{video_path}")
                return
        else:
            video_path = ""

        self._result = SessionSetup(
            track_name=track_name,
            input_mode=input_mode,
            video_path=video_path,
            camera_index=self._camera_spin.value(),
            gps_mode="simulated" if self._rb_gps_sim.isChecked() else "live",
            speed_mode="simulated" if self._rb_spd_sim.isChecked() else "live",
        )
        self.accept()
