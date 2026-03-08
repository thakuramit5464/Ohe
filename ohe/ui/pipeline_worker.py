"""
ui/pipeline_worker.py
----------------------
QThread-based pipeline worker.

Runs the full detection pipeline in a background thread and emits Qt signals
that the main window connects to for live GUI updates.

Signals
-------
new_frame(np.ndarray, int, object)   — BGR frame + frame_id + WireCandidate|None
new_measurement(Measurement)         — after every detected wire
new_anomaly(Anomaly)                 — for each rule violation
new_event_clip(str, object)          — (clip_path, Anomaly) when a clip is saved
stats_update(dict)                   — periodic dict with running stats
error(str)                           — fatal pipeline error message
finished()                           — emitted when loop exits cleanly
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from ohe.core.config import AppConfig
from ohe.core.models import Anomaly, Measurement
from ohe.events.clip_writer import EventClipWriter
from ohe.geo.provider import GeoProvider, NullGeoProvider, SimulatedGeoProvider
from ohe.logging_.csv_writer import CsvWriter
from ohe.logging_.log_worker import LogWorker
from ohe.logging_.session import SessionLogger
from ohe.processing.calibration import CalibrationModel
from ohe.processing.detector import WireDetector
from ohe.processing.measurement import MeasurementEngine
from ohe.processing.pipeline import ProcessingPipeline
from ohe.rules.engine import RulesEngine
from ohe.rules.thresholds import Thresholds


class PipelineWorker(QThread):
    """Background thread — runs the detection pipeline and emits Qt signals."""

    # Signals (UI connects these in main_window.py)
    new_frame       = pyqtSignal(np.ndarray, int, object)   # frame, frame_id, WireCandidate|None
    new_measurement = pyqtSignal(object)                    # Measurement
    new_anomaly     = pyqtSignal(object)                    # Anomaly
    new_event_clip  = pyqtSignal(str, object)               # clip_path, Anomaly
    stats_update    = pyqtSignal(dict)                      # running stats dict
    error           = pyqtSignal(str)
    finished        = pyqtSignal()

    def __init__(
        self,
        video_path: str,
        cfg: AppConfig,
        cal: CalibrationModel,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._video_path = video_path
        self._cfg = cfg
        self._cal = cal
        self._stop_requested = False

        # Logging
        self._session:    Optional[SessionLogger] = None
        self._log_worker: Optional[LogWorker]     = None

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        self._stop_requested = True

    # ------------------------------------------------------------------
    # QThread.run — executed in the background thread
    # ------------------------------------------------------------------

    def run(self) -> None:  # noqa: C901
        from ohe.ingestion.video_file import VideoFileProvider

        try:
            # Ensure directories exist
            self._cfg.ensure_data_dirs()

            pipeline  = ProcessingPipeline(self._cfg, self._cal)
            detector  = WireDetector(self._cfg.processing)
            measure   = MeasurementEngine(self._cal, self._cfg.processing)
            rules     = RulesEngine(Thresholds.from_config(self._cfg.rules))

            # Geolocation provider
            geo_provider: GeoProvider
            if self._cfg.geo.enabled:
                geo_provider = SimulatedGeoProvider(
                    origin_latitude=self._cfg.geo.origin_latitude,
                    origin_longitude=self._cfg.geo.origin_longitude,
                    speed_kmh=self._cfg.geo.simulated_speed_kmh,
                )
            else:
                geo_provider = NullGeoProvider()

            # Event clip writer
            clip_writer: Optional[EventClipWriter] = None
            if self._cfg.event_video.enabled:
                clip_writer = EventClipWriter(
                    events_dir=self._cfg.events_dir_path(),
                    pre_frames=self._cfg.event_video.pre_frames,
                    post_frames=self._cfg.event_video.post_frames,
                    fps=self._cfg.event_video.video_fps,
                )

            # Session logging
            session_dir = self._cfg.session_dir_path()
            self._session = SessionLogger(session_dir, source=self._video_path)
            info = self._session.start()
            csv_writer = (
                CsvWriter(session_dir, info.session_id)
                if self._cfg.logging.csv_enabled else None
            )
            self._log_worker = LogWorker(self._session, csv_writer, maxsize=1000)
            self._log_worker.start()

            provider = VideoFileProvider(
                self._video_path,
                frame_skip=self._cfg.ingestion.frame_skip,
            )

            # Stats
            frame_count = detected = anomaly_count = 0
            stagger_vals: list[float] = []
            t_start = time.monotonic()

            # Tracking for clip completion
            # Maps: anomaly_rowid -> Anomaly (so we can emit new_event_clip)
            pending_rowids: dict[int, Anomaly] = {}

            with provider:
                for raw in provider.frames():
                    if self._stop_requested:
                        break

                    t_frame_start = time.monotonic()

                    pf = pipeline._preprocessor.run(raw)
                    cand, dbg_frame = detector.detect_debug(pf)
                    m  = measure.compute(cand, pf.roi_offset_x, pf.roi_offset_y)
                    anomalies = rules.evaluate(m)

                    # Attach geo data + model version to each anomaly
                    geo = geo_provider.get_location(raw.frame_id, raw.timestamp_ms)
                    for a in anomalies:
                        if geo is not None:
                            a.latitude  = geo.latitude
                            a.longitude = geo.longitude
                            a.speed_kmh = geo.speed_kmh
                        a.model_version = self._cfg.model_version

                    # Emit frame (show debug overlay on the ROI strip, rest black)
                    annotated = _compose_display_frame(raw.image, dbg_frame, self._cfg)
                    self.new_frame.emit(annotated, raw.frame_id, cand if cand.confidence > 0 else None)

                    if m.stagger_mm is not None:
                        detected += 1
                        stagger_vals.append(m.stagger_mm)
                        self.new_measurement.emit(m)
                        self._log_worker.push_measurement(m, anomalies)

                    for a in anomalies:
                        anomaly_count += 1
                        self.new_anomaly.emit(a)
                        # Start event clip capture
                        if clip_writer is not None:
                            capture = clip_writer.begin_event(raw.frame_id)
                            # Record rowid via a round-trip through the session
                            rowid = self._session.log_anomaly(a)
                            if rowid >= 0:
                                pending_rowids[rowid] = a

                    # Feed frame into clip writer; collect any completed clips
                    if clip_writer is not None:
                        completed_paths = clip_writer.push_frame(raw.image)
                        for clip_path in completed_paths:
                            # Match completed clips back to rowid (FIFO order)
                            if pending_rowids:
                                rowid, anomaly_obj = next(iter(pending_rowids.items()))
                                del pending_rowids[rowid]
                                clip_rel = str(clip_path)
                                self._session.update_anomaly_clip(rowid, clip_rel)
                                anomaly_obj.video_clip = clip_rel
                                self.new_event_clip.emit(clip_rel, anomaly_obj)

                    frame_count += 1

                    # Periodic stats every 15 frames
                    if frame_count % 15 == 0:
                        elapsed     = time.monotonic() - t_start
                        fps         = frame_count / max(elapsed, 0.001)
                        det_pct     = detected / frame_count * 100
                        avg_stagger = (
                            sum(stagger_vals[-30:]) / len(stagger_vals[-30:])
                            if stagger_vals else None
                        )
                        frame_ms = (time.monotonic() - t_frame_start) * 1000
                        total_frames = provider.frame_count
                        progress_pct = (
                            frame_count / max(total_frames, 1) * 100
                            if total_frames > 0 else 0
                        )
                        self.stats_update.emit({
                            "frame":        frame_count,
                            "total_frames": total_frames,
                            "progress_pct": progress_pct,
                            "fps":          fps,
                            "detected":     detected,
                            "det_pct":      det_pct,
                            "anomalies":    anomaly_count,
                            "avg_stagger":  avg_stagger,
                            "elapsed_s":    elapsed,
                            "frame_ms":     frame_ms,
                        })

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            # Finalize any remaining clips
            if clip_writer is not None:
                for clip_path in clip_writer.finalize_all():
                    if pending_rowids:
                        rowid, anomaly_obj = next(iter(pending_rowids.items()))
                        del pending_rowids[rowid]
                        clip_rel = str(clip_path)
                        if self._session:
                            self._session.update_anomaly_clip(rowid, clip_rel)
                        anomaly_obj.video_clip = clip_rel
                        self.new_event_clip.emit(clip_rel, anomaly_obj)

            if self._log_worker:
                self._log_worker.stop()
            if self._session:
                self._session.stop()
            self.finished.emit()


def _compose_display_frame(
    frame: np.ndarray,
    roi_dbg: np.ndarray,
    cfg: AppConfig,
) -> np.ndarray:
    """Overlay the ROI debug panel on the full BGR frame."""
    import cv2
    out = frame.copy()
    roi = cfg.processing.roi
    if roi:
        rx, ry, rw, rh = roi
        cv2.rectangle(out, (rx, ry), (rx + rw, ry + rh), (0, 200, 255), 1)

    # Paste scaled ROI debug strip onto bottom-right corner
    fh, fw = out.shape[:2]
    roi_h, roi_w = roi_dbg.shape[:2]
    scale = min((fw // 3) / max(roi_w, 1), 100 / max(roi_h, 1))
    nw, nh = max(1, int(roi_w * scale)), max(1, int(roi_h * scale))
    small = cv2.resize(roi_dbg, (nw, nh))
    y0, x0 = fh - nh - 4, fw - nw - 4
    out[y0:y0 + nh, x0:x0 + nw] = small
    return out
