"""tests/unit/test_clip_writer.py — Unit tests for EventClipWriter."""
from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path

from ohe.events.clip_writer import EventClipWriter, EventCapture


def _make_frame(h: int = 120, w: int = 160) -> np.ndarray:
    """Return a random BGR frame."""
    return np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)


class TestEventClipWriter:
    def test_push_frame_does_not_raise(self, tmp_path):
        writer = EventClipWriter(events_dir=tmp_path, pre_frames=5, post_frames=3, fps=10.0)
        for _ in range(10):
            completed = writer.push_frame(_make_frame())
        # Nothing should be completed yet (no events triggered)
        assert completed == []

    def test_begin_event_creates_capture(self, tmp_path):
        writer = EventClipWriter(events_dir=tmp_path, pre_frames=5, post_frames=3, fps=10.0)
        for _ in range(5):
            writer.push_frame(_make_frame())
        capture = writer.begin_event(frame_id=5)
        assert not capture.is_complete

    def test_full_event_cycle_creates_file(self, tmp_path):
        """Push pre-frames, trigger event, push post-frames → MP4 created."""
        writer = EventClipWriter(events_dir=tmp_path, pre_frames=5, post_frames=3, fps=10.0)
        # Pre-event frames
        for _ in range(5):
            writer.push_frame(_make_frame())
        # Trigger event
        writer.begin_event(frame_id=5)
        # Push post-event frames via writer (clips collect from push_frame)
        completed_paths: list[Path] = []
        for i in range(4):  # 3 post + 1 extra to ensure completion
            paths = writer.push_frame(_make_frame())
            completed_paths.extend(paths)

        assert len(completed_paths) >= 1, "Expected at least one completed clip"
        clip = completed_paths[0]
        assert clip.exists(), f"Clip file not found: {clip}"
        assert clip.stat().st_size > 0, "Clip file is empty"
        assert clip.suffix == ".mp4"

    def test_finalize_all_writes_pending(self, tmp_path):
        """finalize_all() should write even partially-filled captures."""
        writer = EventClipWriter(events_dir=tmp_path, pre_frames=3, post_frames=30, fps=10.0)
        for _ in range(3):
            writer.push_frame(_make_frame())
        writer.begin_event(frame_id=3)
        # Only push 2 post frames (less than post_frames=30)
        for _ in range(2):
            writer.push_frame(_make_frame())
        paths = writer.finalize_all()
        assert len(paths) >= 1
        assert paths[0].exists()

    def test_clip_filename_contains_frame_id(self, tmp_path):
        writer = EventClipWriter(events_dir=tmp_path, pre_frames=2, post_frames=2, fps=10.0)
        for _ in range(2):
            writer.push_frame(_make_frame())
        writer.begin_event(frame_id=42)
        all_paths = []
        for _ in range(3):  # push extra frames to trigger completion
            all_paths.extend(writer.push_frame(_make_frame()))
        all_paths.extend(writer.finalize_all())
        assert len(all_paths) >= 1, "Expected at least one clip"
        assert any("000042" in p.name for p in all_paths)
