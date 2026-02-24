"""
logging_/export.py
------------------
Session export: reads a completed SQLite session and writes:
  * ``<session_id>_export.csv``    — full per-frame measurements table
  * ``<session_id>_summary.json``  — aggregated session statistics

Can be called programmatically or via ``ohe session export`` CLI command.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SessionExporter:
    """Generates export artefacts from a completed SQLite session database."""

    def __init__(self, db_path: str | Path) -> None:
        self._db = Path(db_path)
        if not self._db.exists():
            raise FileNotFoundError(f"Session database not found: {self._db}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_csv(self, output_path: str | Path | None = None) -> Path:
        """Export all measurements + anomaly flags to a CSV file.

        Returns: path to the written file.
        """
        out = Path(output_path) if output_path else self._db.parent / (self._db.stem + "_export.csv")
        conn = sqlite3.connect(str(self._db))
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT
                m.frame_id,
                m.timestamp_ms,
                m.stagger_mm,
                m.diameter_mm,
                m.confidence,
                m.wire_bbox,
                GROUP_CONCAT(a.anomaly_type, ';') AS anomaly_types,
                GROUP_CONCAT(a.severity, ';')     AS anomaly_severities
            FROM measurements m
            LEFT JOIN anomalies a
                ON m.session_id = a.session_id
                AND m.frame_id  = a.frame_id
            GROUP BY m.frame_id
            ORDER BY m.frame_id
        """).fetchall()
        conn.close()

        import csv
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "frame_id", "timestamp_ms", "stagger_mm", "diameter_mm",
                "confidence", "wire_bbox", "anomaly_types", "anomaly_severities",
            ])
            for r in rows:
                writer.writerow([
                    r["frame_id"],
                    f"{r['timestamp_ms']:.3f}" if r["timestamp_ms"] else "",
                    f"{r['stagger_mm']:.4f}" if r["stagger_mm"] is not None else "",
                    f"{r['diameter_mm']:.4f}" if r["diameter_mm"] is not None else "",
                    f"{r['confidence']:.4f}" if r["confidence"] is not None else "",
                    r["wire_bbox"] or "",
                    r["anomaly_types"] or "",
                    r["anomaly_severities"] or "",
                ])
        logger.info("Exported %d rows to %s", len(rows), out)
        return out

    def export_summary_json(self, output_path: str | Path | None = None) -> Path:
        """Export aggregated session statistics to JSON.

        Returns: path to the written JSON file.
        """
        out = Path(output_path) if output_path else self._db.parent / (self._db.stem + "_summary.json")
        conn = sqlite3.connect(str(self._db))
        conn.row_factory = sqlite3.Row

        session = conn.execute("SELECT * FROM sessions LIMIT 1").fetchone()

        stats = conn.execute("""
            SELECT
                COUNT(*)                      AS total_frames,
                COUNT(stagger_mm)             AS frames_with_stagger,
                AVG(stagger_mm)               AS avg_stagger_mm,
                MIN(stagger_mm)               AS min_stagger_mm,
                MAX(stagger_mm)               AS max_stagger_mm,
                AVG(diameter_mm)              AS avg_diameter_mm,
                MIN(diameter_mm)              AS min_diameter_mm,
                MAX(diameter_mm)              AS max_diameter_mm,
                AVG(confidence)               AS avg_confidence
            FROM measurements
        """).fetchone()

        anomaly_counts = conn.execute("""
            SELECT anomaly_type, severity, COUNT(*) as cnt
            FROM anomalies
            GROUP BY anomaly_type, severity
            ORDER BY cnt DESC
        """).fetchall()
        conn.close()

        detection_rate = (
            stats["frames_with_stagger"] / max(stats["total_frames"], 1) * 100
        )

        summary: dict[str, Any] = {
            "session": {
                "session_id": session["session_id"],
                "source": session["source"],
                "started_at_ms": session["started_at_ms"],
                "ended_at_ms": session["ended_at_ms"],
                "total_frames": session["total_frames"],
                "anomaly_count": session["anomaly_count"],
            },
            "detection": {
                "frames_with_measurement": stats["frames_with_stagger"],
                "detection_rate_pct": round(detection_rate, 2),
                "avg_confidence": round(stats["avg_confidence"] or 0, 4),
            },
            "stagger_mm": {
                "avg": round(stats["avg_stagger_mm"] or 0, 3),
                "min": round(stats["min_stagger_mm"] or 0, 3),
                "max": round(stats["max_stagger_mm"] or 0, 3),
            },
            "diameter_mm": {
                "avg": round(stats["avg_diameter_mm"] or 0, 3),
                "min": round(stats["min_diameter_mm"] or 0, 3),
                "max": round(stats["max_diameter_mm"] or 0, 3),
            },
            "anomaly_breakdown": [
                {"anomaly_type": r["anomaly_type"], "severity": r["severity"], "count": r["cnt"]}
                for r in anomaly_counts
            ],
        }

        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info("Summary JSON written to %s", out)
        return out

    def export_all(self) -> tuple[Path, Path]:
        """Run both exports. Returns (csv_path, json_path)."""
        csv_path = self.export_csv()
        json_path = self.export_summary_json()
        return csv_path, json_path
