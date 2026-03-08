"""
scripts/run_classical_cv.py
----------------------------
Standalone classical CV pipeline for OHE contact-wire detection and
horizontal-stagger estimation.

Processing chain (per frame)
-----------------------------
1. ROI crop  — upper 60 % of the frame where the wire lives
2. Grayscale conversion
3. CLAHE contrast enhancement
4. Gaussian blur  — noise reduction
5. Canny edge detection
6. HoughLinesP  — probabilistic line finder
7. Near-horizontal filter (±30°)
8. Y-cluster merging  — collapses duplicate detections
9. Lowest-wire election  — contact wire is closest to pantograph
10. Stagger computation  — signed pixel offset from image centre

Outputs
-------
  output/inspection_visualized.mp4   — annotated video
  output/stagger_measurements.csv    — per-frame measurement table

Usage
-----
    python scripts/run_classical_cv.py
    python scripts/run_classical_cv.py --video path/to/other.mp4 --out output/

Dependencies: opencv-python, numpy  (no project-internal imports needed)
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_VIDEO   = "video/inspection_video.mp4"
DEFAULT_OUT_DIR = "output"

# ROI: keep only top fraction of the frame (wire is in the upper region)
ROI_TOP_FRACTION    = 0.15   # start  y = H * 0.15
ROI_BOTTOM_FRACTION = 0.75   # end    y = H * 0.75

# Pre-processing
CLAHE_CLIP_LIMIT  = 2.5
CLAHE_TILE_GRID   = (8, 8)
BLUR_KERNEL       = 5          # must be odd

# Canny
CANNY_LOW    = 50
CANNY_HIGH   = 150

# HoughLinesP
HOUGH_RHO      = 1
HOUGH_THETA    = math.radians(1)
HOUGH_THRESH   = 40
HOUGH_MIN_LEN  = 60
HOUGH_MAX_GAP  = 20

# Filtering
WIRE_ANGLE_TOL_DEG  = 30.0    # maximum angle from horizontal
CLUSTER_Y_TOL_PX    = 8       # merge lines within this many Y pixels
MIN_CONFIDENCE      = 0.10    # lines shorter than 10 % of ROI width discarded

# Visualisation colours (BGR)
COL_WIRE    = (255, 80,  0)    # blue-ish
COL_CENTER  = (0,   220, 0)    # green
COL_ARROW   = (0,   0,   230)  # red
COL_TEXT    = (255, 255, 255)  # white
COL_NO_DET  = (0,   60,  200)  # dark orange text when no wire

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("cv_pipeline")


# ===========================================================================
# Step 1 — Pre-processing
# ===========================================================================

def preprocess(bgr: np.ndarray) -> tuple[np.ndarray, int, int, int, int]:
    """
    Crop ROI, enhance contrast, blur.

    Returns
    -------
    roi_gray    : pre-processed grayscale ROI image
    roi_x, roi_y: top-left corner of the ROI in the full frame
    roi_w, roi_h: width / height of the ROI
    """
    h, w = bgr.shape[:2]
    roi_y  = int(h * ROI_TOP_FRACTION)
    roi_y2 = int(h * ROI_BOTTOM_FRACTION)
    roi_h  = roi_y2 - roi_y
    roi_x, roi_w = 0, w

    crop = bgr[roi_y:roi_y2, :]

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT,
                             tileGridSize=CLAHE_TILE_GRID)
    enhanced = clahe.apply(gray)

    blurred = cv2.GaussianBlur(enhanced, (BLUR_KERNEL, BLUR_KERNEL), 0)

    return blurred, roi_x, roi_y, roi_w, roi_h


# ===========================================================================
# Step 2 — Detection
# ===========================================================================

def detect_wire(
    roi_gray: np.ndarray,
) -> Optional[tuple[float, float, float, float, float]]:
    """
    Run Canny + HoughLinesP, filter, cluster, elect contact wire.

    Returns
    -------
    (x1, y1, x2, y2, confidence)  in ROI-local pixel coords, or None.
    """
    edges = cv2.Canny(roi_gray, CANNY_LOW, CANNY_HIGH)

    raw = cv2.HoughLinesP(
        edges,
        rho=HOUGH_RHO,
        theta=HOUGH_THETA,
        threshold=HOUGH_THRESH,
        minLineLength=HOUGH_MIN_LEN,
        maxLineGap=HOUGH_MAX_GAP,
    )
    if raw is None:
        return None

    lines: list[tuple[int, int, int, int]] = [tuple(r[0]) for r in raw]  # type: ignore[misc]

    # --- Filter: keep near-horizontal lines --------------------------------
    horizontal: list[tuple[int, int, int, int]] = []
    for x1, y1, x2, y2 in lines:
        dx, dy = x2 - x1, y2 - y1
        angle = abs(math.degrees(math.atan2(dy, dx)))
        if angle > 90:
            angle = 180 - angle
        if angle <= WIRE_ANGLE_TOL_DEG:
            horizontal.append((x1, y1, x2, y2))

    if not horizontal:
        return None

    # --- Cluster: merge lines close in Y -----------------------------------
    sorted_h = sorted(horizontal, key=lambda l: (l[1] + l[3]) / 2)
    clusters: list[list[tuple[int, int, int, int]]] = []
    for line in sorted_h:
        mid_y = (line[1] + line[3]) / 2
        placed = False
        for cluster in clusters:
            rep_mid_y = (cluster[0][1] + cluster[0][3]) / 2
            if abs(mid_y - rep_mid_y) <= CLUSTER_Y_TOL_PX:
                cluster.append(line)
                placed = True
                break
        if not placed:
            clusters.append([line])

    # Pick longest line from each cluster
    reps = [
        max(c, key=lambda l: math.hypot(l[2] - l[0], l[3] - l[1]))
        for c in clusters
    ]

    # --- Election: lowest wire (highest Y) = contact wire ------------------
    best = max(reps, key=lambda l: (l[1] + l[3]) / 2)
    x1, y1, x2, y2 = best

    roi_w = roi_gray.shape[1]
    length = math.hypot(x2 - x1, y2 - y1)
    confidence = min(1.0, length / max(roi_w, 1))

    if confidence < MIN_CONFIDENCE:
        return None

    return float(x1), float(y1), float(x2), float(y2), confidence


# ===========================================================================
# Step 3 — Stagger computation
# ===========================================================================

def compute_stagger(
    x1: float, y1: float, x2: float, y2: float,
    roi_offset_x: int, frame_width: int,
) -> tuple[float, float]:
    """
    Compute signed stagger offset from the image centre.

    Returns
    -------
    wire_centre_x   : wire midpoint X in full-frame coords (px)
    stagger_px      : signed lateral offset (+ = right of centre)
    """
    wire_cx = (x1 + x2) / 2.0 + roi_offset_x
    image_cx = frame_width / 2.0
    stagger_px = wire_cx - image_cx
    return wire_cx, stagger_px


# ===========================================================================
# Step 4 — Visualisation
# ===========================================================================

def draw_overlay(
    frame: np.ndarray,
    roi_y: int,
    wire_result: Optional[tuple[float, float, float, float, float]],
    wire_cx: Optional[float],
    wire_cy: Optional[float],
    stagger_px: Optional[float],
    frame_id: int,
) -> np.ndarray:
    """
    Draw all overlay elements on *frame* (modified in place, also returned).

    Elements:
      • Green vertical centre line
      • Blue contact wire line (when detected)
      • Wire centre point (filled circle)
      • Red horizontal stagger arrow
      • Stagger text label
      • Frame counter
      • ROI boundary hint (faint)
    """
    h, w = frame.shape[:2]
    img_cx = w // 2

    # --- Green vertical centre reference -----------------------------------
    cv2.line(frame, (img_cx, 0), (img_cx, h), COL_CENTER, 1, cv2.LINE_AA)

    # --- ROI boundary (faint grey dashed feel — just a thin line) ----------
    cv2.line(frame, (0, roi_y), (w, roi_y), (80, 80, 80), 1)

    if wire_result is not None and wire_cx is not None and stagger_px is not None:
        x1, y1, x2, y2, confidence = wire_result
        # Convert ROI-local Y to full-frame Y
        fy1 = int(y1) + roi_y
        fy2 = int(y2) + roi_y
        fx1, fx2 = int(x1), int(x2)

        # --- Blue contact wire line ----------------------------------------
        cv2.line(frame, (fx1, fy1), (fx2, fy2), COL_WIRE, 3, cv2.LINE_AA)

        wire_y_full = int(wire_cy) + roi_y if wire_cy else fy1

        # --- Wire centre point ---------------------------------------------
        cv2.circle(frame, (int(wire_cx), wire_y_full), 7, COL_WIRE, -1, cv2.LINE_AA)
        cv2.circle(frame, (int(wire_cx), wire_y_full), 7, (255, 255, 255), 1, cv2.LINE_AA)

        # --- Red stagger arrow (image_cx → wire_cx) -------------------------
        arrow_y = wire_y_full
        cv2.arrowedLine(
            frame,
            (img_cx, arrow_y),
            (int(wire_cx), arrow_y),
            COL_ARROW, 2, cv2.LINE_AA,
            tipLength=0.15,
        )

        # --- Stagger label --------------------------------------------------
        sign = "+" if stagger_px >= 0 else ""
        stagger_label = f"Stagger: {sign}{stagger_px:.1f} px"
        conf_label    = f"Conf: {confidence:.2f}"

        label_x = max(8, min(int(wire_cx) - 80, w - 200))
        label_y = max(30, wire_y_full - 20)

        # Shadow
        cv2.putText(frame, stagger_label,
                    (label_x + 1, label_y + 1),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
        cv2.putText(frame, stagger_label,
                    (label_x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, COL_TEXT, 2, cv2.LINE_AA)
        cv2.putText(frame, conf_label,
                    (label_x + 1, label_y + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 0), 2)
        cv2.putText(frame, conf_label,
                    (label_x, label_y + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (180, 220, 180), 1, cv2.LINE_AA)

    else:
        # No detection — show message
        msg = "Wire: Not detected"
        cv2.putText(frame, msg,
                    (img_cx - 90, roi_y + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, COL_NO_DET, 2, cv2.LINE_AA)

    # --- Frame counter (top-left) -------------------------------------------
    cv2.putText(frame, f"Frame: {frame_id:,}",
                (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 160, 160), 1, cv2.LINE_AA)

    return frame


# ===========================================================================
# Main pipeline
# ===========================================================================

def run_pipeline(video_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    video_out_path = out_dir / "inspection_visualized.mp4"
    csv_out_path   = out_dir / "stagger_measurements.csv"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        log.error("Cannot open video: %s", video_path)
        sys.exit(1)

    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    log.info("Input  : %s  (%dx%d, %.1f fps, %d frames)", video_path, width, height, fps, total)
    log.info("Output : %s", out_dir)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_out_path), fourcc, fps, (width, height))

    csv_rows: list[dict] = []  # buffered for clean write at end

    frame_id     = 0
    detected     = 0
    not_detected = 0

    while True:
        ok, bgr = cap.read()
        if not ok:
            break

        # ---- pre-process ---------------------------------------------------
        roi_gray, roi_x, roi_y, roi_w, roi_h = preprocess(bgr)

        # ---- detect --------------------------------------------------------
        result = detect_wire(roi_gray)

        wire_cx_full: Optional[float] = None
        stagger_px:   Optional[float] = None
        wire_cy_roi:  Optional[float] = None
        confidence:   float           = 0.0

        if result is not None:
            x1, y1, x2, y2, confidence = result
            wire_cx_full, stagger_px = compute_stagger(
                x1, y1, x2, y2, roi_x, width
            )
            wire_cy_roi = (y1 + y2) / 2.0
            detected += 1
        else:
            not_detected += 1

        # ---- visualise -----------------------------------------------------
        annotated = draw_overlay(
            bgr.copy(),
            roi_y,
            result,
            wire_cx_full,
            wire_cy_roi,
            stagger_px,
            frame_id,
        )
        writer.write(annotated)

        # ---- CSV row -------------------------------------------------------
        csv_rows.append({
            "frame":        frame_id,
            "wire_center_x": f"{wire_cx_full:.3f}" if wire_cx_full is not None else "",
            "stagger_px":   f"{stagger_px:.3f}"   if stagger_px   is not None else "",
            "confidence":   f"{confidence:.4f}",
        })

        frame_id += 1
        if frame_id % 100 == 0:
            pct = frame_id / max(total, 1) * 100
            log.info("  ... %d / %d frames (%.0f%%)", frame_id, total, pct)

    cap.release()
    writer.release()

    # ---- write CSV ---------------------------------------------------------
    with open(csv_out_path, "w", newline="", encoding="utf-8") as f:
        writer_csv = csv.DictWriter(
            f, fieldnames=["frame", "wire_center_x", "stagger_px", "confidence"]
        )
        writer_csv.writeheader()
        writer_csv.writerows(csv_rows)

    det_rate = detected / max(frame_id, 1) * 100
    log.info("──────────────────────────────────────────")
    log.info("Done.")
    log.info("  Frames processed : %d", frame_id)
    log.info("  Wire detected    : %d  (%.1f %%)", detected, det_rate)
    log.info("  Not detected     : %d", not_detected)
    log.info("  Video output     : %s", video_out_path)
    log.info("  CSV output       : %s", csv_out_path)
    log.info("──────────────────────────────────────────")


# ===========================================================================
# CLI entry point
# ===========================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Classical OHE contact-wire detection pipeline."
    )
    p.add_argument(
        "--video", default=DEFAULT_VIDEO,
        help=f"Path to input video (default: {DEFAULT_VIDEO})",
    )
    p.add_argument(
        "--out", default=DEFAULT_OUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUT_DIR})",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # Resolve paths relative to the project root (two levels up from this script)
    project_root = Path(__file__).resolve().parent.parent
    video_path   = (project_root / args.video).resolve()
    out_dir      = (project_root / args.out).resolve()

    if not video_path.exists():
        log.error("Video file not found: %s", video_path)
        sys.exit(1)

    run_pipeline(video_path, out_dir)
