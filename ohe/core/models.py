"""
core/models.py
--------------
Central data-transfer objects (dataclasses) used throughout the OHE pipeline.
All fields are intentionally kept plain Python types / numpy arrays for
easy serialisation and cross-module use without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Ingestion layer
# ---------------------------------------------------------------------------

@dataclass
class RawFrame:
    """A single frame as delivered by a FrameProvider."""

    frame_id: int
    """Zero-based index of the frame within the current session."""

    timestamp_ms: float
    """Timestamp in milliseconds from the start of the video/session."""

    image: np.ndarray
    """BGR image array, shape (H, W, 3), dtype uint8."""

    source: str = ""
    """Human-readable source identifier (file path, camera ID, …)."""


# ---------------------------------------------------------------------------
# Processing layer
# ---------------------------------------------------------------------------

@dataclass
class ProcessedFrame:
    """Frame after pre-processing (ROI crop, colour conversion, enhancement)."""

    raw: RawFrame
    roi_image: np.ndarray
    """Cropped + enhanced grayscale image; shape (H', W'), dtype uint8."""

    roi_offset_x: int = 0
    """Pixel offset of the ROI's left edge in the original frame."""

    roi_offset_y: int = 0
    """Pixel offset of the ROI's top edge in the original frame."""


@dataclass
class WireCandidate:
    """Output of the wire detector — pixel-space wire geometry."""

    frame_id: int
    timestamp_ms: float

    # Wire bounding box in ROI-local pixel coordinates
    bbox_x: int = 0       # left
    bbox_y: int = 0       # top
    bbox_w: int = 0       # width
    bbox_h: int = 0       # height

    # Centre pixel of the wire (ROI-local)
    centre_x: float = 0.0
    centre_y: float = 0.0

    # Wire diameter estimate in pixels
    diameter_px: float = 0.0

    # Confidence score [0.0, 1.0]
    confidence: float = 0.0

    # Binary wire mask (ROI-local), dtype bool; may be None if not produced
    mask: Optional[np.ndarray] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Measurement layer
# ---------------------------------------------------------------------------

@dataclass
class Measurement:
    """Real-world measurement derived from a WireCandidate + calibration."""

    frame_id: int
    timestamp_ms: float

    stagger_mm: Optional[float]
    """Horizontal offset from track centre (mm). Positive = right of centre."""

    diameter_mm: Optional[float]
    """Contact wire diameter (mm)."""

    confidence: float
    """Detector confidence propagated from WireCandidate."""

    # Bounding box in original (full-frame) pixel coordinates
    wire_bbox: Optional[Tuple[int, int, int, int]] = None   # (x, y, w, h)

    # Wire centre in original frame coordinates
    wire_centre_px: Optional[Tuple[float, float]] = None    # (cx, cy)

    def is_valid(self) -> bool:
        """Return True if both stagger and diameter are available."""
        return self.stagger_mm is not None and self.diameter_mm is not None


# ---------------------------------------------------------------------------
# Rules / anomaly layer
# ---------------------------------------------------------------------------

@dataclass
class Anomaly:
    """A threshold violation produced by the RulesEngine."""

    frame_id: int
    timestamp_ms: float

    anomaly_type: str
    """One of: STAGGER_RIGHT, STAGGER_LEFT, DIAMETER_LOW, DIAMETER_HIGH."""

    value: float
    """The offending measured value."""

    threshold: float
    """The threshold that was breached."""

    severity: str
    """'WARNING' or 'CRITICAL'."""

    message: str = ""
    """Human-readable description."""


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------

@dataclass
class SessionInfo:
    """Metadata for a single processing session."""

    session_id: str
    """Unique identifier (e.g. ISO timestamp string)."""

    source: str
    """Video file path or camera identifier."""

    started_at_ms: float
    """Wall-clock start time (epoch ms)."""

    ended_at_ms: Optional[float] = None
    total_frames: int = 0
    anomaly_count: int = 0
    notes: str = ""
