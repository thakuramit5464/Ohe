"""
scripts/run_classical_cv_v2.py
--------------------------------
Enhanced classical CV pipeline for OHE contact-wire detection — v2.

Improvements over v1
---------------------
1. Temporal tracking (EMA smoothing)
   - Predicts wire position when detection fails using exponential moving average
   - Output stagger is always smoothed and stable

2. Improved wire selection
   - Selects the **longest** near-horizontal line (not just lowest)
   - Strict angle rejection (< ±25°)
   - Minimum confidence gate based on line_length / ROI_width

3. Adaptive ROI
   - After a successful detection the ROI is centered vertically around the
     detected wire position for the next frame (±ADAPT_HALF_HEIGHT px band)
   - Falls back to the global ROI when the tracker has no prior position

4. Richer CSV
   - Columns: frame, timestamp_ms, wire_center_x, stagger_px, confidence, source
   - source = "detected" | "tracked" | "lost"

5. Improved HUD overlay
   - Wire status badge:  ✓ Detected / ~ Tracked / ✗ Lost
   - Stagger value with sign (+/−) rendered with drop-shadow
   - Confidence bar (thin coloured bar below stagger text)
   - Frame + timestamp line
   - Adaptive ROI boundary drawn in cyan when active
   - Smoothed stagger ghost line (dimmed) vs raw line

Usage
-----
    .venv/bin/python scripts/run_classical_cv_v2.py
    .venv/bin/python scripts/run_classical_cv_v2.py \\
        --video video/inspection_video.mp4 \\
        --out   output/

Dependencies
------------
    opencv-python-headless, numpy
"""

from __future__ import annotations

import argparse
import csv
import datetime
import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("cv_v2")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_VIDEO   = "video/inspection_video.mp4"
DEFAULT_OUT_DIR = "output"

# Global ROI bounds (fraction of frame height)
ROI_TOP_FRAC    = 0.10   # search from 10 % of frame height
ROI_BOT_FRAC    = 0.75   # search until 75 % of frame height

# Adaptive ROI half-height (px around last known wire Y)
ADAPT_HALF_HEIGHT = 60   # ±60 px vertical band around tracked wire

# Pre-processing
CLAHE_CLIP     = 2.5
CLAHE_GRID     = (8, 8)
BLUR_K         = 5        # Gaussian kernel — must be odd

# Canny
CANNY_LO = 40
CANNY_HI = 130

# HoughLinesP
HOUGH_RHO      = 1
HOUGH_THETA    = math.radians(1)
HOUGH_THRESH   = 35
HOUGH_MIN_LEN  = 55
HOUGH_MAX_GAP  = 25

# Wire selection / filtering
ANGLE_TOL_DEG  = 25.0    # max deviation from horizontal
CLUSTER_Y_TOL  = 10      # Y-merge tolerance (px)
MIN_CONF       = 0.08    # minimum accepted confidence

# EMA smoothing (α → 1.0 = no smoothing, 0.0 = infinite inertia)
EMA_ALPHA      = 0.30    # applied to raw detections; smaller = smoother

# Colours (BGR)
_B_WIRE   = (220, 100,  10)   # blue wire
_B_CTR    = (  0, 220,   0)   # green centre line
_B_ARROW  = (  0,  40, 220)   # red stagger arrow
_B_TRK    = (  0, 200, 240)   # cyan tracked ghost
_B_WHITE  = (255, 255, 255)
_B_SHADOW = ( 10,  10,  10)
_B_WARN   = (  0, 100, 255)   # orange-red for lost

# ---------------------------------------------------------------------------
# Shared CLAHE instance (created once for performance)
# ---------------------------------------------------------------------------
_CLAHE = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_GRID)


# ===========================================================================
# Data classes
# ===========================================================================

@dataclass
class WireDetection:
    """Raw detection result in ROI-local pixel space."""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class FrameResult:
    """All measurements and metadata for one frame."""
    frame_id:      int
    timestamp_ms:  float
    source:        str           # "detected" | "tracked" | "lost"
    wire_cx_raw:   Optional[float] = None   # raw (unsmoothed) full-frame X
    wire_cx_smooth: Optional[float] = None  # EMA-smoothed full-frame X
    wire_cy_full:  Optional[float] = None   # full-frame Y of wire
    stagger_raw:   Optional[float] = None
    stagger_smooth: Optional[float] = None
    confidence:    float = 0.0
    det:           Optional[WireDetection] = None  # ROI-local detection
    roi_y:         int = 0
    roi_h:         int = 0


# ===========================================================================
# Module 1 — Adaptive ROI + Pre-processing
# ===========================================================================

class PreProcessor:
    """
    Crops the frame to an adaptive ROI around the last known wire position,
    then applies CLAHE + Gaussian blur.
    """

    def __init__(self, frame_h: int, frame_w: int) -> None:
        self._H = frame_h
        self._W = frame_w
        # Global ROI limits (px)
        self._global_y0 = int(frame_h * ROI_TOP_FRAC)
        self._global_y1 = int(frame_h * ROI_BOT_FRAC)
        self._adaptive_cy: Optional[float] = None  # last known wire Y (full frame)

    def update_wire_y(self, wire_cy_full: Optional[float]) -> None:
        """Feed the latest detected/tracked Y position for the next frame's ROI."""
        if wire_cy_full is not None:
            self._adaptive_cy = wire_cy_full

    def process(self, bgr: np.ndarray) -> tuple[np.ndarray, int, int]:
        """
        Returns
        -------
        roi_gray  : pre-processed grayscale ROI
        roi_y     : top of ROI in full-frame coords
        roi_h     : height of ROI
        """
        h, w = bgr.shape[:2]
        if self._adaptive_cy is not None:
            # Adaptive: clamp within global bounds
            y0 = max(self._global_y0, int(self._adaptive_cy) - ADAPT_HALF_HEIGHT)
            y1 = min(self._global_y1, int(self._adaptive_cy) + ADAPT_HALF_HEIGHT)
            if y1 - y0 < 20:   # degenerate: fall back to global
                y0, y1 = self._global_y0, self._global_y1
        else:
            y0, y1 = self._global_y0, self._global_y1

        roi_y = y0
        roi_h = y1 - y0
        crop  = bgr[y0:y1, :]

        gray     = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        enhanced = _CLAHE.apply(gray)
        blurred  = cv2.GaussianBlur(enhanced, (BLUR_K, BLUR_K), 0)
        return blurred, roi_y, roi_h


# ===========================================================================
# Module 2 — Wire Detector
# ===========================================================================

class WireDetector:
    """
    Canny edge detection + HoughLinesP → horizontal filter → cluster merge →
    **longest-line** election (most evidence for the wire).
    """

    def detect(self, roi_gray: np.ndarray) -> Optional[WireDetection]:
        edges = cv2.Canny(roi_gray, CANNY_LO, CANNY_HI)
        raw   = cv2.HoughLinesP(
            edges,
            rho=HOUGH_RHO, theta=HOUGH_THETA,
            threshold=HOUGH_THRESH,
            minLineLength=HOUGH_MIN_LEN,
            maxLineGap=HOUGH_MAX_GAP,
        )
        if raw is None:
            return None

        lines: list[tuple[int, int, int, int]] = [tuple(r[0]) for r in raw]  # type: ignore[misc]

        # Filter: reject steep / vertical lines
        horizontal = [
            l for l in lines
            if self._angle_deg(l) <= ANGLE_TOL_DEG
        ]
        if not horizontal:
            return None

        # Cluster by mid-Y
        clusters  = self._cluster(horizontal)
        # Each cluster → longest representative
        reps      = [
            max(c, key=lambda l: math.hypot(l[2] - l[0], l[3] - l[1]))
            for c in clusters
        ]
        # Elect the **longest** line (most confident evidence)
        best       = max(reps, key=lambda l: math.hypot(l[2] - l[0], l[3] - l[1]))
        x1, y1, x2, y2 = best

        roi_w      = roi_gray.shape[1]
        length     = math.hypot(x2 - x1, y2 - y1)
        confidence = min(1.0, length / max(roi_w, 1))

        if confidence < MIN_CONF:
            return None

        return WireDetection(x1=float(x1), y1=float(y1),
                             x2=float(x2), y2=float(y2),
                             confidence=confidence)

    @staticmethod
    def _angle_deg(line: tuple[int, int, int, int]) -> float:
        x1, y1, x2, y2 = line
        angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
        return 180 - angle if angle > 90 else angle

    @staticmethod
    def _cluster(
        lines: list[tuple[int, int, int, int]],
    ) -> list[list[tuple[int, int, int, int]]]:
        sorted_l = sorted(lines, key=lambda l: (l[1] + l[3]) / 2)
        clusters: list[list[tuple[int, int, int, int]]] = []
        for line in sorted_l:
            mid_y  = (line[1] + line[3]) / 2
            placed = False
            for cl in clusters:
                if abs(mid_y - (cl[0][1] + cl[0][3]) / 2) <= CLUSTER_Y_TOL:
                    cl.append(line)
                    placed = True
                    break
            if not placed:
                clusters.append([line])
        return clusters


# ===========================================================================
# Module 3 — EMA Temporal Tracker
# ===========================================================================

class EMATracker:
    """
    Exponential moving-average smoother for wire centre X and Y.

    When a new detection arrives it updates the EMA.
    When detection is missing the EMA prediction is used (tracked).
    After MAX_LOST consecutive misses the track is called lost.
    """

    MAX_LOST = 15   # frames before declaring "lost"

    def __init__(self) -> None:
        self._ema_x: Optional[float] = None
        self._ema_y: Optional[float] = None
        self._lost_count: int = 0

    @property
    def has_track(self) -> bool:
        return self._ema_x is not None

    def update(
        self, wire_cx: Optional[float], wire_cy: Optional[float]
    ) -> tuple[Optional[float], Optional[float], str]:
        """
        Feed new detection (may be None) and return
        (smoothed_cx, smoothed_cy, source_label).
        """
        if wire_cx is not None and wire_cy is not None:
            # Detection arrived — update EMA
            if self._ema_x is None:
                self._ema_x = wire_cx
                self._ema_y = wire_cy
            else:
                self._ema_x = EMA_ALPHA * wire_cx + (1 - EMA_ALPHA) * self._ema_x
                self._ema_y = EMA_ALPHA * wire_cy + (1 - EMA_ALPHA) * self._ema_y
            self._lost_count = 0
            return self._ema_x, self._ema_y, "detected"

        # No detection
        self._lost_count += 1
        if self._ema_x is not None and self._lost_count <= self.MAX_LOST:
            # Use last EMA estimate — no update
            return self._ema_x, self._ema_y, "tracked"

        return None, None, "lost"

    def reset(self) -> None:
        self._ema_x = None
        self._ema_y = None
        self._lost_count = 0


# ===========================================================================
# Module 4 — Visualiser
# ===========================================================================

def _shadow_text(
    img: np.ndarray,
    text: str,
    pos: tuple[int, int],
    scale: float,
    colour: tuple[int, int, int],
    thickness: int = 1,
) -> None:
    """Render text with a 1-px dark shadow for legibility."""
    x, y = pos
    cv2.putText(img, text, (x + 1, y + 1),
                cv2.FONT_HERSHEY_SIMPLEX, scale, _B_SHADOW, thickness + 1,
                cv2.LINE_AA)
    cv2.putText(img, text, pos,
                cv2.FONT_HERSHEY_SIMPLEX, scale, colour, thickness,
                cv2.LINE_AA)


def draw_overlay(frame: np.ndarray, res: FrameResult) -> np.ndarray:
    """
    Render all HUD elements on *frame* and return it.

    HUD elements
    ------------
    • Faint horizontal ROI band (adaptive, shown in cyan outline)
    • Green vertical centre reference line
    • Blue detected wire line
    • Cyan dashed wire ghost when the source is "tracked"
    • Red stagger arrow (centre → wire X)
    • Confidence bar
    • Status panel (top-right corner):
        Wire: ✓ Detected / ~ Tracked / ✗ Lost
        Stagger: ±XX.X px
        Confidence: 0.XX
        Frame: NNNN  |  T=X.XXX s
    """
    frame = frame.copy()
    H, W   = frame.shape[:2]
    img_cx = W // 2

    # ------------------------------------------------------------------
    # ROI band
    # ------------------------------------------------------------------
    roi_y  = res.roi_y
    roi_y2 = res.roi_y + res.roi_h
    band_colour = (0, 180, 180) if res.source != "lost" else (60, 60, 160)
    cv2.line(frame, (0, roi_y),  (W, roi_y),  band_colour, 1)
    cv2.line(frame, (0, roi_y2), (W, roi_y2), band_colour, 1)

    # ------------------------------------------------------------------
    # Green centre reference
    # ------------------------------------------------------------------
    cv2.line(frame, (img_cx, 0), (img_cx, H), _B_CTR, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Wire overlays
    # ------------------------------------------------------------------
    if res.det is not None and res.wire_cy_full is not None and res.source == "detected":
        d    = res.det
        fy1  = int(d.y1) + roi_y
        fy2  = int(d.y2) + roi_y
        fx1  = int(d.x1)
        fx2  = int(d.x2)
        # Wire line
        cv2.line(frame, (fx1, fy1), (fx2, fy2), _B_WIRE, 3, cv2.LINE_AA)

    elif res.source == "tracked" and res.wire_cy_full is not None:
        # Draw ghost wire at tracked position
        cy_int = int(res.wire_cy_full)
        cv2.line(frame, (0, cy_int), (W, cy_int), _B_TRK, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Stagger arrow + dot
    # ------------------------------------------------------------------
    if res.wire_cx_smooth is not None and res.wire_cy_full is not None:
        wcx   = int(res.wire_cx_smooth)
        wcy   = int(res.wire_cy_full)
        arrow_col = _B_ARROW if res.source == "detected" else _B_TRK

        # Dot at wire centre
        cv2.circle(frame, (wcx, wcy), 7, arrow_col, -1, cv2.LINE_AA)
        cv2.circle(frame, (wcx, wcy), 7, _B_WHITE,  1,  cv2.LINE_AA)

        # Arrow: image centre → wire centre (only if offset is meaningful)
        if abs(wcx - img_cx) > 3:
            cv2.arrowedLine(
                frame,
                (img_cx, wcy), (wcx, wcy),
                arrow_col, 2, cv2.LINE_AA, tipLength=0.12,
            )

    # ------------------------------------------------------------------
    # HUD panel (top-right)
    # ------------------------------------------------------------------
    panel_x = W - 240
    panel_y = 14
    line_h  = 20

    # Status badge
    if res.source == "detected":
        status_txt = "Wire: DETECTED"
        status_col = (80, 220, 80)
    elif res.source == "tracked":
        status_txt = "Wire: TRACKED"
        status_col = (0, 200, 240)
    else:
        status_txt = "Wire:  LOST"
        status_col = _B_WARN

    _shadow_text(frame, status_txt, (panel_x, panel_y), 0.50, status_col, 1)

    # Stagger
    if res.stagger_smooth is not None:
        sign = "+" if res.stagger_smooth >= 0 else ""
        stag_txt = f"Stagger: {sign}{res.stagger_smooth:.1f} px"
        stag_col = _B_WHITE
    else:
        stag_txt = "Stagger: ---"
        stag_col = (120, 120, 120)

    _shadow_text(frame, stag_txt, (panel_x, panel_y + line_h), 0.55, stag_col, 2)

    # Confidence bar
    bar_x  = panel_x
    bar_y  = panel_y + line_h + 6
    bar_w  = 200
    conf_w = int(bar_w * min(res.confidence, 1.0))
    conf_col = (
        (80, 220, 80)  if res.confidence >= 0.50 else
        (0, 200, 240)  if res.confidence >= 0.20 else
        (0, 80, 220)
    )
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 6),
                  (50, 50, 50), -1)
    if conf_w > 0:
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + conf_w, bar_y + 6),
                      conf_col, -1)

    conf_txt = f"Confidence: {res.confidence:.2f}"
    _shadow_text(frame, conf_txt, (panel_x, bar_y + 18), 0.42, (180, 180, 180), 1)

    # Frame + timestamp
    ts_s = res.timestamp_ms / 1000.0
    info_txt = f"Frame {res.frame_id:,}  |  {ts_s:.3f} s"
    _shadow_text(frame, info_txt, (8, H - 10), 0.42, (140, 140, 140), 1)

    return frame


# ===========================================================================
# Module 5 — Main pipeline
# ===========================================================================

def find_video(video_arg: str, project_root: Path) -> Path:
    """Try multiple candidate filenames in case the user renamed the file."""
    candidates = [
        project_root / video_arg,
        project_root / "video" / "inspection_video.mp4",
        project_root / "video" / "videoplayback.mp4",
        project_root / "video" / "inspection_visualized.mp4",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    return (project_root / video_arg).resolve()


def run_pipeline(video_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    video_out = out_dir / "inspection_visualized_v2.mp4"
    csv_out   = out_dir / "stagger_measurements.csv"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        log.error("Cannot open video: %s", video_path)
        sys.exit(1)

    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    img_cx = W / 2.0

    log.info("Input  : %s  (%dx%d  %.1f fps  %d frames)", video_path, W, H, fps, total)
    log.info("Output : %s", out_dir)
    log.info("Tracker: EMA  α=%.2f  max_lost=%d", EMA_ALPHA, EMATracker.MAX_LOST)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_out), fourcc, fps, (W, H))

    preprocessor = PreProcessor(H, W)
    detector     = WireDetector()
    tracker      = EMATracker()

    csv_rows: list[dict] = []
    frame_id   = 0
    n_detected = 0
    n_tracked  = 0
    n_lost     = 0

    while True:
        ok, bgr = cap.read()
        if not ok:
            break

        timestamp_ms = frame_id / fps * 1000.0

        # 1 — Pre-process (adaptive ROI)
        roi_gray, roi_y, roi_h = preprocessor.process(bgr)

        # 2 — Detect
        det = detector.detect(roi_gray)

        # Convert detection to full-frame coords
        raw_cx: Optional[float] = None
        raw_cy: Optional[float] = None
        if det is not None:
            raw_cx = det.cx + 0          # ROI x-offset is 0 (full width)
            raw_cy = det.cy + roi_y

        # 3 — Track (EMA)
        smooth_cx, smooth_cy, source = tracker.update(raw_cx, raw_cy)

        # 4 — Stagger
        raw_stagger:    Optional[float] = (raw_cx    - img_cx) if raw_cx    is not None else None
        smooth_stagger: Optional[float] = (smooth_cx - img_cx) if smooth_cx is not None else None

        # 5 — Update adaptive ROI for next frame
        preprocessor.update_wire_y(smooth_cy)

        # 6 — Build result
        res = FrameResult(
            frame_id=frame_id,
            timestamp_ms=timestamp_ms,
            source=source,
            wire_cx_raw=raw_cx,
            wire_cx_smooth=smooth_cx,
            wire_cy_full=smooth_cy,
            stagger_raw=raw_stagger,
            stagger_smooth=smooth_stagger,
            confidence=det.confidence if det else 0.0,
            det=det,
            roi_y=roi_y,
            roi_h=roi_h,
        )

        # 7 — Counters
        if source == "detected":   n_detected += 1
        elif source == "tracked":  n_tracked  += 1
        else:                      n_lost     += 1

        # 8 — Visualise
        annotated = draw_overlay(bgr, res)
        writer.write(annotated)

        # 9 — CSV
        csv_rows.append({
            "frame":        frame_id,
            "timestamp_ms": f"{timestamp_ms:.1f}",
            "wire_center_x": f"{smooth_cx:.3f}" if smooth_cx is not None else "",
            "stagger_px":    f"{smooth_stagger:.3f}" if smooth_stagger is not None else "",
            "confidence":    f"{res.confidence:.4f}",
            "source":        source,
        })

        frame_id += 1
        if frame_id % 100 == 0:
            log.info("  %d / %d  (%.0f%%)  — det:%d  trk:%d  lost:%d",
                     frame_id, total, frame_id / max(total, 1) * 100,
                     n_detected, n_tracked, n_lost)

    cap.release()
    writer.release()

    # Write CSV
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        dw = csv.DictWriter(
            f,
            fieldnames=["frame", "timestamp_ms", "wire_center_x",
                        "stagger_px", "confidence", "source"],
        )
        dw.writeheader()
        dw.writerows(csv_rows)

    total_frames = max(frame_id, 1)
    log.info("═" * 50)
    log.info("Done.")
    log.info("  Frames processed : %d", frame_id)
    log.info("  Detected (raw)   : %d  (%.1f%%)", n_detected, n_detected / total_frames * 100)
    log.info("  Tracked  (EMA)   : %d  (%.1f%%)", n_tracked,  n_tracked  / total_frames * 100)
    log.info("  Lost             : %d  (%.1f%%)", n_lost,     n_lost     / total_frames * 100)
    log.info("  Video output     : %s", video_out)
    log.info("  CSV output       : %s", csv_out)
    log.info("═" * 50)


# ===========================================================================
# CLI
# ===========================================================================

def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="OHE contact-wire detection pipeline v2 "
                    "(EMA tracking + adaptive ROI)"
    )
    p.add_argument("--video", default=DEFAULT_VIDEO,
                   help="Input video path (default: %(default)s)")
    p.add_argument("--out",   default=DEFAULT_OUT_DIR,
                   help="Output directory (default: %(default)s)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    project_root = Path(__file__).resolve().parent.parent
    video_path   = find_video(args.video, project_root)
    out_dir      = (project_root / args.out).resolve()

    if not video_path.exists():
        log.error("Video not found: %s", video_path)
        sys.exit(1)

    run_pipeline(video_path, out_dir)
