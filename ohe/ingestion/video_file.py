"""
ingestion/video_file.py
-----------------------
FrameProvider implementation for local video files (MP4, AVI, MKV, …).

Uses OpenCV VideoCapture. Supports:
* Frame skipping (``frame_skip``)
* Target FPS sub-sampling (``target_fps``)
* Optional start/end frame window
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2

from ohe.core.exceptions import EndOfStreamError, IngestionError
from ohe.core.models import RawFrame
from ohe.ingestion.base import FrameProvider

logger = logging.getLogger(__name__)


class VideoFileProvider(FrameProvider):
    """Reads frames from a local video file via OpenCV VideoCapture."""

    def __init__(
        self,
        path: str | Path,
        frame_skip: int = 1,
        target_fps: float = 0.0,
        start_frame: int = 0,
        end_frame: int = -1,
    ) -> None:
        """
        Args:
            path:        Path to the video file.
            frame_skip:  Process every Nth frame (1 = every frame).
            target_fps:  If > 0, sleep between frames to match this rate.
                         Useful for real-time simulation. 0 = as fast as possible.
            start_frame: Zero-based index of the first frame to yield.
            end_frame:   Last frame index to yield (-1 = until end of file).
        """
        self._path = Path(path)
        self._frame_skip = max(1, frame_skip)
        self._target_fps = target_fps
        self._start_frame = start_frame
        self._end_frame = end_frame

        self._cap: cv2.VideoCapture | None = None
        self._frame_id: int = 0
        self._native_fps: float = 0.0
        self._total_frames: int = -1

    # ------------------------------------------------------------------
    # FrameProvider implementation
    # ------------------------------------------------------------------

    def open(self) -> None:
        if not self._path.exists():
            raise IngestionError(f"Video file not found: {self._path}")

        self._cap = cv2.VideoCapture(str(self._path))
        if not self._cap.isOpened():
            raise IngestionError(f"OpenCV could not open video: {self._path}")

        self._native_fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Seek to start frame if requested
        if self._start_frame > 0:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._start_frame)
            self._frame_id = self._start_frame

        logger.info(
            "Opened video: %s | %.1f fps | %d frames",
            self._path.name, self._native_fps, self._total_frames,
        )

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.debug("VideoFileProvider closed: %s", self._path.name)

    def next_frame(self) -> RawFrame | None:
        if self._cap is None:
            raise IngestionError("Provider not opened. Call open() first.")

        _frame_interval = 1.0 / self._target_fps if self._target_fps > 0 else 0.0
        _last_yield_time: float = 0.0

        # Skip frames (read & discard)
        for _ in range(self._frame_skip - 1):
            ret = self._cap.grab()
            if not ret:
                return None
            self._frame_id += 1

        # Read the actual frame
        ret, image = self._cap.read()
        if not ret or image is None:
            return None

        if self._end_frame >= 0 and self._frame_id > self._end_frame:
            return None

        timestamp_ms = self._cap.get(cv2.CAP_PROP_POS_MSEC)
        frame = RawFrame(
            frame_id=self._frame_id,
            timestamp_ms=timestamp_ms,
            image=image,
            source=str(self._path),
        )
        self._frame_id += self._frame_skip

        # Rate limiting
        if _frame_interval > 0:
            elapsed = time.monotonic() - _last_yield_time
            if elapsed < _frame_interval:
                time.sleep(_frame_interval - elapsed)
            _last_yield_time = time.monotonic()

        return frame

    # ------------------------------------------------------------------
    # Metadata properties
    # ------------------------------------------------------------------

    @property
    def fps(self) -> float:
        return self._native_fps

    @property
    def frame_count(self) -> int:
        return self._total_frames

    @property
    def source_id(self) -> str:
        return str(self._path)
