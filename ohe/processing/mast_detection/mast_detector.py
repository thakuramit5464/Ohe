"""
processing/mast_detection/mast_detector.py
-------------------------------------------
Classical CV mast detector using vertical edge analysis.

Detection pipeline (per frame)
--------------------------------
1. Convert BGR frame to grayscale
2. Apply Sobel X operator  →  vertical edge magnitude
3. Threshold + morphological close  →  binary mask
4. Find external contours
5. Filter by:
   a. Bounding-box area  (≥ min_contour_area)
   b. Aspect ratio        (min_aspect_ratio ≤ H/W ≤ max_aspect_ratio)
   c. Lateral position    (left or right side_zone_fraction of frame)
6. Score remaining candidates by edge density inside their bbox

Returns a list of (bbox, confidence) tuples.
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from ohe.core.config import MastDetectionConfig

logger = logging.getLogger(__name__)

# Named tuple-like return type (kept as plain tuple for simplicity)
# (x, y, w, h), confidence_score
MastCandidate = tuple[tuple[int, int, int, int], float]


class MastDetector:
    """Detect mast candidates in a single BGR frame using classical CV."""

    def __init__(self, config: MastDetectionConfig) -> None:
        self._cfg = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> list[MastCandidate]:
        """Detect mast candidates in *frame*.

        Args:
            frame: BGR image array, shape (H, W, 3), dtype uint8.

        Returns:
            List of ``(bbox, confidence)`` tuples where
            ``bbox = (x, y, w, h)`` in frame-absolute pixel coordinates and
            ``confidence`` ∈ [0, 1].  Empty list when nothing is found or
            detection is disabled.
        """
        if not self._cfg.enabled:
            return []

        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

        # Step 1: Vertical edge magnitude via Sobel X
        edge_map = self._vertical_edges(gray)

        # Step 2: Binary mask
        _, binary = cv2.threshold(
            edge_map, self._cfg.edge_threshold, 255, cv2.THRESH_BINARY
        )

        # Step 3: Morphological close to bridge small vertical gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        # Step 4: Find contours
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return []

        # Step 5: Filter + score
        candidates: list[MastCandidate] = []
        side_px = int(w * self._cfg.side_zone_fraction)

        for contour in contours:
            bbox = cv2.boundingRect(contour)
            x, y, bw, bh = bbox
            area = bw * bh

            if area < self._cfg.min_contour_area:
                continue

            aspect = bh / max(bw, 1)
            if not (self._cfg.min_aspect_ratio <= aspect <= self._cfg.max_aspect_ratio):
                continue

            # Lateral zone: mast must be near left or right edge
            centre_x = x + bw // 2
            in_left_zone  = centre_x <= side_px
            in_right_zone = centre_x >= (w - side_px)
            if not (in_left_zone or in_right_zone):
                continue

            # Confidence: fraction of bbox area covered by edges
            roi_edges = binary[y : y + bh, x : x + bw]
            edge_density = float(np.count_nonzero(roi_edges)) / max(area, 1)
            confidence = min(1.0, edge_density * 3.0)   # scale so ~0.33 density → 1.0

            candidates.append((bbox, confidence))
            logger.debug(
                "Mast candidate: bbox=%s aspect=%.1f conf=%.2f",
                bbox, aspect, confidence,
            )

        return candidates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _vertical_edges(self, gray: np.ndarray) -> np.ndarray:
        """Compute absolute Sobel X response (vertical edge magnitude)."""
        sobel = cv2.Sobel(
            gray, cv2.CV_64F, 1, 0, ksize=self._cfg.sobel_ksize
        )
        # Convert to uint8 magnitude
        magnitude = np.abs(sobel)
        magnitude = np.clip(magnitude / magnitude.max() * 255, 0, 255).astype(np.uint8) \
            if magnitude.max() > 0 else magnitude.astype(np.uint8)
        return magnitude
