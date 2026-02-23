"""
processing/pipeline.py
-----------------------
ProcessingPipeline: orchestrates the full per-frame processing chain.

  RawFrame
    → PreProcessor        → ProcessedFrame
    → WireDetector        → WireCandidate
    → MeasurementEngine   → Measurement
    → (returned to caller)

The pipeline holds references to all processing components and exposes a
single ``run(raw_frame)`` method that returns a Measurement.  Rules engine
and logging are invoked by the higher-level runner (CLI / UI worker thread)
after calling ``pipeline.run()``.
"""

from __future__ import annotations

import logging

from ohe.core.config import AppConfig
from ohe.core.models import Measurement, RawFrame
from ohe.processing.calibration import CalibrationModel
from ohe.processing.detector import WireDetector
from ohe.processing.measurement import MeasurementEngine
from ohe.processing.preprocess import PreProcessor

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """End-to-end per-frame processing chain."""

    def __init__(self, config: AppConfig, calibration: CalibrationModel) -> None:
        self._cfg = config
        self._calibration = calibration

        self._preprocessor = PreProcessor(config.processing, calibration)
        self._detector = WireDetector(config.processing)
        self._measurement = MeasurementEngine(calibration, config.processing)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, raw: RawFrame) -> Measurement:
        """Process one frame end-to-end.

        Returns:
            :class:`Measurement` — fields may be None if confidence is too low.
        """
        processed = self._preprocessor.run(raw)
        candidate = self._detector.detect(processed)
        measurement = self._measurement.compute(
            candidate,
            roi_offset_x=processed.roi_offset_x,
            roi_offset_y=processed.roi_offset_y,
        )
        return measurement

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
        return self._calibration
