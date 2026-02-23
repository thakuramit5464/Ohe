"""
ingestion/base.py
-----------------
Abstract base class for all frame providers.

Concrete implementations (VideoFileProvider, CameraProvider, …) must
implement ``next_frame()`` and the context manager protocol.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from ohe.core.models import RawFrame


class FrameProvider(ABC):
    """Interface contract for anything that yields :class:`RawFrame` objects."""

    @abstractmethod
    def open(self) -> None:
        """Open/initialise the source. Called once before iteration."""

    @abstractmethod
    def close(self) -> None:
        """Release resources held by the provider."""

    @abstractmethod
    def next_frame(self) -> RawFrame | None:
        """Return the next :class:`RawFrame`, or ``None`` at end-of-stream."""

    # ------------------------------------------------------------------
    # Convenience: iterable + context manager
    # ------------------------------------------------------------------

    def frames(self) -> Iterator[RawFrame]:
        """Yield frames until end-of-stream."""
        while True:
            frame = self.next_frame()
            if frame is None:
                return
            yield frame

    def __enter__(self) -> "FrameProvider":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Optional metadata
    # ------------------------------------------------------------------

    @property
    def fps(self) -> float:
        """Native FPS of the source. Override in subclasses."""
        return 0.0

    @property
    def frame_count(self) -> int:
        """Total frame count if known, else -1."""
        return -1

    @property
    def source_id(self) -> str:
        """Human-readable source identifier."""
        return ""
