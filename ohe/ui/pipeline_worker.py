"""
ui/pipeline_worker.py
----------------------
QThread-based pipeline worker — Phase 2.

Accepts a :class:`SessionSetup` from the session setup dialog and:
  * Selects ``VideoFileProvider`` or ``CameraProvider`` based on input_mode
  * Selects ``SimulatedGeoProvider`` or ``NullGeoProvider`` based on gps_mode
  * Selects ``SimulatedSpeedProvider`` or ``NullSpeedProvider`` based on speed_mode
  * Creates track-scoped directories under ``data/tracks/<track_name>/``
  * Names event clips with the pattern:
      <track_name>_<YYYY-MM-DD_HH-MM-SS>_event_<N>.mp4
  * Passes ``track_name`` to ``SessionLogger``
  * Emits all the same Qt signals as Phase 1 + new_event_clip + stats_update

Signals
-------
new_frame(np.ndarray, int, object)
new_measurement(object)
new_anomaly(object)
new_event_clip(str, object)     — (clip_path, Anomaly) when a clip is saved
stats_update(dict)
error(str)
finished()
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
from ohe.speed.provider import NullSpeedProvider, SimulatedSpeedProvider, SpeedProvider
from ohe.ui.session_setup_dialog import SessionSetup


class PipelineWorker(QThread):
    """Background thread — runs the detection pipeline and emits Qt signals."""

    new_frame       = pyqtSignal(np.ndarray, int, object)
    new_measurement = pyqtSignal(object)
    new_anomaly     = pyqtSignal(object)
    new_event_clip  = pyqtSignal(str, object)
    stats_update    = pyqtSignal(dict)
    error           = pyqtSignal(str)
    finished        = pyqtSignal()

    def __init__(
        self,
        setup: SessionSetup,
        cfg: AppConfig,
        cal: CalibrationModel,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._setup   = setup
        self._cfg     = cfg
        self._cal     = cal
        self._stop_requested = False

        self._session:    Optional[SessionLogger] = None
        self._log_worker: Optional[LogWorker]     = None

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        self._stop_requested = True

    # ------------------------------------------------------------------
    # QThread.run
    # ------------------------------------------------------------------

    def run(self) -> None:  # noqa: C901
        from ohe.ingestion.video_file import VideoFileProvider
        from ohe.ingestion.camera import CameraProvider

        setup = self._setup
        pending_rowids: dict[int, Anomaly] = {}

        try:
            # --- Dir setup -----------------------------------------------
            self._cfg.ensure_data_dirs()
            track_root  = self._cfg.ensure_track_dirs(setup.track_name)
            events_dir  = track_root / "events"
            logs_dir    = track_root / "logs"

            # --- Processing components ------------------------------------
            pipeline  = ProcessingPipeline(self._cfg, self._cal)
            detector  = WireDetector(self._cfg.processing)
            measure   = MeasurementEngine(self._cal, self._cfg.processing)
            rules     = RulesEngine(Thresholds.from_config(self._cfg.rules))

            # --- Geo provider --------------------------------------------
            geo_provider: GeoProvider
            if self._cfg.geo.enabled and setup.gps_mode == "simulated":
                geo_provider = SimulatedGeoProvider(
                    origin_latitude=self._cfg.geo.origin_latitude,
                    origin_longitude=self._cfg.geo.origin_longitude,
                    speed_kmh=self._cfg.speed.simulated_base_kmh,
                )
            else:
                geo_provider = NullGeoProvider()

            # --- Speed provider ------------------------------------------
            speed_provider: SpeedProvider
            if setup.speed_mode == "simulated":
                speed_provider = SimulatedSpeedProvider(
                    base_speed_kmh=self._cfg.speed.simulated_base_kmh,
                    jitter_kmh=self._cfg.speed.simulated_jitter_kmh,
                )
            else:
                speed_provider = NullSpeedProvider()

            # --- Event clip writer ----------------------------------------
            ts_str = time.strftime("%Y-%m-%d_%H-%M-%S")
            clip_writer: Optional[EventClipWriter] = None
            clip_counter = [0]  # use list for closure mutation
            if self._cfg.event_video.enabled:
                clip_writer = EventClipWriter(
                    events_dir=events_dir,
                    pre_frames=self._cfg.event_video.pre_frames,
                    post_frames=self._cfg.event_video.post_frames,
                    fps=self._cfg.event_video.video_fps,
                )
                # Override EventClipWriter's filename builder with track-aware names
                _orig_begin = clip_writer.begin_event

                def _track_begin(frame_id: int):
                    clip_counter[0] += 1
                    from ohe.events.clip_writer import EventCapture
                    fname = (
                        f"{setup.track_name}_{ts_str}_event_{clip_counter[0]:03d}.mp4"
                    )
                    cap = EventCapture(
                        pre_frames=list(clip_writer._buffer),
                        post_frames_needed=self._cfg.event_video.post_frames,
                        output_path=events_dir / fname,
                        fps=self._cfg.event_video.video_fps,
                        frame_id=frame_id,
                    )
                    clip_writer._active_captures.append(cap)
                    return cap

                clip_writer.begin_event = _track_begin  # type: ignore[method-assign]

            # --- Session logging -----------------------------------------
            self._session   = SessionLogger(
                logs_dir,
                source=setup.video_path or f"camera:{setup.camera_index}",
                track_name=setup.track_name,
            )
            info        = self._session.start()
            csv_writer  = (
                CsvWriter(logs_dir, info.session_id)
                if self._cfg.logging.csv_enabled else None
            )
            self._log_worker = LogWorker(self._session, csv_writer, maxsize=1000)
            self._log_worker.start()

            # --- Frame provider ------------------------------------------
            if setup.input_mode == "camera":
                provider = CameraProvider(
                    camera_index=setup.camera_index,
                    target_fps=self._cfg.input.camera_fps,
                    frame_skip=self._cfg.ingestion.frame_skip,
                )
            else:
                provider = VideoFileProvider(
                    setup.video_path,
                    frame_skip=self._cfg.ingestion.frame_skip,
                )

            # --- Stats ----------------------------------------------------
            frame_count = detected = anomaly_count = 0
            stagger_vals: list[float] = []
            t_start = time.monotonic()

            with provider:
                for raw in provider.frames():
                    if self._stop_requested:
                        break

                    t_frame = time.monotonic()

                    pf   = pipeline._preprocessor.run(raw)
                    cand, dbg_frame = detector.detect_debug(pf)
                    m    = measure.compute(cand, pf.roi_offset_x, pf.roi_offset_y)
                    anomalies = rules.evaluate(m)

                    # Attach geo + speed + model version to each anomaly
                    geo   = geo_provider.get_location(raw.frame_id, raw.timestamp_ms)
                    speed = speed_provider.get_speed(raw.frame_id, raw.timestamp_ms)
                    for a in anomalies:
                        if geo is not None:
                            a.latitude  = geo.latitude
                            a.longitude = geo.longitude
                        a.speed_kmh    = speed
                        a.model_version = self._cfg.model_version

                    annotated = _compose_display_frame(raw.image, dbg_frame, self._cfg)
                    self.new_frame.emit(annotated, raw.frame_id,
                                        cand if cand.confidence > 0 else None)

                    if m.stagger_mm is not None:
                        detected += 1
                        stagger_vals.append(m.stagger_mm)
                        self.new_measurement.emit(m)
                        self._log_worker.push_measurement(m, anomalies)

                    for a in anomalies:
                        anomaly_count += 1
                        self.new_anomaly.emit(a)
                        if clip_writer is not None:
                            clip_writer.begin_event(raw.frame_id)
                            rowid = self._session.log_anomaly(a)
                            if rowid >= 0:
                                pending_rowids[rowid] = a

                    if clip_writer is not None:
                        for clip_path in clip_writer.push_frame(raw.image):
                            if pending_rowids:
                                rowid, anom = next(iter(pending_rowids.items()))
                                del pending_rowids[rowid]
                                clip_rel = str(clip_path)
                                self._session.update_anomaly_clip(rowid, clip_rel)
                                anom.video_clip = clip_rel
                                self.new_event_clip.emit(clip_rel, anom)

                    frame_count += 1

                    if frame_count % 15 == 0:
                        elapsed = time.monotonic() - t_start
                        fps     = frame_count / max(elapsed, 0.001)
                        total   = provider.frame_count
                        prog    = frame_count / max(total, 1) * 100 if total > 0 else 0
                        self.stats_update.emit({
                            "frame":        frame_count,
                            "total_frames": total,
                            "progress_pct": prog,
                            "fps":          fps,
                            "detected":     detected,
                            "det_pct":      detected / frame_count * 100,
                            "anomalies":    anomaly_count,
                            "avg_stagger":  (
                                sum(stagger_vals[-30:]) / len(stagger_vals[-30:])
                                if stagger_vals else None
                            ),
                            "elapsed_s":    elapsed,
                            "frame_ms":     (time.monotonic() - t_frame) * 1000,
                            "track_name":   setup.track_name,
                        })

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if clip_writer is not None:
                for clip_path in clip_writer.finalize_all():
                    if pending_rowids:
                        rowid, anom = next(iter(pending_rowids.items()))
                        del pending_rowids[rowid]
                        clip_rel = str(clip_path)
                        if self._session:
                            self._session.update_anomaly_clip(rowid, clip_rel)
                        anom.video_clip = clip_rel
                        self.new_event_clip.emit(clip_rel, anom)

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
    fh, fw = out.shape[:2]
    roi_h, roi_w = roi_dbg.shape[:2]
    scale = min((fw // 3) / max(roi_w, 1), 100 / max(roi_h, 1))
    nw = max(1, int(roi_w * scale))
    nh = max(1, int(roi_h * scale))
    small = cv2.resize(roi_dbg, (nw, nh))
    y0, x0 = fh - nh - 4, fw - nw - 4
    out[y0:y0 + nh, x0:x0 + nw] = small
    return out
