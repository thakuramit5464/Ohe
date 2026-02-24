"""
tools/debug_visualiser.py
--------------------------
Headless debug tool: runs the full detection pipeline on a video and saves
annotated frames + a summary video showing what the detector sees.

Outputs (written to ``data/debug/<run_timestamp>/``):
  * ``frame_XXXX_annotated.png`` — full frame with ROI box + wire overlay
  * ``frame_XXXX_roi.png``        — zoomed ROI with Hough/Gaussian overlays
  * ``annotated.mp4``            — full annotated output video
  * ``summary.csv``              — per-frame stagger, diameter, confidence

Usage:
    python -m tools.debug_visualiser --video data/sample_videos/overlap_first4s_looped.mp4
    python -m tools.debug_visualiser --video foo.mp4 --every 5 --max-frames 100
"""

from __future__ import annotations

import csv
import logging
import time
from pathlib import Path

import click
import cv2
import numpy as np

# Bootstrap logging before importing ohe modules
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

from ohe.core.config import load_config
from ohe.core.models import Measurement
from ohe.ingestion.video_file import VideoFileProvider
from ohe.processing.calibration import CalibrationModel
from ohe.processing.detector import WireDetector
from ohe.processing.measurement import MeasurementEngine
from ohe.processing.preprocess import PreProcessor
from ohe.rules.engine import RulesEngine
from ohe.rules.thresholds import Thresholds


def _draw_full_frame_overlay(
    frame: np.ndarray,
    m: Measurement,
    anomalies: list,
    roi_rect: tuple | None,
    frame_id: int,
) -> np.ndarray:
    """Draw ROI box, wire bbox, stagger line, and measurement text on a copy of frame."""
    out = frame.copy()
    h, w = out.shape[:2]

    # ROI rectangle (cyan)
    if roi_rect:
        rx, ry, rw, rh = roi_rect
        cv2.rectangle(out, (rx, ry), (rx + rw, ry + rh), (255, 255, 0), 1)
        cv2.putText(out, "ROI", (rx + 2, ry + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1)

    # Wire bounding box (green)
    if m.wire_bbox:
        x, y, bw, bh = m.wire_bbox
        cv2.rectangle(out, (x, y), (x + bw, y + bh), (0, 255, 0), 2)

    # Wire centre vertical line (stagger indicator)
    if m.wire_centre_px:
        cx, cy = int(m.wire_centre_px[0]), int(m.wire_centre_px[1])
        cv2.circle(out, (cx, cy), 5, (0, 0, 255), -1)
        cv2.line(out, (cx, 0), (cx, h), (0, 0, 255), 1)

    # Track centre line (white dashed approximation = solid thin)
    track_cx = w // 2   # placeholder — use calibration in production
    cv2.line(out, (track_cx, 0), (track_cx, h), (200, 200, 200), 1)

    # Measurement HUD (top-left)
    severity_colour = {
        "WARNING": (0, 200, 255),
        "CRITICAL": (0, 0, 255),
    }
    hud_lines = [
        f"Frame: {frame_id}",
        f"Stagger: {m.stagger_mm:.1f} mm" if m.stagger_mm is not None else "Stagger: ---",
        f"Diameter: {m.diameter_mm:.2f} mm" if m.diameter_mm is not None else "Diameter: ---",
        f"Confidence: {m.confidence:.2f}",
    ]
    for i, a in enumerate(anomalies[:2]):
        colour = severity_colour.get(a.severity, (255, 255, 255))
        cv2.putText(out, f"[{a.severity}] {a.anomaly_type}", (8, 85 + i * 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1)

    bg = np.zeros((len(hud_lines) * 18 + 6, 220, 3), dtype=np.uint8)
    out[4:4 + bg.shape[0], 4:4 + 220] = (out[4:4 + bg.shape[0], 4:4 + 220] * 0.4 + bg * 0.0).astype(np.uint8)
    for i, line in enumerate(hud_lines):
        cv2.putText(out, line, (8, 18 + i * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

    return out


@click.command("debug-visualiser")
@click.option("--video", required=True, type=click.Path(exists=True), help="Input video path.")
@click.option("--config", "config_path", default=None, type=click.Path(), help="YAML config.")
@click.option("--every", default=1, show_default=True, help="Save annotated PNG every N frames (1=all).")
@click.option("--max-frames", default=360, show_default=True, help="Max frames to process.")
@click.option("--output-dir", default=None, type=click.Path(), help="Output directory override.")
@click.option("--write-video/--no-write-video", default=True, show_default=True, help="Write annotated MP4.")
def main(video, config_path, every, max_frames, output_dir, write_video):
    """Run detection pipeline and save annotated debug output for parameter tuning."""
    cfg = load_config(config_path)

    # Output directory
    ts = time.strftime("%Y%m%dT%H%M%S")
    out_dir = Path(output_dir) if output_dir else Path("data/debug") / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Debug output → %s", out_dir)

    # Build pipeline components
    cal = CalibrationModel.from_json(cfg.calibration_path(), cfg.calibration.fallback_px_per_mm)
    preprocessor = PreProcessor(cfg.processing, cal)
    detector = WireDetector(cfg.processing)
    measure_eng = MeasurementEngine(cal, cfg.processing)
    rules = RulesEngine(Thresholds.from_config(cfg.rules))

    roi_rect = tuple(cfg.processing.roi) if cfg.processing.roi else None

    # Video writer (set up after first frame)
    video_writer = None

    # CSV summary
    csv_path = out_dir / "summary.csv"
    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["frame_id", "timestamp_ms", "stagger_mm", "diameter_mm", "confidence", "anomalies"])

    provider = VideoFileProvider(video)
    frame_count = 0
    detected_count = 0

    with provider:
        for raw in provider.frames():
            if frame_count >= max_frames:
                break

            # Run detection
            pf = preprocessor.run(raw)
            cand, roi_dbg = detector.detect_debug(pf)
            m = measure_eng.compute(cand, pf.roi_offset_x, pf.roi_offset_y)
            anomalies = rules.evaluate(m)

            if m.stagger_mm is not None:
                detected_count += 1

            # Log to CSV
            csv_writer.writerow([
                m.frame_id, f"{m.timestamp_ms:.1f}",
                f"{m.stagger_mm:.3f}" if m.stagger_mm is not None else "",
                f"{m.diameter_mm:.3f}" if m.diameter_mm is not None else "",
                f"{m.confidence:.3f}",
                ";".join(a.anomaly_type for a in anomalies),
            ])

            # Annotate full frame
            full_annotated = _draw_full_frame_overlay(raw.image, m, anomalies, roi_rect, raw.frame_id)

            # Stamp the ROI debug panel onto the full frame (bottom-right)
            roi_h, roi_w = roi_dbg.shape[:2]
            fh, fw = full_annotated.shape[:2]
            scale = min(fw // 3 / roi_w, 120 / roi_h)
            new_w, new_h = int(roi_w * scale), int(roi_h * scale)
            roi_small = cv2.resize(roi_dbg, (new_w, new_h))
            y1_paste = fh - new_h - 4
            x1_paste = fw - new_w - 4
            full_annotated[y1_paste:y1_paste + new_h, x1_paste:x1_paste + new_w] = roi_small
            cv2.rectangle(full_annotated, (x1_paste - 1, y1_paste - 1),
                          (x1_paste + new_w, y1_paste + new_h), (100, 100, 100), 1)

            # Init video writer
            if write_video and video_writer is None:
                fh2, fw2 = full_annotated.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                video_writer = cv2.VideoWriter(str(out_dir / "annotated.mp4"), fourcc, 15, (fw2, fh2))

            if video_writer is not None:
                video_writer.write(full_annotated)

            # Save PNG snapshots
            if frame_count % every == 0:
                cv2.imwrite(str(out_dir / f"frame_{raw.frame_id:04d}.png"), full_annotated)
                cv2.imwrite(str(out_dir / f"frame_{raw.frame_id:04d}_roi.png"), roi_dbg)

            frame_count += 1
            if frame_count % 30 == 0:
                pct = detected_count / max(frame_count, 1) * 100
                logger.info("Frame %d / %d | detected: %d (%.0f%%)", frame_count, max_frames, detected_count, pct)

    csv_file.close()
    if video_writer:
        video_writer.release()

    pct = detected_count / max(frame_count, 1) * 100
    click.echo(f"\n[DONE] {frame_count} frames processed")
    click.echo(f"  Wire detected: {detected_count} / {frame_count} frames ({pct:.1f}%)")
    click.echo(f"  Annotated video: {out_dir / 'annotated.mp4'}")
    click.echo(f"  Summary CSV:     {csv_path}")


if __name__ == "__main__":
    main()
