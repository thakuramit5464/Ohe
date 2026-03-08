"""
events/clip_writer.py
---------------------
EventClipWriter — captures a short video clip around each detected anomaly.

How it works
------------
1.  Every raw BGR frame is pushed into a fixed-size ring-buffer via
    ``push_frame()``.  The buffer retains the last ``pre_frames`` frames so
    that when an anomaly fires we already have the lead-up footage.

2.  ``begin_event()`` is called the moment an anomaly is detected.  It
    snapshots the current buffer contents (pre-event frames) and returns an
    ``EventCapture`` context that the caller feeds post-event frames into.

3.  ``EventCapture.add_frame()`` collects up to ``post_frames`` additional
    frames.  Once enough frames are collected (or ``finalize()`` is called),
    the capture writes an MP4 clip to ``events_dir`` and returns the path.

File naming
-----------
``event_<YYYYMMDD_HHMMSS>_f<frame_id>.mp4``
"""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path
from typing import Deque, List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class EventCapture:
    """
    Short-lived object returned by :meth:`EventClipWriter.begin_event`.

    Feed it post-event frames one by one; call :meth:`finalize` (or let
    :meth:`is_complete` go True) to write the clip.
    """

    def __init__(
        self,
        pre_frames: List[np.ndarray],
        post_frames_needed: int,
        output_path: Path,
        fps: float,
        frame_id: int,
    ) -> None:
        self._frames: List[np.ndarray] = list(pre_frames)
        self._post_needed   = post_frames_needed
        self._post_collected = 0
        self._output_path   = output_path
        self._fps           = fps
        self._frame_id      = frame_id
        self._written       = False
        self._clip_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def add_frame(self, frame: np.ndarray) -> Optional[Path]:
        """Add a post-event frame.  Returns the saved path when clip is done."""
        if self._written:
            return self._clip_path
        self._frames.append(frame)
        self._post_collected += 1
        if self._post_collected >= self._post_needed:
            return self._write()
        return None

    def finalize(self) -> Optional[Path]:
        """Force-write the clip even if post_frames quota not yet reached."""
        if not self._written and len(self._frames) > 0:
            return self._write()
        return self._clip_path

    @property
    def is_complete(self) -> bool:
        return self._written

    @property
    def clip_path(self) -> Optional[Path]:
        return self._clip_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write(self) -> Path:
        if not self._frames:
            logger.warning("EventCapture._write: no frames to write")
            self._written = True
            return self._output_path

        h, w = self._frames[0].shape[:2]
        self._output_path.parent.mkdir(parents=True, exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(self._output_path), fourcc, self._fps, (w, h))

        for f in self._frames:
            if f.shape[:2] == (h, w):
                writer.write(f)
            else:
                # Resize if a frame dimension changed (shouldn't happen, but safe)
                writer.write(cv2.resize(f, (w, h)))

        writer.release()
        self._written   = True
        self._clip_path = self._output_path
        logger.info(
            "Event clip saved: %s (%d frames @ %.1f fps)",
            self._output_path.name, len(self._frames), self._fps,
        )
        return self._output_path


class EventClipWriter:
    """
    Manages frame buffering and event clip creation.

    Parameters
    ----------
    events_dir:   Directory where MP4 clips are saved.
    pre_frames:   How many frames before the event to include.
    post_frames:  How many frames after the event to include.
    fps:          Frame-rate for the encoded clip.
    """

    def __init__(
        self,
        events_dir: Path,
        pre_frames: int = 90,
        post_frames: int = 60,
        fps: float = 25.0,
    ) -> None:
        self._events_dir  = Path(events_dir)
        self._pre_frames  = pre_frames
        self._post_frames = post_frames
        self._fps         = fps
        self._buffer: Deque[np.ndarray] = deque(maxlen=max(1, pre_frames))
        self._active_captures: List[EventCapture] = []
        self._clip_counter  = 0

    # ------------------------------------------------------------------
    # Per-frame feed
    # ------------------------------------------------------------------

    def push_frame(self, frame: np.ndarray) -> List[Path]:
        """
        Add a raw BGR frame to the ring-buffer.

        Also feeds the frame into any active :class:`EventCapture` objects.
        Returns a list of clip paths for captures that completed this frame.
        """
        # Feed active captures first (copy frame to avoid mutation)
        completed: List[Path] = []
        still_active: List[EventCapture] = []
        for cap in self._active_captures:
            path = cap.add_frame(frame.copy())
            if path is not None:
                completed.append(path)
            if not cap.is_complete:
                still_active.append(cap)
        self._active_captures = still_active

        # Then update the ring buffer
        self._buffer.append(frame.copy())
        return completed

    # ------------------------------------------------------------------
    # Event trigger
    # ------------------------------------------------------------------

    def begin_event(self, frame_id: int) -> EventCapture:
        """
        Trigger event clip capture around ``frame_id``.

        Returns an :class:`EventCapture` that will accumulate post-event
        frames from future :meth:`push_frame` calls automatically.
        """
        self._clip_counter += 1
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"event_{ts}_f{frame_id:06d}.mp4"
        output_path = self._events_dir / filename

        capture = EventCapture(
            pre_frames=list(self._buffer),
            post_frames_needed=self._post_frames,
            output_path=output_path,
            fps=self._fps,
            frame_id=frame_id,
        )
        self._active_captures.append(capture)
        logger.debug(
            "EventCapture started: frame_id=%d → %s", frame_id, filename
        )
        return capture

    def finalize_all(self) -> List[Path]:
        """Force-write any pending captures (call on pipeline stop)."""
        paths: List[Path] = []
        for cap in self._active_captures:
            p = cap.finalize()
            if p:
                paths.append(p)
        self._active_captures = []
        return paths
