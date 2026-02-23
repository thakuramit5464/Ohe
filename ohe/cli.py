"""
cli.py
------
Command-line interface for headless (no-UI) batch processing.

Usage:
    ohe process --video path/to/file.mp4 [OPTIONS]
    ohe process --video input.mp4 --output sessions/out.csv --config my.yaml
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from ohe.core.bus import DataBus
from ohe.core.config import load_config
from ohe.ingestion.video_file import VideoFileProvider
from ohe.logging_.csv_writer import CsvWriter
from ohe.logging_.session import SessionLogger
from ohe.processing.calibration import CalibrationModel
from ohe.processing.pipeline import ProcessingPipeline
from ohe.rules.engine import RulesEngine
from ohe.rules.thresholds import Thresholds


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
def main() -> None:
    """OHE Stagger & Wire Diameter Measurement System — CLI."""


@main.command("process")
@click.option("--video", required=True, type=click.Path(exists=True), help="Path to input video file.")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to YAML config (default: config/default.yaml).")
@click.option("--output", default=None, type=click.Path(), help="Optional output CSV path override.")
@click.option("--frame-skip", default=1, show_default=True, help="Process every Nth frame.")
@click.option("--log-level", default="INFO", show_default=True, help="Logging verbosity.")
@click.option("--max-frames", default=-1, show_default=True, help="Stop after N frames (-1 = all).")
def process_cmd(
    video: str,
    config_path: str | None,
    output: str | None,
    frame_skip: int,
    log_level: str,
    max_frames: int,
) -> None:
    """Process a video file and output measurements to CSV + SQLite."""
    _setup_logging(log_level)
    logger = logging.getLogger(__name__)

    # Load config
    cfg = load_config(config_path)

    # Build components
    cal = CalibrationModel.from_json(
        cfg.calibration_path(),
        fallback_px_per_mm=cfg.calibration.fallback_px_per_mm,
    )
    pipeline = ProcessingPipeline(cfg, cal)
    rules = RulesEngine(Thresholds.from_config(cfg.rules))
    bus = DataBus()

    # Session + CSV logging
    session_dir = cfg.session_dir_path()
    session_logger = SessionLogger(session_dir, source=video)
    info = session_logger.start()

    csv_writer: CsvWriter | None = None
    if cfg.logging.csv_enabled:
        out_dir = Path(output).parent if output else session_dir
        csv_writer = CsvWriter(out_dir, info.session_id, max_rows=cfg.logging.csv_max_rows)

    # Publish helpers (wires up bus for future subscribers)
    def _on_measurement(m):
        session_logger.log_measurement(m)
        pass

    def _on_anomaly(a):
        session_logger.log_anomaly(a)
        logger.warning("[%s] %s", a.severity, a.message)

    bus.subscribe("measurement", _on_measurement)
    bus.subscribe("anomaly", _on_anomaly)

    # Ingest + process
    provider = VideoFileProvider(video, frame_skip=frame_skip)
    frame_count = 0
    try:
        with provider:
            for raw in provider.frames():
                if max_frames > 0 and frame_count >= max_frames:
                    break
                measurement = pipeline.run(raw)
                anomalies = rules.evaluate(measurement)

                bus.publish("measurement", measurement)
                for anomaly in anomalies:
                    bus.publish("anomaly", anomaly)

                if csv_writer:
                    csv_writer.write(measurement, anomalies)

                frame_count += 1
                if frame_count % 100 == 0:
                    logger.info("Processed %d frames…", frame_count)

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception:
        logger.exception("Fatal error during processing.")
        sys.exit(1)
    finally:
        if csv_writer:
            csv_writer.close()
        final_info = session_logger.stop()
        click.echo(
            f"\n✅ Done — {final_info.total_frames} frames | "
            f"{final_info.anomaly_count} anomalies | "
            f"DB: {session_logger.db_path}"
        )


if __name__ == "__main__":
    main()
