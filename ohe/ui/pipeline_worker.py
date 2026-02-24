"""
ui/pipeline_worker.py
----------------------
QThread-based pipeline worker.

Runs the full detection pipeline in a background thread and emits Qt signals
that the main window connects to for live GUI updates.

Signals
-------
new_frame(np.ndarray, int)           — BGR frame + frame_id
new_measurement(Measurement)         — after every detected wire
new_anomaly(Anomaly)                 — for each rule violation
stats_update(dict)                   — periodic dict with running stats
error(str)                           — fatal pipeline error message
finished()                           — emitted when loop exits cleanly
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from ohe.core.config import AppConfig
from ohe.core.models import Anomaly, Measurement
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
        self._session:   Optional[SessionLogger] = None
        self._log_worker: Optional[LogWorker]    = None

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        self._stop_requested = True

    # ------------------------------------------------------------------
    # QThread.run — executed in the background thread
    # ------------------------------------------------------------------

    def run(self) -> None:  # noqa: C901 (complexity acceptable here)
        from ohe.ingestion.video_file import VideoFileProvider

        try:
            pipeline  = ProcessingPipeline(self._cfg, self._cal)
            detector  = WireDetector(self._cfg.processing)
            measure   = MeasurementEngine(self._cal, self._cfg.processing)
            rules     = RulesEngine(Thresholds.from_config(self._cfg.rules))

            # Session logging
            session_dir = self._cfg.session_dir_path()
            self._session = SessionLogger(session_dir, source=self._video_path)
            info = self._session.start()
            csv_writer = CsvWriter(session_dir, info.session_id) if self._cfg.logging.csv_enabled else None
            self._log_worker = LogWorker(self._session, csv_writer, maxsize=1000)
            self._log_worker.start()

            provider = VideoFileProvider(self._video_path, frame_skip=self._cfg.ingestion.frame_skip)

            # Stats
            frame_count = detected = anomaly_count = 0
            stagger_vals: list[float] = []
            t_start = time.monotonic()

            with provider:
                for raw in provider.frames():
                    if self._stop_requested:
                        break

                    pf = pipeline._preprocessor.run(raw)
                    cand, dbg_frame = detector.detect_debug(pf)
                    m  = measure.compute(cand, pf.roi_offset_x, pf.roi_offset_y)
                    anomalies = rules.evaluate(m)

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

                    frame_count += 1

                    # Periodic stats every 15 frames
                    if frame_count % 15 == 0:
                        elapsed = time.monotonic() - t_start
                        fps = frame_count / max(elapsed, 0.001)
                        det_pct = detected / frame_count * 100
                        avg_stagger = sum(stagger_vals[-30:]) / len(stagger_vals[-30:]) if stagger_vals else None
                        self.stats_update.emit({
                            "frame":      frame_count,
                            "fps":        fps,
                            "detected":   detected,
                            "det_pct":    det_pct,
                            "anomalies":  anomaly_count,
                            "avg_stagger": avg_stagger,
                            "elapsed_s":  elapsed,
                        })

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
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
