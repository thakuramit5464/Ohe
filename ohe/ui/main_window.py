"""
ui/main_window.py
------------------
OHE GUI – Main Window  (Phase 6 — enhanced)

Layout
------
┌─────────────────────────────────────────────────────┐
│  Toolbar: [Open Video] [Start] [Stop] [Export] [Share]│
├──────────────────────┬──────────────────────────────┤
│                      │  MetricCards                 │
│    VideoPanel        │  (Stagger / Diameter / Det%) │
│                      ├──────────────────────────────┤
│                      │  PlotPanel                   │
├──────────────────────┴──────────────────────────────┤
│  QTabWidget                                         │
│   Tab 1: AnomalyPanel (raw anomaly log)             │
│   Tab 2: EventListPanel + EventDetailWidget         │
├─────────────────────────────────────────────────────┤
│  StatusBar: Frame · FPS · Progress · Anomalies      │
└─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ohe.core.config import load_config
from ohe.core.models import Anomaly, Measurement
from ohe.logging_.export import SessionExporter
from ohe.processing.calibration import CalibrationModel
from ohe.ui.anomaly_panel import AnomalyPanel
from ohe.ui.calibration_wizard import CalibrationWizard
from ohe.ui.config_dialog import ConfigDialog
from ohe.ui.event_detail_widget import EventDetailWidget
from ohe.ui.event_list_panel import EventListPanel
from ohe.ui.plot_panel import PlotPanel
from ohe.ui.pipeline_worker import PipelineWorker
from ohe.ui.session_setup_dialog import SessionSetup, SessionSetupDialog
from ohe.ui.share_dialog import ShareDialog
from ohe.ui.video_panel import VideoPanel
from ohe.ui.widgets import MetricCard, Palette, SessionInfoBar


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OHE — Stagger & Wire Diameter Measurement")
        self.setMinimumSize(1100, 700)
        self.resize(1440, 900)

        self._cfg = load_config()
        self._cal = CalibrationModel.from_json(
            self._cfg.calibration_path(),
            fallback_px_per_mm=self._cfg.calibration.fallback_px_per_mm,
        )
        self._worker: PipelineWorker | None = None
        self._last_session_id: str = ""
        self._current_track: str = ""

        self._build_toolbar()
        self._build_menu()
        self._build_central()
        self._build_statusbar()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        menubar.setStyleSheet(
            f"background-color: {Palette.BG_PANEL}; color: {Palette.TEXT};"
        )

        # File menu
        file_menu = menubar.addMenu("File")
        act_open = file_menu.addAction("Open Video…")
        act_open.triggered.connect(self._on_open)
        file_menu.addSeparator()
        act_export_m = file_menu.addAction("Export Last Session…")
        act_export_m.triggered.connect(self._on_export)
        act_share = file_menu.addAction("Share / Export Session…")
        act_share.triggered.connect(self._on_share)
        file_menu.addSeparator()
        act_quit = file_menu.addAction("Quit")
        act_quit.triggered.connect(self.close)

        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        act_settings = tools_menu.addAction("Settings…")
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self._on_settings)

        act_calibrate = tools_menu.addAction("Calibration Wizard…")
        act_calibrate.triggered.connect(self._on_calibrate)

        tools_menu.addSeparator()
        act_debug = tools_menu.addAction("Open Debug Visualiser (CLI)")
        act_debug.triggered.connect(self._on_debug_hint)

        # Help menu
        help_menu = menubar.addMenu("Help")
        act_about = help_menu.addAction("About")
        act_about.triggered.connect(self._on_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._act_start = QAction("▶  Start", self)
        self._act_start.setToolTip("Configure and start a new processing session")
        self._act_start.triggered.connect(self._on_start)
        tb.addAction(self._act_start)

        self._act_stop = QAction("■  Stop", self)
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

        self._act_share = QAction("Share…", self)
        self._act_share.setToolTip("Share / export session data")
        self._act_share.triggered.connect(self._on_share)
        self._act_share.setEnabled(False)
        tb.addAction(self._act_share)

    def _build_central(self) -> None:
        # Outer vertical splitter: top (video+info) | bottom (tabs)
        outer_split = QSplitter(Qt.Orientation.Vertical)
        outer_split.setHandleWidth(4)

        # ---- Top: SessionInfoBar + video + right panel ----------------
        top_container = QWidget()
        top_v = QVBoxLayout(top_container)
        top_v.setContentsMargins(0, 0, 0, 0)
        top_v.setSpacing(0)

        # Session info bar
        self._session_info_bar = SessionInfoBar()
        top_v.addWidget(self._session_info_bar)

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
        top_v.addWidget(top)
        outer_split.addWidget(top_container)

        # ---- Bottom: tabbed panel ----
        self._tab_widget = QTabWidget()

        # Tab 1: Anomaly log
        self._anomaly_panel = AnomalyPanel()
        self._tab_widget.addTab(self._anomaly_panel, "⚡  Anomaly Log")

        # Tab 2: Events (list + detail side by side)
        events_widget = QWidget()
        events_lay = QHBoxLayout(events_widget)
        events_lay.setContentsMargins(4, 4, 4, 4)
        events_lay.setSpacing(6)

        self._event_list_panel  = EventListPanel()
        self._event_detail_widget = EventDetailWidget()
        events_lay.addWidget(self._event_list_panel, stretch=3)
        events_lay.addWidget(self._event_detail_widget, stretch=0)
        self._event_list_panel.event_selected.connect(self._event_detail_widget.show_event)
        self._tab_widget.addTab(events_widget, "🎬  Event Clips")

        self._tab_widget.setFixedHeight(240)
        outer_split.addWidget(self._tab_widget)

        outer_split.setStretchFactor(0, 4)
        outer_split.setStretchFactor(1, 1)

        self.setCentralWidget(outer_split)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        self._lbl_track  = QLabel("Track: —")
        self._lbl_frame  = QLabel("Frame: —")
        self._lbl_fps    = QLabel("FPS: —")
        self._lbl_anoms  = QLabel("Anomalies: 0")
        self._lbl_events = QLabel("Clips: 0")

        for lbl in (self._lbl_track, self._lbl_frame, self._lbl_fps,
                    self._lbl_anoms, self._lbl_events):
            lbl.setStyleSheet(f"color: {Palette.TEXT_DIM}; padding: 0 10px;")
            sb.addWidget(lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedWidth(180)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {Palette.BG_PANEL};
                border: 1px solid #2a4a7f;
                border-radius: 4px;
                text-align: center;
                color: {Palette.TEXT};
                font-size: 10px;
            }}
            QProgressBar::chunk {{ background-color: #4a8adf; border-radius: 4px; }}
            """
        )
        sb.addPermanentWidget(self._progress)

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------

    def _on_open(self) -> None:
        """Open a video file without starting — pre-selects for the dialog."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "", "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*)"
        )
        if path:
            self._pending_video_path = path
            self.setWindowTitle(f"OHE — {Path(path).name}")

    def _on_start(self) -> None:
        """Open the session setup dialog then launch the pipeline."""
        dlg = SessionSetupDialog(
            parent=self,
            initial_video_path=getattr(self, "_pending_video_path", ""),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        setup = dlg.session_setup
        if setup is None:
            return

        self._current_track = setup.track_name
        self._lbl_track.setText(f"Track: {setup.track_name}")
        self.setWindowTitle(f"OHE — {setup.track_name}")

        # Update session info bar
        source = setup.video_path or f"camera:{setup.camera_index}"
        self._session_info_bar.update_session(
            track_name=setup.track_name,
            source=source,
            gps_mode=setup.gps_mode,
            speed_mode=setup.speed_mode,
            model_version=self._cfg.model_version,
        )

        self._act_start.setEnabled(False)
        self._act_stop.setEnabled(True)
        self._act_export.setEnabled(False)
        self._act_share.setEnabled(False)
        self._plot_panel.clear()
        self._anomaly_panel.clear()
        self._event_list_panel.clear()
        self._tab_widget.setTabText(1, "🎬  Event Clips")
        self._progress.setValue(0)
        self._lbl_events.setText("Clips: 0")
        self._lbl_anoms.setText("Anomalies: 0")
        self._video_panel.set_status("STARTING…", Palette.ACCENT2)

        self._worker = PipelineWorker(setup, self._cfg, self._cal, parent=self)
        self._worker.new_frame.connect(self._on_frame)
        self._worker.new_measurement.connect(self._on_measurement)
        self._worker.new_anomaly.connect(self._on_anomaly)
        self._worker.new_event_clip.connect(self._on_event_clip)
        self._worker.stats_update.connect(self._on_stats)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker:
            self._worker.request_stop()
        self._act_stop.setEnabled(False)

    def _on_settings(self) -> None:
        dlg = ConfigDialog(self._cfg, parent=self)
        if dlg.exec() and self._worker and self._worker.isRunning():
            QMessageBox.information(
                self, "Settings Applied",
                "New settings will take effect from the next Start."
            )

    def _on_calibrate(self) -> None:
        # Use most recently configured video path if available
        video_path = getattr(self, "_pending_video_path", "")
        wizard = CalibrationWizard(
            video_path=video_path,
            parent=self,
        )
        if wizard.exec() and wizard.result_calibration:
            self._cal = wizard.result_calibration
            QMessageBox.information(
                self, "Calibration Updated",
                f"px/mm = {self._cal.px_per_mm:.4f}\n"
                f"Calibration saved to config/calibration.json"
            )

    def _on_debug_hint(self) -> None:
        QMessageBox.information(
            self, "Debug Visualiser",
            "Run from a PowerShell terminal:\n\n"
            ".venv\\Scripts\\python.exe tools/debug_visualiser.py "
            "--video <your_video.mp4>"
        )

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About OHE",
            "<b>OHE Stagger &amp; Wire Diameter Measurement</b><br>"
            "Version 0.2.0 — Phase 6<br><br>"
            "Complete event analysis system: wire detection, geolocation,<br>"
            "event clips, detailed logs, and data sharing.<br><br>"
            "Built with OpenCV, scipy, PyQt6, pyqtgraph."
        )

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
            csv_path, json_path, events_path = exp.export_all()
            QMessageBox.information(
                self, "Export Complete",
                f"CSV:    {csv_path}\n"
                f"JSON:   {json_path}\n"
                f"Events: {events_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _on_share(self) -> None:
        dlg = ShareDialog(
            session_dir=self._cfg.session_dir_path(),
            events_dir=self._cfg.events_dir_path(),
            session_id=self._last_session_id,
            parent=self,
        )
        dlg.exec()

    # ------------------------------------------------------------------
    # Worker signal handlers (run on UI thread via queued connection)
    # ------------------------------------------------------------------

    def _on_frame(self, frame: np.ndarray, frame_id: int, cand) -> None:
        self._video_panel.update_frame(frame)
        self._lbl_frame.setText(f"Frame: {frame_id:,}")

    def _on_measurement(self, m: Measurement) -> None:
        stagger_col = Palette.TEXT
        if m.stagger_mm is not None:
            abs_s = abs(m.stagger_mm)
            stagger_col = (
                Palette.CRITICAL if abs_s >= 150 else
                Palette.WARNING  if abs_s >= 100 else
                Palette.OK
            )
            self._card_stagger.set_value(m.stagger_mm, stagger_col)
        if m.diameter_mm is not None:
            d_colour = Palette.CRITICAL if m.diameter_mm < 8 else Palette.OK
            self._card_diameter.set_value(m.diameter_mm, d_colour)
        self._plot_panel.add_measurement(m)

    def _on_anomaly(self, a: Anomaly) -> None:
        self._anomaly_panel.add_anomaly(a)
        count = self._anomaly_panel.count
        self._lbl_anoms.setText(f"Anomalies: {count}")
        self._event_list_panel.add_event(a)
        # Update Events tab badge
        self._tab_widget.setTabText(1, f"🎬  Event Clips ({self._event_list_panel.count})")

    def _on_event_clip(self, clip_path: str, anomaly: object) -> None:
        """Called when an event clip is written — update the event list."""
        if isinstance(anomaly, Anomaly):
            self._event_list_panel.update_clip_path(clip_path, anomaly)
            clip_count = self._event_list_panel.count
            self._lbl_events.setText(f"Clips: {clip_count}")

    def _on_stats(self, stats: dict) -> None:
        fps     = stats.get("fps", 0.0)
        progress = int(stats.get("progress_pct", 0))
        det_pct = stats.get("det_pct", 0.0)
        frame_ms = stats.get("frame_ms", 0.0)

        self._lbl_fps.setText(f"FPS: {fps:.1f}")
        self._card_det_pct.set_value(
            det_pct,
            Palette.OK if det_pct >= 60 else Palette.WARNING,
        )
        self._progress.setValue(progress)
        self._progress.setFormat(f"{progress}%  |  {frame_ms:.1f}ms/f")
        self._video_panel.set_status(f"PROCESSING  {fps:.0f} fps", Palette.OK)

    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Pipeline Error", msg)
        self._on_finished()

    def _on_finished(self) -> None:
        self._act_start.setEnabled(True)
        self._act_stop.setEnabled(False)
        self._act_export.setEnabled(True)
        self._act_share.setEnabled(True)
        self._progress.setValue(100)
        self._progress.setFormat("✓ Done")
        self._video_panel.show_placeholder(
            f"✓ Session complete — {self._current_track}\n"
            "Click ▶ Start for a new session or use Export / Share"
        )
        self._video_panel.set_status("COMPLETE", Palette.OK)
        # Capture latest session id for share dialog
        track_root = self._cfg.track_dir_path(self._current_track) if self._current_track else None
        logs_dir   = (track_root / "logs") if track_root else self._cfg.session_dir_path()
        sessions   = sorted(logs_dir.glob("*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
        if sessions:
            self._last_session_id = sessions[0].stem

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(3000)
        event.accept()
