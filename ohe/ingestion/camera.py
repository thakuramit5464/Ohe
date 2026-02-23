"""
ingestion/camera.py
-------------------
Stub FrameProvider for live camera input.
Will be fully implemented in a later phase when hardware is available.
"""

from __future__ import annotations

import logging

from ohe.core.exceptions import IngestionError
from ohe.core.models import RawFrame
from ohe.ingestion.base import FrameProvider

logger = logging.getLogger(__name__)


class CameraProvider(FrameProvider):
    """Live camera frame provider — STUB (Phase 2+)."""

    def __init__(self, camera_index: int = 0) -> None:
        self._index = camera_index

    def open(self) -> None:
        raise IngestionError(
            "CameraProvider is not yet implemented. Use VideoFileProvider for offline processing."
        )

    def close(self) -> None:
        pass

    def next_frame(self) -> RawFrame | None:
        raise IngestionError("CameraProvider is not yet implemented.")

    @property
    def source_id(self) -> str:
        return f"camera:{self._index}"
