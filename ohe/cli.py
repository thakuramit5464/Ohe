"""
cli.py  (Phase 3 — enhanced)
-----------------------------
Command-line interface for headless (no-UI) batch processing.

Commands:
    ohe process   Run detection pipeline on a video file
    ohe export    Export a completed session SQLite DB to CSV + JSON summary
    ohe sessions  List all recorded sessions in the session directory
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from tqdm import tqdm

from ohe.core.bus import DataBus
from ohe.core.config import load_config
from ohe.ingestion.video_file import VideoFileProvider
from ohe.logging_.csv_writer import CsvWriter
from ohe.logging_.export import SessionExporter
from ohe.logging_.log_worker import LogWorker
from ohe.logging_.session import SessionLogger
from ohe.processing.calibration import CalibrationModel
from ohe.processing.pipeline import ProcessingPipeline
from ohe.rules.engine import RulesEngine
from ohe.rules.thresholds import Thresholds


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
def main() -> None:
    """OHE Stagger & Wire Diameter Measurement System -- CLI."""


# ---------------------------------------------------------------------------
# ohe process
# ---------------------------------------------------------------------------

@main.command("process")
@click.option("--video", required=True, type=click.Path(exists=True), help="Path to input video file.")
@click.option("--config", "config_path", default=None, type=click.Path(), help="YAML config (default: config/default.yaml).")
@click.option("--frame-skip", default=1, show_default=True, help="Process every Nth frame.")
@click.option("--max-frames", default=-1, show_default=True, help="Stop after N frames (-1 = all).")
@click.option("--log-level", default="WARNING", show_default=True, help="Logging verbosity.")
@click.option("--export/--no-export", default=True, show_default=True, help="Auto-export CSV + JSON summary after processing.")
def process_cmd(video, config_path, frame_skip, max_frames, log_level, export):
    """Process a video file: detect wire, compute measurements, log to SQLite + CSV."""
    _setup_logging(log_level)

    cfg = load_config(config_path)
    cal = CalibrationModel.from_json(
        cfg.calibration_path(),
        fallback_px_per_mm=cfg.calibration.fallback_px_per_mm,
    )
    pipeline = ProcessingPipeline(cfg, cal)
    rules = RulesEngine(Thresholds.from_config(cfg.rules))
    bus = DataBus()

    # Session + CSV + background log worker
    session_dir = cfg.session_dir_path()
    session_logger = SessionLogger(session_dir, source=video)
    info = session_logger.start()

    csv_writer: CsvWriter | None = None
    if cfg.logging.csv_enabled:
        csv_writer = CsvWriter(session_dir, info.session_id, max_rows=cfg.logging.csv_max_rows)

    worker = LogWorker(session_logger, csv_writer, maxsize=1000)
    worker.start()

    # Bus wires warning/critical anomalies to stderr
    def _on_anomaly(a):
        if a.severity == "CRITICAL":
            tqdm.write(f"  [CRITICAL] {a.message}")

    bus.subscribe("anomaly", _on_anomaly)

    # Determine total frames for progress bar
    provider = VideoFileProvider(video, frame_skip=frame_skip)
    provider.open()
    total = provider.frame_count if provider.frame_count > 0 else None
    if max_frames > 0:
        total = min(total or max_frames, max_frames // frame_skip)

    # Running stats
    detected = 0
    anomaly_total = 0
    stagger_vals: list[float] = []

    click.echo(f"\nProcessing: {Path(video).name}")
    click.echo(f"Session ID: {info.session_id}")
    click.echo(f"Output dir: {session_dir}\n")

    frame_count = 0
    try:
        with tqdm(
            total=total,
            unit="frame",
            dynamic_ncols=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ) as pbar:
            for raw in provider.frames():
                if max_frames > 0 and frame_count >= max_frames:
                    break

                measurement = pipeline.run(raw)
                anomalies = rules.evaluate(measurement)

                # Async write (non-blocking)
                worker.push_measurement(measurement, anomalies)

                # Publish for any other subscribers
                bus.publish("measurement", measurement)
                for a in anomalies:
                    bus.publish("anomaly", a)

                # Stats
                if measurement.stagger_mm is not None:
                    detected += 1
                    stagger_vals.append(measurement.stagger_mm)
                anomaly_total += len(anomalies)

                frame_count += 1
                pbar.update(1)

                # Live postfix stats every 30 frames
                if frame_count % 30 == 0:
                    avg_stagger = (
                        sum(stagger_vals[-30:]) / len(stagger_vals[-30:])
                        if stagger_vals else 0.0
                    )
                    det_pct = detected / frame_count * 100
                    pbar.set_postfix({
                        "det%": f"{det_pct:.0f}",
                        "stagger": f"{avg_stagger:+.1f}mm",
                        "anomalies": anomaly_total,
                    })

    except KeyboardInterrupt:
        click.echo("\nInterrupted — flushing logs...")
    except Exception:
        logging.exception("Fatal error")
        sys.exit(1)
    finally:
        provider.close()
        worker.stop()
        if csv_writer:
            csv_writer.close()
        final_info = session_logger.stop()

    det_pct = detected / max(frame_count, 1) * 100
    avg_stagger = sum(stagger_vals) / len(stagger_vals) if stagger_vals else None
    stagger_range = (min(stagger_vals), max(stagger_vals)) if stagger_vals else (None, None)

    click.echo("\n" + "=" * 60)
    click.echo(f" SESSION COMPLETE")
    click.echo("=" * 60)
    click.echo(f"  Frames processed : {frame_count}")
    click.echo(f"  Wire detected    : {detected} ({det_pct:.1f}%)")
    click.echo(f"  Anomalies        : {anomaly_total}")
    if avg_stagger is not None:
        click.echo(f"  Avg stagger      : {avg_stagger:+.1f} mm")
        click.echo(f"  Stagger range    : {stagger_range[0]:+.1f} .. {stagger_range[1]:+.1f} mm")
    click.echo(f"  Database         : {session_logger.db_path}")
    if worker.dropped_count:
        click.echo(f"  [WARN] Dropped   : {worker.dropped_count} log items")

    # Auto-export
    if export and session_logger.db_path:
        click.echo("\nExporting summary...")
        try:
            exp = SessionExporter(session_logger.db_path)
            csv_out, json_out = exp.export_all()
            click.echo(f"  Export CSV  : {csv_out}")
            click.echo(f"  Summary JSON: {json_out}")
        except Exception as e:
            click.echo(f"  Export failed: {e}")

    click.echo("")


# ---------------------------------------------------------------------------
# ohe export
# ---------------------------------------------------------------------------

@main.command("export")
@click.option("--db", required=True, type=click.Path(exists=True), help="Path to session SQLite .sqlite file.")
@click.option("--out-dir", default=None, type=click.Path(), help="Output directory (default: same as DB).")
def export_cmd(db, out_dir):
    """Export a completed session database to CSV + JSON summary."""
    out_dir_path = Path(out_dir) if out_dir else Path(db).parent
    out_dir_path.mkdir(parents=True, exist_ok=True)

    exp = SessionExporter(db)
    csv_out = exp.export_csv(out_dir_path / (Path(db).stem + "_export.csv"))
    json_out = exp.export_summary_json(out_dir_path / (Path(db).stem + "_summary.json"))

    click.echo(f"Export CSV  : {csv_out}")
    click.echo(f"Summary JSON: {json_out}")


# ---------------------------------------------------------------------------
# ohe sessions
# ---------------------------------------------------------------------------

@main.command("sessions")
@click.option("--config", "config_path", default=None, type=click.Path(), help="YAML config.")
@click.option("--limit", default=20, show_default=True, help="Number of sessions to show.")
def sessions_cmd(config_path, limit):
    """List recent sessions in the session directory."""
    cfg = load_config(config_path)
    session_dir = cfg.session_dir_path()

    dbs = sorted(session_dir.glob("*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not dbs:
        click.echo(f"No sessions found in {session_dir}")
        return

    click.echo(f"\n{'ID':<30} {'Source':<30} {'Frames':>8} {'Anomalies':>10}")
    click.echo("-" * 82)

    for db in dbs[:limit]:
        try:
            import sqlite3
            conn = sqlite3.connect(str(db))
            row = conn.execute(
                "SELECT session_id, source, total_frames, anomaly_count FROM sessions LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                src = Path(row[1]).name if row[1] else "?"
                click.echo(f"  {row[0]:<28} {src:<30} {row[2]:>8} {row[3]:>10}")
        except Exception:
            click.echo(f"  {db.stem:<28} [error reading database]")

    click.echo("")


if __name__ == "__main__":
    main()
