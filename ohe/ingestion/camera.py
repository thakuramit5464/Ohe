"""
ingestion/camera.py
-------------------
FrameProvider implementation for live camera input via OpenCV VideoCapture.

Supports:
* Any camera index recognised by OpenCV (0 = default system camera)
* Configurable target FPS (rate-limiting via sleep)
* Frame-skip for performance

When no camera hardware is connected, ``open()`` raises :class:`IngestionError`
with a clear message so the GUI can surface a helpful dialog instead of crashing.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2

from ohe.core.exceptions import IngestionError
from ohe.core.models import RawFrame
from ohe.ingestion.base import FrameProvider

logger = logging.getLogger(__name__)


class CameraProvider(FrameProvider):
    """
    Live camera frame provider backed by ``cv2.VideoCapture``.

    Parameters
    ----------
    camera_index:   OpenCV camera index (0 = first/default camera).
    target_fps:     If > 0, sleep between frames to cap at this rate.
                    0 = capture as fast as the camera allows.
    frame_skip:     Grab-and-discard every N-1 frames, yield every Nth.
    """

    def __init__(
        self,
        camera_index: int = 0,
        target_fps: float = 0.0,
        frame_skip: int = 1,
    ) -> None:
        self._index       = camera_index
        self._target_fps  = target_fps
        self._frame_skip  = max(1, frame_skip)
        self._cap: cv2.VideoCapture | None = None
        self._frame_id: int = 0
        self._native_fps: float = 0.0
        self._last_yield_time: float = 0.0

    # ------------------------------------------------------------------
    # FrameProvider implementation
    # ------------------------------------------------------------------

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self._index)
        if not self._cap.isOpened():
            self._cap = None
            raise IngestionError(
                f"Could not open camera at index {self._index}. "
                "Check that a camera is connected and not in use by another application."
            )
        self._native_fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._frame_id   = 0
        logger.info(
            "Camera opened: index=%d | reported %.1f fps",
            self._index, self._native_fps,
        )

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.debug("CameraProvider closed: index=%d", self._index)

    def next_frame(self) -> RawFrame | None:
        if self._cap is None:
            raise IngestionError("CameraProvider not opened. Call open() first.")

        _frame_interval = 1.0 / self._target_fps if self._target_fps > 0 else 0.0

        # Skip frames
        for _ in range(self._frame_skip - 1):
            ret = self._cap.grab()
            if not ret:
                return None
            self._frame_id += 1

        ret, image = self._cap.read()
        if not ret or image is None:
            logger.warning("CameraProvider: failed to read frame (camera disconnected?)")
            return None

        # Wall-clock timestamp (ms) — cameras don't provide reliable video timestamps
        timestamp_ms = time.time() * 1000.0

        frame = RawFrame(
            frame_id=self._frame_id,
            timestamp_ms=timestamp_ms,
            image=image,
            source=f"camera:{self._index}",
        )
        self._frame_id += self._frame_skip

        # Rate limiting
        if _frame_interval > 0:
            elapsed = time.monotonic() - self._last_yield_time
            if elapsed < _frame_interval:
                time.sleep(_frame_interval - elapsed)
        self._last_yield_time = time.monotonic()

        return frame

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def fps(self) -> float:
        return self._target_fps if self._target_fps > 0 else self._native_fps

    @property
    def frame_count(self) -> int:
        return -1   # live camera — total frames unknown

    @property
    def source_id(self) -> str:
        return f"camera:{self._index}"
