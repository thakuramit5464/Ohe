"""
processing/measurement.py
--------------------------
Converts a WireCandidate (pixel-space) into a Measurement (real-world mm).

Uses the CalibrationModel for:
  * Pixel → mm conversion (diameter)
  * Track-centre offset → stagger (mm)

Also translates ROI-local bounding box back to full-frame pixel coordinates.
"""

from __future__ import annotations

import logging

from ohe.core.config import ProcessingConfig
from ohe.core.models import Measurement, WireCandidate
from ohe.processing.calibration import CalibrationModel

logger = logging.getLogger(__name__)


class MeasurementEngine:
    """Computes real-world stagger and diameter from a WireCandidate."""

    def __init__(self, calibration: CalibrationModel, config: ProcessingConfig) -> None:
        self._cal = calibration
        self._cfg = config

    def compute(
        self,
        candidate: WireCandidate,
        roi_offset_x: int = 0,
        roi_offset_y: int = 0,
    ) -> Measurement:
        """Derive a :class:`Measurement` from *candidate*.

        Args:
            candidate:    Detection result in ROI-local pixel coords.
            roi_offset_x: X offset of the ROI within the full frame (px).
            roi_offset_y: Y offset of the ROI within the full frame (px).

        Returns:
            :class:`Measurement` with real-world values (or None fields if
            confidence is below the configured minimum).
        """
        min_conf = self._cfg.min_detection_confidence

        if candidate.confidence < min_conf:
            logger.debug(
                "Frame %d: confidence %.2f below threshold %.2f — no measurement",
                candidate.frame_id, candidate.confidence, min_conf,
            )
            return Measurement(
                frame_id=candidate.frame_id,
                timestamp_ms=candidate.timestamp_ms,
                stagger_mm=None,
                diameter_mm=None,
                confidence=candidate.confidence,
            )

        # Wire centre in full-frame pixel coordinates
        full_cx = candidate.centre_x + roi_offset_x
        full_cy = candidate.centre_y + roi_offset_y

        # Stagger: signed offset from track centre
        stagger_mm = self._cal.stagger_from_centre_px(full_cx)

        # Diameter: convert detected pixel thickness to mm
        diameter_mm = self._cal.px_to_mm(candidate.diameter_px) if candidate.diameter_px > 0 else None

        # Bounding box in full-frame coords
        wire_bbox = (
            candidate.bbox_x + roi_offset_x,
            candidate.bbox_y + roi_offset_y,
            candidate.bbox_w,
            candidate.bbox_h,
        )

        logger.debug(
            "Frame %d: stagger=%.2f mm  diameter=%.2f mm  conf=%.2f",
            candidate.frame_id,
            stagger_mm,
            diameter_mm if diameter_mm is not None else float("nan"),
            candidate.confidence,
        )

        return Measurement(
            frame_id=candidate.frame_id,
            timestamp_ms=candidate.timestamp_ms,
            stagger_mm=stagger_mm,
            diameter_mm=diameter_mm,
            confidence=candidate.confidence,
            wire_bbox=wire_bbox,
            wire_centre_px=(full_cx, full_cy),
        )
