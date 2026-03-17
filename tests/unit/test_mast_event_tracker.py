"""
tests/unit/test_mast_event_tracker.py
---------------------------------------
Unit tests for MastEventTracker temporal consistency logic.
"""

from __future__ import annotations

import pytest

from ohe.core.config import MastDetectionConfig
from ohe.processing.mast_detection.mast_event_tracker import MastEventTracker

_BBOX = (5, 20, 30, 150)   # (x, y, w, h)  — a tall left-side bbox


def _make_config(min_frames: int = 3, iou: float = 0.25) -> MastDetectionConfig:
    return MastDetectionConfig(
        enabled=True,
        sobel_ksize=3,
        edge_threshold=80,
        min_contour_area=200,
        min_aspect_ratio=2.0,
        max_aspect_ratio=30.0,
        side_zone_fraction=0.35,
        min_frames_to_confirm=min_frames,
        iou_threshold=iou,
    )


def _run_frames(
    tracker: MastEventTracker,
    n: int,
    bbox=_BBOX,
    confidence: float = 0.8,
    chainage_start: float = 100.0,
    chainage_step: float = 0.5,
) -> list:
    """Feed `n` frames of the same candidate; return list of (MastEvent | None)."""
    events = []
    for i in range(n):
        chainage = chainage_start + i * chainage_step
        event = tracker.update(
            candidates=[(bbox, confidence)],
            frame_id=i,
            timestamp_ms=float(i * 40),
            chainage_m=chainage,
            last_mast_chainage_m=None,
        )
        events.append(event)
    return events


class TestMastEventTracker:
    def test_no_event_before_threshold(self):
        """Candidates seen fewer than min_frames_to_confirm times must not fire."""
        cfg = _make_config(min_frames=3)
        tracker = MastEventTracker(cfg)
        events = _run_frames(tracker, n=2)
        assert all(e is None for e in events), (
            "Expected no events before threshold reached"
        )

    def test_event_fires_at_threshold(self):
        """Exactly at min_frames_to_confirm an event should be emitted."""
        cfg = _make_config(min_frames=3)
        tracker = MastEventTracker(cfg)
        events = _run_frames(tracker, n=3)
        fired = [e for e in events if e is not None]
        assert len(fired) == 1, f"Expected exactly 1 event, got {len(fired)}"

    def test_event_fires_only_once_per_mast(self):
        """After confirmation a second event must NOT fire for the same mast."""
        cfg = _make_config(min_frames=3)
        tracker = MastEventTracker(cfg)
        events = _run_frames(tracker, n=8)
        fired = [e for e in events if e is not None]
        assert len(fired) == 1, f"Expected exactly 1 event in 8 frames, got {len(fired)}"

    def test_event_contains_correct_fields(self):
        cfg = _make_config(min_frames=3)
        tracker = MastEventTracker(cfg)
        events = _run_frames(tracker, n=3, chainage_start=500.0, chainage_step=1.0)
        event = next(e for e in events if e is not None)
        assert event.frame_id == 2                          # third frame (0-indexed)
        assert event.chainage_m == pytest.approx(502.0)     # 500 + 2×1.0
        assert event.confidence == pytest.approx(0.8)
        assert event.mast_bbox == _BBOX

    def test_mast_spacing_computed_correctly(self):
        """Spacing from last mast is computed correctly when last chainage provided."""
        cfg = _make_config(min_frames=2)
        tracker = MastEventTracker(cfg)
        last_mast = 300.0
        event = None
        for i in range(2):
            event = tracker.update(
                candidates=[(_BBOX, 0.9)],
                frame_id=i,
                timestamp_ms=float(i * 40),
                chainage_m=340.0 + i,
                last_mast_chainage_m=last_mast,
            )
        # event fires on frame i=1: chainage = 341.0
        assert event is not None
        assert event.mast_spacing_m == pytest.approx(341.0 - last_mast)

    def test_first_mast_has_no_spacing(self):
        """When last_mast_chainage_m is None, mast_spacing_m should be None."""
        cfg = _make_config(min_frames=3)
        tracker = MastEventTracker(cfg)
        events = _run_frames(tracker, n=3)
        event = next(e for e in events if e is not None)
        assert event.mast_spacing_m is None

    def test_reset_clears_state(self):
        """After reset() the tracker should behave as if starting fresh."""
        cfg = _make_config(min_frames=3)
        tracker = MastEventTracker(cfg)
        # Prime to almost-confirmation
        _run_frames(tracker, n=2)
        tracker.reset()
        # Feed only 2 frames again — should NOT fire because reset cleared the count
        events = _run_frames(tracker, n=2)
        assert all(e is None for e in events), "Expected no event after reset + 2 frames"

    def test_stale_track_dropped(self):
        """A track that misses too many frames should be dropped and not confirm."""
        cfg = _make_config(min_frames=5)
        tracker = MastEventTracker(cfg)
        # Feed 2 frames then 10 empty frames (no candidates)
        for i in range(2):
            tracker.update([(_BBOX, 0.8)], i, float(i * 40), 100.0, None)
        for i in range(10):
            tracker.update([], 100 + i, float((100 + i) * 40), 100.0 + i, None)
        # Now feed the candidate again — it should start a FRESH track (frame_count = 1)
        events_new = _run_frames(tracker, n=4, chainage_start=200.0)
        # Should NOT have fired yet (only 4 frames < 5 threshold for fresh track)
        assert all(e is None for e in events_new)
