"""
processing/detector.py  (Phase 2 — improved)
---------------------------------------------
Classical wire detector using Canny edges + Probabilistic Hough lines.

Key improvements over Phase 1
------------------------------
1. **ROI-relative confidence** — confidence is now the fraction of the ROI
   width covered by the elected line, not the full image width.
2. **Lowest-wire selection** — among all near-horizontal candidates,
   the *lowest* line (highest Y, closest to the pantograph) is elected as
   the contact wire, not the longest one.
3. **Line-cluster voting** — nearby parallel lines are merged into cluster
   representatives before election, suppressing duplicate detections.
4. **Gaussian profile diameter** — a vertical intensity profile is fitted
   with a 1-D Gaussian to get a sub-pixel width estimate, replacing the
   crude edge-span count.
5. **Diagnostic mode** — ``detect_debug()`` returns an annotated BGR image
   for the debug visualiser without altering the normal detection path.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import cv2
import numpy as np
from scipy.optimize import curve_fit  # type: ignore[import-untyped]

from ohe.core.config import ProcessingConfig
from ohe.core.models import ProcessedFrame, WireCandidate

logger = logging.getLogger(__name__)

# Contact wire is expected within ±30° of horizontal
_WIRE_ANGLE_TOLERANCE_DEG = 30.0
# Lines whose mid-Y values are within this many pixels are considered one cluster
_CLUSTER_Y_TOLERANCE_PX = 8


class WireDetector:
    """Detects the contact wire in a :class:`ProcessedFrame`."""

    def __init__(self, config: ProcessingConfig) -> None:
        self._cfg = config

    # ------------------------------------------------------------------
    # Public API — normal detection
    # ------------------------------------------------------------------

    def detect(self, pf: ProcessedFrame) -> WireCandidate:
        """Detect contact wire; return :class:`WireCandidate` (conf=0 if not found)."""
        lines = self._find_hough_lines(pf.roi_image)
        if lines is None:
            return self._empty(pf)

        horizontal = self._filter_horizontal(lines)
        if not horizontal:
            return self._empty(pf)

        clusters = self._cluster_lines(horizontal)
        best = self._elect_lowest_wire(clusters)
        return self._build_candidate(pf, best)

    # ------------------------------------------------------------------
    # Public API — debug / visualiser hook
    # ------------------------------------------------------------------

    def detect_debug(self, pf: ProcessedFrame) -> tuple[WireCandidate, np.ndarray]:
        """Same as :meth:`detect` but also returns an annotated BGR overlay image.

        The returned image has the same dimensions as ``pf.roi_image`` but is
        converted to BGR so colours can be drawn on it.
        """
        dbg = cv2.cvtColor(pf.roi_image, cv2.COLOR_GRAY2BGR)

        lines = self._find_hough_lines(pf.roi_image)
        if lines is None:
            return self._empty(pf), dbg

        # Draw all Hough lines in blue
        for x1, y1, x2, y2 in lines:
            cv2.line(dbg, (x1, y1), (x2, y2), (255, 150, 0), 1)

        horizontal = self._filter_horizontal(lines)
        # Draw horizontal-filtered lines in yellow
        for x1, y1, x2, y2 in horizontal:
            cv2.line(dbg, (x1, y1), (x2, y2), (0, 255, 255), 1)

        if not horizontal:
            return self._empty(pf), dbg

        clusters = self._cluster_lines(horizontal)
        best = self._elect_lowest_wire(clusters)

        # Draw elected wire in green, thick
        x1, y1, x2, y2 = best
        cv2.line(dbg, (x1, y1), (x2, y2), (0, 255, 0), 3)

        cand = self._build_candidate(pf, best)

        # Draw wire centre and bbox
        if cand.confidence > 0:
            cx, cy = int(cand.centre_x), int(cand.centre_y)
            cv2.circle(dbg, (cx, cy), 5, (0, 0, 255), -1)
            cv2.rectangle(
                dbg,
                (cand.bbox_x, cand.bbox_y),
                (cand.bbox_x + cand.bbox_w, cand.bbox_y + cand.bbox_h),
                (0, 200, 0), 1,
            )
            label = f"conf={cand.confidence:.2f} diam={cand.diameter_px:.1f}px"
            cv2.putText(dbg, label, (cx - 60, cy - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        return cand, dbg

    # ------------------------------------------------------------------
    # Step 1: Canny + Hough
    # ------------------------------------------------------------------

    def _find_hough_lines(
        self, img: np.ndarray
    ) -> Optional[list[tuple[int, int, int, int]]]:
        edges = cv2.Canny(img, self._cfg.canny_threshold1, self._cfg.canny_threshold2)
        raw = cv2.HoughLinesP(
            edges,
            rho=self._cfg.hough_rho,
            theta=math.radians(self._cfg.hough_theta_deg),
            threshold=self._cfg.hough_threshold,
            minLineLength=self._cfg.hough_min_line_length,
            maxLineGap=self._cfg.hough_max_line_gap,
        )
        if raw is None or len(raw) == 0:
            return None
        return [tuple(r[0]) for r in raw]  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Step 2: filter to near-horizontal lines
    # ------------------------------------------------------------------

    def _filter_horizontal(
        self, lines: list[tuple[int, int, int, int]]
    ) -> list[tuple[int, int, int, int]]:
        result = []
        tol = _WIRE_ANGLE_TOLERANCE_DEG
        for x1, y1, x2, y2 in lines:
            dx, dy = x2 - x1, y2 - y1
            angle = abs(math.degrees(math.atan2(dy, dx)))
            if angle > 90:
                angle = 180 - angle
            if angle <= tol:
                result.append((x1, y1, x2, y2))
        return result

    # ------------------------------------------------------------------
    # Step 3: cluster nearby lines by mid-Y
    # ------------------------------------------------------------------

    def _cluster_lines(
        self, lines: list[tuple[int, int, int, int]]
    ) -> list[tuple[int, int, int, int]]:
        """Merge lines whose mid-Y values are within _CLUSTER_Y_TOLERANCE_PX."""
        # Sort by mid-Y
        sorted_lines = sorted(lines, key=lambda l: (l[1] + l[3]) / 2)
        clusters: list[list[tuple[int, int, int, int]]] = []
        for line in sorted_lines:
            mid_y = (line[1] + line[3]) / 2
            placed = False
            for cluster in clusters:
                rep = cluster[0]
                rep_mid_y = (rep[1] + rep[3]) / 2
                if abs(mid_y - rep_mid_y) <= _CLUSTER_Y_TOLERANCE_PX:
                    cluster.append(line)
                    placed = True
                    break
            if not placed:
                clusters.append([line])

        # From each cluster, pick the longest line as representative
        representatives = []
        for cluster in clusters:
            best = max(cluster, key=lambda l: (l[2] - l[0]) ** 2 + (l[3] - l[1]) ** 2)
            representatives.append(best)
        return representatives

    # ------------------------------------------------------------------
    # Step 4: elect lowest (contact) wire — highest Y = closest to pantograph
    # ------------------------------------------------------------------

    def _elect_lowest_wire(
        self, lines: list[tuple[int, int, int, int]]
    ) -> tuple[int, int, int, int]:
        """Return the line whose midpoint has the highest Y value (lowest in image)."""
        return max(lines, key=lambda l: (l[1] + l[3]) / 2)

    # ------------------------------------------------------------------
    # Step 5: build WireCandidate with Gaussian diameter
    # ------------------------------------------------------------------

    def _build_candidate(
        self, pf: ProcessedFrame, line: tuple[int, int, int, int]
    ) -> WireCandidate:
        x1, y1, x2, y2 = line
        h, w = pf.roi_image.shape[:2]

        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        # Gaussian-fitted diameter
        diameter_px = self._gaussian_diameter(pf.roi_image, int(cx), int(cy))

        # Bounding box
        pad = max(int(diameter_px / 2) + 2, 4)
        bx = max(0, min(x1, x2) - pad)
        by = max(0, int(cy) - pad)
        bw = min(w - bx, abs(x2 - x1) + 2 * pad)
        bh = min(h - by, 2 * pad)

        # Confidence: fraction of ROI width covered (capped at 1.0)
        line_len = math.hypot(x2 - x1, y2 - y1)
        confidence = min(1.0, line_len / max(w, 1))

        return WireCandidate(
            frame_id=pf.raw.frame_id,
            timestamp_ms=pf.raw.timestamp_ms,
            bbox_x=bx, bbox_y=by, bbox_w=bw, bbox_h=bh,
            centre_x=cx, centre_y=cy,
            diameter_px=diameter_px,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Gaussian diameter estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _gaussian_diameter(
        img: np.ndarray, cx: int, cy: int, search_half: int = 25
    ) -> float:
        """Fit a 1-D Gaussian to a vertical intensity profile centred at (cx, cy).

        Returns the FWHM (full-width at half-maximum) as the wire diameter in px.
        Falls back to 4.0 px if the fit fails or the profile is featureless.
        """
        h = img.shape[0]
        y0 = max(0, cy - search_half)
        y1 = min(h, cy + search_half + 1)
        col = img[y0:y1, cx].astype(np.float64)
        if col.size < 5:
            return 4.0

        xs = np.arange(len(col), dtype=np.float64)
        # Initial guesses: amplitude=max, mean=centre, sigma=5
        peak_idx = int(np.argmax(col))
        amp0 = float(col[peak_idx])
        mu0 = float(peak_idx)
        sigma0 = 5.0
        baseline0 = float(col.min())

        if amp0 - baseline0 < 5:
            # Featureless column — no detectable wire
            return 4.0

        def _gaussian(x, amp, mu, sigma, baseline):
            return baseline + amp * np.exp(-0.5 * ((x - mu) / (sigma + 1e-9)) ** 2)

        try:
            popt, _ = curve_fit(
                _gaussian, xs, col,
                p0=[amp0 - baseline0, mu0, sigma0, baseline0],
                bounds=([0, 0, 0.5, 0], [255, len(col), search_half, 255]),
                maxfev=200,
            )
            sigma_fit = abs(popt[2])
            fwhm = 2.355 * sigma_fit   # FWHM = 2√(2 ln 2) · σ
            return max(1.0, min(fwhm, search_half * 2))
        except Exception:
            # Fall back to edge-span method
            edges = cv2.Canny(img[y0:y1, max(0, cx - 2):cx + 3], 30, 100)
            edge_rows = np.where(edges[:, 2] > 0)[0]
            if len(edge_rows) >= 2:
                return float(edge_rows[-1] - edge_rows[0] + 1)
            return 4.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty(pf: ProcessedFrame) -> WireCandidate:
        return WireCandidate(frame_id=pf.raw.frame_id, timestamp_ms=pf.raw.timestamp_ms, confidence=0.0)
