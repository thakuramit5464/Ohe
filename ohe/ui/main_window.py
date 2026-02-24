"""
ui/main_window.py
------------------
OHE GUI – Main Window

Layout
------
┌─────────────────────────────────────────────────────┐
│  Toolbar: [Open Video] [Start] [Stop] [Export]      │
├──────────────────────┬──────────────────────────────┤
│                      │  MetricCards                 │
│    VideoPanel        │  (Stagger / Diameter / Det%) │
│                      ├──────────────────────────────┤
│                      │  PlotPanel                   │
│                      │  (Stagger + Diameter traces) │
├──────────────────────┴──────────────────────────────┤
│  AnomalyPanel (scrollable log)                      │
├─────────────────────────────────────────────────────┤
│  StatusBar: Frame · FPS · Session path              │
└─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ohe.core.config import load_config
from ohe.core.models import Anomaly, Measurement
from ohe.logging_.export import SessionExporter
from ohe.processing.calibration import CalibrationModel
from ohe.ui.anomaly_panel import AnomalyPanel
from ohe.ui.plot_panel import PlotPanel
from ohe.ui.pipeline_worker import PipelineWorker
from ohe.ui.video_panel import VideoPanel
from ohe.ui.widgets import MetricCard, Palette


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OHE — Stagger & Wire Diameter Measurement")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._cfg = load_config()
        self._cal = CalibrationModel.from_json(
            self._cfg.calibration_path(),
            fallback_px_per_mm=self._cfg.calibration.fallback_px_per_mm,
        )
        self._worker: PipelineWorker | None = None
        self._video_path: str | None = None

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._act_open = QAction("Open Video", self)
        self._act_open.setToolTip("Select a video file to process")
        self._act_open.triggered.connect(self._on_open)
        tb.addAction(self._act_open)

        tb.addSeparator()

        self._act_start = QAction("Start", self)
        self._act_start.setToolTip("Start processing")
        self._act_start.triggered.connect(self._on_start)
        self._act_start.setEnabled(False)
        tb.addAction(self._act_start)

        self._act_stop = QAction("Stop", self)
        self._act_stop.setToolTip("Stop processing")
        self._act_stop.triggered.connect(self._on_stop)
        self._act_stop.setEnabled(False)
        tb.addAction(self._act_stop)

        tb.addSeparator()

        self._act_export = QAction("Export Session", self)
        self._act_export.setToolTip("Export last session to CSV + JSON")
        self._act_export.triggered.connect(self._on_export)
        self._act_export.setEnabled(False)
        tb.addAction(self._act_export)

    def _build_central(self) -> None:
        # Outer vertical splitter: top (video+info) | bottom (anomaly log)
        outer_split = QSplitter(Qt.Orientation.Vertical)
        outer_split.setHandleWidth(4)

        # ---- Top section ----
        top = QWidget()
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(4, 4, 4, 4)
        top_lay.setSpacing(6)

        # Left: video
        self._video_panel = VideoPanel()
        self._video_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        top_lay.addWidget(self._video_panel, stretch=3)

        # Right: metric cards + plot
        right = QWidget()
        right.setFixedWidth(420)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)

        # Metric cards row
        cards_box = QGroupBox("Live Measurements")
        cards_box.setStyleSheet(f"QGroupBox {{ border: 1px solid #2a4a7f; border-radius:6px; color: {Palette.TEXT_DIM}; }}")
        cards_box.setFixedHeight(100)
        cards_lay = QHBoxLayout(cards_box)
        cards_lay.setContentsMargins(6, 14, 6, 6)

        self._card_stagger  = MetricCard("Stagger",  "mm")
        self._card_diameter = MetricCard("Diameter", "mm")
        self._card_det_pct  = MetricCard("Detected",  "%")
        for c in (self._card_stagger, self._card_diameter, self._card_det_pct):
            cards_lay.addWidget(c)
        right_lay.addWidget(cards_box)

        # Plot panel
        self._plot_panel = PlotPanel()
        right_lay.addWidget(self._plot_panel, stretch=1)

        top_lay.addWidget(right, stretch=0)
        outer_split.addWidget(top)

        # ---- Bottom: anomaly log ----
        self._anomaly_panel = AnomalyPanel()
        self._anomaly_panel.setFixedHeight(180)
        outer_split.addWidget(self._anomaly_panel)

        outer_split.setStretchFactor(0, 4)
        outer_split.setStretchFactor(1, 1)

        self.setCentralWidget(outer_split)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        self._lbl_file   = QLabel("No file")
        self._lbl_frame  = QLabel("Frame: —")
        self._lbl_fps    = QLabel("FPS: —")
        self._lbl_anoms  = QLabel("Anomalies: 0")

        for lbl in (self._lbl_file, self._lbl_frame, self._lbl_fps, self._lbl_anoms):
            lbl.setStyleSheet(f"color: {Palette.TEXT_DIM}; padding: 0 10px;")
            sb.addWidget(lbl)

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "", "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*)"
        )
        if not path:
            return
        self._video_path = path
        self._lbl_file.setText(Path(path).name)
        self._act_start.setEnabled(True)
        self._video_panel.show_placeholder(f"Ready: {Path(path).name}")
        self._plot_panel.clear()
        self._anomaly_panel.clear()

    def _on_start(self) -> None:
        if not self._video_path:
            return

        self._act_start.setEnabled(False)
        self._act_stop.setEnabled(True)
        self._act_export.setEnabled(False)
        self._plot_panel.clear()
        self._anomaly_panel.clear()

        self._worker = PipelineWorker(self._video_path, self._cfg, self._cal, parent=self)
        self._worker.new_frame.connect(self._on_frame)
        self._worker.new_measurement.connect(self._on_measurement)
        self._worker.new_anomaly.connect(self._on_anomaly)
        self._worker.stats_update.connect(self._on_stats)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker:
            self._worker.request_stop()
        self._act_stop.setEnabled(False)

    def _on_export(self) -> None:
        sessions = sorted(
            self._cfg.session_dir_path().glob("*.sqlite"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not sessions:
            QMessageBox.information(self, "Export", "No session databases found.")
            return
        db = sessions[0]
        try:
            exp = SessionExporter(db)
            csv_path, json_path = exp.export_all()
            QMessageBox.information(
                self, "Export Complete",
                f"CSV:  {csv_path}\nJSON: {json_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    # ------------------------------------------------------------------
    # Worker signal handlers (run on UI thread via queued connection)
    # ------------------------------------------------------------------

    def _on_frame(self, frame: np.ndarray, frame_id: int, cand) -> None:
        self._video_panel.update_frame(frame)
        self._lbl_frame.setText(f"Frame: {frame_id}")

    def _on_measurement(self, m: Measurement) -> None:
        # Update metric cards
        severity_colour = Palette.TEXT
        if m.stagger_mm is not None:
            abs_s = abs(m.stagger_mm)
            severity_colour = (
                Palette.CRITICAL if abs_s >= 150 else
                Palette.WARNING  if abs_s >= 100 else
                Palette.OK
            )
            self._card_stagger.set_value(m.stagger_mm, severity_colour)
        if m.diameter_mm is not None:
            d_colour = Palette.CRITICAL if m.diameter_mm < 8 else Palette.OK
            self._card_diameter.set_value(m.diameter_mm, d_colour)
        # Update plots
        self._plot_panel.add_measurement(m)

    def _on_anomaly(self, a: Anomaly) -> None:
        self._anomaly_panel.add_anomaly(a)
        self._lbl_anoms.setText(f"Anomalies: {self._anomaly_panel.count}")

    def _on_stats(self, stats: dict) -> None:
        self._lbl_fps.setText(f"FPS: {stats['fps']:.1f}")
        det_pct = stats.get("det_pct", 0)
        self._card_det_pct.set_value(
            det_pct,
            Palette.OK if det_pct >= 60 else Palette.WARNING,
        )

    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Pipeline Error", msg)
        self._on_finished()

    def _on_finished(self) -> None:
        self._act_start.setEnabled(True)
        self._act_stop.setEnabled(False)
        self._act_export.setEnabled(True)
        self._video_panel.show_placeholder("Processing complete — open a new file or export session")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(3000)
        event.accept()
