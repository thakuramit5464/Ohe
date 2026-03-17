"""
processing/pipeline.py
-----------------------
ProcessingPipeline: orchestrates the full per-frame processing chain.

Extended pipeline (v2):

  RawFrame
    → PreProcessor          → ProcessedFrame
    → WireDetector          → WireCandidate
    → MeasurementEngine     → Measurement  (stagger, diameter)
    → MastDetector          → mast candidates
    → MastEventTracker      → MastEvent (optional)
    → ChainageEstimator     → chainage_m
    → LaserHeightNode       → height_m
    ─────────────────────────────────────────────────────
    → enriched Measurement  (+ height_m, chainage_m, mast_event)

Rules engine and logging are invoked by the higher-level runner (CLI / UI
worker thread) after calling pipeline.run().
"""

from __future__ import annotations

import logging
from typing import Optional

from ohe.core.config import AppConfig
from ohe.core.models import MastEvent, Measurement, RawFrame
from ohe.processing.calibration import CalibrationModel
from ohe.processing.chainage_estimator import ChainageEstimator
from ohe.processing.detector import WireDetector
from ohe.processing.laser_height_node import LaserHeightNode
from ohe.processing.mast_detection import MastDetector, MastEventTracker
from ohe.processing.measurement import MeasurementEngine
from ohe.processing.preprocess import PreProcessor

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """End-to-end per-frame processing chain with measurement fusion."""

    def __init__(self, config: AppConfig, calibration: CalibrationModel) -> None:
        self._cfg = config

        # Existing components
        self._preprocessor  = PreProcessor(config.processing, calibration)
        self._detector      = WireDetector(config.processing)
        self._measurement   = MeasurementEngine(calibration, config.processing)

        # New components (v2)
        self._mast_detector = MastDetector(config.mast_detection)
        self._mast_tracker  = MastEventTracker(config.mast_detection)
        self._chainage      = ChainageEstimator(config.chainage)
        self._height_node   = LaserHeightNode(config.laser_height)

        # Session state
        self._last_mast_chainage_m: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        raw: RawFrame,
        speed_kmh: Optional[float] = None,
        sensor_distance_m: Optional[float] = None,
    ) -> Measurement:
        """Process one frame end-to-end and return an enriched Measurement.

        Args:
            raw:              Raw video frame.
            speed_kmh:        Override vehicle speed (km/h).  When None the
                              chainage estimator uses its configured speed.
            sensor_distance_m: Raw laser distance reading (m) for real-sensor
                              mode.  Ignored in simulated mode.

        Returns:
            :class:`Measurement` with vision, height, chainage, and optional
            mast event fields populated.  Fields may be ``None`` when detection
            confidence is below threshold or sensor data is unavailable.
        """
        # ── Step 1: vision processing ────────────────────────────────────
        processed   = self._preprocessor.run(raw)
        candidate   = self._detector.detect(processed)
        measurement = self._measurement.compute(
            candidate,
            roi_offset_x=processed.roi_offset_x,
            roi_offset_y=processed.roi_offset_y,
        )

        # ── Step 2: chainage update ──────────────────────────────────────
        chainage_m = self._chainage.update(
            timestamp_ms=raw.timestamp_ms,
            speed_kmh=speed_kmh,
        )

        # ── Step 3: laser height ─────────────────────────────────────────
        height_m = self._height_node.get_height(
            timestamp_ms=raw.timestamp_ms,
            raw_distance_m=sensor_distance_m,
        )

        # ── Step 4: mast detection ───────────────────────────────────────
        mast_event: Optional[MastEvent] = None

        if self._cfg.mast_detection.enabled:
            candidates = self._mast_detector.detect(raw.image)
            mast_event = self._mast_tracker.update(
                candidates=candidates,
                frame_id=raw.frame_id,
                timestamp_ms=raw.timestamp_ms,
                chainage_m=chainage_m,
                last_mast_chainage_m=self._last_mast_chainage_m,
            )
            if mast_event is not None:
                spacing = self._chainage.register_mast()
                # Attach spacing computed by estimator (authoritative value)
                mast_event.mast_spacing_m = spacing
                self._last_mast_chainage_m = chainage_m

        # ── Step 5: fuse into enriched Measurement ───────────────────────
        measurement.height_m   = height_m
        measurement.chainage_m = chainage_m
        measurement.mast_event = mast_event

        return measurement

    def reset_session(self) -> None:
        """Reset stateful pipeline components (call at session start)."""
        self._chainage.reset(self._cfg.chainage.initial_chainage_m)
        self._mast_tracker.reset()
        self._last_mast_chainage_m = None
        logger.info("Pipeline session state reset")

    # ------------------------------------------------------------------
    # Component accessors (for UI config dialogs, tests, etc.)
    # ------------------------------------------------------------------

    @property
    def preprocessor(self) -> PreProcessor:
        return self._preprocessor

    @property
    def detector(self) -> WireDetector:
        return self._detector

    @property
    def calibration(self) -> CalibrationModel:
        return self._preprocessor._calibration   # type: ignore[attr-defined]

    @property
    def chainage_estimator(self) -> ChainageEstimator:
        return self._chainage

    @property
    def laser_height_node(self) -> LaserHeightNode:
        return self._height_node

    @property
    def mast_detector(self) -> MastDetector:
        return self._mast_detector

    @property
    def mast_tracker(self) -> MastEventTracker:
        return self._mast_tracker
