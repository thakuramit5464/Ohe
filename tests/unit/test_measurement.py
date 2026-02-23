"""tests/unit/test_measurement.py — MeasurementEngine unit tests."""

import pytest
import numpy as np

from ohe.core.config import ProcessingConfig
from ohe.core.models import WireCandidate, ProcessedFrame, RawFrame
from ohe.processing.calibration import CalibrationModel
from ohe.processing.measurement import MeasurementEngine


def make_calibration(px_per_mm=10.0, centre_x=500) -> CalibrationModel:
    return CalibrationModel(
        px_per_mm=px_per_mm,
        track_centre_x_px=centre_x,
        image_width_px=1000,
        image_height_px=500,
    )


def make_config(min_confidence=0.5) -> ProcessingConfig:
    return ProcessingConfig(min_detection_confidence=min_confidence)


def make_candidate(cx=600.0, diameter_px=12.0, confidence=0.9) -> WireCandidate:
    return WireCandidate(
        frame_id=1, timestamp_ms=33.0,
        centre_x=cx, centre_y=50.0,
        diameter_px=diameter_px,
        confidence=confidence,
        bbox_x=int(cx)-6, bbox_y=44, bbox_w=12, bbox_h=12,
    )


class TestMeasurementEngine:
    def test_stagger_positive_right(self):
        cal = make_calibration(px_per_mm=10.0, centre_x=500)
        eng = MeasurementEngine(cal, make_config())
        # Wire 100px right of centre → +10 mm
        m = eng.compute(make_candidate(cx=600.0))
        assert m.stagger_mm == pytest.approx(10.0)

    def test_stagger_negative_left(self):
        cal = make_calibration(px_per_mm=10.0, centre_x=500)
        eng = MeasurementEngine(cal, make_config())
        m = eng.compute(make_candidate(cx=400.0))
        assert m.stagger_mm == pytest.approx(-10.0)

    def test_diameter_conversion(self):
        cal = make_calibration(px_per_mm=10.0, centre_x=500)
        eng = MeasurementEngine(cal, make_config())
        m = eng.compute(make_candidate(diameter_px=120.0))
        assert m.diameter_mm == pytest.approx(12.0)

    def test_low_confidence_returns_none_fields(self):
        cal = make_calibration()
        eng = MeasurementEngine(cal, make_config(min_confidence=0.8))
        m = eng.compute(make_candidate(confidence=0.3))
        assert m.stagger_mm is None
        assert m.diameter_mm is None

    def test_roi_offset_applied(self):
        cal = make_calibration(px_per_mm=10.0, centre_x=500)
        eng = MeasurementEngine(cal, make_config())
        # candidate centre_x=100 in ROI, roi_offset_x=400 → full_cx=500 → stagger=0
        m = eng.compute(make_candidate(cx=100.0), roi_offset_x=400)
        assert m.stagger_mm == pytest.approx(0.0)

    def test_bbox_translated_to_full_frame(self):
        cal = make_calibration()
        eng = MeasurementEngine(cal, make_config())
        c = make_candidate(cx=50.0)
        c.bbox_x = 44
        m = eng.compute(c, roi_offset_x=200, roi_offset_y=100)
        assert m.wire_bbox[0] == 44 + 200
        assert m.wire_bbox[1] == c.bbox_y + 100
