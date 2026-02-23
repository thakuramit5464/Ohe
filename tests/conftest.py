"""
conftest.py
-----------
Shared pytest fixtures for the OHE test suite.
"""

from __future__ import annotations

import numpy as np
import pytest

from ohe.core.models import RawFrame, ProcessedFrame
from ohe.processing.calibration import CalibrationModel


# ---------------------------------------------------------------------------
# Reusable fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_bgr_frame() -> RawFrame:
    """A 200×400 BGR frame filled with random noise."""
    img = np.random.randint(0, 256, (200, 400, 3), dtype=np.uint8)
    return RawFrame(frame_id=0, timestamp_ms=0.0, image=img, source="fixture")


@pytest.fixture
def wire_bgr_frame() -> RawFrame:
    """A 200×800 BGR frame with a bright horizontal wire at y=100."""
    img = np.zeros((200, 800, 3), dtype=np.uint8)
    img[97:104, :] = 220   # 7-pixel bright wire band
    return RawFrame(frame_id=0, timestamp_ms=0.0, image=img, source="fixture_wire")


@pytest.fixture
def default_calibration() -> CalibrationModel:
    """10 px/mm, 800-wide frame, centre at x=400."""
    return CalibrationModel(
        px_per_mm=10.0,
        track_centre_x_px=400,
        image_width_px=800,
        image_height_px=200,
    )
