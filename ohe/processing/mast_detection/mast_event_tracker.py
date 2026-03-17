"""
processing/mast_detection/mast_event_tracker.py
------------------------------------------------
Temporal consistency filter for mast candidates.

Logic
-----
* Internally maintains a list of *tracked candidates*, each counting how many
  consecutive frames it has been seen.
* A NEW candidate (from MastDetector.detect()) is matched to an existing track
  if its bounding box overlaps with IoU ≥ iou_threshold.
* When a track's frame count reaches min_frames_to_confirm a MastEvent is
  emitted and the track enters "confirmed" state (no repeat events until the
  candidate leaves the frame for at least one frame).
* Tracks that receive no match in a frame are decremented; those that reach
  zero are dropped.
"""

from __future__ import annotations

import logging
from typing import Optional

from ohe.core.config import MastDetectionConfig
from ohe.core.models import MastEvent
from ohe.processing.mast_detection.mast_detector import MastCandidate

logger = logging.getLogger(__name__)


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Compute Intersection-over-Union of two (x, y, w, h) bounding boxes."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    ix = max(ax, bx)
    iy = max(ay, by)
    ix2 = min(ax + aw, bx + bw)
    iy2 = min(ay + ah, by + bh)

    if ix2 <= ix or iy2 <= iy:
        return 0.0

    inter = (ix2 - ix) * (iy2 - iy)
    union = aw * ah + bw * bh - inter
    return inter / max(union, 1)


class _Track:
    """Internal track record for a mast candidate."""

    def __init__(
        self,
        bbox: tuple[int, int, int, int],
        confidence: float,
    ) -> None:
        self.bbox        = bbox
        self.confidence  = confidence
        self.frame_count = 1      # frames seen so far
        self.confirmed   = False  # True once event has been emitted
        self.missed      = 0      # consecutive frames not matched

    def update(self, bbox: tuple[int, int, int, int], confidence: float) -> None:
        self.bbox       = bbox
        self.confidence = max(self.confidence, confidence)
        self.frame_count += 1
        self.missed = 0


class MastEventTracker:
    """Maintain temporal consistency and emit confirmed MastEvents."""

    def __init__(self, config: MastDetectionConfig) -> None:
        self._cfg    = config
        self._tracks: list[_Track] = []
        # Max frames a track can be "missing" before it is dropped
        self._max_missed = 5

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        candidates: list[MastCandidate],
        frame_id: int,
        timestamp_ms: float,
        chainage_m: float,
        last_mast_chainage_m: Optional[float],
    ) -> Optional[MastEvent]:
        """Update tracks with new candidates; return MastEvent if confirmed.

        Args:
            candidates:           List of (bbox, confidence) from MastDetector.
            frame_id:             Current frame index.
            timestamp_ms:         Frame timestamp.
            chainage_m:           Current track chainage.
            last_mast_chainage_m: Chainage of the previous confirmed mast,
                                  or None if no mast confirmed yet.

        Returns:
            :class:`MastEvent` when a mast is newly confirmed, else ``None``.
        """
        matched_tracks: set[int] = set()

        # --- Match incoming candidates to existing tracks ---------------
        for bbox, conf in candidates:
            best_idx   = -1
            best_score = self._cfg.iou_threshold  # minimum to match

            for i, track in enumerate(self._tracks):
                score = _iou(bbox, track.bbox)
                if score > best_score:
                    best_score = score
                    best_idx   = i

            if best_idx >= 0:
                self._tracks[best_idx].update(bbox, conf)
                matched_tracks.add(best_idx)
            else:
                # New candidate — start a new track
                self._tracks.append(_Track(bbox, conf))
                matched_tracks.add(len(self._tracks) - 1)

        # --- Mark unmatched tracks as missed ----------------------------
        for i, track in enumerate(self._tracks):
            if i not in matched_tracks:
                track.missed += 1

        # --- Check for newly confirmed tracks ---------------------------
        event: Optional[MastEvent] = None

        for track in self._tracks:
            if (
                not track.confirmed
                and track.frame_count >= self._cfg.min_frames_to_confirm
                and track.missed == 0
            ):
                track.confirmed = True
                spacing = (
                    chainage_m - last_mast_chainage_m
                    if last_mast_chainage_m is not None
                    else None
                )
                event = MastEvent(
                    frame_id    = frame_id,
                    timestamp_ms= timestamp_ms,
                    chainage_m  = chainage_m,
                    confidence  = track.confidence,
                    mast_spacing_m = spacing,
                    mast_bbox   = track.bbox,
                )
                logger.info(
                    "Mast confirmed  frame=%d  chainage=%.1fm  spacing=%s  conf=%.2f",
                    frame_id, chainage_m,
                    f"{spacing:.1f}m" if spacing is not None else "first",
                    track.confidence,
                )
                # Only emit one event per update cycle
                break

        # --- Drop stale tracks -----------------------------------------
        self._tracks = [t for t in self._tracks if t.missed <= self._max_missed]

        return event

    def reset(self) -> None:
        """Clear all tracks (call at session start)."""
        self._tracks.clear()
