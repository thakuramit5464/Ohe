"""tests/unit/test_detector.py — WireDetector tests using synthetic wire images."""

import numpy as np
import pytest

from ohe.core.config import ProcessingConfig
from ohe.core.models import ProcessedFrame, RawFrame
from ohe.processing.detector import WireDetector


def make_processed_frame_with_wire(
    h: int = 100,
    w: int = 400,
    wire_y: int = 50,
    wire_thickness: int = 4,
    frame_id: int = 0,
) -> ProcessedFrame:
    """Synthesise a grayscale frame with a bright horizontal wire."""
    img = np.zeros((h, w), dtype=np.uint8)
    y0 = max(0, wire_y - wire_thickness // 2)
    y1 = min(h, wire_y + wire_thickness // 2)
    img[y0:y1, :] = 200  # bright wire band

    raw = RawFrame(frame_id=frame_id, timestamp_ms=0.0, image=np.zeros((h, w, 3), dtype=np.uint8))
    return ProcessedFrame(raw=raw, roi_image=img, roi_offset_x=0, roi_offset_y=0)


def make_empty_frame(h=100, w=400) -> ProcessedFrame:
    """Fully black frame — no wire detectable."""
    img = np.zeros((h, w), dtype=np.uint8)
    raw = RawFrame(frame_id=0, timestamp_ms=0.0, image=np.zeros((h, w, 3), dtype=np.uint8))
    return ProcessedFrame(raw=raw, roi_image=img)


class TestWireDetector:
    def setup_method(self):
        self.cfg = ProcessingConfig(
            canny_threshold1=30,
            canny_threshold2=100,
            hough_threshold=20,
            hough_min_line_length=30,
            hough_max_line_gap=20,
            min_detection_confidence=0.0,
        )
        self.detector = WireDetector(self.cfg)

    def test_detects_horizontal_wire(self):
        pf = make_processed_frame_with_wire(wire_y=50)
        cand = self.detector.detect(pf)
        assert cand.confidence > 0.0, "Should detect the synthetic wire"

    def test_wire_centre_near_expected_y(self):
        pf = make_processed_frame_with_wire(wire_y=50)
        cand = self.detector.detect(pf)
        if cand.confidence > 0.0:
            assert abs(cand.centre_y - 50) < 10, "Wire Y centre should be close to 50"

    def test_empty_frame_returns_zero_confidence(self):
        pf = make_empty_frame()
        cand = self.detector.detect(pf)
        assert cand.confidence == 0.0

    def test_frame_id_propagated(self):
        pf = make_processed_frame_with_wire(frame_id=99)
        cand = self.detector.detect(pf)
        assert cand.frame_id == 99
