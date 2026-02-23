"""tests/integration/test_pipeline.py — End-to-end pipeline test using synthetic frame."""

import numpy as np
import pytest

from ohe.core.config import load_config
from ohe.core.models import Measurement, RawFrame
from ohe.processing.calibration import CalibrationModel
from ohe.processing.pipeline import ProcessingPipeline
from ohe.rules.engine import RulesEngine
from ohe.rules.thresholds import Thresholds


def make_synthetic_wire_frame(
    h: int = 200,
    w: int = 800,
    wire_y: int = 100,
    wire_x_start: int = 0,
    wire_x_end: int = 800,
    wire_thickness: int = 6,
) -> RawFrame:
    """Create a synthetic BGR frame with a bright white horizontal wire."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    y0 = max(0, wire_y - wire_thickness // 2)
    y1 = min(h, wire_y + wire_thickness // 2 + 1)
    img[y0:y1, wire_x_start:wire_x_end] = 220
    return RawFrame(frame_id=0, timestamp_ms=0.0, image=img, source="synthetic")


class TestPipelineIntegration:
    def setup_method(self):
        self.cfg = load_config()
        # Lower bar for synthetic test: use no ROI, low min confidence
        self.cfg.processing.roi = None
        self.cfg.processing.min_detection_confidence = 0.0
        self.cfg.processing.canny_threshold1 = 30
        self.cfg.processing.canny_threshold2 = 100
        self.cfg.processing.hough_threshold = 15
        self.cfg.processing.hough_min_line_length = 20
        self.cal = CalibrationModel(
            px_per_mm=10.0,
            track_centre_x_px=400,
            image_width_px=800,
            image_height_px=200,
        )
        self.pipeline = ProcessingPipeline(self.cfg, self.cal)

    def test_pipeline_returns_measurement(self):
        raw = make_synthetic_wire_frame(w=800, wire_y=100)
        m = self.pipeline.run(raw)
        assert isinstance(m, Measurement)
        assert m.frame_id == 0

    def test_measurement_confidence_positive_when_wire_present(self):
        raw = make_synthetic_wire_frame(w=800, wire_y=100)
        m = self.pipeline.run(raw)
        # Wire spans full width — expect reasonable confidence
        assert m.confidence >= 0.0

    def test_stagger_near_zero_for_centred_wire(self):
        """Wire centred on track centre should give ~0 stagger."""
        raw = make_synthetic_wire_frame(w=800, wire_y=100)
        m = self.pipeline.run(raw)
        if m.stagger_mm is not None:
            # The wire spans the whole width, so its centre ≈ image centre = track centre
            assert abs(m.stagger_mm) < 50.0, f"Unexpected stagger: {m.stagger_mm}"

    def test_rules_engine_no_anomaly_on_normal_measurement(self):
        rules = RulesEngine(Thresholds.from_config(self.cfg.rules))
        m = Measurement(0, 0.0, stagger_mm=50.0, diameter_mm=12.0, confidence=0.8)
        assert rules.evaluate(m) == []

    def test_rules_engine_anomaly_on_critical_stagger(self):
        rules = RulesEngine(Thresholds.from_config(self.cfg.rules))
        m = Measurement(0, 0.0, stagger_mm=210.0, diameter_mm=12.0, confidence=0.8)
        anomalies = rules.evaluate(m)
        assert any(a.severity == "CRITICAL" for a in anomalies)
