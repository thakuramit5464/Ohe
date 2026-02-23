"""
processing/detector.py
-----------------------
Classical wire detector using Canny edges + Hough line transform.

Strategy
--------
1. Canny edge detection on the pre-processed (grayscale+CLAHE) image.
2. Probabilistic Hough Line Transform to find candidate line segments.
3. Filter lines by angle (near-horizontal wires only by default).
4. Cluster nearby lines → elect a single "best wire" candidate.
5. Return a :class:`WireCandidate` with pixel-space geometry.

Wire diameter estimation:
  After selecting the dominant line, we measure the thickness of the
  edge band it sits in via perpendicular intensity profile fitting.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import cv2
import numpy as np

from ohe.core.config import ProcessingConfig
from ohe.core.models import ProcessedFrame, WireCandidate

logger = logging.getLogger(__name__)

# Angle tolerance around horizontal (degrees). Wires are roughly horizontal.
_WIRE_ANGLE_TOLERANCE_DEG = 30.0


class WireDetector:
    """Detects the contact wire in a :class:`ProcessedFrame`."""

    def __init__(self, config: ProcessingConfig) -> None:
        self._cfg = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, pf: ProcessedFrame) -> WireCandidate:
        """Detect the contact wire in *pf* and return a :class:`WireCandidate`.

        If no wire is found, returns a candidate with ``confidence=0.0``.
        """
        img = pf.roi_image  # grayscale, enhanced

        # Step 1 — Canny edges
        edges = cv2.Canny(
            img,
            self._cfg.canny_threshold1,
            self._cfg.canny_threshold2,
        )

        # Step 2 — Probabilistic Hough lines
        lines = cv2.HoughLinesP(
            edges,
            rho=self._cfg.hough_rho,
            theta=math.radians(self._cfg.hough_theta_deg),
            threshold=self._cfg.hough_threshold,
            minLineLength=self._cfg.hough_min_line_length,
            maxLineGap=self._cfg.hough_max_line_gap,
        )

        if lines is None or len(lines) == 0:
            logger.debug("Frame %d: no Hough lines found", pf.raw.frame_id)
            return self._empty_candidate(pf)

        # Step 3 — Filter to near-horizontal lines
        wire_lines = self._filter_horizontal(lines)
        if not wire_lines:
            logger.debug("Frame %d: no near-horizontal lines after filter", pf.raw.frame_id)
            return self._empty_candidate(pf)

        # Step 4 — Cluster and elect best wire line
        best_line = self._elect_wire_line(wire_lines, img.shape)

        # Step 5 — Build candidate from elected line
        candidate = self._build_candidate(pf, best_line, edges)
        logger.debug(
            "Frame %d: wire detected — centre=(%.1f, %.1f) conf=%.2f",
            pf.raw.frame_id, candidate.centre_x, candidate.centre_y, candidate.confidence,
        )
        return candidate

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter_horizontal(
        self, lines: np.ndarray
    ) -> list[tuple[int, int, int, int]]:
        """Keep only lines within ±_WIRE_ANGLE_TOLERANCE_DEG of horizontal."""
        result: list[tuple[int, int, int, int]] = []
        tol = _WIRE_ANGLE_TOLERANCE_DEG
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = x2 - x1
            dy = y2 - y1
            angle_deg = abs(math.degrees(math.atan2(dy, dx)))
            # Normalise to [0, 90]
            if angle_deg > 90:
                angle_deg = 180 - angle_deg
            if angle_deg <= tol:
                result.append((x1, y1, x2, y2))
        return result

    def _elect_wire_line(
        self,
        lines: list[tuple[int, int, int, int]],
        img_shape: tuple[int, ...],
    ) -> tuple[int, int, int, int]:
        """Pick the longest near-horizontal line as the wire candidate."""
        best: Optional[tuple[int, int, int, int]] = None
        best_len_sq = -1
        for x1, y1, x2, y2 in lines:
            len_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
            if len_sq > best_len_sq:
                best_len_sq = len_sq
                best = (x1, y1, x2, y2)
        return best  # type: ignore[return-value]

    def _build_candidate(
        self,
        pf: ProcessedFrame,
        line: tuple[int, int, int, int],
        edges: np.ndarray,
    ) -> WireCandidate:
        """Convert a raw Hough line into a WireCandidate."""
        x1, y1, x2, y2 = line
        h, w = pf.roi_image.shape[:2]

        # Wire centre in ROI-local coords
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        # Estimate wire thickness via vertical edge profile at centre column
        diameter_px = self._estimate_diameter(edges, int(cx), int(cy))

        # Bounding box around the line (padded by diameter estimate)
        pad = max(int(diameter_px / 2), 2)
        bx = max(0, min(x1, x2) - pad)
        by = max(0, int(cy) - pad)
        bw = min(w - bx, abs(x2 - x1) + 2 * pad)
        bh = min(h - by, 2 * pad)

        # Confidence: ratio of line length to image width
        line_len = math.hypot(x2 - x1, y2 - y1)
        confidence = min(1.0, line_len / w)

        return WireCandidate(
            frame_id=pf.raw.frame_id,
            timestamp_ms=pf.raw.timestamp_ms,
            bbox_x=bx,
            bbox_y=by,
            bbox_w=bw,
            bbox_h=bh,
            centre_x=cx,
            centre_y=cy,
            diameter_px=diameter_px,
            confidence=confidence,
        )

    @staticmethod
    def _estimate_diameter(edges: np.ndarray, cx: int, cy: int, search_radius: int = 20) -> float:
        """Estimate wire diameter in pixels by counting vertical edge pixels.

        Looks at a vertical column of the edge image centred at (cx, cy)
        and counts the span between the first and last active edge pixels.
        Returns a default of 4.0 px if nothing is found.
        """
        h = edges.shape[0]
        col_start = max(0, cy - search_radius)
        col_end = min(h, cy + search_radius)
        col = edges[col_start:col_end, cx]
        edge_rows = np.where(col > 0)[0]
        if len(edge_rows) >= 2:
            return float(edge_rows[-1] - edge_rows[0] + 1)
        return 4.0  # fallback

    @staticmethod
    def _empty_candidate(pf: ProcessedFrame) -> WireCandidate:
        return WireCandidate(
            frame_id=pf.raw.frame_id,
            timestamp_ms=pf.raw.timestamp_ms,
            confidence=0.0,
        )
