"""tests/unit/test_models.py — Core data model tests."""

import numpy as np
import pytest

from ohe.core.models import (
    Anomaly,
    Measurement,
    ProcessedFrame,
    RawFrame,
    SessionInfo,
    WireCandidate,
)


def make_raw_frame(frame_id: int = 0) -> RawFrame:
    return RawFrame(
        frame_id=frame_id,
        timestamp_ms=frame_id * 33.3,
        image=np.zeros((100, 200, 3), dtype=np.uint8),
        source="test",
    )


class TestRawFrame:
    def test_fields_set(self):
        f = make_raw_frame(5)
        assert f.frame_id == 5
        assert f.image.shape == (100, 200, 3)
        assert f.source == "test"

    def test_timestamp(self):
        f = make_raw_frame(10)
        assert pytest.approx(f.timestamp_ms, rel=1e-3) == 333.0


class TestMeasurement:
    def test_is_valid_both_present(self):
        m = Measurement(0, 0.0, stagger_mm=10.0, diameter_mm=12.5, confidence=0.9)
        assert m.is_valid()

    def test_is_valid_missing_stagger(self):
        m = Measurement(0, 0.0, stagger_mm=None, diameter_mm=12.5, confidence=0.9)
        assert not m.is_valid()

    def test_is_valid_missing_diameter(self):
        m = Measurement(0, 0.0, stagger_mm=10.0, diameter_mm=None, confidence=0.9)
        assert not m.is_valid()


class TestWireCandidate:
    def test_default_confidence(self):
        wc = WireCandidate(frame_id=1, timestamp_ms=33.3)
        assert wc.confidence == 0.0


class TestAnomaly:
    def test_fields(self):
        a = Anomaly(0, 0.0, "STAGGER_RIGHT", 201.0, 200.0, "CRITICAL", "test msg")
        assert a.anomaly_type == "STAGGER_RIGHT"
        assert a.severity == "CRITICAL"


class TestSessionInfo:
    def test_defaults(self):
        s = SessionInfo(session_id="abc", source="test.mp4", started_at_ms=1000.0)
        assert s.total_frames == 0
        assert s.anomaly_count == 0
        assert s.ended_at_ms is None
